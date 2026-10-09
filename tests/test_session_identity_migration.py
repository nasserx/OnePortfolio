"""Schema 40 account identity upgrades use disposable copies, never portfolio.db."""

import re
import sqlite3

import pytest
import sqlalchemy as sa

from portfolio_app import create_app, db
from portfolio_app.models import User
from portfolio_app.migrations import TARGET_SCHEMA_VERSION
from tests.test_migrations import _config_for
from tests.test_financial_baseline import ledger
from tests.test_portfolio_transfers import pair, transfer, PC


@pytest.fixture
def schema39(pair, test_db_path, tmp_path):
    transfer(pair)
    expected = PC.get_financial_snapshot(pair.uid)
    path = tmp_path / 'schema39.sqlite'
    with sqlite3.connect(test_db_path) as source, sqlite3.connect(path) as destination:
        source.backup(destination)
        destination.execute('DROP INDEX ix_user_session_identity')
        destination.execute('ALTER TABLE user DROP COLUMN session_identity')
        destination.execute('PRAGMA user_version=39')
    return path, pair.uid, expected


def persisted_rows(path):
    with sqlite3.connect(path) as connection:
        tables = ('user', 'portfolio', 'transaction', 'dividend', 'portfolio_event',
                  'portfolio_transfer', 'mutation_receipt', 'financial_audit')
        result = {}
        for table in tables:
            columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')
                       if row[1] != 'session_identity']
            fields = ','.join(f'"{column}"' for column in columns)
            result[table] = connection.execute(f'SELECT {fields} FROM "{table}" ORDER BY id').fetchall()
        return result


def test_upgrade_preserves_records_audits_receipts_and_invalidates_v1(schema39):
    path, uid, expected = schema39
    before = persisted_rows(path)
    identity = None
    for _ in range(2):
        app = create_app(_config_for(path))
        with app.app_context():
            user = db.session.get(User, uid)
            assert re.fullmatch('[0-9a-f]{64}', user.session_identity)
            if identity is not None:
                assert user.get_id() == identity
            identity = user.get_id()
            assert app.login_manager._user_callback(identity).id == uid
            assert app.login_manager._user_callback(f'v1:{uid}:{user.auth_generation}') is None
            assert app.login_manager._user_callback(str(uid)) is None
            assert PC.get_financial_snapshot(uid) == expected
            connection = db.session.connection()
            assert connection.exec_driver_sql('PRAGMA user_version').scalar() == TARGET_SCHEMA_VERSION == 40
            assert connection.exec_driver_sql('PRAGMA foreign_key_check').all() == []
            assert connection.exec_driver_sql('PRAGMA foreign_keys').scalar() == 1
            db.session.remove()
            db.engine.dispose()
        assert persisted_rows(path) == before


@pytest.mark.parametrize('marker', ['UPDATE user SET session_identity', 'CREATE UNIQUE INDEX IF NOT EXISTS ix_user_session_identity'])
def test_identity_upgrade_failure_is_atomic_and_retryable(schema39, marker):
    path, uid, expected = schema39
    before = persisted_rows(path)
    def fail(connection, cursor, statement, *args):
        if marker in statement:
            raise RuntimeError('injected identity migration failure')
    sa.event.listen(sa.engine.Engine, 'after_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='injected identity'):
            create_app(_config_for(path))
    finally:
        sa.event.remove(sa.engine.Engine, 'after_cursor_execute', fail)
    with sqlite3.connect(path) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 39
        assert 'session_identity' not in {row[1] for row in connection.execute('PRAGMA table_info(user)')}
    assert persisted_rows(path) == before
    app = create_app(_config_for(path))
    with app.app_context():
        assert PC.get_financial_snapshot(uid) == expected
        assert db.session.connection().exec_driver_sql('PRAGMA user_version').scalar() == 40
        db.session.remove()
        db.engine.dispose()


def test_fresh_accounts_have_distinct_random_identities_and_unique_index(app):
    with app.app_context():
        users = [User(username=f'Identity{i}', email=f'identity{i}@example.com', is_verified=True) for i in range(2)]
        db.session.add_all(users)
        db.session.commit()
        assert users[0].session_identity != users[1].session_identity
        assert all(re.fullmatch('[0-9a-f]{64}', user.session_identity) for user in users)
        old_identity = users[0].get_id()
        users[0].auth_generation += 1
        db.session.commit()
        assert app.login_manager._user_callback(old_identity) is None
        assert app.login_manager._user_callback(users[0].get_id()).id == users[0].id
        users[1].session_identity = users[0].session_identity
        with pytest.raises(sa.exc.IntegrityError):
            db.session.commit()
        db.session.rollback()
