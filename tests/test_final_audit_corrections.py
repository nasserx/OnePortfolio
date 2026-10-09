"""Independent final-audit reproductions on disposable databases only."""

from decimal import Decimal as D, localcontext
import json
import re

import pytest
from flask_login import login_user

from portfolio_app import db
from portfolio_app.models import User, Transaction, Dividend, Symbol
from portfolio_app.services.factory import Services
from portfolio_app.calculators.portfolio_calculator import PortfolioCalculator as PC
from portfolio_app.calculators.allocation_charts import build_allocation_chart_data
from tests.test_financial_baseline import ledger
from tests.test_portfolio_transfers import pair, day
from tests.test_auth import mail_log, _begin, _verify
from tests._auth import authenticate_client
from portfolio_app.repositories.read_snapshot import read_snapshot
from portfolio_app.services.mutation import mutation_transaction
from portfolio_app.routes.transactions import _get_transactions_page_context
from portfolio_app.routes.portfolios import _get_portfolios_page_context


@pytest.fixture(autouse=True)
def isolated_decimal_flags(app):
    # Existing display formatters may flag a failed quantize before their large
    # value fallback. Extreme rendering diagnostics must not leak those flags
    # into another test's ambient-context contract.
    with app.app_context(), db.engine.connect() as connection:
        original_mode = connection.exec_driver_sql('PRAGMA journal_mode').scalar()
    try:
        with localcontext():
            yield
    finally:
        # Journal modes are persistent SQLite settings, even for a shared test
        # fixture. Restore them so other suites keep their original coverage.
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
            with db.engine.connect() as connection:
                assert original_mode in ('delete', 'wal')
                connection.exec_driver_sql(f'PRAGMA journal_mode={original_mode}').scalar()


def test_deleted_account_session_never_acquires_reused_user_id(app, mail_log, monkeypatch):
    owner, survivor, replacement = (app.test_client() for _ in range(3))
    _verify(owner, _begin(owner, mail_log, 'old@example.com'))
    _verify(survivor, _begin(survivor, mail_log, 'old@example.com'))
    with survivor.session_transaction() as state:
        old_session = dict(state)
    with app.app_context():
        old_id = User.query.filter_by(email='old@example.com').one().id
    owner.post('/settings/delete/request')
    owner.post('/settings/delete/verify', data={'code': mail_log[-1][1]})
    _verify(replacement, _begin(replacement, mail_log, 'new@example.com'))
    with app.app_context():
        new_id = User.query.filter_by(email='new@example.com').one().id
        assert new_id == old_id  # Exercise SQLite rowid reuse, not just logout.
        portfolio = Services(user_id=new_id).portfolio_service.create_portfolio('Private replacement', user_id=new_id)
        pid = portfolio.id
    assert replacement.get('/api/portfolio-summary').status_code == 200
    for path in ('/api/portfolio-summary', '/transactions/', '/portfolios/',
                 f'/api/holdings?portfolio_id={pid}&symbol=BTC'):
        with survivor.session_transaction() as state:
            state.update(old_session)
        assert survivor.get(path).status_code == 302
    # Even fresh valid CSRF and an otherwise valid signed intention for the
    # recycled numeric ID cannot turn the old identity into authorization.
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', True)
    survivor.auto_mutation_tokens = False
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', survivor.get('/login').text)[1]
    page = replacement.get('/portfolios/').text
    intent = re.search(r'name="mutation_token" value="([^"]+)"', page)[1]
    with survivor.session_transaction() as state:
        state.update({key: value for key, value in old_session.items() if key != 'csrf_token'})
    values = dict(amount_delta='1', deposit_date='2024-01-02', csrf_token=csrf, mutation_token=intent)
    assert survivor.post(f'/portfolios/deposit/{pid}', data=values).status_code == 302
    with app.app_context():
        assert PC.get_portfolio_snapshot(pid, user_id=new_id).cash_balance == D('0')
    values['csrf_token'] = re.search(r'name="csrf_token" value="([^"]+)"', page)[1]
    assert replacement.post(f'/portfolios/deposit/{pid}', data=values,
                            headers={'X-Requested-With': 'XMLHttpRequest'}).status_code == 200
    with app.app_context():
        assert PC.get_portfolio_snapshot(pid, user_id=new_id).cash_balance == D('1')


