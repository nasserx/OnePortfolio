"""Exact TEXT persistence and disposable schema-35 financial reconciliation."""

from datetime import datetime
from decimal import Decimal as D, localcontext
from types import SimpleNamespace
import sqlite3

import pytest
import sqlalchemy as sa

from portfolio_app import create_app, db
from portfolio_app import migrations
from portfolio_app.calculators import PortfolioCalculator as PC
from portfolio_app.calculators.financial_math import replay_symbol_transactions
from portfolio_app.calculators.financial_snapshots import (
    build_asset_snapshot, build_portfolio_snapshot, build_global_snapshot,
)
from portfolio_app.calculators.transaction_order import order_transactions
from portfolio_app.models import Transaction, Dividend, PortfolioEvent
from portfolio_app.services.transaction_service import ValidationError
from portfolio_app.utils.exact_decimal import ExactDecimalText, canonical_decimal_text
from tests.test_financial_baseline import ledger, _trade
from tests.test_migrations import _create_version_33_no_action_database, _config_for
from tests._auth import authenticate_client


FIELDS = {'transaction': ('price', 'quantity', 'fees'),
          'dividend': ('amount',), 'portfolio_event': ('amount_delta',)}


@pytest.mark.parametrize('value, text', [
    ('0', '0'), ('-0', '0'), ('0E-10', '0'), ('185000.000', '185000'),
    ('0.003', '0.003'), ('1234567890.1234567890', '1234567890.123456789'),
    ('0.00000000001', '0.00000000001'),
    ('123456789012345678901234567890.12345678901234567890',
     '123456789012345678901234567890.1234567890123456789'),
])
def test_canonical_text_is_context_independent(value, text):
    with localcontext() as context:
        context.prec = 6
        assert canonical_decimal_text(D(value)) == text
        assert ExactDecimalText().process_result_value(text, None) == D(value)


@pytest.mark.parametrize('value', [0.1, float('inf'), True, D('NaN'), D('Infinity'), D('-Infinity')])
def test_type_rejects_float_and_nonfinite_binding(value):
    with pytest.raises(ValueError):
        ExactDecimalText().process_bind_param(value, None)


@pytest.mark.parametrize('value', [1.5, 'NaN', 'Infinity', '-0', '1.00', '1E-11'])
def test_type_rejects_nontext_nonfinite_or_noncanonical_storage(value):
    with pytest.raises(ValueError):
        ExactDecimalText().process_result_value(value, None)


@pytest.mark.parametrize('value', [
    '1234567890.1234567890', '0.00000000001', '0.000000000000000000123456789',
    '987654321098765432109876543210.1234567890123456789',
])
def test_every_authoritative_field_round_trips_exactly_and_is_text(ledger, value):
    amount = D(value)
    trade = Transaction(portfolio_id=ledger.pid, transaction_type='Buy', symbol='BTC',
                        price=amount, quantity=amount, fees=amount, date=datetime(2024, 1, 1))
    income = Dividend(portfolio_id=ledger.pid, symbol='BTC', amount=amount,
                      date=datetime(2024, 1, 1))
    funding = PortfolioEvent(portfolio_id=ledger.pid, event_type='Deposit', amount_delta=amount)
    db.session.add_all([trade, income, funding])
    db.session.commit()
    ids = [row.id for row in (trade, income, funding)]
    db.session.expunge_all()
    for model, identifier in zip((Transaction, Dividend, PortfolioEvent), ids):
        row = db.session.get(model, identifier)
        for field in FIELDS[model.__tablename__]:
            assert getattr(row, field) == amount
            assert isinstance(getattr(row, field), D)
            stored, kind = db.session.execute(sa.text(
                f'SELECT "{field}", typeof("{field}") FROM "{model.__tablename__}" WHERE id=:id'
            ), {'id': identifier}).one()
            assert (stored, kind) == (canonical_decimal_text(amount), 'text')


