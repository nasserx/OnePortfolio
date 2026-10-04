"""Database-facing financial façade and legacy response adapters.

Aggregate reads compose immutable snapshots using the pure financial engine.
The separate write-side replay below only maintains legacy compatibility columns.
"""

from decimal import Decimal
from portfolio_app.calculators.transaction_order import order_transactions
from portfolio_app.calculators.financial_math import (
    calculate_cash_balance,
    calculate_quantity_held,
)
from portfolio_app.calculators.financial_snapshots import (
    build_asset_snapshot, build_portfolio_snapshot, build_global_snapshot,
    sum_income_details,
)
from portfolio_app.models import Portfolio, Transaction, PortfolioEvent, Dividend
from portfolio_app.utils.decimal_utils import ZERO, to_decimal as _to_decimal, safe_divide as _safe_divide

# Realized P&L is computed on demand from the transactions table. There is
# intentionally no snapshot table — a single source of truth eliminates the
# class of bugs where a stored snapshot drifts from the underlying trades
# (e.g., orphan rows surviving a deletion under FK-OFF SQLite).

class PortfolioCalculator:
    """Utility class for portfolio calculations.

    Most read methods accept an optional keyword-only ``user_id`` argument.
    When provided, the underlying SQL query joins ``Portfolio`` and filters
    by ``Portfolio.user_id`` — defence-in-depth against a caller that
    accidentally passes a portfolio_id that doesn't belong to the current
    user. Callers in the service layer thread the value through from the
    repository's ``user_id`` property so the calculator never trusts the
    caller blindly.

    The argument is *optional* (default ``None``) for backwards
    compatibility with internal recursive calls and tests; treat omitting
    it as a deliberate choice, not a free pass.
    """

    _to_decimal = staticmethod(_to_decimal)

    @staticmethod
    def _scope_to_user(query, model_cls, user_id):
        """Add a Portfolio JOIN + user_id filter when ``user_id`` is given.

        Returns the query unchanged if ``user_id`` is None, so the helper
        is a no-op for legacy unscoped call sites. Models passed in must
        carry a ``portfolio_id`` column (Transaction, Dividend, PortfolioEvent).
        """
        if user_id is not None:
            query = query.join(Portfolio, model_cls.portfolio_id == Portfolio.id) \
                         .filter(Portfolio.user_id == user_id)
        return query

    @staticmethod
    def normalize_symbol(symbol) -> str:
        if symbol is None:
            return ''
        return str(symbol).strip().upper()

    # ------------------------------------------------------------------
    # Quantity helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_quantity_held_for_symbol(portfolio_id, symbol, *, user_id=None, exclude_transaction_id=None):
        """Return current quantity held for a specific symbol inside a portfolio."""
        normalized = PortfolioCalculator.normalize_symbol(symbol)

        query = Transaction.query.filter_by(portfolio_id=portfolio_id, symbol=normalized)
        query = PortfolioCalculator._scope_to_user(query, Transaction, user_id)
        if exclude_transaction_id is not None:
            query = query.filter(Transaction.id != exclude_transaction_id)
        transactions = query.order_by(Transaction.date.asc()).all()

        return calculate_quantity_held(transactions)

    # ------------------------------------------------------------------
    # Portfolio-level aggregates
    # ------------------------------------------------------------------

    @staticmethod
    def get_total_deposits_for_portfolio(portfolio_id, *, user_id=None) -> Decimal:
        """Total deposits = sum of Initial + Deposit events only.

        Withdrawals are excluded so this represents gross capital ever allocated.
        """
        query = (
            PortfolioEvent.query.with_entities(PortfolioEvent.amount_delta)
            .filter(
                PortfolioEvent.portfolio_id == portfolio_id,
                PortfolioEvent.event_type.in_(['Initial', 'Deposit']),
            )
        )
        query = PortfolioCalculator._scope_to_user(query, PortfolioEvent, user_id)
        return sum((_to_decimal(row.amount_delta) for row in query.order_by(PortfolioEvent.id).all()), ZERO)

    @staticmethod
    def get_net_deposits_for_portfolio(portfolio_id, *, user_id=None) -> Decimal:
        """Net deposits = signed sum of all PortfolioEvent rows.

        ``amount_delta`` is positive for Initial/Deposit and negative for
        Withdrawal, so a plain SUM gives ``deposits − withdrawals``. This
        replaces the denormalized ``portfolio.net_deposits`` column whose
        value could drift if the events log was edited outside the service.
        """
        query = (
            PortfolioEvent.query.with_entities(PortfolioEvent.amount_delta)
            .filter(PortfolioEvent.portfolio_id == portfolio_id)
        )
        query = PortfolioCalculator._scope_to_user(query, PortfolioEvent, user_id)
        return sum((_to_decimal(row.amount_delta) for row in query.order_by(PortfolioEvent.id).all()), ZERO)

    @staticmethod
    def get_total_capital_for_portfolio(portfolio_id, *, user_id=None) -> Decimal:
        """Total capital = deposits minus withdrawals.

        Portfolio capital entries are stored as signed event deltas in the
        existing schema, so this is the same read path as net deposits.
        """
        return PortfolioCalculator.get_net_deposits_for_portfolio(
            portfolio_id, user_id=user_id,
        )

    @staticmethod
    def _cash_transactions(portfolio_id, *, user_id=None, exclude_transaction_id=None):
        """Cash and replay reads share deterministic canonical ordering."""
        query = Transaction.query.filter_by(portfolio_id=portfolio_id)
        query = PortfolioCalculator._scope_to_user(query, Transaction, user_id)
        if exclude_transaction_id is not None:
            query = query.filter(Transaction.id != exclude_transaction_id)
        return order_transactions(query.all())

    @staticmethod
    def get_available_cash_for_portfolio(portfolio_id, *, user_id=None, exclude_transaction_id=None) -> Decimal:
        """Lightweight validation read, using the same pure cash function as snapshots."""
        return calculate_cash_balance(
            PortfolioCalculator.get_net_deposits_for_portfolio(portfolio_id, user_id=user_id),
            PortfolioCalculator._cash_transactions(
                portfolio_id, user_id=user_id, exclude_transaction_id=exclude_transaction_id,
            ),
            PortfolioCalculator.get_dividend_total_for_portfolio(portfolio_id, user_id=user_id),
        )

    @staticmethod
    def get_portfolio_snapshot(portfolio_id, *, user_id=None):
        """Load scoped inputs once per financial view; never persist or cache results.

        Funding/income sum individually loaded Decimal column values, never SQL
        floating-point reductions. Trading values always come from fresh canonical
        replay, never Transaction.average_cost or Transaction.net_amount.
        """
        query = Portfolio.query.filter_by(id=portfolio_id)
        if user_id is not None:
            query = query.filter_by(user_id=user_id)
        portfolio = query.first()

        income_by_symbol = PortfolioCalculator._income_by_symbol(portfolio_id, user_id=user_id)

        sym_query = Transaction.query.with_entities(Transaction.symbol).filter_by(portfolio_id=portfolio_id)
        sym_query = PortfolioCalculator._scope_to_user(sym_query, Transaction, user_id)
        symbols = [
            PortfolioCalculator.normalize_symbol(row.symbol)
            for row in sym_query.distinct().all()
            if PortfolioCalculator.normalize_symbol(row.symbol)
        ]
        assets = {}
        for symbol in symbols:
            assets[symbol] = PortfolioCalculator.get_asset_snapshot(
                portfolio_id, symbol, user_id=user_id,
                income=income_by_symbol.get(symbol, ZERO),
            )
        for symbol, income in income_by_symbol.items():
            if symbol not in assets:
                assets[symbol] = build_asset_snapshot(symbol, [], income)

        return build_portfolio_snapshot(
            portfolio_id=portfolio_id,
            name=portfolio.name if portfolio is not None else '',
            assets=assets,
            funding_inflows=PortfolioCalculator.get_total_deposits_for_portfolio(portfolio_id, user_id=user_id),
            net_contributions=PortfolioCalculator.get_net_deposits_for_portfolio(portfolio_id, user_id=user_id),
            cash_transactions=PortfolioCalculator._cash_transactions(portfolio_id, user_id=user_id),
            income=sum(income_by_symbol.values(), ZERO),
            income_by_symbol=income_by_symbol,
        )

    @staticmethod
    def get_financial_snapshot(user_id=None):
        """Canonical global read model; every aggregate consumer uses this path."""
        query = Portfolio.query
        if user_id is not None:
            query = query.filter_by(user_id=user_id)
        return build_global_snapshot(
            PortfolioCalculator.get_portfolio_snapshot(portfolio.id, user_id=user_id)
            for portfolio in query.all()
        )

    @staticmethod
    def get_portfolio_summary(user_id=None):
        return PortfolioCalculator.get_financial_snapshot(user_id).as_portfolio_summary()

    @staticmethod
    def get_portfolio_dashboard_totals(user_id=None):
        return dict(PortfolioCalculator.get_financial_snapshot(user_id).totals)

    @staticmethod
    def get_realized_performance_for_portfolio(portfolio_id, *, user_id=None):
        return PortfolioCalculator.get_portfolio_snapshot(
            portfolio_id, user_id=user_id,
        ).as_realized_performance()

    @staticmethod
    def get_user_symbol_performance(user_id):
        if user_id is None:
            return []
        return PortfolioCalculator.get_financial_snapshot(user_id).as_symbol_performance()

    @staticmethod
    def get_portfolio_transactions_summary(portfolio_id, *, user_id=None):
        snapshot = PortfolioCalculator.get_portfolio_snapshot(portfolio_id, user_id=user_id)
        # Preserve the historical public dictionary shape.
        return {
            key: value for key, value in snapshot.transactions.items()
            if key not in ('realized_cost_basis', 'realized_proceeds')
        }

    @staticmethod
    def get_asset_snapshot(portfolio_id, symbol, *, user_id=None, income=None):
        symbol = PortfolioCalculator.normalize_symbol(symbol)
        query = Transaction.query.filter_by(portfolio_id=portfolio_id, symbol=symbol)
        query = PortfolioCalculator._scope_to_user(query, Transaction, user_id)
        if income is None:
            income = PortfolioCalculator._income_by_symbol(
                portfolio_id, user_id=user_id,
            ).get(symbol, ZERO)
        return build_asset_snapshot(symbol, query.all(), income)

    @staticmethod
    def get_symbol_transactions_summary(portfolio_id, symbol, *, user_id=None):
        return dict(PortfolioCalculator.get_asset_snapshot(
            portfolio_id, symbol, user_id=user_id,
        ).transactions)

    @staticmethod
    def get_symbol_transactions_summary_from_list(transactions):
        """Pure list entry point shares the same canonical asset replay boundary."""
        return dict(build_asset_snapshot('', transactions).transactions)

    @staticmethod
    def get_dividend_total_for_portfolio(portfolio_id, *, user_id=None) -> Decimal:
        """Return the sum of dividend income for a portfolio."""
        return sum(PortfolioCalculator._income_by_symbol(portfolio_id, user_id=user_id).values(), ZERO)

    @staticmethod
    def _income_by_symbol(portfolio_id, *, user_id=None):
        # Column reads bypass unexpired ORM attributes that may still contain
        # pre-storage precision. The scale-converted persisted values are the
        # no-schema phase's deterministic accounting inputs.
        query = Dividend.query.with_entities(Dividend.symbol, Dividend.amount).filter_by(
            portfolio_id=portfolio_id,
        )
        query = PortfolioCalculator._scope_to_user(query, Dividend, user_id)
        return sum_income_details(query.order_by(Dividend.id).all())

    # ------------------------------------------------------------------
    # Recalculation (after add/edit/delete transaction)
    # ------------------------------------------------------------------

    @staticmethod
    def recalculate_all_averages_for_symbol(portfolio_id, symbol, *, user_id=None):
        """Maintain legacy average_cost/net_amount columns for compatibility.

        No financial consumer reads these values. Canonical read projections
        come from raw replay instead. The caller is responsible for committing.
        """
        symbol = PortfolioCalculator.normalize_symbol(symbol)
        query = Transaction.query.filter_by(portfolio_id=portfolio_id, symbol=symbol)
        query = PortfolioCalculator._scope_to_user(query, Transaction, user_id)
        transactions = order_transactions(query.all())

        running_quantity = ZERO
        running_cost = ZERO

        for transaction in transactions:
            transaction.calculate_net_amount()

            if transaction.transaction_type == 'Buy':
                cost = (
                    _to_decimal(transaction.price) * _to_decimal(transaction.quantity)
                    + _to_decimal(transaction.fees)
                )
                running_cost += cost
                running_quantity += _to_decimal(transaction.quantity)
                transaction.average_cost = _safe_divide(running_cost, running_quantity)

            elif transaction.transaction_type == 'Sell':
                sell_qty = _to_decimal(transaction.quantity)
                avg_cost = _safe_divide(running_cost, running_quantity)
                transaction.average_cost = avg_cost
                running_quantity -= sell_qty
                running_cost     -= avg_cost * sell_qty
                if running_quantity == ZERO:
                    running_cost = ZERO

        return transactions
