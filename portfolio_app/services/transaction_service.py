"""Transaction service for transaction-related business logic."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Any
from portfolio_app.models.transaction import Transaction
from portfolio_app.models.symbol import Symbol
from portfolio_app.models.dividend import Dividend
from portfolio_app.repositories.transaction_repository import TransactionRepository
from portfolio_app.repositories.symbol_repository import SymbolRepository
from portfolio_app.repositories.portfolio_repository import PortfolioRepository
from portfolio_app.repositories.dividend_repository import DividendRepository
from portfolio_app.calculators.portfolio_calculator import PortfolioCalculator
from portfolio_app.calculators.transaction_manager import TransactionManager
from portfolio_app.utils.decimal_utils import ZERO
from portfolio_app.utils.messages import MESSAGES


class ValidationError(Exception):
    """Raised for validation errors."""
    pass


class TransactionService:
    """Service for transaction-related business logic."""

    def __init__(
        self,
        transaction_repo: TransactionRepository,
        symbol_repo: SymbolRepository,
        portfolio_repo: PortfolioRepository,
        dividend_repo: Optional[DividendRepository] = None,
    ):
        self.transaction_repo = transaction_repo
        self.symbol_repo = symbol_repo
        self.portfolio_repo = portfolio_repo
        self.dividend_repo = dividend_repo

    def add_transaction(
        self,
        portfolio_id: int,
        transaction_type: str,
        symbol: str,
        price: Decimal,
        quantity: Decimal,
        fees: Decimal,
        notes: str = '',
        date: Optional[Any] = None
    ) -> Transaction:
        """Add a new transaction."""
        if not self.portfolio_repo.get_by_id(portfolio_id):
            raise ValueError(MESSAGES['PORTFOLIO_NOT_FOUND'])

        if transaction_type == 'Sell':
            gross = Decimal(str(price)) * Decimal(str(quantity))
            if Decimal(str(fees)) > gross:
                raise ValidationError(MESSAGES['FEES_EXCEED_PROCEEDS'])
            held = PortfolioCalculator.get_quantity_held_for_symbol(
                portfolio_id, symbol, user_id=self.portfolio_repo.user_id,
            )
            # Safety: refuse to compound an already-corrupt state. If a
            # previous bug ever drove holdings below zero (or held is
            # otherwise non-numeric), a Sell of any size would breach
            # ``quantity > held`` against a negative number — block it.
            if held <= ZERO or Decimal(str(quantity)) > held:
                raise ValidationError(MESSAGES['INSUFFICIENT_QUANTITY'])

        # Chronological-walk invariant — same logic that update_transaction
        # uses. The plain ``quantity > held`` check above is date-blind:
        # a Sell dated *before* an existing Buy passes it because total
        # holdings still cover the sell, even though the position didn't
        # exist on the sell date. Simulating the post-add timeline catches
        # that (running_quantity would dip below zero) and also covers any
        # Buy whose date predates earlier Sells of the same symbol.
        self._assert_walk_non_negative(
            portfolio_id=portfolio_id,
            edit_id=None,
            proposed_symbol=PortfolioCalculator.normalize_symbol(symbol),
            proposed_type=transaction_type,
            proposed_quantity=Decimal(str(quantity)),
            proposed_date=date if date is not None else datetime.now(timezone.utc),
        )

        transaction = TransactionManager.create_transaction(
            portfolio_id=portfolio_id,
            transaction_type=transaction_type,
            symbol=symbol,
            price=price,
            quantity=quantity,
            fees=fees,
            notes=notes,
            date=date
        )

        self.transaction_repo.add(transaction)
        self.transaction_repo.flush()

        PortfolioCalculator.recalculate_all_averages_for_symbol(
            portfolio_id, symbol, user_id=self.portfolio_repo.user_id,
        )

        self.transaction_repo.commit()
        return transaction

    def update_transaction(
        self,
        transaction_id: int,
        price: Optional[Decimal] = None,
        quantity: Optional[Decimal] = None,
        fees: Optional[Decimal] = None,
        notes: Optional[str] = None,
        symbol: Optional[str] = None,
        date: Optional[Any] = None
    ) -> Transaction:
        """Update an existing transaction."""
        transaction = self.transaction_repo.get_by_id(transaction_id)
        if not transaction:
            raise ValueError(MESSAGES['TRANSACTION_NOT_FOUND'])

        if not self.portfolio_repo.get_by_id(transaction.portfolio_id):
            raise ValueError(MESSAGES['TRANSACTION_NOT_FOUND'])

        if self._has_no_changes(transaction, price, quantity, fees, notes, symbol, date):
            return transaction

        # Validate post-mutation invariants BEFORE applying the change.
        # Mirrors the Sell-path checks from add_transaction (fees ≤ gross
        # and oversell vs currently-held), and additionally simulates the
        # full chronological recomputation to reject edits that would
        # drive the running quantity below zero at any point — e.g. a
        # backdated Sell, a Buy whose quantity is reduced below later
        # Sells, or a symbol change that orphans existing Sells.
        self._validate_update_invariants(
            transaction=transaction,
            price=price,
            quantity=quantity,
            fees=fees,
            symbol=symbol,
            date=date,
        )

        # Reject the edit if it would push available cash below zero —
        # e.g. raising a Buy's quantity past current cash, lowering a
        # Sell's proceeds below what's already been withdrawn.
        new_price    = price    if price    is not None else transaction.price
        new_quantity = quantity if quantity is not None else transaction.quantity
        new_fees     = fees     if fees     is not None else transaction.fees
        old_effect = self._cash_effect(transaction)
        new_effect = self._proposed_cash_effect(
            transaction.transaction_type, new_price, new_quantity, new_fees,
        )
        # Sell-lowered = clawing back proceeds the user has already spent
        # ("Insufficient amount." reads as if the *new* value is wrong,
        # which it isn't — that's why the message diverges by type).
        # Buy-raised = genuinely asking the portfolio to spend more than
        # it has, so the existing INSUFFICIENT_AMOUNT wording fits.
        cash_msg = (
            MESSAGES['CASH_ALREADY_SPENT']
            if transaction.transaction_type == 'Sell'
            else MESSAGES['INSUFFICIENT_AMOUNT']
        )
        self._assert_cash_after_delta(
            transaction.portfolio_id,
            new_effect - old_effect,
            error_message=cash_msg,
        )

        old_symbol = transaction.symbol
        portfolio_id = transaction.portfolio_id

        TransactionManager.update_transaction(
            transaction,
            price=price,
            quantity=quantity,
            fees=fees,
            notes=notes,
            symbol=symbol,
            date=date
        )

        self.transaction_repo.flush()

        uid = self.portfolio_repo.user_id
        if symbol and old_symbol != transaction.symbol:
            PortfolioCalculator.recalculate_all_averages_for_symbol(portfolio_id, old_symbol, user_id=uid)
            PortfolioCalculator.recalculate_all_averages_for_symbol(portfolio_id, transaction.symbol, user_id=uid)
        else:
            PortfolioCalculator.recalculate_all_averages_for_symbol(portfolio_id, transaction.symbol, user_id=uid)

        self.transaction_repo.commit()
        return transaction

    def delete_transaction(self, transaction_id: int) -> int:
        """Delete a transaction. Returns portfolio_id of the deleted transaction."""
        transaction = self.transaction_repo.get_by_id(transaction_id)
        if not transaction:
            raise ValueError(MESSAGES['TRANSACTION_NOT_FOUND'])

        if not self.portfolio_repo.get_by_id(transaction.portfolio_id):
            raise ValueError(MESSAGES['TRANSACTION_NOT_FOUND'])

        portfolio_id = transaction.portfolio_id
        symbol = transaction.symbol

        # Reject the delete if removing this row would leave the
        # remaining transactions in an impossible chronological state —
        # e.g. deleting a Buy that is the only cover for a later Sell.
        # Walk the remaining (portfolio, symbol) timeline excluding this
        # row; reject if running quantity would dip below zero.
        self._assert_walk_non_negative(
            portfolio_id=portfolio_id,
            edit_id=transaction.id,
            proposed_symbol=PortfolioCalculator.normalize_symbol(symbol),
            proposed_type=None,            # exclude this row, add nothing
            proposed_quantity=Decimal('0'),
            proposed_date=None,
        )

        # Removing the row reverses its cash effect — deleting a Sell
        # claws back inflow and may push cash below zero if the user
        # has already withdrawn or spent it. (Deleting a Buy returns
        # cash, so this check is a no-op for Buys.)
        self._assert_cash_after_delta(
            portfolio_id,
            -self._cash_effect(transaction),
            error_message=MESSAGES['CASH_ALREADY_SPENT'],
        )

        self.transaction_repo.delete(transaction)
        self.transaction_repo.flush()

        PortfolioCalculator.recalculate_all_averages_for_symbol(
            portfolio_id, symbol, user_id=self.portfolio_repo.user_id,
        )

        self.transaction_repo.commit()
        return portfolio_id

    def add_symbol(self, portfolio_id: int, symbol: str) -> Symbol:
        """Track a new symbol in a portfolio."""
        symbol = PortfolioCalculator.normalize_symbol(symbol)

        if not self.portfolio_repo.get_by_id(portfolio_id):
            raise ValueError(MESSAGES['PORTFOLIO_NOT_FOUND'])

        existing = self.symbol_repo.get_by_portfolio_and_ticker(portfolio_id, symbol)
        if existing:
            raise ValueError(MESSAGES['SYMBOL_ALREADY_TRACKED'].format(symbol=symbol))

        tracked = Symbol(portfolio_id=portfolio_id, symbol=symbol)
        self.symbol_repo.add(tracked)
        self.symbol_repo.commit()

        return tracked

    def delete_symbol(self, portfolio_id: int, symbol: str) -> None:
        """Stop tracking a symbol and remove all its transactions."""
        symbol = PortfolioCalculator.normalize_symbol(symbol)

        if not self.portfolio_repo.get_by_id(portfolio_id):
            raise ValueError(MESSAGES['PORTFOLIO_NOT_FOUND'])

        tracked = self.symbol_repo.get_by_portfolio_and_ticker(portfolio_id, symbol)
        if not tracked:
            raise ValueError(MESSAGES['SYMBOL_NOT_FOUND'])

        for tx in self.transaction_repo.get_by_symbol(portfolio_id, symbol):
            self.transaction_repo.delete(tx)

        self.symbol_repo.delete(tracked)
        self.symbol_repo.commit()

    def _cash_effect(self, transaction):
        """Signed contribution this transaction makes to available cash.

        Buy → negative (price*qty + fees outflow).
        Sell → positive (price*qty - fees inflow).
        Removing a transaction reverses its effect; replacing it with a
        new shape is ``new_effect - old_effect``.
        """
        price = Decimal(str(transaction.price))
        quantity = Decimal(str(transaction.quantity))
        fees = Decimal(str(transaction.fees))
        gross = price * quantity
        if transaction.transaction_type == 'Sell':
            return gross - fees
        return -(gross + fees)

    @staticmethod
    def _proposed_cash_effect(transaction_type, price, quantity, fees):
        """Same as :meth:`_cash_effect` but for a hypothetical row before
        it is persisted (used by update_transaction to compute the delta
        between the old and new shape)."""
        gross = Decimal(str(price)) * Decimal(str(quantity))
        f = Decimal(str(fees))
        if transaction_type == 'Sell':
            return gross - f
        return -(gross + f)

    def _assert_cash_after_delta(self, portfolio_id, delta_change, *, error_message=None):
        """Reject the in-progress mutation if it would push available cash
        below zero. ``delta_change`` is the signed change to the
        portfolio's cash position the mutation would cause; if it raises
        cash (≥ 0) the check is a no-op and saves a query.

        ``error_message`` lets the caller pick the wording that fits its
        context: ``CASH_ALREADY_SPENT`` for clawback paths (delete a Sell,
        lower a Dividend), ``INSUFFICIENT_AMOUNT`` for over-spend paths
        (raise a Buy). Default falls back to the generic over-spend
        message so existing callers stay correct.
        """
        if delta_change >= ZERO:
            return
        current_cash = PortfolioCalculator.get_available_cash_for_portfolio(
            portfolio_id, user_id=self.portfolio_repo.user_id,
        )
        if current_cash + delta_change < ZERO:
            raise ValueError(error_message or MESSAGES['INSUFFICIENT_AMOUNT'])

    def _has_no_changes(self, transaction, price, quantity, fees, notes, symbol, date):
        """Check if the new values are identical to the existing transaction."""
        if price is not None and Decimal(str(price)) != Decimal(str(transaction.price)):
            return False
        if quantity is not None and Decimal(str(quantity)) != Decimal(str(transaction.quantity)):
            return False
        if fees is not None and Decimal(str(fees)) != Decimal(str(transaction.fees)):
            return False
        if notes is not None and str(notes) != str(transaction.notes or ''):
            return False
        if symbol is not None and PortfolioCalculator.normalize_symbol(symbol) != PortfolioCalculator.normalize_symbol(transaction.symbol):
            return False
        if date is not None and date != transaction.date:
            return False
        return True

    def _validate_update_invariants(self, *, transaction, price, quantity, fees, symbol, date):
        """Reject the proposed update if it would violate a financial invariant.

        Mirrors the Sell-path checks performed in :meth:`add_transaction`
        (fees ≤ gross and quantity ≤ currently-held, both raising
        :class:`ValidationError` with the same canonical messages), and
        additionally simulates the chronological recomputation that
        :meth:`PortfolioCalculator.recalculate_all_averages_for_symbol`
        performs — rejecting any edit that would drive the running
        quantity below zero at any point in the timeline.
        """
        new_price    = Decimal(str(price))    if price    is not None else Decimal(str(transaction.price))
        new_quantity = Decimal(str(quantity)) if quantity is not None else Decimal(str(transaction.quantity))
        new_fees     = Decimal(str(fees))     if fees     is not None else Decimal(str(transaction.fees))
        new_symbol   = (PortfolioCalculator.normalize_symbol(symbol)
                        if symbol is not None else (transaction.symbol or ''))
        new_date     = date if date is not None else transaction.date

        portfolio_id = transaction.portfolio_id
        old_symbol   = (transaction.symbol or '')

        # Sell-path checks — same exceptions and messages as add_transaction.
        if transaction.transaction_type == 'Sell':
            gross = new_price * new_quantity
            if new_fees > gross:
                raise ValidationError(MESSAGES['FEES_EXCEED_PROCEEDS'])
            held = PortfolioCalculator.get_quantity_held_for_symbol(
                portfolio_id, new_symbol,
                user_id=self.portfolio_repo.user_id,
                exclude_transaction_id=transaction.id,
            )
            if new_quantity > held:
                raise ValidationError(MESSAGES['INSUFFICIENT_QUANTITY'])

        # Chronological-walk invariant for the new-symbol stream — the
        # transaction at its proposed values participates in the walk.
        self._assert_walk_non_negative(
            portfolio_id=portfolio_id,
            edit_id=transaction.id,
            proposed_symbol=new_symbol,
            proposed_type=transaction.transaction_type,
            proposed_quantity=new_quantity,
            proposed_date=new_date,
        )

        # If the symbol is changing, the old-symbol stream loses this row.
        # Verify that stream is still self-consistent without it.
        if new_symbol != old_symbol:
            self._assert_walk_non_negative(
                portfolio_id=portfolio_id,
                edit_id=transaction.id,
                proposed_symbol=old_symbol,
                proposed_type=None,
                proposed_quantity=Decimal('0'),
                proposed_date=None,
            )

    def _assert_walk_non_negative(self, *, portfolio_id, edit_id,
                                  proposed_symbol, proposed_type,
                                  proposed_quantity, proposed_date):
        """Simulate the (portfolio, symbol) chronological walk and raise if
        the running quantity ever goes negative.

        ``proposed_type=None`` means the proposed row is excluded entirely
        from the walk (used for the old-symbol stream when an edit moves
        the row to a different symbol). ``edit_id=None`` is the add path:
        no existing row to exclude, and the proposed row has no id yet, so
        it sorts after any same-date/same-type peer (matches the post-
        commit ordering it would have once auto-incremented).

        Ordering matches the SQL ORDER BY in
        :meth:`PortfolioCalculator.recalculate_all_averages_for_symbol`:
        ``func.date(date) ASC, buy_first ASC, id ASC``.

        The query is scoped by the repo's user_id so a forged portfolio_id
        from another user simulates an empty existing-row set rather than
        leaking that user's transactions into the walk.
        """
        query = Transaction.query.filter_by(
            portfolio_id=portfolio_id, symbol=proposed_symbol,
        )
        query = PortfolioCalculator._scope_to_user(
            query, Transaction, self.portfolio_repo.user_id,
        )
        if edit_id is not None:
            query = query.filter(Transaction.id != edit_id)
        rows = query.all()

        walk = [
            (r.date, 0 if r.transaction_type == 'Buy' else 1, r.id,
             r.transaction_type, Decimal(str(r.quantity)))
            for r in rows
        ]

        if proposed_type is not None:
            # New rows have no id yet — slot them after any existing
            # same-date/same-type peer so the simulation matches what
            # ``recalculate_all_averages_for_symbol`` will do post-commit.
            sort_id = edit_id if edit_id is not None else 2**63
            walk.append((
                proposed_date,
                0 if proposed_type == 'Buy' else 1,
                sort_id,
                proposed_type,
                proposed_quantity,
            ))

        def _key(item):
            d = item[0]
            d_only = d.date() if d is not None else datetime.min.date()
            return (d_only, item[1], item[2])

        walk.sort(key=_key)

        # Identify the proposed row (if present) so we can distinguish two
        # very different dip causes:
        #   * dip lands on the proposed Sell itself  → the user's Sell
        #     can't fit at its date (truly "insufficient quantity")
        #   * dip lands on an existing later Sell    → the proposed
        #     change/delete leaves that Sell uncovered (a much clearer
        #     message: "a later Sell depends on this Buy")
        if proposed_type is not None:
            proposed_id = edit_id if edit_id is not None else 2**63
        else:
            proposed_id = None  # delete, or old-stream check after symbol change

        running = Decimal('0')
        for _date, _b, tid, ttype, qty in walk:
            if ttype == 'Buy':
                running += qty
            else:
                running -= qty
                if running < 0:
                    if proposed_id is not None and tid == proposed_id:
                        raise ValidationError(MESSAGES['INSUFFICIENT_QUANTITY'])
                    raise ValidationError(MESSAGES['LATER_SELL_NEEDS_BUY'])

    # ------------------------------------------------------------------
    # Dividend operations
    # ------------------------------------------------------------------

    def add_dividend(
        self,
        portfolio_id: int,
        symbol: str,
        amount: Decimal,
        date: datetime,
        notes: str = '',
    ) -> Dividend:
        """Add a new dividend income record."""
        portfolio = self.portfolio_repo.get_by_id(portfolio_id)
        if not portfolio:
            raise ValueError(MESSAGES['PORTFOLIO_NOT_FOUND'])

        normalized_symbol = (symbol or '').strip().upper()
        if not normalized_symbol:
            raise ValidationError(MESSAGES['SYMBOL_REQUIRED'])

        dividend = Dividend(
            portfolio_id=portfolio_id,
            symbol=normalized_symbol,
            amount=amount,
            date=date,
            notes=notes or None,
        )
        self.dividend_repo.add(dividend)
        self.dividend_repo.commit()
        return dividend

    def update_dividend(
        self,
        dividend_id: int,
        amount: Optional[Decimal] = None,
        date: Optional[datetime] = None,
        notes: Optional[str] = None,
    ) -> Dividend:
        """Update an existing dividend."""
        dividend = self.dividend_repo.get_by_id(dividend_id)
        if not dividend or not self.portfolio_repo.get_by_id(dividend.portfolio_id):
            raise ValueError(MESSAGES['DIVIDEND_NOT_FOUND'])

        # Lowering the amount reduces available cash; reject if the user
        # has already spent the difference on Buys or withdrawn it.
        if amount is not None:
            delta = Decimal(str(amount)) - Decimal(str(dividend.amount))
            self._assert_cash_after_delta(
                dividend.portfolio_id, delta,
                error_message=MESSAGES['CASH_ALREADY_SPENT'],
            )
            dividend.amount = amount
        if date is not None:
            dividend.date = date
        if notes is not None:
            dividend.notes = notes or None

        self.dividend_repo.commit()
        return dividend

    def delete_dividend(self, dividend_id: int) -> None:
        """Delete a dividend record."""
        dividend = self.dividend_repo.get_by_id(dividend_id)
        if not dividend or not self.portfolio_repo.get_by_id(dividend.portfolio_id):
            raise ValueError(MESSAGES['DIVIDEND_NOT_FOUND'])

        # Removing the dividend reverses the cash inflow it represented.
        # If a Buy or Withdrawal already consumed that money, refuse the
        # delete rather than letting available cash go negative.
        self._assert_cash_after_delta(
            dividend.portfolio_id, -Decimal(str(dividend.amount)),
            error_message=MESSAGES['CASH_ALREADY_SPENT'],
        )

        self.dividend_repo.delete(dividend)
        self.dividend_repo.commit()
