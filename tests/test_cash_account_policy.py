"""Cash-account acceptance policy; all persistence is the isolated test fixture."""

from datetime import datetime, date
from decimal import Decimal as D, localcontext

import pytest

from portfolio_app import db
from portfolio_app.calculators.daily_cash import CashFact, build_daily_cash_ledger
from portfolio_app.calculators.portfolio_calculator import PortfolioCalculator as PC
from portfolio_app.models import Transaction
from portfolio_app.services.cash_account import cash_fact
from tests.test_financial_baseline import ledger
from tests._auth import authenticate_client
from tests._financial import expected_percent


def day(n):
    return datetime(2024, 1, n)


def deposit(l, amount='555', n=1):
    l.svc.portfolio_service.deposit_funds(l.pid, D(amount), date=day(n))
    return l.svc.portfolio_event_repo.get_by_portfolio_id(l.pid)[0]


def trade(l, kind='Buy', price='555', n=1, quantity='1', fees='0', symbol='BTC'):
    return l.svc.transaction_service.add_transaction(
        l.pid, kind, symbol, D(price), D(quantity), D(fees), date=day(n),
    )


def dividend(l, amount='555', n=1):
    return l.svc.transaction_service.add_dividend(l.pid, 'BTC', D(amount), day(n))


def ledger_for(l):
    return l.svc.portfolio_service.cash_account.ledger(l.pid)


def legacy_buy(l):
    """Explicit legacy fixture, not an accepted new service mutation."""
    row = Transaction(portfolio_id=l.pid, symbol='BTC', transaction_type='Buy',
                      price=D('555'), quantity=D('1'), fees=D('0'), date=day(1))
    db.session.add(row)
    db.session.commit()
    return row


@pytest.mark.parametrize('funding_day,buy_day,valid', [(1, 2, True), (1, 1, True), (2, 1, False)])
def test_funding_date_controls_buy_acceptance(ledger, funding_day, buy_day, valid):
    deposit(ledger, n=funding_day)
    if valid:
        trade(ledger, n=buy_day)
        assert ledger_for(ledger).closing_cash == D('0')
    else:
        with pytest.raises(ValueError, match='Insufficient cash for this purchase'):
            trade(ledger, n=buy_day)
        assert Transaction.query.count() == 0


def test_unfunded_buy_is_rejected_without_implicit_funding(ledger):
    with pytest.raises(ValueError, match='Insufficient cash for this purchase'):
        trade(ledger)
    assert Transaction.query.count() == 0
    assert ledger_for(ledger).days == ()


@pytest.mark.parametrize('source', ['sale', 'dividend'])
def test_same_day_inflows_fund_buys_without_intraday_cash_order(ledger, source):
    if source == 'sale':
        deposit(ledger)
        trade(ledger)
        trade(ledger, 'Sell', '555', 2)
    else:
        dividend(ledger, n=2)
    trade(ledger, n=2, symbol='NEW')
    assert ledger_for(ledger).minimum_closing_cash == D('0')
    with pytest.raises(ValueError, match='Insufficient cash'):
        trade(ledger, price='0.01', n=2)


@pytest.mark.parametrize('change', ['increase_buy', 'decrease_deposit', 'delete_deposit',
    'move_deposit', 'move_buy', 'withdraw', 'historical_withdraw'])
