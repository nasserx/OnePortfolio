"""Atomic internal flows preserve external funding and canonical financial truth."""

from datetime import datetime
from decimal import Decimal as D, localcontext
from types import SimpleNamespace

import pytest
from sqlalchemy import event, text

from portfolio_app import db
from portfolio_app.models import PortfolioTransfer, PortfolioEvent, Transaction
from portfolio_app.models.user import User
from portfolio_app.services.factory import Services
from portfolio_app.calculators.portfolio_calculator import PortfolioCalculator as PC
from portfolio_app.routes.portfolios import _get_portfolios_page_context
from tests.test_financial_baseline import ledger
from tests._financial import assert_accounting_invariants
from tests._auth import authenticate_client


def day(n):
    return datetime(2024, 1, n)


@pytest.fixture
def pair(ledger):
    svc = ledger.svc
    b = svc.portfolio_service.create_portfolio('Destination', user_id=ledger.uid)
    c = svc.portfolio_service.create_portfolio('Third', user_id=ledger.uid)
    svc.portfolio_service.deposit_funds(ledger.pid, D('1000'), date=day(1))
    return SimpleNamespace(svc=svc, uid=ledger.uid, a=ledger.pid, b=b.id, c=c.id)


def transfer(p, amount='100', n=2, source=None, destination=None):
    return p.svc.transfer_service.create(
        p.a if source is None else source, p.b if destination is None else destination,
        D(amount), date=day(n), notes='linked',
    )


def buy(p, pid, amount, n=3):
    return p.svc.transaction_service.add_transaction(pid, 'Buy', 'BTC', D(amount), D('1'), D('0'), date=day(n))


def snapshot(p, pid):
    return PC.get_portfolio_snapshot(pid, user_id=p.uid)


def balances(p):
    return tuple(snapshot(p, pid).cash_balance for pid in (p.a, p.b, p.c))


def test_transfer_reconciles_every_scope_without_external_funding_or_earnings(pair):
    p = pair
    buy(p, p.a, '100', 1)
    p.svc.transaction_service.add_transaction(p.a, 'Sell', 'BTC', D('110'), D('1'), D('0'), date=day(2))
    p.svc.transaction_service.add_dividend(p.a, 'BTC', D('20'), day(2))
    before = PC.get_financial_snapshot(p.uid)
    count = PortfolioEvent.query.count()
    row = transfer(p)
    after = PC.get_financial_snapshot(p.uid)
    assert PortfolioTransfer.query.count() == 1
    assert PortfolioEvent.query.count() == count
    assert balances(p) == (D('930'), D('100'), D('0'))
    for key in ('cash_balance', 'book_value', 'net_contributions', 'gross_deposits',
                'realized_trading_pnl', 'released_cost_basis', 'realized_trading_return', 'dividend_income'):
        assert after.totals[key] == before.totals[key]
    assert after.totals['net_internal_transfers'] == D('0')
    assert after.totals['transfer_in'] == after.totals['transfer_out'] == D('100')
    for pid, net, funding in [(p.a, '-100', '1000'), (p.b, '100', '0')]:
        snap = snapshot(p, pid)
        assert snap.net_internal_transfers == D(net)
        assert snap.net_contributions == snap.gross_deposits == D(funding)
        assert snap.withdrawals == D('0')
        assert_accounting_invariants(snap.transactions, cash=snap.cash_balance,
            net_funding=snap.net_contributions, net_internal_transfers=snap.net_internal_transfers,
            dividend_income=snap.dividend_income, book_value=snap.metrics['book_value'])
        cash = p.svc.portfolio_service.cash_account.ledger(pid)
        assert cash.closing_cash == snap.cash_balance == PC.get_cash_balance_for_portfolio(pid, user_id=p.uid)
        side = cash.days[-1]
        assert (side.transfer_out if pid == p.a else side.transfer_in) == row.amount
    assert after.totals['book_value'] == D('1000') + D('10') + D('20')


