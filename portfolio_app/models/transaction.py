"""Transaction model for buy/sell operations."""

from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Numeric, CheckConstraint
from portfolio_app import db


class Transaction(db.Model):
    """A single buy or sell transaction for a symbol within a portfolio."""

    __tablename__ = 'transaction'

    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey('portfolio.id'), nullable=False)
    transaction_type = db.Column(db.String(10), nullable=False)  # 'Buy' or 'Sell'
    symbol = db.Column(db.String(20), nullable=True)
    # Higher precision to support crypto-style pricing (e.g. 0.0002344)
    price = db.Column(Numeric(20, 10), nullable=False)
    quantity = db.Column(Numeric(20, 10), nullable=False)
    fees = db.Column(Numeric(20, 10), nullable=False, default=0)
    # Buy: gross + fees  |  Sell: gross - fees
    net_amount = db.Column(Numeric(20, 10), nullable=False, default=0)
    average_cost = db.Column(Numeric(20, 10), nullable=False, default=0)
    date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    notes = db.Column(db.Text, nullable=True)

    # One sell → one ClosedTrade snapshot (None for Buy transactions).
    # passive_deletes=True lets the DB CASCADE handle deletion without a pre-load SELECT.
    closed_trade = db.relationship(
        'ClosedTrade',
        backref='transaction',
        uselist=False,
        cascade='all, delete-orphan',
        passive_deletes=True,
    )

    @property
    def date_short(self):
        if not self.date:
            return ''
        return self.date.strftime('%Y-%m-%d')

    @property
    def date_full(self):
        if not self.date:
            return ''
        return self.date.strftime('%Y-%m-%d %H:%M')

    __table_args__ = (
        CheckConstraint('price > 0', name='check_price_positive'),
        CheckConstraint('quantity > 0', name='check_quantity_positive'),
        CheckConstraint('fees >= 0', name='check_fees_non_negative'),
        CheckConstraint('net_amount >= 0', name='check_net_amount_non_negative'),
    )

    def calculate_net_amount(self):
        """Calculate and store net_amount from price, quantity, and fees.

        Buy:  net_amount = (price × quantity) + fees
        Sell: net_amount = (price × quantity) - fees
        """
        price = Decimal(str(self.price))
        quantity = Decimal(str(self.quantity))
        fees = Decimal(str(self.fees))
        gross = price * quantity

        if self.transaction_type == 'Sell':
            self.net_amount = gross - fees
        else:  # Buy
            self.net_amount = gross + fees

    def to_dict(self):
        return {
            'id': self.id,
            'portfolio_id': self.portfolio_id,
            'portfolio_name': self.portfolio.name,
            'transaction_type': self.transaction_type,
            'symbol': (self.symbol or '').upper(),
            'price': float(self.price),
            'quantity': float(self.quantity),
            'fees': float(self.fees),
            'net_amount': float(self.net_amount),
            'average_cost': float(self.average_cost),
            'date': self.date.strftime('%Y-%m-%d %H:%M'),
            'date_short': self.date.strftime('%b %d, %Y'),
            'date_full': self.date.strftime('%B %d, %Y at %H:%M'),
            'notes': self.notes or ''
        }
