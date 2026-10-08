"""Schema 38 and durable receipts, using disposable fixtures exclusively."""

import sqlite3

import pytest
import sqlalchemy as sa

from portfolio_app import create_app, db, migrations
from portfolio_app.calculators.portfolio_calculator import PortfolioCalculator as PC
from portfolio_app.models import MutationReceipt, PortfolioTransfer
from tests.test_financial_baseline import ledger
from tests.test_portfolio_transfers import pair, transfer
from tests.test_migrations import _config_for
from tests.test_mutation_integrity import client_for, token, post, create_case


@pytest.fixture
def schema37(pair, test_db_path, tmp_path):
    transfer(pair)
    expected = PC.get_financial_snapshot(pair.uid)
    path = tmp_path / 'schema37.sqlite'
    with sqlite3.connect(test_db_path) as source, sqlite3.connect(path) as destination:
        source.backup(destination)
        destination.execute('DROP TABLE mutation_receipt')
        destination.execute('PRAGMA user_version=37')
    return path, pair.uid, expected


def assert_schema(connection):
    assert connection.exec_driver_sql('PRAGMA user_version').scalar() == 38
    assert {r[1] for r in connection.exec_driver_sql('PRAGMA table_info(mutation_receipt)')} == {
        'id', 'user_id', 'operation_key', 'request_digest', 'response_json',
    }
    keys = connection.exec_driver_sql('PRAGMA foreign_key_list(mutation_receipt)').all()
    assert [(r[2], r[3], r[4], r[6]) for r in keys] == [('user', 'user_id', 'id', 'CASCADE')]
    assert connection.exec_driver_sql('PRAGMA foreign_keys').scalar() == 1
    assert connection.exec_driver_sql('PRAGMA foreign_key_check').all() == []


def test_fresh_schema_receipt_constraints_and_exact_financial_types(app):
    with app.app_context():
        assert_schema(db.session.connection())
        assert PortfolioTransfer.__table__.c.amount.type.impl.__class__.__name__ == 'Text'


def test_upgrade_preserves_every_raw_financial_row_and_snapshot(schema37):
    path, uid, expected = schema37
    tables = ('portfolio', 'transaction', 'portfolio_event', 'dividend', 'portfolio_transfer')
    with sqlite3.connect(path) as connection:
        before = {table: connection.execute(f'SELECT * FROM "{table}" ORDER BY id').fetchall() for table in tables}
    upgraded = create_app(_config_for(path))
    with upgraded.app_context():
        assert_schema(db.session.connection())
        assert MutationReceipt.query.count() == 0
        assert PC.get_financial_snapshot(uid) == expected
        db.session.remove()
        db.engine.dispose()
    with sqlite3.connect(path) as connection:
        assert before == {table: connection.execute(f'SELECT * FROM "{table}" ORDER BY id').fetchall() for table in tables}
    reopened = create_app(_config_for(path))
    with reopened.app_context():
        assert_schema(db.session.connection())
        assert PC.get_financial_snapshot(uid) == expected
        db.session.remove()
        db.engine.dispose()


def test_failed_upgrade_rolls_back_schema_version_and_retries(schema37):
    path, uid, expected = schema37
    def fail(connection, cursor, statement, parameters, context, many):
        if statement.startswith('CREATE INDEX ix_mutation_user_revision'):
            raise RuntimeError('injected migration index failure')
    sa.event.listen(sa.engine.Engine, 'after_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='injected'):
            create_app(_config_for(path))
    finally:
        sa.event.remove(sa.engine.Engine, 'after_cursor_execute', fail)
    with sqlite3.connect(path) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 37
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='mutation_receipt'").fetchall() == []
    retried = create_app(_config_for(path))
    with retried.app_context():
        assert_schema(db.session.connection())
        assert PC.get_financial_snapshot(uid) == expected
        db.session.remove()
        db.engine.dispose()


def test_receipt_survives_new_application_and_connection(pair, app, test_db_path):
    path, values, model = create_case(pair, 'Transfer')
    intent = token(app, pair.uid)
    result = post(client_for(app, pair.uid), path, values, intent)
    assert result.status_code == 200
    class RestartConfig(_config_for(test_db_path)):
        SECRET_KEY = app.secret_key
    restarted = create_app(RestartConfig)
    with restarted.app_context():
        again = post(client_for(restarted, pair.uid), path, values, intent)
        assert again.json == result.json
        assert model.query.count() == 1
        db.session.remove()
        db.engine.dispose()


def test_receipt_uniqueness_and_account_cascade(pair):
    from portfolio_app.models import User
    from portfolio_app.services.mutation import record_mutation
    record_mutation(pair.uid, 'same-key')
    db.session.commit()
    record_mutation(pair.uid, 'same-key')
    with pytest.raises(sa.exc.IntegrityError):
        db.session.commit()
    db.session.rollback()
    pair.svc.user_repo.delete(db.session.get(User, pair.uid))
    db.session.commit()
    assert MutationReceipt.query.count() == 0
