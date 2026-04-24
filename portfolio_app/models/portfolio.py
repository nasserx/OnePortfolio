"""Portfolio model representing a named portfolio."""

from datetime import datetime, timezone
from sqlalchemy import Numeric
from portfolio_app import db


class Portfolio(db.Model):
    """Represents a named portfolio belonging to a user."""

    __tablename__ = 'portfolio'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    name = db.Column(db.String(50), nullable=False)
    net_deposits = db.Column(Numeric(15, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    transactions = db.relationship('Transaction', backref='portfolio', lazy='dynamic', cascade='all, delete-orphan')
    events = db.relationship('PortfolioEvent', backref='portfolio', lazy='dynamic', cascade='all, delete-orphan')
    symbols = db.relationship('Symbol', backref='portfolio', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'net_deposits': float(self.net_deposits),
            'created_at': self.created_at.strftime('%Y-%m-%d'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d')
        }
