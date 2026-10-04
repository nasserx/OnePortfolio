"""Transaction model for buy/sell operations."""

from datetime import datetime, timezone
from sqlalchemy import CheckConstraint
from portfolio_app import db
from portfolio_app.utils.decimal_utils import decimal_text
from portfolio_app.utils.exact_decimal import ExactDecimalText


class Transaction(db.Model):
    """A single buy or sell transaction for a symbol within a portfolio."""

    __tablename__ = 'transaction'

    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(
        db.Integer,
        db.ForeignKey('portfolio.id', ondelete='CASCADE'),
        nullable=False,
    )
    transaction_type = db.Column(db.String(10), nullable=False)  # 'Buy' or 'Sell'
    symbol = db.Column(db.String(20), nullable=True)
    price = db.Column(ExactDecimalText(), nullable=False)
    quantity = db.Column(ExactDecimalText(), nullable=False)
    fees = db.Column(ExactDecimalText(), nullable=False, default=0, server_default='0')
    date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    notes = db.Column(db.Text, nullable=True)

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
        CheckConstraint("typeof(price) = 'text'", name='check_price_text'),
        CheckConstraint("typeof(quantity) = 'text'", name='check_quantity_text'),
        CheckConstraint("typeof(fees) = 'text'", name='check_fees_text'),
    )

    def to_dict(self, *, projection, portfolio_name):
        """Serialize with explicit canonical history context, never legacy fields.

        Callers reuse the asset snapshot's projection map and portfolio name for
        all rows. No query or replay occurs here. The snapshot must be fresh for
        these records; it is a point-in-time read model, not a persistent cache.
        """
        if projection.transaction_id != self.id or projection.portfolio_id != self.portfolio_id:
            raise ValueError('Projection does not belong to this transaction.')
        net_pnl = projection.realized_trading_pnl
        net_pnl_percent = projection.trade_return_percent
        return {
            'id': self.id,
            'portfolio_id': self.portfolio_id,
            'portfolio_name': portfolio_name,
            'transaction_type': self.transaction_type,
            'symbol': (self.symbol or '').upper(),
            'price': decimal_text(self.price),
            'quantity': decimal_text(self.quantity),
            'fees': decimal_text(self.fees),
            'net_amount': decimal_text(projection.cash_amount),
            'average_cost': decimal_text(projection.applicable_average_unit_cost),
            'net_pnl': decimal_text(net_pnl) if net_pnl is not None else None,
            'net_pnl_percent': decimal_text(net_pnl_percent) if net_pnl_percent is not None else None,
            'date': self.date.strftime('%Y-%m-%d %H:%M'),
            'date_short': self.date.strftime('%b %d, %Y'),
            'date_full': self.date.strftime('%B %d, %Y at %H:%M'),
            'notes': self.notes or ''
        }