@pytest.mark.parametrize('amount', ['0', '-1', 'NaN', 'Infinity', '-Infinity'])
def test_invalid_amount_rejected_without_side_effects(pair, amount):
    with pytest.raises(ValueError):
        transfer(pair, amount)
    assert balances(pair) == (D('1000'), D('0'), D('0'))
    assert PortfolioTransfer.query.count() == 0


@pytest.mark.parametrize('which', ['same', 'missing_source', 'missing_destination', 'foreign_source', 'foreign_destination'])
def test_invalid_endpoints_rejected_without_existence_leak(pair, which):
    other = User(username='outsider', email='outsider@example.com', is_verified=True)
    db.session.add(other)
    db.session.commit()
    other_svc = Services(user_id=other.id)
    portfolio = other_svc.portfolio_service.create_portfolio('Private', user_id=other.id)
    source, destination = pair.a, pair.b
    if which == 'same': destination = source
    elif which == 'missing_source': source = 999999
    elif which == 'missing_destination': destination = 999999
    elif which == 'foreign_source': source = portfolio.id
    else: destination = portfolio.id
    with pytest.raises(ValueError) as error:
        transfer(pair, source=source, destination=destination)
    assert str(error.value) == ('Choose two different portfolios.' if which == 'same' else 'Select portfolios belonging to your account.')
    assert PortfolioTransfer.query.count() == 0


@pytest.mark.parametrize('precision', [3, 28, 80])
def test_exact_high_precision_round_trip_and_ambient_context_independence(pair, precision):
    amount = D('100.12345678901234567890123456789012345')
    with localcontext() as ambient:
        ambient.prec = precision
        row = transfer(pair, str(amount))
        identifier = row.id
        db.session.expunge_all()
        loaded = db.session.get(PortfolioTransfer, identifier)
        assert loaded.amount == amount
        assert snapshot(pair, pair.b).cash_balance == amount
        raw = db.session.execute(text('SELECT amount, typeof(amount) FROM portfolio_transfer')).one()
        assert raw == (str(amount), 'text')
        assert loaded.to_dict()['amount'] == str(amount)


@pytest.mark.parametrize('amount,n', [('1001', 2), ('1', 1)])
def test_insufficient_or_later_cash_is_rejected(pair, amount, n):
    if n == 1:
        event_row = PortfolioEvent.query.one()
        pair.svc.portfolio_service.update_portfolio_event(event_row.id, D('1000'), date=day(2))
    with pytest.raises(ValueError, match='Insufficient cash'):
        transfer(pair, amount, n)
    assert PortfolioTransfer.query.count() == 0


def test_historical_transfer_cannot_consume_cash_needed_later(pair):
    buy(pair, pair.a, '900', 3)
    pair.svc.portfolio_service.deposit_funds(pair.a, D('1000'), date=day(4))
    with pytest.raises(ValueError):
        transfer(pair, '101', 2)
    assert balances(pair)[0] == D('1100')


@pytest.mark.parametrize('inflow', ['deposit', 'sale', 'dividend', 'transfer'])
def test_same_day_inflows_can_fund_transfer(pair, inflow):
    if inflow == 'deposit':
        source = pair.a
    elif inflow == 'sale':
        buy(pair, pair.a, '1000', 1)
        pair.svc.transaction_service.add_transaction(pair.a, 'Sell', 'BTC', D('1000'), D('1'), D('0'), date=day(2))
        source = pair.a
    elif inflow == 'dividend':
        pair.svc.transaction_service.add_dividend(pair.c, 'BTC', D('100'), day(2))
        source = pair.c
    else:
        transfer(pair, destination=pair.c)
        source = pair.c
    transfer(pair, source=source)
    assert snapshot(pair, pair.b).cash_balance == D('100')


def legacy_buy(p, pid):
    row = Transaction(portfolio_id=pid, transaction_type='Buy', symbol='BTC',
                      price=D('100'), quantity=D('1'), fees=D('0'), date=day(1))
    db.session.add(row)
    db.session.commit()