def test_prospective_history_rejects_cash_reducing_mutations(ledger, change):
    event = deposit(ledger, '100', 2)
    buy = trade(ledger, price='100', n=3)
    # Final cash remains ample: validating only ending cash would miss the deficit.
    deposit(ledger, '1000', 5)
    ps, ts = ledger.svc.portfolio_service, ledger.svc.transaction_service
    actions = {
        'increase_buy': lambda: ts.update_transaction(buy.id, price=D('101')),
        'decrease_deposit': lambda: ps.update_portfolio_event(event.id, D('99')),
        'delete_deposit': lambda: ps.delete_portfolio_event(event.id),
        'move_deposit': lambda: ps.update_portfolio_event(event.id, D('100'), date=day(4)),
        'move_buy': lambda: ts.update_transaction(buy.id, date=day(1)),
        'withdraw': lambda: ps.withdraw_funds(ledger.pid, D('1001'), date=day(5)),
        'historical_withdraw': lambda: ps.withdraw_funds(ledger.pid, D('1'), date=day(2)),
    }
    with pytest.raises(ValueError):
        actions[change]()
    # Rejected edits never dirty raw facts or leak through subsequent autoflush.
    assert ledger_for(ledger).minimum_closing_cash == D('0')
    assert ledger_for(ledger).closing_cash == D('1000')
    assert buy.price == D('100') and buy.date == day(3)
    assert event.amount_delta == D('100') and event.date == day(2)


@pytest.mark.parametrize('source', ['sell', 'dividend'])
@pytest.mark.parametrize('action', ['reduce', 'delete', 'move'])
def test_spent_inflow_edits_and_deletes_validate_all_later_days(ledger, source, action):
    ts = ledger.svc.transaction_service
    if source == 'sell':
        deposit(ledger, '100')
        trade(ledger, price='100')
        inflow = trade(ledger, 'Sell', '100', 2)
        edit = ts.update_transaction
        remove = ts.delete_transaction
        values = {'price': D('99')}
    else:
        inflow = dividend(ledger, '100', 2)
        edit = ts.update_dividend
        remove = ts.delete_dividend
        values = {'amount': D('99')}
    trade(ledger, price='100', n=3, symbol='NEW')
    deposit(ledger, '1000', 5)
    with pytest.raises(ValueError):
        if action == 'delete':
            remove(inflow.id)
        else:
            edit(inflow.id, **(values if action == 'reduce' else {'date': day(4)}))
    assert ledger_for(ledger).minimum_closing_cash == D('0')


def test_legacy_deficit_readable_and_metadata_edits_allowed(ledger):
    buy = legacy_buy(ledger)
    event = deposit(ledger, '600', 2)
    history = ledger_for(ledger)
    assert history.closing_cash == D('45')
    assert history.minimum_closing_cash == D('-555')
    assert history.first_deficit_date == day(1).date()
    ledger.svc.transaction_service.update_transaction(buy.id, notes='legacy notes')
    ledger.svc.portfolio_service.update_portfolio_event(event.id, D('600'), notes='funding notes')
    assert buy.price == D('555') and buy.notes == 'legacy notes'
    assert event.amount_delta == D('600') and event.notes == 'funding notes'
    assert ledger_for(ledger) == history
    assert PC.get_cash_balance_for_portfolio(ledger.pid, user_id=ledger.uid) == D('45')


def test_progressive_legacy_repairs_then_strict_policy(ledger):
    buy = legacy_buy(ledger)
    with pytest.raises(ValueError):
        ledger.svc.transaction_service.update_transaction(buy.id, price=D('556'))
    for amount, minimum in [('100', '-455'), ('200', '-255'), ('255', '0')]:
        deposit(ledger, amount)
        assert ledger_for(ledger).minimum_closing_cash == D(minimum)
    with pytest.raises(ValueError):
        trade(ledger, price='1')


@pytest.mark.parametrize('action', ['reduce', 'delete'])
def test_legacy_buy_repair_allowed(ledger, action):
    buy = legacy_buy(ledger)
    if action == 'reduce':
        ledger.svc.transaction_service.update_transaction(buy.id, price=D('500'))
        assert ledger_for(ledger).minimum_closing_cash == D('-500')
    else:
        ledger.svc.transaction_service.delete_transaction(buy.id)
        assert ledger_for(ledger).minimum_closing_cash == D('0')


def test_legacy_equal_minimum_mutation_is_allowed(ledger):
    legacy_buy(ledger)
    deposit(ledger, '1000', 2)
    ledger.svc.portfolio_service.withdraw_funds(ledger.pid, D('1'), date=day(2))
    assert ledger_for(ledger).minimum_closing_cash == D('-555')


