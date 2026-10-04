"""PortfolioEvent model for cash events (deposits/withdrawals/initial)."""

from datetime import datetime, timezone
from sqlalchemy import CheckConstraint, Index
from portfolio_app import db
from portfolio_app.utils.exact_decimal import ExactDecimalText


class PortfolioEvent(db.Model):
    """A single cash event (Initial deposit, Deposit, or Withdrawal)."""

    __tablename__ = 'portfolio_event'

    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(
        db.Integer,
        db.ForeignKey('portfolio.id', ondelete='CASCADE'),
        nullable=False,
    )

    # Initial / Deposit / Withdrawal
    event_type = db.Column(db.String(20), nullable=False)

    # Signed delta: positive for deposits/initial, negative for withdrawals
    amount_delta = db.Column(ExactDecimalText(), nullable=False, default=0, server_default='0')

    date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    notes = db.Column(db.Text, nullable=True)

    __table_args__ = (
        CheckConstraint("typeof(amount_delta) = 'text'", name='check_amount_delta_text'),
        Index('ix_portfolio_event_portfolio_date', portfolio_id, date),
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
