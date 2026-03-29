"""Dividend model for dividend income transactions."""

from datetime import datetime
from decimal import Decimal
from sqlalchemy import Numeric, CheckConstraint
from portfolio_app import db


class Dividend(db.Model):
    """A dividend income event linked to a fund."""

    __tablename__ = 'dividend'

    id         = db.Column(db.Integer, primary_key=True)
    fund_id    = db.Column(db.Integer, db.ForeignKey('fund.id'), nullable=False)
    symbol     = db.Column(db.String(20), nullable=True)
    amount     = db.Column(Numeric(20, 10), nullable=False)
    date       = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    notes      = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    fund = db.relationship('Fund', backref=db.backref('dividends', lazy='dynamic', cascade='all, delete-orphan'))

    __table_args__ = (
        CheckConstraint('amount > 0', name='check_dividend_amount_positive'),
    )

    @property
    def date_short(self) -> str:
        return self.date.strftime('%Y-%m-%d') if self.date else ''

    @property
    def date_full(self) -> str:
        return self.date.strftime('%Y-%m-%d %H:%M') if self.date else ''

    def to_dict(self) -> dict:
        """Convert model to dictionary."""
        return {
            'id':         self.id,
            'fund_id':    self.fund_id,
            'symbol':     self.symbol or '',
            'asset_class': self.fund.asset_class if self.fund else '',
            'type':       'Dividend',
            'amount':     float(self.amount),
            'date':       self.date_full,
            'date_short': self.date.strftime('%b %d, %Y') if self.date else '',
            'notes':      self.notes or '',
        }
