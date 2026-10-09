"""Forward schema 39; all upgrades use copies of isolated fixture databases."""

import sqlite3

import pytest
import sqlalchemy as sa

from portfolio_app import create_app, db
from portfolio_app.migrations import TARGET_SCHEMA_VERSION
from portfolio_app.models import FinancialAudit
from tests.test_financial_baseline import ledger
from tests.test_portfolio_transfers import pair, transfer, PC
from tests.test_migrations import _config_for
from tests.test_mutation_integrity import client_for, token, post, create_case


@pytest.fixture
def schema38(pair, test_db_path, tmp_path):
    transfer(pair)
    expected = PC.get_financial_snapshot(pair.uid)
    path = tmp_path / 'schema38.sqlite'
    with sqlite3.connect(test_db_path) as source, sqlite3.connect(path) as destination:
        source.backup(destination)
        destination.execute('DROP TABLE financial_audit')
        destination.execute('PRAGMA user_version=38')
    return path, pair.uid, expected


def assert_schema(connection):
    assert connection.exec_driver_sql('PRAGMA user_version').scalar() == TARGET_SCHEMA_VERSION
    columns = {r[1]: r[2] for r in connection.exec_driver_sql('PRAGMA table_info(financial_audit)')}
    assert columns == dict(id='INTEGER', user_id='INTEGER', mutation_receipt_id='INTEGER',
                          entity_type='VARCHAR(32)', entity_id='INTEGER', action='VARCHAR(6)',
                          before_state='TEXT', after_state='TEXT', created_at='DATETIME')
    keys = connection.exec_driver_sql('PRAGMA foreign_key_list(financial_audit)').all()
    assert {(r[2], r[3], r[6]) for r in keys} == {
        ('user', 'user_id', 'CASCADE'), ('mutation_receipt', 'mutation_receipt_id', 'NO ACTION'),
    }
    assert {r[1] for r in connection.exec_driver_sql('PRAGMA index_list(financial_audit)')} == {
        'ix_audit_user_history', 'ix_audit_user_entity', 'ix_audit_user_mutation',
    }
    assert {r[0] for r in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='financial_audit'")} == {
        'financial_audit_no_update', 'financial_audit_no_delete',
    }
    assert connection.exec_driver_sql('PRAGMA foreign_keys').scalar() == 1
    assert connection.exec_driver_sql('PRAGMA foreign_key_check').all() == []


def test_fresh_schema_audit_constraints_and_no_live_entity_foreign_key(app):
    with app.app_context():
        assert_schema(db.session.connection())


def test_upgrade_preserves_all_existing_records_receipts_and_accounting(schema38):
    path, uid, expected = schema38
    tables = ('user', 'portfolio', 'transaction', 'portfolio_event', 'dividend', 'portfolio_transfer', 'mutation_receipt')
    with sqlite3.connect(path) as connection:
        before = {t: connection.execute(f'SELECT * FROM "{t}" ORDER BY id').fetchall() for t in tables}
    for _ in range(2):
        upgraded = create_app(_config_for(path))
        with upgraded.app_context():
            assert_schema(db.session.connection())
            assert FinancialAudit.query.count() == 0  # No invented historical revisions.
            assert PC.get_financial_snapshot(uid) == expected
            db.session.remove()
            db.engine.dispose()
    with sqlite3.connect(path) as connection:
        assert before == {t: connection.execute(f'SELECT * FROM "{t}" ORDER BY id').fetchall() for t in tables}


@pytest.mark.parametrize('marker', ['CREATE INDEX ix_audit_user_', 'CREATE TRIGGER financial_audit_no_delete'])
def test_failed_upgrade_rolls_back_all_schema_artifacts_then_retries(schema38, marker):
    path, uid, expected = schema38
    def fail(connection, cursor, statement, parameters, context, many):
        if marker in statement:
            raise RuntimeError('injected audit DDL failure')
    sa.event.listen(sa.engine.Engine, 'after_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='injected'):
            create_app(_config_for(path))
    finally:
        sa.event.remove(sa.engine.Engine, 'after_cursor_execute', fail)
    with sqlite3.connect(path) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 38
        assert connection.execute("SELECT name FROM sqlite_master WHERE tbl_name='financial_audit'").fetchall() == []
    retried = create_app(_config_for(path))
    with retried.app_context():
        assert_schema(db.session.connection())
        assert PC.get_financial_snapshot(uid) == expected
        db.session.remove()
        db.engine.dispose()


def test_audit_survives_restart_and_receipt_replay_does_not_append(pair, app, test_db_path):
    path, values, _ = create_case(pair, 'Transfer')
    intent = token(app, pair.uid)
    result = post(client_for(app, pair.uid), path, values, intent)
    assert result.status_code == 200
    expected = pair.svc.audit_repo.history()
    class RestartConfig(_config_for(test_db_path)):
        SECRET_KEY = app.secret_key
    restarted = create_app(RestartConfig)
    with restarted.app_context():
        from portfolio_app.services.factory import Services
        assert post(client_for(restarted, pair.uid), path, values, intent).json == result.json
        assert Services(user_id=pair.uid).audit_repo.history() == expected
        db.session.remove()
        db.engine.dispose()


def test_upgraded_account_retains_new_revisions_until_account_deletion(schema38):
    from portfolio_app.models import User, MutationReceipt
    from portfolio_app.services.factory import Services
    from portfolio_app.services.mutation import mutation_transaction
    path, uid, _ = schema38
    upgraded = create_app(_config_for(path))
    with upgraded.app_context():
        svc = Services(user_id=uid)
        portfolio = svc.portfolio_service.create_portfolio('After upgrade')
        assert len(svc.audit_repo.history()) == 1
        svc.portfolio_service.delete_portfolio(portfolio.id)
        assert [r.action for r in svc.audit_repo.history()] == ['create', 'delete']
        with mutation_transaction():
            svc.user_repo.delete(db.session.get(User, uid))
        assert FinancialAudit.query.count() == MutationReceipt.query.count() == 0
        assert_schema(db.session.connection())
        db.session.remove()
        db.engine.dispose()
