"""FundEvent model for funding events (deposits/withdrawals)."""

from datetime import datetime, timezone
from sqlalchemy import Numeric, Index
from portfolio_app import db


class FundEvent(db.Model):
    """A single funding event (Initial deposit, Deposit, or Withdrawal) for a fund."""

    __tablename__ = 'fund_event'

    id = db.Column(db.Integer, primary_key=True)
    fund_id = db.Column(db.Integer, db.ForeignKey('fund.id'), nullable=False)

    # Initial / Deposit / Withdrawal
    event_type = db.Column(db.String(20), nullable=False)

    # Signed delta: positive for deposits/initial, negative for withdrawals
    amount_delta = db.Column(Numeric(15, 2), nullable=False, default=0)

    date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    notes = db.Column(db.Text, nullable=True)

    __table_args__ = (
        Index('ix_fund_event_fund_date', fund_id, date),
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