@pytest.mark.parametrize('precision', [3, 28, 80])
def test_high_precision_daily_cash_and_snapshot_reconcile(ledger, precision):
    with localcontext() as ctx:
        ctx.prec = precision
        deposit(ledger, '1234567890.1234567890123456789012345')
        trade(ledger, price='1234567890.123456789012345678901234', fees='0.0000000000000000000000004')
        dividend(ledger, '0.0000000000000000000000001')
        history = ledger_for(ledger)
        assert history.closing_cash == D('0.0000000000000000000000002')
        assert history.closing_cash == PC.get_portfolio_snapshot(ledger.pid, user_id=ledger.uid).cash_balance


def test_buy_fee_and_sell_fee_cash_effects(ledger):
    deposit(ledger, '100')
    with pytest.raises(ValueError):
        trade(ledger, price='100', fees='1')
    trade(ledger, price='99', fees='1')
    trade(ledger, 'Sell', '110', 2, fees='2')
    assert ledger_for(ledger).days[-1].net_sale_proceeds == D('108')
    assert ledger_for(ledger).closing_cash == D('108')


@pytest.mark.parametrize('n,expected', [(1, '0'), (2, '300'), (3, '300'), (4, '300'), (5, '400'), (6, '400')])
def test_max_uses_minimum_from_date_through_future(ledger, n, expected):
    deposit(ledger, '500', 2)
    trade(ledger, price='200', n=4)
    deposit(ledger, '100', 5)
    account = ledger.svc.portfolio_service.cash_account
    assert D(account.withdrawal_max(ledger.pid, day(n))) == D(expected)
    if D(expected):
        ledger.svc.portfolio_service.withdraw_funds(ledger.pid, D(expected), date=day(n))
        assert ledger_for(ledger).minimum_closing_cash >= D('0')


@pytest.mark.parametrize('amount,expected', [('1.005', '1.00'), ('1.009', '1.00'), ('1.019', '1.01'), ('2.00', '2.00')])
def test_max_floor_is_service_acceptable(ledger, amount, expected):
    deposit(ledger, amount)
    maximum = ledger.svc.portfolio_service.cash_account.withdrawal_max(ledger.pid, day(1))
    assert maximum == expected
    ledger.svc.portfolio_service.withdraw_funds(ledger.pid, D(maximum), date=day(1))
    assert ledger_for(ledger).minimum_closing_cash >= D('0')


def test_empty_and_legacy_negative_max_are_zero(ledger):
    account = ledger.svc.portfolio_service.cash_account
    assert D(account.withdrawal_max(ledger.pid, day(1))) == D('0')
    legacy_buy(ledger)
    assert D(account.withdrawal_max(ledger.pid, day(1))) == D('0')


def test_max_after_an_earlier_legacy_deficit_uses_only_affected_path(ledger):
    legacy_buy(ledger)
    deposit(ledger, '1000', 2)
    account = ledger.svc.portfolio_service.cash_account
    assert D(account.withdrawal_max(ledger.pid, day(1))) == D('0')
    assert D(account.withdrawal_max(ledger.pid, day(2))) == D('445')
    ledger.svc.portfolio_service.withdraw_funds(ledger.pid, D('445'), date=day(2))
    assert ledger_for(ledger).minimum_closing_cash == D('-555')
    assert ledger_for(ledger).closing_cash == D('0')


def test_btc_correctly_funded_full_sequence(ledger):
    deposit(ledger)
    trade(ledger, price='185000', quantity='0.003')
    sale = trade(ledger, 'Sell', '186000', 2, quantity='0.003')
    ledger.svc.portfolio_service.withdraw_funds(ledger.pid, D('558'), date=day(3))
    deposit(ledger, '3', 4)
    snap = PC.get_portfolio_snapshot(ledger.pid, user_id=ledger.uid)
    assert snap.cash_balance == D('3')
    assert snap.net_contributions == D('0')
    assert snap.metrics['book_value'] == D('3')
    assert snap.metrics['realized_trading_pnl'] == D('3')
    assert snap.metrics['realized_trading_return'] == expected_percent('3', '555')
    assert ledger_for(ledger).closing_cash == snap.cash_balance


