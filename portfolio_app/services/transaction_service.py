"""Transaction service for transaction-related business logic."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, Any
from portfolio_app.models.transaction import Transaction
from portfolio_app.models.asset import Asset
from portfolio_app.models.dividend import Dividend
from portfolio_app.repositories.transaction_repository import TransactionRepository
from portfolio_app.repositories.asset_repository import AssetRepository
from portfolio_app.repositories.fund_repository import FundRepository
from portfolio_app.repositories.dividend_repository import DividendRepository
from portfolio_app.calculators.portfolio_calculator import PortfolioCalculator
from portfolio_app.calculators.transaction_manager import TransactionManager


class ValidationError(Exception):
    """Raised for validation errors."""
    pass


class TransactionService:
    """Service for transaction-related business logic."""

    def __init__(
        self,
        transaction_repo: TransactionRepository,
        asset_repo: AssetRepository,
        fund_repo: FundRepository,
        dividend_repo: Optional[DividendRepository] = None,
    ):
        """Initialize service with repositories.

        Args:
            transaction_repo: Transaction repository
            asset_repo: Asset repository
            fund_repo: Fund repository
            dividend_repo: Dividend repository
        """
        self.transaction_repo = transaction_repo
        self.asset_repo = asset_repo
        self.fund_repo = fund_repo
        self.dividend_repo = dividend_repo

    def add_transaction(
        self,
        fund_id: int,
        transaction_type: str,
        symbol: str,
        price: Decimal,
        quantity: Decimal,
        fees: Decimal,
        notes: str = '',
        date: Optional[Any] = None
    ) -> Transaction:
        """Add a new transaction.

        Args:
            fund_id: Fund ID
            transaction_type: 'Buy' or 'Sell'
            symbol: Asset symbol
            price: Price per unit
            quantity: Quantity
            fees: Transaction fees
            notes: Optional notes

        Returns:
            Created transaction

        Raises:
            ValidationError: If fees exceed sell proceeds
        """
        # Validate fees don't exceed sell proceeds
        if transaction_type == 'Sell':
            gross = price * quantity
            if fees > gross:
                raise ValidationError('Fees exceed proceeds')

        # Create transaction
        transaction = TransactionManager.create_transaction(
            fund_id=fund_id,
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

        # Recalculate averages
        PortfolioCalculator.recalculate_all_averages_for_symbol(fund_id, symbol)

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
        """Update an existing transaction.

        Args:
            transaction_id: Transaction ID
            price: New price (optional)
            quantity: New quantity (optional)
            fees: New fees (optional)
            notes: New notes (optional)
            symbol: New symbol (optional)
            date: New date (optional)

        Returns:
            Updated transaction

        Raises:
            ValueError: If transaction not found
        """
        transaction = self.transaction_repo.get_by_id(transaction_id)
        if not transaction:
            raise ValueError('Transaction not found')

        # Check if anything actually changed - skip update if not
        if self._has_no_changes(transaction, price, quantity, fees, notes, symbol, date):
            return transaction

        old_symbol = transaction.symbol
        fund_id = transaction.fund_id

        # Update transaction
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

        # Recalculate averages for both old and new symbols if changed
        if symbol and old_symbol != transaction.symbol:
            PortfolioCalculator.recalculate_all_averages_for_symbol(fund_id, old_symbol)
            PortfolioCalculator.recalculate_all_averages_for_symbol(fund_id, transaction.symbol)
        else:
            PortfolioCalculator.recalculate_all_averages_for_symbol(fund_id, transaction.symbol)

        self.transaction_repo.commit()
        return transaction

    def delete_transaction(self, transaction_id: int) -> int:
        """Delete a transaction.

        Args:
            transaction_id: Transaction ID

        Returns:
            Fund ID of the deleted transaction

        Raises:
            ValueError: If transaction not found
        """
        transaction = self.transaction_repo.get_by_id(transaction_id)
        if not transaction:
            raise ValueError('Transaction not found')

        fund_id = transaction.fund_id
        symbol = transaction.symbol

        self.transaction_repo.delete(transaction)
        self.transaction_repo.flush()

        # Recalculate averages after deletion
        PortfolioCalculator.recalculate_all_averages_for_symbol(fund_id, symbol)

        self.transaction_repo.commit()
        return fund_id

    def add_asset(self, fund_id: int, symbol: str) -> Asset:
        """Add a tracked symbol to an asset class.

        Args:
            fund_id: Asset class ID
            symbol: Symbol to track

        Returns:
            Created symbol record

        Raises:
            ValueError: If symbol is already added to this asset class
        """
        symbol = PortfolioCalculator.normalize_symbol(symbol)

        # Check if already exists
        existing = self.asset_repo.get_by_fund_and_symbol(fund_id, symbol)
        if existing:
            raise ValueError(f"'{symbol}' is already added to this asset class.")

        asset = Asset(fund_id=fund_id, symbol=symbol)
        self.asset_repo.add(asset)
        self.asset_repo.commit()

        return asset

    def delete_asset(self, fund_id: int, symbol: str) -> None:
        """Delete a tracked asset and all its transactions.

        Args:
            fund_id: Fund ID
            symbol: Asset symbol

        Raises:
            ValueError: If asset not found
        """
        symbol = PortfolioCalculator.normalize_symbol(symbol)

        asset = self.asset_repo.get_by_fund_and_symbol(fund_id, symbol)
        if not asset:
            raise ValueError('Asset not found')

        for tx in self.transaction_repo.get_by_symbol(fund_id, symbol):
            self.transaction_repo.delete(tx)

        self.asset_repo.delete(asset)
        self.asset_repo.commit()

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
        fund_id: int,
        amount: Decimal,
        date: datetime,
        notes: str = '',
    ) -> Dividend:
        """Add a new dividend income record.

        Args:
            fund_id: Fund ID
            amount: Dividend amount (must be > 0)
            date: Dividend date
            notes: Optional notes

        Returns:
            Created Dividend

        Raises:
            ValidationError: If fund not found
        """
        fund = self.fund_repo.get_by_id(fund_id)
        if not fund:
            raise ValidationError('Category not found.')

        dividend = Dividend(
            fund_id=fund_id,
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
        """Update an existing dividend.

        Args:
            dividend_id: Dividend ID
            amount: New amount (optional)
            date: New date (optional)
            notes: New notes (optional)

        Returns:
            Updated Dividend

        Raises:
            ValueError: If dividend not found
        """
        dividend = self.dividend_repo.get_by_id(dividend_id)
        if not dividend or not self.fund_repo.get_by_id(dividend.fund_id):
            raise ValueError('Dividend not found')

        if amount is not None:
            dividend.amount = amount
        if date is not None:
            dividend.date = date
        if notes is not None:
            dividend.notes = notes or None

        self.dividend_repo.commit()
        return dividend

    def delete_dividend(self, dividend_id: int) -> None:
        """Delete a dividend record.

        Args:
            dividend_id: Dividend ID

        Raises:
            ValueError: If dividend not found
        """
        dividend = self.dividend_repo.get_by_id(dividend_id)
        if not dividend or not self.fund_repo.get_by_id(dividend.fund_id):
            raise ValueError('Dividend not found')

        self.dividend_repo.delete(dividend)
        self.dividend_repo.commit()

