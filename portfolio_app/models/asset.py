"""Asset model for tracked symbols."""

from datetime import datetime
from sqlalchemy import UniqueConstraint, Index
from portfolio_app import db


class Asset(db.Model):
    """A tracked symbol (ticker) inside a fund.

    Allows creating a position row on the Transactions page before any
    buy/sell transactions exist for that symbol.
    """

    __tablename__ = 'asset'

    id = db.Column(db.Integer, primary_key=True)
    fund_id = db.Column(db.Integer, db.ForeignKey('fund.id'), nullable=False)
    symbol = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(fund_id, symbol, name='uq_asset_fund_symbol'),
        Index('ix_asset_fund_symbol', fund_id, symbol),
    )

    def to_dict(self):
        """Convert model to dictionary."""
        return {
            'id': self.id,
            'fund_id': self.fund_id,
            'portfolio_name': self.fund.name if getattr(self, 'fund', None) else None,
            'symbol': (self.symbol or '').upper(),
            'created_at': self.created_at.strftime('%Y-%m-%d') if self.created_at else None,
            'updated_at': self.updated_at.strftime('%Y-%m-%d') if self.updated_at else None,
        }