def test_orm_rejects_float_before_sql_persistence(ledger):
    db.session.add(Transaction(portfolio_id=ledger.pid, transaction_type='Buy', symbol='BTC',
                               price=0.1, quantity=D('1'), fees=D('0')))
    with pytest.raises(sa.exc.StatementError, match='Invalid finite decimal'):
        db.session.flush()
    db.session.rollback()
    assert Transaction.query.count() == 0


def test_exact_persisted_value_is_preserved_by_calculation_above_28_digits(ledger):
    # Phase 7 converts the former ambient-context loss into a correctness contract.
    price = D('123456789012345678901234567890.123456789')
    row = _trade(ledger, 'Buy', str(price), '1', 1)
    db.session.refresh(row)
    with localcontext() as context:
        context.prec = 28
        assert row.price == price
        replay = replay_symbol_transactions([row])
        assert replay.projections[0].gross_amount == price
        assert replay.summary['cost_basis'] == price
        assert context.prec == 28


def test_high_precision_withdrawal_sign_conversion_and_edit_are_exact(ledger, app):
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('100'))
    amount = D('0.123456789012345678901234567890123456789')
    ledger.svc.portfolio_service.withdraw_funds(ledger.pid, amount)
    row = PortfolioEvent.query.filter_by(event_type='Withdrawal').one()
    identifier = row.id
    db.session.refresh(row)
    assert row.amount_delta == amount.copy_negate()
    client = app.test_client()
    authenticate_client(client, ledger.uid)
    result = client.post(f'/portfolios/events/edit/{identifier}', data={
        'edit_cash_event_amount': str(amount), 'edit_cash_event_notes': 'exact sign',
        'date': '2024-01-01',
    }, headers={'X-Requested-With': 'XMLHttpRequest'})
    assert result.get_json()['success']
    db.session.expire_all()
    assert db.session.get(PortfolioEvent, identifier).amount_delta == amount.copy_negate()


def _assert_schema(conn):
    for table, fields in FIELDS.items():
        info = {r[1]: r for r in conn.exec_driver_sql(f'PRAGMA table_info("{table}")')}
        assert all(info[field][2] == 'TEXT' and info[field][3] for field in fields)
        assert not {'average_cost', 'net_amount'} & set(info)
        fk = conn.exec_driver_sql(f'PRAGMA foreign_key_list("{table}")').one()
        assert (fk[2], fk[3], fk[4], fk[6]) == ('portfolio', 'portfolio_id', 'id', 'CASCADE')
    assert conn.exec_driver_sql('PRAGMA user_version').scalar() == 36
    assert conn.exec_driver_sql('PRAGMA foreign_key_check').all() == []


def test_fresh_schema_has_exact_types_and_no_persisted_derivatives(app):
    with app.app_context(), db.engine.connect() as conn:
        _assert_schema(conn)
    assert not hasattr(Transaction, 'net_amount')
    assert not hasattr(Transaction, 'average_cost')
    assert not hasattr(Transaction, 'calculate_net_amount')
    assert not hasattr(PC, 'recalculate_all_averages_for_symbol')


@pytest.mark.parametrize('field, value', [('price', '0'), ('price', '-1'),
                                         ('quantity', '0'), ('quantity', '-1'), ('fees', '-1')])
def test_service_owns_trade_sign_validation_after_numeric_checks_removed(ledger, field, value):
    row = _trade(ledger, 'Buy', '10', '1', 1)
    values = dict(price=D('10'), quantity=D('1'), fees=D('0'))
    values[field] = D(value)
    with pytest.raises(ValidationError):
        ledger.svc.transaction_service.add_transaction(ledger.pid, 'Buy', 'BTC', **values)
    with pytest.raises(ValidationError):
        ledger.svc.transaction_service.update_transaction(row.id, **{field: D(value)})
    assert Transaction.query.count() == 1


@pytest.mark.parametrize('value', ['0', '-1'])
def test_service_owns_income_sign_validation(ledger, value):
    service = ledger.svc.transaction_service
    row = service.add_dividend(ledger.pid, 'BTC', D('1'), datetime(2024, 1, 1))
    with pytest.raises(ValidationError):
        service.add_dividend(ledger.pid, 'BTC', D(value), datetime(2024, 1, 1))
    with pytest.raises(ValidationError):
        service.update_dividend(row.id, amount=D(value))