def test_global_read_is_one_committed_state_during_transfer(pair, app, monkeypatch):
    p = pair
    with db.engine.connect() as connection:
        connection.exec_driver_sql('PRAGMA journal_mode=WAL')
    before = PC.get_financial_snapshot(p.uid)
    original = PC.get_portfolio_snapshot
    changed = False

    def interleave(pid, **kwargs):
        nonlocal changed
        result = original(pid, **kwargs)
        if not changed:
            changed = True
            with app.app_context():  # A genuinely separate Session/connection.
                Services(user_id=p.uid).transfer_service.create(p.a, p.b, D('100'), date=day(2))
                db.session.remove()
        return result

    monkeypatch.setattr(PC, 'get_portfolio_snapshot', interleave)
    result = PC.get_financial_snapshot(p.uid)
    assert result == before
    assert result.totals['net_internal_transfers'] == D('0')


def test_dividend_only_symbol_is_visible_in_assets(ledger, app):
    l = ledger
    l.svc.transaction_service.add_dividend(l.pid, 'DIVONLY', D('25'), day(2), notes='Dividend-only history marker')
    client = app.test_client()
    authenticate_client(client, l.uid)
    response = client.get('/transactions/')
    assert response.status_code == 200
    assert 'Dividend-only history marker' in response.get_data(as_text=True)


def test_chart_overflow_never_emits_nonfinite_payload():
    chart = build_allocation_chart_data([
        {'name': 'Large', 'book_value': D('1e309'), 'net_contributions': D('1e309')},
    ])
    json.dumps(chart, allow_nan=False)


@pytest.mark.parametrize('kind', ['Buy', 'Sell', 'Deposit', 'Withdrawal', 'Dividend'])
def test_portfolio_read_during_separate_connection_mutation(pair, app, monkeypatch, kind):
    p = pair
    p.svc.transaction_service.add_transaction(p.a, 'Buy', 'BTC', D('100'), D('2'), D('0'), date=day(1))
    with db.engine.connect() as connection:
        connection.exec_driver_sql('PRAGMA journal_mode=WAL')
    before = PC.get_portfolio_snapshot(p.a, user_id=p.uid)
    original = PC._dividend_income_by_symbol
    changed = False

    def interleave(*args, **kwargs):
        nonlocal changed
        result = original(*args, **kwargs)
        if not changed:
            changed = True
            with app.app_context():
                svc = Services(user_id=p.uid)
                if kind in ('Buy', 'Sell'):
                    svc.transaction_service.add_transaction(p.a, kind, 'BTC', D('110'), D('1'), D('0'), date=day(2))
                elif kind == 'Dividend':
                    svc.transaction_service.add_dividend(p.a, 'BTC', D('10'), day(2))
                elif kind == 'Deposit':
                    svc.portfolio_service.deposit_funds(p.a, D('10'), date=day(2))
                else:
                    svc.portfolio_service.withdraw_funds(p.a, D('10'), date=day(2))
                db.session.remove()
        return result

    monkeypatch.setattr(PC, '_dividend_income_by_symbol', interleave)
    assert PC.get_portfolio_snapshot(p.a, user_id=p.uid) == before
    after = PC.get_portfolio_snapshot(p.a, user_id=p.uid)
    assert after != before
    assert after.cash_balance == p.svc.portfolio_service.cash_account.ledger(p.a).closing_cash


