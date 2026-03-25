"""Fund model for different asset categories."""

from datetime import datetime
from decimal import Decimal
from sqlalchemy import Numeric
from portfolio_app import db


class Fund(db.Model):
    """Funds model for different asset categories."""

    __tablename__ = 'capital'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    category = db.Column(db.String(50), nullable=False)
    amount = db.Column(Numeric(15, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    transactions = db.relationship('Transaction', backref='fund', lazy='dynamic', cascade='all, delete-orphan')
    events = db.relationship('FundEvent', backref='fund', lazy='dynamic', cascade='all, delete-orphan')
    assets = db.relationship('Asset', backref='fund', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'category': self.category,
            'amount': float(self.amount),
            'created_at': self.created_at.strftime('%Y-%m-%d'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d')
        }