def test_mutations_write_raw_row_only_never_historical_projections(ledger):
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('1000'))
    _trade(ledger, 'Buy', '1', '1', 1)
    statements = []

    def capture(conn, cursor, statement, parameters, context, many):
        if statement.lstrip().split()[0].upper() in ('INSERT', 'UPDATE', 'DELETE'):
            statements.append(statement)

    sa.event.listen(db.engine, 'before_cursor_execute', capture)
    try:
        row = _trade(ledger, 'Buy', '2', '2', 2)
        ledger.svc.transaction_service.update_transaction(row.id, price=D('2.00000000001'))
        ledger.svc.transaction_service.delete_transaction(row.id)
    finally:
        sa.event.remove(db.engine, 'before_cursor_execute', capture)
    assert len([sql for sql in statements if sql.lstrip().startswith('UPDATE')]) == 1
    assert all('average_cost' not in sql and 'net_amount' not in sql for sql in statements)


@pytest.fixture
def legacy35(tmp_path, monkeypatch):
    """Use historical migrations to construct a genuine disposable schema 35."""
    path = tmp_path / 'legacy35.sqlite'
    _create_version_33_no_action_database(path)
    with monkeypatch.context() as patch:
        patch.setattr(migrations, 'TARGET_SCHEMA_VERSION', 35)
        patch.setattr(migrations, '_migrate_exact_decimal_storage', lambda *args: None)
        old_app = create_app(_config_for(path))
        with old_app.app_context():
            db.session.remove()
            db.engine.dispose()
    with sqlite3.connect(path) as conn:
        conn.executescript('''
            INSERT INTO portfolio VALUES (52,41,'BTC','2024-01-01','2024-01-01');
            INSERT INTO "transaction" VALUES
              (71,52,'Buy','BTC',185000,0.003,0,999,999,'2024-01-01','BTC buy'),
              (72,52,'Sell','BTC',186000,0.003,0,888,888,'2024-01-03','BTC sell'),
              (73,51,'Buy','REP',1,1,0,999,999,'2024-01-01','repeating one'),
              (74,51,'Buy','REP',2,2,0,999,999,'2024-01-02','repeating two'),
              (75,51,'Sell','REP',3,1,0,888,888,'2024-01-03','partial sale'),
              (76,51,'Buy','PREC',1234567890.123456789,0.12345678901,0.00000000006,
               999,999,'2024-01-04','legacy lossy inputs');
            INSERT INTO portfolio_event VALUES
              (81,52,'Deposit',555,'2024-01-02','BTC funding'),
              (82,52,'Withdrawal',-558,'2024-01-04','BTC withdraw'),
              (83,52,'Deposit',3,'2024-01-05','BTC final'),
              (84,51,'Deposit',0.006,'2024-01-05','legacy subcent');
            INSERT INTO dividend VALUES (91,51,'REP',0.00000000006,'2024-01-06',
                                        'legacy subscale income','2024-01-06');
            CREATE INDEX custom_trade_date ON "transaction" (portfolio_id,date,id);
        ''')
    return path


def _observed_records(conn, legacy):
    result = {}
    for table, fields in FIELDS.items():
        columns = {field: (sa.Numeric(15, 2) if table == 'portfolio_event' else sa.Numeric(20, 10))
                   if legacy else ExactDecimalText() for field in fields}
        columns['date'] = sa.DateTime()
        # Exclude only the deliberately removed derivatives from reconciliation.
        names = [r[1] for r in conn.exec_driver_sql(f'PRAGMA table_info("{table}")')
                 if r[1] not in ('net_amount', 'average_cost')]
        query = sa.text('SELECT ' + ','.join(f'"{name}"' for name in names) +
                        f' FROM "{table}" ORDER BY id').columns(**columns)
        result[table] = [dict(row._mapping) for row in conn.execute(query)]
    return result