def test_legacy_transfer_in_improves_deficit_and_transfer_out_cannot_worsen(pair):
    legacy_buy(pair, pair.b)
    transfer(pair, '25', 1)
    assert pair.svc.portfolio_service.cash_account.ledger(pair.b).minimum_closing_cash == D('-75')
    with pytest.raises(ValueError):
        transfer(pair, '1', 1, source=pair.b, destination=pair.c)
    transfer(pair, '75', 1)
    assert snapshot(pair, pair.b).cash_balance == D('0')


@pytest.mark.parametrize('change', ['amount', 'date', 'source', 'destination', 'delete'])
def test_edit_delete_rejects_invalid_prospective_histories_atomically(pair, change):
    row = transfer(pair)
    identifier = row.id
    buy(pair, pair.b, '100', 3)
    before = balances(pair)
    old = row.to_dict()
    actions = {
        'amount': lambda: pair.svc.transfer_service.update(identifier, amount=D('1001')),
        'date': lambda: pair.svc.transfer_service.update(identifier, date=day(4)),
        'source': lambda: pair.svc.transfer_service.update(identifier, source_portfolio_id=pair.c),
        'destination': lambda: pair.svc.transfer_service.update(identifier, destination_portfolio_id=pair.c),
        'delete': lambda: pair.svc.transfer_service.delete(identifier),
    }
    with pytest.raises(ValueError): actions[change]()
    assert pair.svc.transfer_repo.get_by_id(identifier).to_dict() == old
    assert balances(pair) == before


@pytest.mark.parametrize('change', ['amount', 'date', 'source', 'destination', 'notes', 'delete'])
def test_valid_edits_and_deletion_update_all_sides(pair, change):
    row = transfer(pair)
    svc = pair.svc.transfer_service
    if change == 'amount':
        svc.update(row.id, amount=D('50'))
        assert balances(pair) == (D('950'), D('50'), D('0'))
    elif change == 'date':
        svc.update(row.id, date=day(3))
        assert pair.svc.portfolio_service.cash_account.ledger(pair.b).days[0].date == day(3).date()
    elif change == 'source':
        pair.svc.portfolio_service.deposit_funds(pair.c, D('100'), date=day(1))
        svc.update(row.id, source_portfolio_id=pair.c)
        assert balances(pair) == (D('1000'), D('100'), D('0'))
    elif change == 'destination':
        svc.update(row.id, destination_portfolio_id=pair.c)
        assert balances(pair) == (D('900'), D('0'), D('100'))
    elif change == 'notes':
        svc.update(row.id, notes='edited')
        assert row.notes == 'edited'
        assert balances(pair) == (D('900'), D('100'), D('0'))
    else:
        svc.delete(row.id)
        assert PortfolioTransfer.query.count() == 0
        assert balances(pair) == (D('1000'), D('0'), D('0'))


@pytest.mark.parametrize('operation', ['create', 'edit', 'delete'])
def test_database_failure_rolls_back_both_sides(pair, operation):
    row = transfer(pair) if operation != 'create' else None
    before = balances(pair)
    count = PortfolioTransfer.query.count()
    verb = {'create': 'INSERT', 'edit': 'UPDATE', 'delete': 'DELETE'}[operation]
    def fail(conn, cursor, statement, parameters, context, many):
        if statement.startswith(verb) and 'portfolio_transfer' in statement:
            raise RuntimeError('injected persistence failure')
    event.listen(db.engine, 'after_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='injected'):
            if operation == 'create': transfer(pair)
            elif operation == 'edit': pair.svc.transfer_service.update(row.id, amount=D('50'))
            else: pair.svc.transfer_service.delete(row.id)
    finally:
        event.remove(db.engine, 'after_cursor_execute', fail)
    assert balances(pair) == before
    assert PortfolioTransfer.query.count() == count


@pytest.mark.parametrize('side', ['a', 'b'])
def test_portfolio_deletion_requires_resolving_linked_transfers(pair, side):
    row = transfer(pair)
    pid = getattr(pair, side)
    with pytest.raises(ValueError, match='Remove linked transfers'):
        pair.svc.portfolio_service.delete_portfolio(pid)
    pair.svc.transfer_service.delete(row.id)
    pair.svc.portfolio_service.delete_portfolio(pid)
    assert pair.svc.portfolio_repo.get_by_id(pid) is None


def test_concurrent_transfer_and_buy_cannot_spend_same_source_cash(pair, app):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    barrier = Barrier(2)
    def spend(kind):
        with app.app_context():
            svc = Services(user_id=pair.uid)
            barrier.wait(timeout=10)
            try:
                if kind == 'transfer': svc.transfer_service.create(pair.a, pair.b, D('800'), date=day(2))
                else: svc.transaction_service.add_transaction(pair.a, 'Buy', 'BTC', D('800'), D('1'), D('0'), date=day(2))
                return True
            except ValueError: return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(spend, ['transfer', 'buy'])) == [False, True]
    db.session.expire_all()
    assert snapshot(pair, pair.a).cash_balance == D('200')


