"""One atomic same-owner, same-accounting-unit cash transfer."""

from datetime import datetime, timezone
from portfolio_app import db
from portfolio_app.utils.exact_decimal import ExactDecimalText
from portfolio_app.utils.decimal_utils import decimal_text


class PortfolioTransfer(db.Model):
    __tablename__ = 'portfolio_transfer'

    id = db.Column(db.Integer, primary_key=True)
    source_portfolio_id = db.Column(db.Integer, db.ForeignKey('portfolio.id', ondelete='RESTRICT'), nullable=False)
    destination_portfolio_id = db.Column(db.Integer, db.ForeignKey('portfolio.id', ondelete='RESTRICT'), nullable=False)
    amount = db.Column(ExactDecimalText(), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint('source_portfolio_id != destination_portfolio_id', name='check_transfer_distinct'),
        db.CheckConstraint("typeof(amount) = 'text'", name='check_transfer_amount_text'),
        db.Index('ix_transfer_source_date', 'source_portfolio_id', 'date'),
        db.Index('ix_transfer_destination_date', 'destination_portfolio_id', 'date'),
    )

    def to_dict(self):
        """Raw editable fields only; no floats or formatted money."""
        return dict(id=self.id, source_portfolio_id=self.source_portfolio_id,
                    destination_portfolio_id=self.destination_portfolio_id,
                    amount=decimal_text(self.amount), date=self.date.strftime('%Y-%m-%d'),
                    notes=self.notes or '')