def _snapshots(records):
    portfolios = []
    for pid, name in ((51, 'Preserved Portfolio'), (52, 'BTC')):
        trades = [SimpleNamespace(**row) for row in records['transaction'] if row['portfolio_id'] == pid]
        income = {}
        for row in records['dividend']:
            if row['portfolio_id'] == pid:
                income[row['symbol']] = income.get(row['symbol'], D('0')) + row['amount']
        assets = {symbol: build_asset_snapshot(symbol, [t for t in trades if t.symbol == symbol],
                                              income.get(symbol, D('0')))
                  for symbol in dict.fromkeys([t.symbol for t in trades] + list(income))}
        funds = [row for row in records['portfolio_event'] if row['portfolio_id'] == pid]
        portfolios.append(build_portfolio_snapshot(
            portfolio_id=pid, name=name, assets=assets, cash_transactions=order_transactions(trades),
            funding_inflows=sum((r['amount_delta'] for r in funds if r['event_type'] in ('Initial', 'Deposit')), D('0')),
            net_contributions=sum((r['amount_delta'] for r in funds), D('0')),
            income=sum(income.values(), D('0')), income_by_symbol=income,
        ))
    return build_global_snapshot(portfolios)


def test_upgrade_reconciles_every_raw_fact_projection_and_snapshot(legacy35):
    engine = sa.create_engine(f'sqlite:///{legacy35.as_posix()}')
    with engine.connect() as conn:
        before = _observed_records(conn, legacy=True)
        schema_before = conn.exec_driver_sql('PRAGMA table_info("transaction")').all()
        assert {'average_cost', 'net_amount'} <= {r[1] for r in schema_before}
        indexes = conn.exec_driver_sql("SELECT name,sql FROM sqlite_master WHERE type='index' ORDER BY name").all()
        parents = conn.exec_driver_sql('SELECT * FROM portfolio ORDER BY id').all()
    engine.dispose()
    expected = _snapshots(before)
    # Preserve old ORM-decoded values, not original input digits or SQL CAST text.
    assert before['portfolio_event'][-1]['amount_delta'] == D('0.01')
    assert before['dividend'][-1]['amount'] == D('0.0000000001')
    assert before['transaction'][-1]['price'] == D('1234567890.1234567165')
    upgraded = create_app(_config_for(legacy35))
    with upgraded.app_context(), db.engine.connect() as conn:
        _assert_schema(conn)
        after = _observed_records(conn, legacy=False)
        assert after == before
        assert _snapshots(after) == expected
        assert PC.get_financial_snapshot(41) == expected
        assert conn.exec_driver_sql("SELECT name,sql FROM sqlite_master WHERE type='index' ORDER BY name").all() == indexes
        assert conn.exec_driver_sql('SELECT * FROM portfolio ORDER BY id').all() == parents
        for table, fields in FIELDS.items():
            for field in fields:
                assert conn.exec_driver_sql(f'SELECT DISTINCT typeof("{field}") FROM "{table}"').all() == [('text',)]
        btc = expected.portfolios[1]
        assert (btc.cash_balance, btc.net_contributions, btc.transactions['total_quantity_held'],
                btc.transactions['cost_basis'], btc.transactions['realized_pnl'], btc.metrics['book_value']) == tuple(map(D, ('3','0','0','0','3','3')))
        sale = btc.asset('BTC').transaction_projections[72]
        assert (sale.net_sale_proceeds, sale.released_cost_basis, sale.realized_trading_pnl) == (D('558'), D('555'), D('3'))
        # Reopen/idempotence and SQL-level referential integrity, not ORM cascade.
        assert conn.exec_driver_sql('PRAGMA foreign_keys').scalar() == 1
        with pytest.raises(sa.exc.IntegrityError):
            conn.exec_driver_sql("INSERT INTO portfolio_event (portfolio_id,event_type,amount_delta) VALUES (999,'Deposit','1')")
        conn.rollback()
        conn.exec_driver_sql('DELETE FROM portfolio WHERE id=52')
        assert conn.exec_driver_sql('SELECT count(*) FROM "transaction" WHERE portfolio_id=52').scalar() == 0
        assert conn.exec_driver_sql('SELECT count(*) FROM portfolio_event WHERE portfolio_id=52').scalar() == 0
        conn.rollback()
        db.session.remove()
        db.engine.dispose()
    reopened = create_app(_config_for(legacy35))
    with reopened.app_context():
        assert PC.get_financial_snapshot(41) == expected


