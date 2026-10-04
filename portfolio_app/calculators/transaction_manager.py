"""Transaction manager for transaction operations."""

from portfolio_app.models import Transaction
from portfolio_app.calculators.portfolio_calculator import PortfolioCalculator


class TransactionManager:
    """Manager for transaction operations"""

    @staticmethod
    def create_transaction(portfolio_id, transaction_type, price, quantity, fees, notes='', symbol=None, date=None):
        """Create raw transaction facts; projections are calculated on read."""
        symbol = PortfolioCalculator.normalize_symbol(symbol)
        transaction = Transaction(
            portfolio_id=portfolio_id,
            transaction_type=transaction_type,
            symbol=symbol,
            price=price,
            quantity=quantity,
            fees=fees,
            notes=notes
        )
        if date is not None:
            transaction.date = date

        return transaction

    @staticmethod
    def update_transaction(transaction, price=None, quantity=None, fees=None, notes=None, symbol=None, date=None):
        """Update raw transaction facts without writing derived history."""
        if price is not None:
            transaction.price = price
        if quantity is not None:
            transaction.quantity = quantity
        if fees is not None:
            transaction.fees = fees
        if notes is not None:
            transaction.notes = notes
        if symbol is not None:
            transaction.symbol = PortfolioCalculator.normalize_symbol(symbol)
        if date is not None:
            transaction.date = date

        return transaction
