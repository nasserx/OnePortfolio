"""Request intent, stale writes and rollback on disposable database fixtures."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal as D
from threading import Barrier

import pytest
from flask import g
from sqlalchemy import event

from portfolio_app import db
from portfolio_app.calculators.portfolio_calculator import PortfolioCalculator as PC
from portfolio_app.models import Transaction, PortfolioEvent, Dividend, PortfolioTransfer, User, MutationReceipt
from portfolio_app.services.factory import Services
from portfolio_app.services.mutation import current_revision, mutation_transaction
from portfolio_app.utils.mutation_requests import issue_mutation_token
from tests._auth import authenticate_client
from tests.test_financial_baseline import ledger
from tests.test_portfolio_transfers import pair, day, buy, transfer


HEADERS = {'X-Requested-With': 'XMLHttpRequest'}


def token(app, uid):
    with app.test_request_context():
        g.pop('_mutation_revisions', None)
        return issue_mutation_token(uid)


def client_for(app, uid):
    # The fixture deliberately holds an app context; clear Flask-Login's
    # per-context cache when switching clients inside that same test context.
    g.pop('_login_user', None)
    g.pop('_services', None)
    client = app.test_client()
    client.auto_mutation_tokens = False
    authenticate_client(client, uid)
    return client


def post(client, path, values, intent):
    return client.post(path, data={**values, 'mutation_token': intent}, headers=HEADERS)


def create_case(p, kind):
    if kind in ('Buy', 'Sell'):
        if kind == 'Sell':
            buy(p, p.a, '100', 1)
        return '/transactions/add', dict(portfolio_id=p.a, transaction_type=kind,
            symbol='BTC', price='100', quantity='1', fees='0', date='2024-01-02'), Transaction
    if kind in ('Deposit', 'Withdrawal'):
        action = 'deposit' if kind == 'Deposit' else 'withdraw'
        return f'/portfolios/{action}/{p.a}', {'amount_delta': '100', f'{action}_date': '2024-01-02'}, PortfolioEvent
    if kind == 'Dividend':
        return '/transactions/dividends/add', dict(portfolio_id=p.a, div_symbol='BTC',
            amount='100', date='2024-01-02'), Dividend
    return '/portfolios/transfers/add', dict(source_portfolio_id=p.a,
        destination_portfolio_id=p.b, amount='100', date='2024-01-02'), PortfolioTransfer


@pytest.mark.parametrize('kind', ['Buy', 'Sell', 'Deposit', 'Withdrawal', 'Dividend', 'Transfer'])
def test_retry_has_exactly_one_effect_and_replays_original_response(pair, app, kind):
    path, values, model = create_case(pair, kind)
    client = client_for(app, pair.uid)
    intent = token(app, pair.uid)
    count = model.query.count()
    first = post(client, path, values, intent)
    assert first.status_code == 200, first.json
    snapshot = PC.get_financial_snapshot(pair.uid)
    second = post(client, path, values, intent)
    assert second.status_code == 200
    assert second.json == first.json
    assert model.query.count() == count + 1
    assert PC.get_financial_snapshot(pair.uid) == snapshot


def test_two_intentionally_distinct_identical_buys_are_allowed(pair, app):
    path, values, model = create_case(pair, 'Buy')
    client = client_for(app, pair.uid)
    for _ in range(2):
        assert post(client, path, values, token(app, pair.uid)).status_code == 200
    assert model.query.count() == 2
    assert PC.get_portfolio_snapshot(pair.a, user_id=pair.uid).cash_balance == D('800')


def edit_case(p, kind):
    if kind == 'transaction':
        row = buy(p, p.a, '100', 1)
        return f'/transactions/edit/{row.id}', {'edit_price': '200', 'edit_notes': 'changed'}, row
    if kind == 'funding':
        row = PortfolioEvent.query.filter_by(portfolio_id=p.a).one()
        return f'/portfolios/events/edit/{row.id}', {'edit_cash_event_amount': '2000'}, row
    if kind == 'dividend':
        row = p.svc.transaction_service.add_dividend(p.a, 'BTC', D('10'), day(1))
        return f'/transactions/dividends/edit/{row.id}', {'edit_amount': '20', 'edit_date': '2024-01-01'}, row
    row = transfer(p)
    return f'/portfolios/transfers/edit/{row.id}', dict(source_portfolio_id=p.a,
        destination_portfolio_id=p.b, amount='200', date='2024-01-02'), row


@pytest.mark.parametrize('kind', ['transaction', 'funding', 'dividend', 'transfer'])
def test_edit_retries_converge_and_stale_edits_fail(pair, app, kind):
    path, values, row = edit_case(pair, kind)
    client = client_for(app, pair.uid)
    first_token, stale_token = token(app, pair.uid), token(app, pair.uid)
    first = post(client, path, values, first_token)
    assert first.status_code == 200, first.json
    expected = PC.get_financial_snapshot(pair.uid)
    assert post(client, path, values, first_token).json == first.json
    assert PC.get_financial_snapshot(pair.uid) == expected
    assert post(client, path, values, stale_token).status_code == 409
    assert PC.get_financial_snapshot(pair.uid) == expected
    # A newly opened form may intentionally submit the same final values.
    assert post(client, path, values, token(app, pair.uid)).status_code == 200
    assert PC.get_financial_snapshot(pair.uid) == expected


@pytest.mark.parametrize('kind', ['transaction', 'funding', 'dividend', 'transfer'])
def test_stale_deletion_rejected_and_successful_delete_replay_is_safe(pair, app, kind):
    path, values, row = edit_case(pair, kind)
    client = client_for(app, pair.uid)
    stale = token(app, pair.uid)
    assert post(client, path, values, token(app, pair.uid)).status_code == 200
    delete_path = path.replace('/edit/', '/delete/')
    assert post(client, delete_path, {}, stale).status_code == 409
    assert db.session.get(type(row), row.id) is not None
    current = token(app, pair.uid)
    response = post(client, delete_path, {}, current)
    assert response.status_code == 200, response.json
    assert post(client, delete_path, {}, current).json == response.json
    assert db.session.get(type(row), row.id) is None


def test_token_cannot_be_reused_for_changed_payload_or_another_user(pair, app):
    path, values, _ = create_case(pair, 'Deposit')
    client = client_for(app, pair.uid)
    intent = token(app, pair.uid)
    assert post(client, path, values, intent).status_code == 200
    assert post(client, path, {**values, 'amount_delta': '200'}, intent).status_code == 409
    other = User(username='other', email='other@mutation.test', is_verified=True)
    db.session.add(other)
    db.session.commit()
    assert post(client_for(app, other.id), path, values, intent).status_code == 409


def test_missing_and_tampered_intents_are_rejected(pair, app):
    path, values, _ = create_case(pair, 'Buy')
    client = client_for(app, pair.uid)
    before = PC.get_financial_snapshot(pair.uid)
    assert client.post(path, data=values, headers=HEADERS).status_code == 409
    assert post(client, path, values, token(app, pair.uid) + 'tampered').status_code == 409
    assert PC.get_financial_snapshot(pair.uid) == before


def test_failed_validation_does_not_consume_submission(pair, app):
    path, values, _ = create_case(pair, 'Buy')
    values['price'] = '1100'
    client = client_for(app, pair.uid)
    intent = token(app, pair.uid)
    assert post(client, path, values, intent).status_code == 400
    pair.svc.portfolio_service.deposit_funds(pair.a, D('100'), date=day(1))
    assert post(client, path, values, intent).status_code == 200
    assert post(client, path, values, intent).status_code == 200
    assert Transaction.query.count() == 1


@pytest.mark.parametrize('kind', ['Buy', 'Sell', 'Deposit', 'Withdrawal', 'Dividend', 'Transfer'])
def test_exception_after_sql_write_rolls_back_financial_state_and_receipt(pair, app, kind):
    path, values, model = create_case(pair, kind)
    client = client_for(app, pair.uid)
    intent = token(app, pair.uid)
    before = PC.get_financial_snapshot(pair.uid)
    count, receipts = model.query.count(), MutationReceipt.query.count()
    def fail(connection, cursor, statement, parameters, context, many):
        if statement.startswith('INSERT INTO mutation_receipt'):
            raise RuntimeError('injected after financial writes')
    event.listen(db.engine, 'after_cursor_execute', fail)
    try:
        assert post(client, path, values, intent).status_code == 409
    finally:
        event.remove(db.engine, 'after_cursor_execute', fail)
    assert model.query.count() == count
    assert MutationReceipt.query.count() == receipts
    assert PC.get_financial_snapshot(pair.uid) == before
    # Rollback leaves the same intention retryable.
    assert post(client, path, values, intent).status_code == 200


@pytest.mark.parametrize('kind', ['transaction', 'funding', 'dividend', 'transfer'])
@pytest.mark.parametrize('operation', ['edit', 'delete'])
def test_failure_after_edit_or_delete_sql_restores_raw_records_and_snapshots(pair, app, kind, operation):
    path, values, row = edit_case(pair, kind)
    if operation == 'delete':
        path, values = path.replace('/edit/', '/delete/'), {}
    before = PC.get_financial_snapshot(pair.uid)
    raw = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    def fail(connection, cursor, statement, parameters, context, many):
        if statement.startswith('INSERT INTO mutation_receipt'):
            raise RuntimeError('injected before owner commit')
    client = client_for(app, pair.uid)
    intent = token(app, pair.uid)
    event.listen(db.engine, 'after_cursor_execute', fail)
    try:
        assert post(client, path, values, intent).status_code == 409
    finally:
        event.remove(db.engine, 'after_cursor_execute', fail)
    restored = db.session.get(type(row), raw['id'])
    assert {name: getattr(restored, name) for name in raw} == raw
    assert PC.get_financial_snapshot(pair.uid) == before


@pytest.mark.parametrize('kind', ['portfolio', 'symbol', 'account'])
def test_multi_record_removal_rolls_back_after_intermediate_delete(pair, monkeypatch, kind):
    p = pair
    buy(p, p.a, '100', 1)
    p.svc.transaction_service.add_dividend(p.a, 'BTC', D('10'), day(1))
    p.svc.transaction_service.add_symbol(p.a, 'BTC')
    if kind == 'account':
        transfer(p)
        auth = p.svc.auth_service
        monkeypatch.setattr(auth, '_deletion_code_is_live', lambda user: True)
        monkeypatch.setattr('portfolio_app.services.auth_service.verify_otp', lambda *a, **k: True)
    before = PC.get_financial_snapshot(p.uid)
    def fail(connection, cursor, statement, parameters, context, many):
        if statement.startswith('DELETE FROM'):
            raise RuntimeError('injected after first delete')
    event.listen(db.engine, 'after_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='injected'):
            if kind == 'portfolio':
                p.svc.portfolio_service.delete_portfolio(p.a)
            elif kind == 'symbol':
                p.svc.transaction_service.delete_symbol(p.a, 'BTC')
            else:
                p.svc.auth_service.confirm_account_deletion(db.session.get(User, p.uid), '123456')
    finally:
        event.remove(db.engine, 'after_cursor_execute', fail)
    assert PC.get_financial_snapshot(p.uid) == before


def test_nested_services_cannot_commit_partial_outer_mutation(pair):
    before = PC.get_financial_snapshot(pair.uid)
    with pytest.raises(RuntimeError, match='injected'):
        with mutation_transaction():
            pair.svc.portfolio_service.deposit_funds(pair.a, D('10'), date=day(1))
            pair.svc.transfer_service.create(pair.a, pair.b, D('100'), day(2))
            raise RuntimeError('injected outer failure')
    assert PC.get_financial_snapshot(pair.uid) == before
    with pytest.raises(RuntimeError, match='Only the financial mutation owner'):
        with mutation_transaction():
            pair.svc.portfolio_service.deposit_funds(pair.a, D('10'), date=day(1))
            pair.svc.portfolio_repo.commit()
    assert PC.get_financial_snapshot(pair.uid) == before


def test_composed_success_advances_revision_once(pair):
    before = current_revision(pair.uid)
    count = MutationReceipt.query.count()
    with mutation_transaction():
        pair.svc.portfolio_service.deposit_funds(pair.a, D('10'), date=day(1))
        pair.svc.transfer_service.create(pair.a, pair.b, D('100'), day(2))
    assert current_revision(pair.uid) > before
    assert MutationReceipt.query.count() == count + 1


@pytest.mark.parametrize('operation', ['rollback', 'commit'])
def test_caught_helper_transaction_errors_cannot_resume_unprotected_writes(pair, operation):
    before = PC.get_financial_snapshot(pair.uid)
    with mutation_transaction():
        pair.svc.portfolio_service.deposit_funds(pair.a, D('10'), date=day(1))
        if operation == 'rollback':
            db.session.rollback()
        else:
            with pytest.raises(RuntimeError, match='Only the financial mutation owner'):
                db.session.commit()
        with pytest.raises(RuntimeError, match='already failed'):
            pair.svc.portfolio_service.withdraw_funds(pair.a, D('100'), date=day(1))
    assert PC.get_financial_snapshot(pair.uid) == before


def test_write_between_page_read_and_template_cannot_bless_stale_fields(pair, app, monkeypatch, request):
    import re
    import portfolio_app.routes.transactions as routes
    row = buy(pair, pair.a, '100', 1)
    tid = row.id
    # Reporting now holds a real read snapshot through rendering. WAL permits
    # this deliberately synchronous interleaved commit; rollback-journal mode
    # correctly waits until the read finishes (covered separately).
    with db.engine.connect() as connection:
        original_mode = connection.exec_driver_sql('PRAGMA journal_mode').scalar()
        connection.exec_driver_sql('PRAGMA journal_mode=WAL').scalar()
    def restore_mode():
        db.session.remove()
        db.engine.dispose()
        with db.engine.connect() as connection:
            assert original_mode in ('delete', 'wal')
            connection.exec_driver_sql(f'PRAGMA journal_mode={original_mode}').scalar()
    request.addfinalizer(restore_mode)
    original = routes._get_transactions_page_context
    def read_then_concurrent_write(*args, **kwargs):
        context = original(*args, **kwargs)
        # A separate connection commits after the page's reads but before its
        # template asks for hidden tokens.
        with app.app_context():
            Services(user_id=pair.uid).transaction_service.update_transaction(tid, notes='newer')
        return context
    monkeypatch.setattr(routes, '_get_transactions_page_context', read_then_concurrent_write)
    client = client_for(app, pair.uid)
    html = client.get('/transactions/').get_data(as_text=True)
    intent = re.search(r'name="mutation_token" value="([^"]+)"', html).group(1)
    response = post(client, f'/transactions/edit/{tid}', {'edit_notes': 'stale'}, intent)
    assert response.status_code == 409
    db.session.expire_all()
    assert db.session.get(Transaction, tid).notes == 'newer'


def test_handled_response_error_after_service_success_still_rolls_back(pair, app, monkeypatch):
    import portfolio_app.routes.portfolios as routes
    original = routes.flash
    def fail_success(message, category):
        if category == 'success':
            raise ValueError('injected response failure')
        return original(message, category)
    monkeypatch.setattr(routes, 'flash', fail_success)
    before = PC.get_financial_snapshot(pair.uid)
    client = client_for(app, pair.uid)
    result = client.post(f'/portfolios/deposit/{pair.a}', data={
        'amount_delta': '100', 'deposit_date': '2024-01-01', 'mutation_token': token(app, pair.uid),
    })
    assert result.status_code == 302
    assert PC.get_financial_snapshot(pair.uid) == before


def test_scoped_portfolio_creation_cannot_assign_another_owner(pair):
    with pytest.raises(ValueError):
        pair.svc.portfolio_service.create_portfolio('forged', user_id=99999)


def race(app, uid, operations):
    barrier = Barrier(len(operations))
    def run(operation):
        with app.app_context():
            service = Services(user_id=uid)
            barrier.wait(timeout=10)
            try:
                operation(service)
                return 'accepted'
            except Exception as exc:
                from portfolio_app.services.transaction_service import ValidationError
                assert isinstance(exc, (ValueError, ValidationError)), repr(exc)
                return 'rejected'
    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        results = list(pool.map(run, operations))
    db.session.expire_all()
    return sorted(results)


@pytest.mark.parametrize('kinds', [('buy', 'buy'), ('buy', 'withdraw'), ('buy', 'transfer'),
                                  ('withdraw', 'transfer'), ('transfer', 'transfer')])
def test_separate_connections_cannot_double_spend_source(pair, app, kinds):
    p = pair
    operations = {
        'buy': lambda s: s.transaction_service.add_transaction(p.a, 'Buy', 'BTC', D('800'), D('1'), D('0'), date=day(2)),
        'withdraw': lambda s: s.portfolio_service.withdraw_funds(p.a, D('800'), date=day(2)),
        'transfer': lambda s: s.transfer_service.create(p.a, p.b, D('800'), day(2)),
    }
    assert race(app, p.uid, [operations[k] for k in kinds]) == ['accepted', 'rejected']
    assert p.svc.portfolio_service.cash_account.ledger(p.a).closing_cash == D('200')


def test_separate_connections_cannot_oversell(pair, app):
    p = pair
    buy(p, p.a, '100', 1)
    sell = lambda s: s.transaction_service.add_transaction(p.a, 'Sell', 'BTC', D('110'), D('1'), D('0'), date=day(2))
    assert race(app, p.uid, [sell, sell]) == ['accepted', 'rejected']
    assert Transaction.query.filter_by(transaction_type='Sell').count() == 1


def test_sell_and_historical_quantity_edit_use_same_writer_reservation(pair, app):
    p = pair
    row = buy(p, p.a, '100', 1)
    tid = row.id
    sell = lambda s: s.transaction_service.add_transaction(p.a, 'Sell', 'BTC', D('110'), D('1'), D('0'), date=day(2))
    reduce = lambda s: s.transaction_service.update_transaction(tid, quantity=D('0.5'))
    assert race(app, p.uid, [sell, reduce]) == ['accepted', 'rejected']


@pytest.mark.parametrize('second', ['edit', 'delete'])
def test_edit_races_reject_stale_revision(pair, app, second):
    row = buy(pair, pair.a, '100', 1)
    tid, revision = row.id, current_revision(pair.uid)
    edit = lambda s: s.transaction_service.update_transaction(tid, notes='first', expected_revision=revision)
    other = (lambda s: s.transaction_service.update_transaction(tid, notes='second', expected_revision=revision)) if second == 'edit' else (
        lambda s: s.transaction_service.delete_transaction(tid, expected_revision=revision))
    assert race(app, pair.uid, [edit, other]) == ['accepted', 'rejected']


def test_concurrent_same_http_intent_executes_once(pair, app):
    path, values, _ = create_case(pair, 'Transfer')
    intent = token(app, pair.uid)
    clients = [client_for(app, pair.uid), client_for(app, pair.uid)]
    barrier = Barrier(2)
    def send(client):
        barrier.wait(timeout=10)
        return post(client, path, values, intent)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(send, clients))
    assert [r.status_code for r in results] == [200, 200]
    assert results[0].json == results[1].json
    db.session.expire_all()
    assert PortfolioTransfer.query.count() == 1


@pytest.mark.parametrize('kind', ['transaction', 'funding', 'dividend', 'transfer', 'portfolio'])
@pytest.mark.parametrize('operation', ['edit', 'delete'])
def test_foreign_and_missing_targets_are_indistinguishable(pair, app, kind, operation):
    if kind == 'portfolio':
        path, values = f'/portfolios/rename/{pair.a}', {'name': 'forged'}
        if operation == 'delete':
            path, values = f'/portfolios/delete/{pair.a}', {}
    else:
        path, values, _ = edit_case(pair, kind)
        if operation == 'delete':
            path, values = path.replace('/edit/', '/delete/'), {}
    before = PC.get_financial_snapshot(pair.uid)
    other = User(username='attacker', email='attacker@mutation.test', is_verified=True)
    db.session.add(other)
    db.session.commit()
    client = client_for(app, other.id)
    foreign = post(client, path, values, token(app, other.id))
    missing = post(client, path.rsplit('/', 1)[0] + '/999999', values, token(app, other.id))
    assert foreign.status_code == missing.status_code == 400
    assert foreign.json == missing.json
    assert PC.get_financial_snapshot(pair.uid) == before


def test_protected_financial_routes_never_accept_get(app):
    for rule in app.url_map.iter_rules():
        if getattr(app.view_functions[rule.endpoint], '_protected_submission', False):
            assert 'GET' not in rule.methods


def test_csrf_remains_required_even_with_valid_mutation_token(pair, app, monkeypatch):
    client = client_for(app, pair.uid)
    path, values, _ = create_case(pair, 'Buy')
    intent = token(app, pair.uid)
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', True)
    response = post(client, path, values, intent)
    assert response.status_code == 400
    assert Transaction.query.count() == 0


def test_rendered_financial_forms_include_signed_intents(pair, app):
    import re
    client = client_for(app, pair.uid)
    for path in ('/transactions/', '/portfolios/'):
        html = client.get(path).get_data(as_text=True)
        forms = re.findall(r'<form\b[^>]*method="POST"[^>]*>(.*?)</form>', html, re.S)
        assert forms
        for form in forms:
            assert 'type="hidden" name="mutation_token"' in form
