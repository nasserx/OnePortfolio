"""One transaction owner for validation, writes and durable retry receipts.

SQLite is the supported mutation backend. Nested services join the owner's
transaction and cannot independently commit. An error poisons the complete
operation even when a route or caller catches it.
"""

from contextlib import contextmanager
from functools import wraps
from secrets import token_hex
from sqlalchemy import event
from sqlalchemy.orm import Session

from portfolio_app import db
from portfolio_app.models.mutation_receipt import MutationReceipt
from portfolio_app.utils.messages import MESSAGES
from portfolio_app.models.user import User
from portfolio_app.services.financial_audit import append_financial_audit


@event.listens_for(Session, 'before_commit')
def _prevent_nested_commit(session):
    if 'financial_mutation' in session.info and not session.info.get('financial_mutation_committing'):
        session.info['financial_mutation']['failed'] = True
        raise RuntimeError('Only the financial mutation owner may commit.')


@event.listens_for(Session, 'after_rollback')
def _poison_rolled_back_mutation(session):
    # A helper must not release the reservation and then continue under a stale
    # "protected" flag, even when its caller catches a database exception.
    state = session.info.get('financial_mutation')
    if state is not None:
        state['failed'] = True


def current_revision(user_id):
    return db.session.query(db.func.max(MutationReceipt.id)).filter_by(user_id=user_id).scalar() or 0


def record_mutation(user_id, key=None, digest='', response=None):
    receipt = MutationReceipt(user_id=user_id, operation_key=key or token_hex(32),
                              request_digest=digest, response_json=response)
    db.session.add(receipt)
    state = db.session.info.get('financial_mutation')
    if state is not None:
        state['receipt_users'].add(user_id)
        state['receipts'][user_id] = receipt


def abort_mutation():
    """Mark a handled route error for owner rollback, without releasing its lock."""
    state = db.session.info.get('financial_mutation')
    if state is not None:
        state['failed'] = True


@contextmanager
def mutation_transaction():
    session = db.session()
    active = session.info.get('financial_mutation')
    if active is not None:
        try:
            if active['failed']:
                raise RuntimeError('The financial mutation has already failed.')
            yield active
        except Exception:
            active['failed'] = True
            raise
        return
    # Pending work belongs to its caller; never discard it to obtain a lock.
    if session.new or session.dirty or session.deleted:
        raise RuntimeError('Financial mutations require a clean session boundary.')
    state = {'failed': False, 'writes': 0, 'users': set(), 'receipt_users': set(), 'receipts': {}}
    try:
        connection = session.connection()
        if connection.dialect.name != 'sqlite':
            raise RuntimeError('Financial mutation locking requires SQLite.')
        if connection.connection.driver_connection.in_transaction:
            raise RuntimeError('Enter the financial mutation boundary before starting a database transaction.')
        connection.exec_driver_sql('BEGIN IMMEDIATE')
        session.expire_all()
        session.info['financial_mutation'] = state
        yield state
        if state['failed']:
            session.rollback()
        else:
            session.flush()
            for uid in sorted(state['users'] - state['receipt_users']):
                if session.get(User, uid) is not None:
                    record_mutation(uid)
            session.flush()
            append_financial_audit(session, state)
            session.flush()
            # Only this owner may commit, including when called from a route.
            session.info['financial_mutation_committing'] = True
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.info.pop('financial_mutation', None)
        session.info.pop('financial_mutation_committing', None)


def financial_mutation(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        expected = kwargs.pop('expected_revision', None)
        with mutation_transaction() as state:
            repo = getattr(self, 'portfolio_repo', None)
            uid = repo.user_id if repo else None
            if expected is not None and (uid is None or expected != current_revision(uid)):
                raise ValueError(MESSAGES['MUTATION_STALE'])
            result = method(self, *args, **kwargs)
            db.session.flush()
            state['writes'] += 1
            if uid is not None:
                state['users'].add(uid)
            return result
    return guarded
