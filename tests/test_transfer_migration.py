"""Schema 37 on disposable databases only; never open the working portfolio.db."""

import sqlite3
from decimal import Decimal as D

import pytest
import sqlalchemy as sa

from portfolio_app import create_app, db, migrations
from portfolio_app.models import PortfolioTransfer
from portfolio_app.calculators.portfolio_calculator import PortfolioCalculator as PC
from tests.test_migrations import _config_for
from tests.test_portfolio_transfers import pair, transfer
from tests.test_financial_baseline import ledger
from tests.test_portfolio_transfers import day


def schema(conn):
    columns = {r[1]: r for r in conn.exec_driver_sql('PRAGMA table_info(portfolio_transfer)')}
    assert columns['amount'][2] == 'TEXT'
    assert all(columns[k][3] for k in ('source_portfolio_id', 'destination_portfolio_id', 'amount', 'date', 'created_at', 'updated_at'))
    keys = conn.exec_driver_sql('PRAGMA foreign_key_list(portfolio_transfer)').all()
    assert {(r[2], r[3], r[4], r[6]) for r in keys} == {
        ('portfolio', 'source_portfolio_id', 'id', 'RESTRICT'),
        ('portfolio', 'destination_portfolio_id', 'id', 'RESTRICT'),
    }
    assert {r[1] for r in conn.exec_driver_sql('PRAGMA index_list(portfolio_transfer)')} == {
        'ix_transfer_source_date', 'ix_transfer_destination_date',
    }
    assert conn.exec_driver_sql('PRAGMA user_version').scalar() == migrations.TARGET_SCHEMA_VERSION
    assert conn.exec_driver_sql('PRAGMA foreign_keys').scalar() == 1
    assert conn.exec_driver_sql('PRAGMA foreign_key_check').all() == []


@pytest.fixture
def version36(pair, test_db_path, tmp_path):
    """Copy only the isolated fixture database; remove the additive new table."""
    svc = pair.svc
    svc.transaction_service.add_transaction(pair.a, 'Buy', 'PREC', D('0.12345678901234567890123456789'), D('2'), D('1E-30'), date=day(1))
    svc.transaction_service.add_transaction(pair.a, 'Sell', 'PREC', D('1'), D('1'), D('1E-30'), date=day(2))
    svc.transaction_service.add_dividend(pair.a, 'PREC', D('1E-31'), day(3))
    svc.portfolio_service.deposit_funds(pair.c, D('555'), date=day(1))
    svc.transaction_service.add_transaction(pair.c, 'Buy', 'BTC', D('185000'), D('0.003'), D('0'), date=day(1))
    svc.transaction_service.add_transaction(pair.c, 'Sell', 'BTC', D('186000'), D('0.003'), D('0'), date=day(2))
    svc.portfolio_service.withdraw_funds(pair.c, D('558'), date=day(3))
    svc.portfolio_service.deposit_funds(pair.c, D('3'), date=day(4))
    path = tmp_path / 'schema36.sqlite'
    expected = PC.get_financial_snapshot(pair.uid)
    with sqlite3.connect(test_db_path) as source, sqlite3.connect(path) as destination:
        source.backup(destination)
        destination.execute('DROP TABLE portfolio_transfer')
        destination.execute('PRAGMA user_version=36')
    return path, expected, pair.uid


def test_fresh_schema_uses_exact_transfer_table(app):
    with app.app_context():
        schema(db.session.connection())


def test_upgrade_preserves_all_existing_financial_records_and_snapshot(version36):
    path, expected, uid = version36
    with sqlite3.connect(path) as conn:
        before = {table: conn.execute(f'SELECT * FROM "{table}" ORDER BY id').fetchall()
                  for table in ('portfolio', 'portfolio_event', 'transaction', 'dividend')}
    upgraded = create_app(_config_for(path))
    with upgraded.app_context():
        schema(db.session.connection())
        assert PC.get_financial_snapshot(uid) == expected
        btc = next(p for p in PC.get_financial_snapshot(uid).portfolios if p.name == 'Third')
        assert btc.cash_balance == btc.metrics['book_value'] == btc.metrics['realized_trading_pnl'] == D('3')
        assert PortfolioTransfer.query.count() == 0
        db.session.remove()
        db.engine.dispose()
    with sqlite3.connect(path) as conn:
        for table, rows in before.items():
            assert conn.execute(f'SELECT * FROM "{table}" ORDER BY id').fetchall() == rows
    reopened = create_app(_config_for(path))
    with reopened.app_context():
        assert PC.get_financial_snapshot(uid) == expected


def test_failed_transfer_migration_rolls_back_table_indexes_and_version(version36):
    path, _, _ = version36
    engine = sa.create_engine(f'sqlite:///{path.as_posix()}')
    with engine.connect() as conn:
        before = conn.exec_driver_sql('SELECT type,name,sql FROM sqlite_master ORDER BY name').all()
        def fail(conn, cursor, statement, parameters, context, many):
            if statement.startswith('CREATE INDEX ix_transfer'):
                raise RuntimeError('injected index failure')
        sa.event.listen(conn, 'before_cursor_execute', fail)
        try:
            with pytest.raises(RuntimeError, match='injected'):
                migrations._migrate_portfolio_transfers(conn, sa)
        finally:
            sa.event.remove(conn, 'before_cursor_execute', fail)
        assert conn.exec_driver_sql('PRAGMA user_version').scalar() == 36
        assert conn.exec_driver_sql('SELECT type,name,sql FROM sqlite_master ORDER BY name').all() == before
    engine.dispose()


def test_startup_failure_keeps_old_version_and_can_retry(version36):
    path, expected, uid = version36
    def fail(conn, cursor, statement, parameters, context, many):
        if statement.startswith('CREATE INDEX ix_transfer'):
            raise RuntimeError('injected startup failure')
    sa.event.listen(sa.engine.Engine, 'after_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='injected startup failure'):
            create_app(_config_for(path))
    finally:
        sa.event.remove(sa.engine.Engine, 'after_cursor_execute', fail)
    with sqlite3.connect(path) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 36
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='portfolio_transfer'").fetchall() == []
    retried = create_app(_config_for(path))
    with retried.app_context():
        schema(db.session.connection())
        assert PC.get_financial_snapshot(uid) == expected


@pytest.mark.parametrize('operation', ['delete_source', 'delete_destination', 'orphan_source', 'orphan_destination', 'self_transfer'])
def test_foreign_keys_and_distinct_endpoint_constraint(pair, operation):
    row = transfer(pair)
    conn = db.session.connection()
    statements = {
        'delete_source': f'DELETE FROM portfolio WHERE id={pair.a}',
        'delete_destination': f'DELETE FROM portfolio WHERE id={pair.b}',
        'orphan_source': f'UPDATE portfolio_transfer SET source_portfolio_id=999999 WHERE id={row.id}',
        'orphan_destination': f'UPDATE portfolio_transfer SET destination_portfolio_id=999999 WHERE id={row.id}',
        'self_transfer': f'UPDATE portfolio_transfer SET destination_portfolio_id=source_portfolio_id WHERE id={row.id}',
    }
    with pytest.raises(sa.exc.IntegrityError): conn.exec_driver_sql(statements[operation])
    db.session.rollback()
    assert pair.svc.transfer_repo.get_by_id(row.id).amount == D('100')
