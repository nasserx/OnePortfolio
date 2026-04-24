"""Transaction service for transaction-related business logic."""

from datetime import datetime
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
            gross = price * quantity
            if fees > gross:
                raise ValidationError(MESSAGES['FEES_EXCEED_PROCEEDS'])
            held = PortfolioCalculator.get_quantity_held_for_symbol(portfolio_id, symbol)
            if quantity > held:
                raise ValidationError(MESSAGES['INSUFFICIENT_QUANTITY'])

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

        PortfolioCalculator.recalculate_all_averages_for_symbol(portfolio_id, symbol)

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

        if symbol and old_symbol != transaction.symbol:
            PortfolioCalculator.recalculate_all_averages_for_symbol(portfolio_id, old_symbol)
            PortfolioCalculator.recalculate_all_averages_for_symbol(portfolio_id, transaction.symbol)
        else:
            PortfolioCalculator.recalculate_all_averages_for_symbol(portfolio_id, transaction.symbol)

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

        self.transaction_repo.delete(transaction)
        self.transaction_repo.flush()

        PortfolioCalculator.recalculate_all_averages_for_symbol(portfolio_id, symbol)

        self.transaction_repo.commit()
        return portfolio_id

    def add_symbol(self, portfolio_id: int, symbol: str) -> Symbol:
        """Track a new symbol in a portfolio."""
        symbol = PortfolioCalculator.normalize_symbol(symbol)

        if not self.portfolio_repo.get_by_id(portfolio_id):
            raise ValueError(MESSAGES['PORTFOLIO_NOT_FOUND'])

        existing = self.symbol_repo.get_by_portfolio_and_ticker(portfolio_id, symbol)
        if existing:
            raise ValueError(MESSAGES['SYMBOL_ALREADY_TRACKED_SYMBOL'].format(symbol=symbol))

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

        dividend = Dividend(
            portfolio_id=portfolio_id,
            symbol=symbol.upper(),
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

        if amount is not None:
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

        self.dividend_repo.delete(dividend)
        self.dividend_repo.commit()
