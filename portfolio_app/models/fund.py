"""Fund model for different asset classes."""

from datetime import datetime
from decimal import Decimal
from sqlalchemy import Numeric
from portfolio_app import db


class Fund(db.Model):
    """Represents a user's fund allocated to a specific asset class."""

    __tablename__ = 'fund'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    asset_class = db.Column(db.String(50), nullable=False)
    cash_balance = db.Column(Numeric(15, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    transactions = db.relationship('Transaction', backref='fund', lazy='dynamic', cascade='all, delete-orphan')
    events = db.relationship('FundEvent', backref='fund', lazy='dynamic', cascade='all, delete-orphan')
    assets = db.relationship('Asset', backref='fund', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        """Convert model to dictionary."""
        return {
            'id': self.id,
            'asset_class': self.asset_class,
            'cash_balance': float(self.cash_balance),
            'created_at': self.created_at.strftime('%Y-%m-%d'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d')
        }
