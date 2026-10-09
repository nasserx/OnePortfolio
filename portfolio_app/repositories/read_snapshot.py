"""Explicit SQLite read snapshots, without taking the financial writer lock."""

from contextlib import contextmanager
from functools import wraps

from sqlalchemy import event
from sqlalchemy.orm import Session

from portfolio_app import db


@event.listens_for(Session, 'before_flush')
def _no_flush_during_report(session, *args):
    if session.info.get('owned_read_snapshot'):
        raise RuntimeError('A financial reporting snapshot cannot write.')


@event.listens_for(Session, 'before_commit')
def _no_commit_during_report(session):
    if session.info.get('owned_read_snapshot'):
        raise RuntimeError('A financial reporting snapshot cannot commit.')


@contextmanager
def read_snapshot():
    """Join an existing database transaction, or own a clean read-only one.

    SQLAlchemy's logical autobegin alone does not issue SQLite BEGIN for SELECT.
    Start a real deferred transaction. Nested reports and reads within mutations
    join their owner's transaction and never commit/rollback its work.
    """
    session = db.session()
    connection = session.connection()
    if connection.dialect.name != 'sqlite':
        raise RuntimeError('Financial read snapshots require SQLite.')
    driver = connection.connection.driver_connection
    if driver.in_transaction:
        if not session.info.get('owned_read_snapshot') and not session.info.get('financial_mutation'):
            # A caller-owned transaction can still inherit clean identity-map
            # rows cached *before* its BEGIN. Refresh those, but never discard
            # pending edits or assume ownership of the caller's transaction.
            for row in list(session.identity_map.values()):
                if row not in session.dirty and row not in session.deleted:
                    session.expire(row)
        yield
        return
    if session.new or session.dirty or session.deleted:
        raise RuntimeError('A standalone reporting snapshot requires a clean session.')
    session.expire_all()  # Do not combine cached ORM rows with a new SQL snapshot.
    previous_query_only = connection.exec_driver_sql('PRAGMA query_only').scalar()
    try:
        connection.exec_driver_sql('PRAGMA query_only = ON')
        connection.exec_driver_sql('BEGIN')
        session.info['owned_read_snapshot'] = True
        with session.no_autoflush:
            yield
    finally:
        # Only release the physical read transaction we created. Do not call
        # Session.rollback(): returned, fully loaded history rows remain usable.
        try:
            if driver.in_transaction:
                connection.exec_driver_sql('ROLLBACK')
        finally:
            connection.exec_driver_sql(f'PRAGMA query_only = {int(previous_query_only)}')
            session.info.pop('owned_read_snapshot', None)


def coherent_read(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with read_snapshot():
            return function(*args, **kwargs)
    return wrapped
