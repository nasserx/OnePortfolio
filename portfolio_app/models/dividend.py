"""Dividend model for dividend income transactions."""

from datetime import datetime, timezone
from sqlalchemy import Numeric, CheckConstraint
from portfolio_app import db


class Dividend(db.Model):
    """A dividend income event linked to a portfolio."""

    __tablename__ = 'dividend'

    id           = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey('portfolio.id'), nullable=False)
    # Every dividend is attributed to a symbol. The dashboard groups
    # holdings by (portfolio_id, symbol); a null-symbol dividend would be
    # invisible there and was historically dropped from totals by a
    # defensive filter in the calculator. Enforce non-null at the schema
    # boundary so the filter can go away.
    symbol       = db.Column(db.String(20), nullable=False)
    amount       = db.Column(Numeric(20, 10), nullable=False)
    date         = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    notes        = db.Column(db.Text, nullable=True)
    created_at   = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    portfolio = db.relationship('Portfolio', backref=db.backref('dividends', lazy='dynamic', cascade='all, delete-orphan'))

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
        return {
            'id':             self.id,
            'portfolio_id':   self.portfolio_id,
            'symbol':         self.symbol or '',
            'portfolio_name': self.portfolio.name if self.portfolio else '',
            'type':           'Dividend',
            'amount':         float(self.amount),
            'date':           self.date_full,
            'date_short':     self.date.strftime('%b %d, %Y') if self.date else '',
            'notes':          self.notes or '',
        }
