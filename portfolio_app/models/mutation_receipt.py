"""Durable successful submissions and an account-wide mutation revision."""

from portfolio_app import db


class MutationReceipt(db.Model):
    __tablename__ = 'mutation_receipt'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    operation_key = db.Column(db.String(64), nullable=False)
    request_digest = db.Column(db.String(64), nullable=False)
    response_json = db.Column(db.Text)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'operation_key', name='uq_mutation_user_key'),
        db.Index('ix_mutation_user_revision', 'user_id', 'id'),
        {'sqlite_autoincrement': True},
    )