@pytest.mark.parametrize('page', ['assets', 'portfolios'])
def test_page_history_and_metrics_share_database_snapshot(pair, app, monkeypatch, page):
    p = pair
    p.svc.transaction_service.add_transaction(p.a, 'Buy', 'BTC', D('100'), D('2'), D('0'), date=day(1))
    with db.engine.connect() as connection:
        connection.exec_driver_sql('PRAGMA journal_mode=WAL')
    original = PC.get_portfolio_snapshot
    changed = False

    def interleave(*args, **kwargs):
        nonlocal changed
        result = original(*args, **kwargs)
        if not changed:
            changed = True
            with app.app_context():
                svc = Services(user_id=p.uid)
                svc.transaction_service.add_transaction(p.a, 'Sell', 'BTC', D('110'), D('1'), D('0'), date=day(2))
                svc.transfer_service.create(p.a, p.b, D('100'), date=day(2))
                db.session.remove()
        return result

    monkeypatch.setattr(PC, 'get_portfolio_snapshot', interleave)
    with app.test_request_context():
        login_user(db.session.get(User, p.uid))
        if page == 'assets':
            holding = _get_transactions_page_context()['holdings'][0]
            assert len(holding['transactions']) == 1
            assert set(holding['transaction_projections']) == {row.id for row in holding['transactions']}
            assert holding['summary']['total_quantity_held'] == D('2')
        else:
            rows = _get_portfolios_page_context()['portfolio_details']
            assert sum(row['cash_balance'] for row in rows) == D('800')
            assert not any('Transfer' in event.event_type for row in rows for event in row['events'])


def test_read_boundary_is_real_deferred_read_only_and_releases_on_error(pair):
    session = db.session()
    connection = session.connection()
    statements = []
    from sqlalchemy import event
    def record(conn, cursor, statement, *args):
        statements.append(statement)
    event.listen(db.engine, 'before_cursor_execute', record)
    try:
        with pytest.raises(ValueError, match='read failed'):
            with read_snapshot():
                assert connection.connection.driver_connection.in_transaction
                assert connection.exec_driver_sql('PRAGMA query_only').scalar() == 1
                with read_snapshot():
                    assert PC.get_portfolio_snapshot(pair.a, user_id=pair.uid).cash_balance == D('1000')
                raise ValueError('read failed')
        assert not connection.connection.driver_connection.in_transaction
        assert connection.exec_driver_sql('PRAGMA query_only').scalar() == 0
    finally:
        event.remove(db.engine, 'before_cursor_execute', record)
    assert 'BEGIN' in statements and 'BEGIN IMMEDIATE' not in statements
    pair.svc.portfolio_service.deposit_funds(pair.a, D('1'), date=day(1))


def test_read_does_not_own_existing_mutation_or_discard_pending_work(pair):
    p = pair
    with pytest.raises(ValueError, match='outer rollback'):
        with mutation_transaction():
            p.svc.portfolio_service.deposit_funds(p.a, D('10'), date=day(1))
            assert PC.get_portfolio_snapshot(p.a, user_id=p.uid).cash_balance == D('1010')
            assert db.session.connection().connection.driver_connection.in_transaction
            raise ValueError('outer rollback')
    assert PC.get_portfolio_snapshot(p.a, user_id=p.uid).cash_balance == D('1000')
    row = User(username='Pending', email='pending@example.com', is_verified=True)
    db.session.add(row)
    with pytest.raises(RuntimeError, match='clean session'):
        PC.get_financial_snapshot(p.uid)
    assert row in db.session.new
    db.session.rollback()