def test_failed_upgrade_rolls_back_all_three_tables_and_version(legacy35):
    engine = sa.create_engine(f'sqlite:///{legacy35.as_posix()}')
    with engine.connect() as conn:
        before = _observed_records(conn, True)
        schema = conn.exec_driver_sql('SELECT type,name,sql FROM sqlite_master ORDER BY name').all()
        conn.commit()

        def fail_second_rebuild(conn, cursor, statement, parameters, context, many):
            if statement.startswith('ALTER TABLE "_exact36_dividend"'):
                raise RuntimeError('injected rebuild failure')

        sa.event.listen(conn, 'before_cursor_execute', fail_second_rebuild)
        try:
            with pytest.raises(RuntimeError, match='injected'):
                migrations._migrate_exact_decimal_storage(conn, sa)
        finally:
            sa.event.remove(conn, 'before_cursor_execute', fail_second_rebuild)
        assert conn.exec_driver_sql('PRAGMA user_version').scalar() == 35
        assert _observed_records(conn, True) == before
        assert conn.exec_driver_sql('SELECT type,name,sql FROM sqlite_master ORDER BY name').all() == schema
        migrations._migrate_exact_decimal_storage(conn, sa)
        _assert_schema(conn)
    engine.dispose()


def test_derived_column_custom_dependency_stops_upgrade_without_loss(legacy35):
    with sqlite3.connect(legacy35) as conn:
        conn.execute('CREATE INDEX custom_derived ON "transaction" (average_cost)')
    with pytest.raises(RuntimeError, match='custom_derived'):
        create_app(_config_for(legacy35))
    with sqlite3.connect(legacy35) as conn:
        assert conn.execute('PRAGMA user_version').fetchone() == (35,)
        assert conn.execute('SELECT average_cost,net_amount FROM "transaction" WHERE id=72').fetchone() == (888,888)


def test_upgrade_preserves_autoincrement_high_water_and_trigger(legacy35):
    with sqlite3.connect(legacy35) as conn:
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='transaction'").fetchone()[0]
        sql = sql.replace('"transaction"', 'sequence_fixture', 1)
        sql = sql.replace('PRIMARY KEY,', 'PRIMARY KEY AUTOINCREMENT,', 1)
        conn.execute(sql)
        conn.execute('INSERT INTO sequence_fixture SELECT * FROM "transaction"')
        conn.execute('DROP TABLE "transaction"')
        conn.execute('ALTER TABLE sequence_fixture RENAME TO "transaction"')
        conn.execute('''INSERT INTO "transaction"
            (id,portfolio_id,transaction_type,symbol,price,quantity,fees,net_amount,average_cost)
            VALUES (999,51,'Buy','SEQ',1,1,0,1,1)''')
        conn.execute('DELETE FROM "transaction" WHERE id=999')
        conn.execute('CREATE TABLE notes_audit (transaction_id INTEGER, notes TEXT)')
        conn.execute('''CREATE TRIGGER notes_changed AFTER UPDATE OF notes ON "transaction"
            BEGIN INSERT INTO notes_audit VALUES (NEW.id, NEW.notes); END''')
    upgraded = create_app(_config_for(legacy35))
    with upgraded.app_context():
        row = Transaction(portfolio_id=51, transaction_type='Buy', symbol='SEQ',
                          price=D('1'), quantity=D('1'), fees=D('0'))
        db.session.add(row)
        db.session.commit()
        assert row.id == 1000
        row.notes = 'preserved trigger'
        db.session.commit()
        assert db.session.execute(sa.text('SELECT * FROM notes_audit')).all() == [(1000, 'preserved trigger')]
        assert db.session.execute(sa.text('PRAGMA foreign_key_check')).all() == []