def test_history_counts_labels_api_and_withdrawal_max(pair, app):
    from flask import g
    row = transfer(pair, '100.009')
    g._services = pair.svc
    items = {r['portfolio'].id: r for r in _get_portfolios_page_context()['portfolio_details']}
    assert len(items[pair.a]['events']) == 2
    assert len(items[pair.b]['events']) == 1
    outgoing, incoming = items[pair.a]['events'][-1], items[pair.b]['events'][0]
    assert (outgoing.event_type, incoming.event_type) == ('Transfer Out', 'Transfer In')
    assert outgoing.transfer['id'] == incoming.transfer['id'] == row.id
    assert outgoing.amount_delta == D('-100.009') and incoming.amount_delta == D('100.009')
    client = app.test_client()
    authenticate_client(client, pair.uid)
    html = client.get('/portfolios/').get_data(as_text=True)
    assert 'Transfer Out' in html and 'Transfer In' in html
    assert 'data-transfer-action="edit"' in html
    assert 'From Portfolio' in html and 'To Portfolio' in html
    payload = client.get('/api/portfolio-summary').json
    source = next(r for r in payload['portfolio_summary'] if r['id'] == pair.a)
    assert source['net_internal_transfers'] == '-100.009'
    assert source['net_contributions'] == '1000'
    assert client.get(f'/portfolios/withdrawal-max/{pair.a}?date=2024-01-02').json['amount'] == '899.99'
    assert client.get(f'/portfolios/withdrawal-max/{pair.b}?date=2024-01-02').json['amount'] == '100.00'


def test_transfer_ajax_crud_uses_exact_strings_and_foreign_id_is_hidden(pair, app):
    client = app.test_client()
    authenticate_client(client, pair.uid)
    data = dict(source_portfolio_id=pair.a, destination_portfolio_id=pair.b,
                amount='10.1234567890123456789012345', date='2024-01-02', notes='exact')
    headers = {'X-Requested-With': 'XMLHttpRequest'}
    result = client.post('/portfolios/transfers/add', data=data, headers=headers)
    assert result.status_code == 200
    row = result.json['transfer']
    assert row['amount'] == data['amount']
    data['notes'] = 'notes only'
    result = client.post(f'/portfolios/transfers/edit/{row["id"]}', data=data, headers=headers)
    assert result.json['transfer']['amount'] == data['amount']
    assert client.post('/portfolios/transfers/delete/999999', headers=headers).json['errors']['__all__'] == 'Transfer not found.'
    assert client.post(f'/portfolios/transfers/delete/{row["id"]}', headers=headers).json['success']