def test_dividend_only_history_crud_and_isolation(ledger, app):
    l = ledger
    first = l.svc.transaction_service.add_dividend(l.pid, 'ONLY', D('25'), day(1), notes='first dividend')
    second = l.svc.transaction_service.add_dividend(l.pid, 'ONLY', D('5'), day(2), notes='second dividend')
    ids = first.id, second.id
    client = app.test_client()
    authenticate_client(client, l.uid)
    with app.test_request_context():
        login_user(db.session.get(User, l.uid))
        context = _get_transactions_page_context()
        assert len(context['holdings']) == 1
        holding = context['holdings'][0]
        assert holding['transactions'] == []
        assert holding['summary']['total_quantity_held'] == D('0')
    assert Transaction.query.count() == Symbol.query.count() == 0
    assert 'first dividend' in client.get('/transactions/').text
    response = client.post(f'/transactions/dividends/edit/{ids[0]}', data={
        'edit_amount': '30', 'edit_date': '2024-01-01', 'edit_notes': 'updated dividend'},
        headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.status_code == 200 and response.json['success']
    assert 'updated dividend' in client.get('/transactions/').text
    snap = PC.get_portfolio_snapshot(l.pid, user_id=l.uid)
    assert snap.cash_balance == snap.dividend_income == snap.metrics['book_value'] == D('35')
    assert snap.metrics['realized_trading_return'] is None
    other = User(username='Other', email='other@example.com', is_verified=True)
    db.session.add(other)
    db.session.commit()
    stranger = app.test_client()
    authenticate_client(stranger, other.id)
    # Separate request context avoids the ledger fixture's Flask-Login cache.
    with app.app_context():
        assert 'updated dividend' not in stranger.get('/transactions/').text
        rejected = stranger.post(f'/transactions/dividends/delete/{ids[0]}',
            headers={'X-Requested-With': 'XMLHttpRequest'})
        assert not rejected.json['success']
    assert Dividend.query.count() == 2
    for identifier in ids:
        assert client.post(f'/transactions/dividends/delete/{identifier}',
            headers={'X-Requested-With': 'XMLHttpRequest'}).json['success']
    assert PC.get_portfolio_snapshot(l.pid, user_id=l.uid).cash_balance == D('0')


@pytest.mark.parametrize('values', [('1e309',), ('1e-400',), ('1e308', '1e308'),
                                   ('1e308',), ('0.1', '0.2'), ('100', '200')])
def test_chart_presentation_range_and_exact_totals(values):
    rows = [dict(name=str(i), book_value=D(value), net_contributions=D(value)) for i, value in enumerate(values)]
    datasets = build_allocation_chart_data(rows)
    json.dumps(datasets, allow_nan=False)
    unsupported = values in [('1e309',), ('1e-400',), ('1e308', '1e308')]
    for dataset in datasets.values():
        assert dataset.get('unavailable', False) == unsupported
        if unsupported:
            assert dataset['total'] is None and dataset['values'] == []
        else:
            from portfolio_app.utils.financial_arithmetic import exact_sum
            assert dataset['total'] == float(exact_sum(D(value) for value in values))
            assert dataset['categories'] == [row['name'] for row in sorted(rows, key=lambda row: row['book_value'], reverse=True)]


@pytest.mark.parametrize('value', ['1e309', '1e-400', '1e308'])
def test_large_and_small_persisted_values_render_overview(ledger, app, value):
    l = ledger
    l.svc.portfolio_service.deposit_funds(l.pid, D(value), date=day(1))
    snap = PC.get_portfolio_snapshot(l.pid, user_id=l.uid)
    assert snap.cash_balance == snap.metrics['book_value'] == D(value)
    client = app.test_client()
    authenticate_client(client, l.uid)
    response = client.get('/')
    assert response.status_code == 200
    assert 'Infinity' not in response.text and 'NaN' not in response.text


def test_overview_handles_float_representable_portfolios_with_overflowing_total(ledger, app):
    l = ledger
    second = l.svc.portfolio_service.create_portfolio('Second large', user_id=l.uid).id
    for pid in (l.pid, second):
        l.svc.portfolio_service.deposit_funds(pid, D('1e308'), date=day(1))
    snapshot = PC.get_financial_snapshot(l.uid)
    assert snapshot.totals['cash_balance'] == snapshot.total_book_value == D('2e308')
    datasets = build_allocation_chart_data(snapshot.as_portfolio_summary()[0])
    assert all(dataset['unavailable'] for dataset in datasets.values())
    json.dumps(datasets, allow_nan=False)
    client = app.test_client()
    authenticate_client(client, l.uid)
    assert client.get('/').status_code == 200
    assert D(client.get('/api/portfolio-summary').json['book_value']) == D('2e308')


@pytest.mark.parametrize('kind', ['Buy', 'Sell', 'Dividend'])
def test_asset_snapshot_alone_joins_one_committed_state(pair, app, monkeypatch, kind):
    p = pair
    p.svc.transaction_service.add_transaction(p.a, 'Buy', 'BTC', D('100'), D('2'), D('0'), date=day(1))
    with db.engine.connect() as connection:
        connection.exec_driver_sql('PRAGMA journal_mode=WAL')
    before = PC.get_asset_snapshot(p.a, 'BTC', user_id=p.uid)
    original = PC._dividend_income_by_symbol
    changed = False

    def interleave(*args, **kwargs):
        nonlocal changed
        result = original(*args, **kwargs)
        if not changed:
            changed = True
            with app.app_context():
                svc = Services(user_id=p.uid)
                if kind == 'Dividend':
                    svc.transaction_service.add_dividend(p.a, 'BTC', D('10'), day(2))
                else:
                    svc.transaction_service.add_transaction(p.a, kind, 'BTC', D('110'), D('1'), D('0'), date=day(2))
                db.session.remove()
        return result

    monkeypatch.setattr(PC, '_dividend_income_by_symbol', interleave)
    assert PC.get_asset_snapshot(p.a, 'BTC', user_id=p.uid) == before
    assert PC.get_asset_snapshot(p.a, 'BTC', user_id=p.uid) != before


def test_rollback_journal_read_allows_writer_reservation_but_not_mixed_commit(pair, app):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from sqlalchemy import event
    p = pair
    db.session.remove()
    db.engine.dispose()
    with db.engine.connect() as connection:
        assert connection.exec_driver_sql('PRAGMA journal_mode=DELETE').scalar() == 'delete'
    written = Event()
    def after_sql(conn, cursor, statement, *args):
        if statement.startswith('INSERT INTO portfolio_event'):
            written.set()
    def deposit():
        with app.app_context():
            Services(user_id=p.uid).portfolio_service.deposit_funds(p.a, D('10'), date=day(2))
            db.session.remove()
    event.listen(db.engine, 'after_cursor_execute', after_sql)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            with read_snapshot():
                before = PC.get_portfolio_snapshot(p.a, user_id=p.uid)
                future = pool.submit(deposit)
                assert written.wait(timeout=5)  # Reader did not take BEGIN IMMEDIATE.
                assert not future.done()  # SQLite's shared read lock delays commit.
                assert PC.get_portfolio_snapshot(p.a, user_id=p.uid) == before
            future.result(timeout=10)
        assert PC.get_portfolio_snapshot(p.a, user_id=p.uid).cash_balance == D('1010')
    finally:
        event.remove(db.engine, 'after_cursor_execute', after_sql)


def test_existing_explicit_read_transaction_is_not_closed(pair):
    connection = db.session.connection()
    connection.exec_driver_sql('BEGIN')
    try:
        with read_snapshot():
            assert PC.get_portfolio_snapshot(pair.a, user_id=pair.uid).cash_balance == D('1000')
        assert connection.connection.driver_connection.in_transaction
    finally:
        db.session.rollback()


def test_read_setup_failure_restores_connection_writeability(pair):
    from sqlalchemy import event
    def fail(conn, cursor, statement, *args):
        if statement == 'BEGIN':
            raise RuntimeError('injected read setup failure')
    event.listen(db.engine, 'after_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='injected read setup'):
            PC.get_financial_snapshot(pair.uid)
    finally:
        event.remove(db.engine, 'after_cursor_execute', fail)
    assert db.session.connection().exec_driver_sql('PRAGMA query_only').scalar() == 0
    pair.svc.portfolio_service.deposit_funds(pair.a, D('1'), date=day(1))
    assert PC.get_portfolio_snapshot(pair.a, user_id=pair.uid).cash_balance == D('1001')


@pytest.mark.parametrize('existing_transaction', [False, True])
def test_read_snapshot_refreshes_previously_cached_clean_rows(pair, app, existing_transaction):
    # An ORM Session identity map is not a database snapshot either.
    row = pair.svc.portfolio_repo.get_by_id(pair.a)
    assert row.name == 'Baseline'
    with app.app_context():
        Services(user_id=pair.uid).portfolio_service.rename_portfolio(pair.a, 'Fresh name')
        db.session.remove()
    if existing_transaction:
        db.session.connection().exec_driver_sql('BEGIN')
    try:
        assert PC.get_portfolio_snapshot(pair.a, user_id=pair.uid).name == 'Fresh name'
    finally:
        if existing_transaction:
            db.session.rollback()


def test_account_replacement_between_authentication_and_writer_reservation(app, mail_log, monkeypatch):
    from contextlib import contextmanager
    from portfolio_app.utils import mutation_requests
    from portfolio_app.utils.mutation_requests import issue_mutation_token
    browser = app.test_client()
    browser.auto_mutation_tokens = False
    _verify(browser, _begin(browser, mail_log, 'before-race@example.com'))
    with app.app_context():
        old = User.query.filter_by(email='before-race@example.com').one()
        uid = old.id
        pid = Services(user_id=uid).portfolio_service.create_portfolio('Old', user_id=uid).id
        with app.test_request_context():
            intent = issue_mutation_token(uid)
    original = mutation_requests.mutation_transaction
    changed = False

    @contextmanager
    def interleave():
        nonlocal changed
        if not changed:
            changed = True
            with app.app_context():
                auth = Services(user_id=uid).auth_service
                old = db.session.get(User, uid)
                code = auth.request_account_deletion(old)
                assert auth.confirm_account_deletion(old, code)[0]
                issue = auth.begin_authentication('after-race@example.com')
                new = auth.verify_challenge(issue.token, issue.code, 'authentication')
                assert new.id == uid
                new_pid = Services(user_id=uid).portfolio_service.create_portfolio('New private', user_id=uid).id
                assert new_pid == pid
                db.session.remove()
        with original() as state:
            yield state

    monkeypatch.setattr(mutation_requests, 'mutation_transaction', interleave)
    response = browser.post(f'/portfolios/deposit/{pid}', data={
        'amount_delta': '1', 'deposit_date': '2024-01-01', 'mutation_token': intent},
        headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.status_code == 409
    with app.app_context():
        assert PC.get_portfolio_snapshot(pid, user_id=uid).cash_balance == D('0')


def test_account_replacement_between_authentication_and_report_snapshot(app, mail_log):
    from sqlalchemy import event
    browser = app.test_client()
    _verify(browser, _begin(browser, mail_log, 'old-reader@example.com'))
    with app.app_context():
        uid = User.query.filter_by(email='old-reader@example.com').one().id
        engine = db.engine
    changed = False
    def interleave(conn, cursor, statement, *args):
        nonlocal changed
        if statement == 'BEGIN' and not changed:
            changed = True
            with app.app_context():
                auth = Services(user_id=uid).auth_service
                old = db.session.get(User, uid)
                assert auth.confirm_account_deletion(old, auth.request_account_deletion(old))[0]
                issue = auth.begin_authentication('new-reader@example.com')
                new = auth.verify_challenge(issue.token, issue.code, 'authentication')
                assert new.id == uid
                Services(user_id=uid).portfolio_service.create_portfolio('Replacement secret', user_id=uid)
                db.session.remove()
    event.listen(engine, 'before_cursor_execute', interleave)
    try:
        response = browser.get('/api/portfolio-summary')
    finally:
        event.remove(engine, 'before_cursor_execute', interleave)
    assert changed
    assert response.status_code == 302
    assert 'Replacement secret' not in response.text
