"""Account-private committed financial history, independent of live entities."""

from sqlalchemy import DDL, event
from portfolio_app import db


class FinancialAudit(db.Model):
    __tablename__ = 'financial_audit'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    mutation_receipt_id = db.Column(db.Integer, db.ForeignKey('mutation_receipt.id'), nullable=False)
    entity_type = db.Column(db.String(32), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)  # Deliberately not an entity FK.
    action = db.Column(db.String(6), nullable=False)
    before_state = db.Column(db.Text)
    after_state = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False)

    __table_args__ = (
        db.CheckConstraint("action IN ('create', 'update', 'delete')", name='check_audit_action'),
        db.CheckConstraint(
            "(action = 'create' AND before_state IS NULL AND after_state IS NOT NULL) OR "
            "(action = 'update' AND before_state IS NOT NULL AND after_state IS NOT NULL) OR "
            "(action = 'delete' AND before_state IS NOT NULL AND after_state IS NULL)",
            name='check_audit_states',
        ),
        db.Index('ix_audit_user_history', 'user_id', 'created_at', 'id'),
        db.Index('ix_audit_user_mutation', 'user_id', 'mutation_receipt_id', 'id'),
        db.Index('ix_audit_user_entity', 'user_id', 'entity_type', 'entity_id', 'created_at', 'id'),
        {'sqlite_autoincrement': True},
    )


# These protections apply to ORM, bulk SQL and direct SQLite writes. A parent
# account's ON DELETE CASCADE runs after its user row is removed, so it remains
# the sole supported deletion exception. Model DDL serves fresh and upgrade DBs.
event.listen(FinancialAudit.__table__, 'after_create', DDL('''
CREATE TRIGGER financial_audit_no_update BEFORE UPDATE ON financial_audit
BEGIN SELECT RAISE(ABORT, 'Financial audit records are append-only'); END
''').execute_if(dialect='sqlite'))
event.listen(FinancialAudit.__table__, 'after_create', DDL('''
CREATE TRIGGER financial_audit_no_delete BEFORE DELETE ON financial_audit
WHEN EXISTS (SELECT 1 FROM user WHERE id = OLD.user_id)
BEGIN SELECT RAISE(ABORT, 'Financial audit records are retained for the account lifetime'); END
''').execute_if(dialect='sqlite'))