def test_confirmed_account_removal_resolves_only_that_accounts_transfers(pair, monkeypatch):
    transfer(pair)
    other = User(username='kept', email='kept@example.com', is_verified=True)
    db.session.add(other)
    db.session.commit()
    svc = Services(user_id=other.id)
    a = svc.portfolio_service.create_portfolio('Other A', user_id=other.id)
    b = svc.portfolio_service.create_portfolio('Other B', user_id=other.id)
    svc.portfolio_service.deposit_funds(a.id, D('10'), date=day(1))
    kept = svc.transfer_service.create(a.id, b.id, D('10'), date=day(1))
    kept_id = kept.id
    auth = pair.svc.auth_service
    monkeypatch.setattr(auth, '_deletion_code_is_live', lambda user: True)
    monkeypatch.setattr('portfolio_app.services.auth_service.verify_otp', lambda *args, **kwargs: True)
    user = db.session.get(User, pair.uid)
    assert auth.confirm_account_deletion(user, 'verified-code')[0]
    assert db.session.get(User, pair.uid) is None
    assert PortfolioTransfer.query.count() == 1
    assert db.session.get(PortfolioTransfer, kept_id).amount == D('10')


@pytest.mark.parametrize('operation', ['read', 'edit', 'delete'])
def test_foreign_transfer_cannot_be_read_edited_or_deleted(pair, app, operation):
    row = transfer(pair)
    other = User(username='foreign', email='foreign@example.com', is_verified=True)
    db.session.add(other)
    db.session.commit()
    svc = Services(user_id=other.id)
    if operation == 'read':
        assert svc.transfer_repo.get_by_id(row.id) is None
        assert svc.transfer_repo.get_by_portfolio_ids([pair.a, pair.b]) == []
        assert PC.get_transfer_totals(pair.a, user_id=other.id) == (D('0'), D('0'))
    else:
        with pytest.raises(ValueError, match='Transfer not found'):
            if operation == 'edit': svc.transfer_service.update(row.id, amount=D('1'))
            else: svc.transfer_service.delete(row.id)
    assert balances(pair) == (D('900'), D('100'), D('0'))


@pytest.mark.parametrize('operation', ['delete', 'reduce', 'delay'])
def test_destination_legacy_repair_cannot_be_undone_by_transfer_mutation(pair, operation):
    legacy_buy(pair, pair.b)
    row = transfer(pair, '25', 1)
    with pytest.raises(ValueError):
        if operation == 'delete': pair.svc.transfer_service.delete(row.id)
        elif operation == 'reduce': pair.svc.transfer_service.update(row.id, amount=D('24'))
        else: pair.svc.transfer_service.update(row.id, date=day(2))
    assert snapshot(pair, pair.b).cash_balance == D('-75')


def test_transfer_date_cannot_move_before_source_funding(pair):
    funding = PortfolioEvent.query.one()
    pair.svc.portfolio_service.update_portfolio_event(funding.id, D('1000'), date=day(2))
    row = transfer(pair)
    with pytest.raises(ValueError): pair.svc.transfer_service.update(row.id, date=day(1))
    assert row.date == day(2)


def test_existing_funding_mutations_and_transfer_chains_use_same_ledger(pair):
    row = transfer(pair)
    transfer(pair, source=pair.b, destination=pair.c)
    with pytest.raises(ValueError): pair.svc.transfer_service.delete(row.id)
    funding = PortfolioEvent.query.one()
    with pytest.raises(ValueError): pair.svc.portfolio_service.delete_portfolio_event(funding.id)
    assert balances(pair) == (D('900'), D('0'), D('100'))


def test_python_float_is_not_an_authoritative_transfer_amount(pair):
    with pytest.raises(ValueError):
        pair.svc.transfer_service.create(pair.a, pair.b, 0.1, date=day(2))
    assert PortfolioTransfer.query.count() == 0


def test_withdrawal_max_accounts_for_future_transfer_but_not_future_receipt(pair):
    transfer(pair, '100.009', 3)
    account = pair.svc.portfolio_service.cash_account
    assert account.withdrawal_max(pair.a, day(2)) == '899.99'
    assert account.withdrawal_max(pair.b, day(2)) == '0.00'
    assert account.withdrawal_max(pair.b, day(3)) == '100.00'
