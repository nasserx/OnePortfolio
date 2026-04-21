"""Asset model for tracked symbols."""

from datetime import datetime, timezone
from sqlalchemy import UniqueConstraint, Index
from portfolio_app import db


class Asset(db.Model):
    """A tracked symbol (ticker) inside a portfolio."""

    __tablename__ = 'asset'

    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey('portfolio.id'), nullable=False)
    symbol = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint(portfolio_id, symbol, name='uq_asset_portfolio_symbol'),
        Index('ix_asset_portfolio_symbol', portfolio_id, symbol),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'portfolio_id': self.portfolio_id,
            'portfolio_name': self.portfolio.name if getattr(self, 'portfolio', None) else None,
            'symbol': (self.symbol or '').upper(),
            'created_at': self.created_at.strftime('%Y-%m-%d') if self.created_at else None,
            'updated_at': self.updated_at.strftime('%Y-%m-%d') if self.updated_at else None,
        }
