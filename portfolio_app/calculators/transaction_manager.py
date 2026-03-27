"""Transaction manager for transaction operations."""

from portfolio_app.models import Transaction
from portfolio_app.calculators.portfolio_calculator import PortfolioCalculator


class TransactionManager:
    """Manager for transaction operations"""

    @staticmethod
    def create_transaction(fund_id, transaction_type, price, quantity, fees, notes='', symbol=None, date=None):
        """Create a new transaction and update calculations"""
        symbol = PortfolioCalculator.normalize_symbol(symbol)
        transaction = Transaction(
            fund_id=fund_id,
            transaction_type=transaction_type,
            symbol=symbol,
            price=price,
            quantity=quantity,
            fees=fees,
            notes=notes
        )
        if date is not None:
            transaction.date = date

        transaction.calculate_net_amount()
        return transaction

    @staticmethod
    def update_transaction(transaction, price=None, quantity=None, fees=None, notes=None, symbol=None, date=None):
        """Update a transaction and recalculate"""
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

        transaction.calculate_net_amount()
        return transaction