def test_null_legacy_date_uses_existing_earliest_day_policy(ledger):
    buy = legacy_buy(ledger)
    buy.date = None
    db.session.commit()
    assert ledger_for(ledger).first_deficit_date == date.min
    assert cash_fact(buy).date == date.min


def test_daily_grouping_is_order_independent():
    facts = [CashFact(day(1), 'buy_outflows', D('555')), CashFact(day(1), 'funding_inflows', D('555'))]
    assert build_daily_cash_ledger(facts) == build_daily_cash_ledger(reversed(facts))
    assert build_daily_cash_ledger(facts).minimum_closing_cash == D('0')


def test_max_api_is_exact_date_aware_and_tenant_scoped(ledger, app):
    deposit(ledger, '500.009', 2)
    trade(ledger, price='200', n=4)
    client = app.test_client()
    authenticate_client(client, ledger.uid)
    response = client.get(f'/portfolios/withdrawal-max/{ledger.pid}?date=2024-01-02')
    assert response.json == {'success': True, 'amount': '300.00'}
    assert response.headers['Cache-Control'] == 'no-store'
    assert client.get(f'/portfolios/withdrawal-max/{ledger.pid}?date=invalid').status_code == 400
    from portfolio_app.models.user import User
    user = User(username='other', email='other@example.com', is_verified=True)
    db.session.add(user)
    db.session.commit()
    other = ledger.svc.portfolio_service.create_portfolio('Other', user_id=user.id)
    assert client.get(f'/portfolios/withdrawal-max/{other.id}?date=2024-01-02').status_code == 400


def test_concurrent_buys_cannot_both_spend_the_same_cash(ledger, app):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from portfolio_app.services.factory import Services
    deposit(ledger, '100')
    barrier = Barrier(2)
    def buy():
        with app.app_context():
            service = Services(user_id=ledger.uid).transaction_service
            barrier.wait(timeout=10)
            try:
                service.add_transaction(ledger.pid, 'Buy', 'BTC', D('80'), D('1'), D('0'), date=day(1))
                return 'accepted'
            except ValueError as exc:
                assert str(exc) == 'Insufficient cash for this purchase.'
                return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: buy(), range(2)))
    assert sorted(results) == ['accepted', 'rejected']
    db.session.expire_all()
    assert ledger_for(ledger).closing_cash == D('20')


def test_no_op_edit_releases_sqlite_writer_reservation(ledger):
    deposit(ledger)
    buy = trade(ledger)
    ledger.svc.transaction_service.update_transaction(buy.id)
    assert not db.session.connection().connection.driver_connection.in_transaction


def test_valid_metadata_edits_and_date_defaults_are_deterministic(ledger):
    event = deposit(ledger)
    buy = trade(ledger)
    ledger.svc.portfolio_service.update_portfolio_event(event.id, D('555'), notes='note')
    ledger.svc.transaction_service.update_transaction(buy.id, notes='note')
    assert ledger_for(ledger).minimum_closing_cash == D('0')
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('10'))
    row = ledger.svc.transaction_service.add_transaction(ledger.pid, 'Buy', 'NEW', D('10'), D('1'), D('0'))
    assert row.date is not None
    assert ledger_for(ledger).closing_cash == D('0')


def test_purchase_error_is_returned_to_ajax_form(ledger, app):
    client = app.test_client()
    authenticate_client(client, ledger.uid)
    response = client.post('/transactions/add', data={
        'portfolio_id': ledger.pid, 'transaction_type': 'Buy', 'symbol': 'BTC',
        'price': '555', 'quantity': '1', 'fees': '0', 'date': '2024-01-01',
    }, headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.status_code == 400
    assert response.json['errors']['quantity'] == 'Insufficient cash for this purchase.'
