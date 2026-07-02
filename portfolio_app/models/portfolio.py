"""Portfolio model representing a named portfolio."""

from datetime import datetime, timezone
from portfolio_app import db


class Portfolio(db.Model):
    """Represents a named portfolio belonging to a user.

    Cash flow (deposits/withdrawals) is stored exclusively in
    ``PortfolioEvent`` rows; the previous ``net_deposits`` column was a
    denormalized cache that could drift from the events log and was
    removed in migration step 25.
    """

    __tablename__ = 'portfolio'

    id = db.Column(db.Integer, primary_key=True)
    # Every portfolio is owned by exactly one user. Pre-existing rows with
    # NULL user_id are purged in migration step 22; new rows are required to
    # carry an owner so cross-user queries cannot accidentally surface them.
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(50), nullable=False)
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
            'created_at': self.created_at.strftime('%Y-%m-%d'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d'),
        }
