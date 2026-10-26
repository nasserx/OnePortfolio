"""Bound incoming work without rounding financial facts or derived results."""

from datetime import datetime
from decimal import Decimal as D, localcontext
import sqlite3

import pytest

from portfolio_app import create_app, db
from portfolio_app.migrations import run_startup_schema, TARGET_SCHEMA_VERSION
from portfolio_app.calculators.financial_math import calculate_cumulative_return
from portfolio_app.calculators import PortfolioCalculator
from portfolio_app.forms.portfolio_forms import PortfolioDepositForm
from portfolio_app.forms.transaction_forms import TransactionEditForm
from portfolio_app.forms.validators import parse_decimal_field
from portfolio_app.services.transaction_preview import preview_values, PreviewUnavailable
from portfolio_app.models import PortfolioEvent, Dividend, Transaction, PortfolioTransfer
from portfolio_app.utils.decimal_utils import parse_financial_decimal
from portfolio_app.utils.exact_decimal import canonical_decimal_text, ExactDecimalText
from tests.test_financial_baseline import ledger
from tests._auth import authenticate_client
from tests.test_migrations import _config_for, _create_version_33_no_action_database
from tests.test_dividend_preservation_migration import close_app, dump
from tests.test_migration_legacy_replay import _create_capital_era_database, _attribute_capital_dividend


@pytest.mark.parametrize('value', [
    '1e100000', '1e-100000', '0e-100000', '0e100000',
    '1e64', '1e-65', '9' * 65, '0.' + '0' * 64 + '1',
    '1' * 257, '0' * 257, '1e' + '0' * 255,
    D('1e100000'), D('1e-100000'), D('0e-100000'),
])
def test_rejects_out_of_budget_input_without_expanding(value):
    # Never format the hostile values or pass them to arithmetic in this test.
    with pytest.raises(ValueError, match='Financial number exceeds'):
        parse_financial_decimal(value)


@pytest.mark.parametrize('value', [
    '9' * 64, '1e-64', '9' * 64 + '.' + '9' * 64,
    '  +1,000.000000000000000000000000000001  ', '-0.00',
])
def test_boundary_values_remain_exact_under_small_decimal_context(value):
    with localcontext() as context:
        context.prec = 3
        assert parse_financial_decimal(value) == D(value.replace(',', '').strip())


def test_form_rejects_exponent_expansion_as_a_field_error():
    form = PortfolioDepositForm({'amount_delta': '1e100000', 'deposit_date': '2024-01-01'}, 1)
    assert not form.validate()
    assert 'amount_delta' in form.errors


@pytest.mark.parametrize('operation', ['deposit', 'withdraw', 'buy', 'dividend', 'transfer'])
def test_direct_services_reject_before_ledger_arithmetic(ledger, monkeypatch, operation):
    other = ledger.svc.portfolio_service.create_portfolio('Other')
    for svc in (ledger.svc.portfolio_service, ledger.svc.transaction_service, ledger.svc.transfer_service):
        monkeypatch.setattr(svc.cash_account, 'validate', lambda *a, **kw: pytest.fail('Reached cash arithmetic'))
    calls = {
        'deposit': lambda: ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('1e100000')),
        'withdraw': lambda: ledger.svc.portfolio_service.withdraw_funds(ledger.pid, D('1e100000')),
        'buy': lambda: ledger.svc.transaction_service.add_transaction(ledger.pid, 'Buy', 'BTC', D('1e100000'), D('1'), D('0')),
        'dividend': lambda: ledger.svc.transaction_service.add_dividend(ledger.pid, 'BTC', D('1e100000'), datetime(2024, 1, 1)),
        'transfer': lambda: ledger.svc.transfer_service.create(ledger.pid, other.id, D('1e100000')),
    }
    with pytest.raises(ValueError, match='Financial number exceeds'):
        calls[operation]()
    assert all(model.query.count() == 0 for model in (PortfolioEvent, Dividend, Transaction, PortfolioTransfer))


def test_create_and_edit_http_reject_without_writing(ledger, app):
    row = ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('10'), date=datetime(2024, 1, 1))
    event = PortfolioEvent.query.filter_by(portfolio_id=row.id).one()
    event_id = event.id
    client = app.test_client()
    authenticate_client(client, ledger.uid)
    for path, data, field in [
        (f'/portfolios/deposit/{ledger.pid}', {'amount_delta': '1e100000', 'deposit_date': '2024-01-01'}, 'amount_delta'),
        (f'/portfolios/events/edit/{event_id}', {'edit_cash_event_amount': '1e-100000'}, 'edit_cash_event_amount'),
    ]:
        response = client.post(path, data=data, headers={'X-Requested-With': 'XMLHttpRequest'})
        assert not response.json['success']
        assert field in response.json['errors']
    db.session.expire_all()
    assert PortfolioEvent.query.count() == 1
    assert db.session.get(PortfolioEvent, event_id).amount_delta == D('10')


def test_legacy_storage_and_derived_ratios_are_not_action_inputs():
    # Existing safely bounded historical values may exceed new entry limits.
    value = D('1e309')
    text = canonical_decimal_text(value)
    assert ExactDecimalText().process_result_value(text, None) == value
    assert calculate_cumulative_return(D('1e128'), D('1e-128')) == D('1e258')


def test_storage_rejects_extreme_exponent_before_fixed_point_formatting():
    with pytest.raises(ValueError, match='Financial number exceeds'):
        canonical_decimal_text(D('1e100000'))


def test_oversized_text_is_rejected_before_decimal_construction(monkeypatch):
    import portfolio_app.utils.decimal_utils as decimals
    monkeypatch.setattr(decimals, 'to_decimal', lambda value: pytest.fail('Constructed oversized Decimal'))
    with pytest.raises(ValueError, match='Financial number exceeds'):
        parse_financial_decimal('1' * 257)


def test_storage_rejects_huge_exponent_before_format(monkeypatch):
    import portfolio_app.utils.exact_decimal as storage
    monkeypatch.setattr(storage, 'format', lambda *args: pytest.fail('Expanded huge exponent'), raising=False)
    with pytest.raises(ValueError, match='Financial number exceeds'):
        storage.canonical_decimal_text(D('1e1000000000'))


def test_boundary_trade_keeps_product_below_input_scale_exact(ledger):
    service = ledger.svc
    service.portfolio_service.deposit_funds(ledger.pid, D('1e-64'), date=datetime(2024, 1, 1))
    service.transaction_service.add_transaction(
        ledger.pid, 'Buy', 'BTC', D('1e-64'), D('1e-64'), D('0'), date=datetime(2024, 1, 1),
    )
    snapshot = PortfolioCalculator.get_portfolio_snapshot(ledger.pid, user_id=ledger.uid)
    assert snapshot.transactions['position_cost_basis'] == D('1e-128')
    assert snapshot.cash_balance == D('0.' + '0' * 64 + '9' * 64)


@pytest.mark.parametrize('consumer', ['reader', 'overview'])
def test_schema40_historical_tiny_fixed_point_survives_upgrade(ledger, app, consumer):
    text = '0.' + '0' * 8192 + '1'
    row = PortfolioEvent(portfolio_id=ledger.pid, event_type='Deposit', amount_delta=D('1'))
    db.session.add(row)
    db.session.commit()
    identifier = row.id
    # The old writer stored canonical fixed-point TEXT, not exponent notation.
    db.session.remove()
    with db.engine.begin() as connection:
        connection.exec_driver_sql('UPDATE portfolio_event SET amount_delta=? WHERE id=?', (text, identifier))
        connection.exec_driver_sql('PRAGMA user_version=40')
    try:
        run_startup_schema(app)
        with db.engine.connect() as connection:
            assert connection.exec_driver_sql('PRAGMA user_version').scalar() == TARGET_SCHEMA_VERSION
            assert connection.exec_driver_sql('SELECT amount_delta FROM portfolio_event WHERE id=?', (identifier,)).scalar() == text
        if consumer == 'reader':
            assert db.session.get(PortfolioEvent, identifier).amount_delta == D('1e-8193')
            assert PortfolioCalculator.get_portfolio_snapshot(ledger.pid, user_id=ledger.uid).cash_balance == D('1e-8193')
        else:
            client = app.test_client()
            authenticate_client(client, ledger.uid)
            assert client.get('/').status_code == 200
    finally:
        db.session.remove()
        with db.engine.begin() as connection:
            connection.exec_driver_sql(f'PRAGMA user_version={TARGET_SCHEMA_VERSION}')


@pytest.mark.parametrize('version', [36, 40])
def test_unsupported_historical_text_blocks_before_upgrade_changes(tmp_path, version):
    path = tmp_path / 'unsupported-history.sqlite'
    _create_version_33_no_action_database(path)
    close_app(create_app(_config_for(path)))
    with sqlite3.connect(path) as connection:
        connection.execute('UPDATE dividend SET amount=? WHERE id=63', ('0.' + '0' * 32768 + '1',))
        connection.execute(f'PRAGMA user_version={version}')
    before = dump(path)
    for _ in range(2):
        with pytest.raises(RuntimeError, match=r'historical decimal.*dividend.*63.*amount'):
            create_app(_config_for(path))
        assert dump(path) == before
    # Restore the verified original fact, then retry the same database.
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE dividend SET amount='25' WHERE id=63")
    close_app(create_app(_config_for(path)))
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT id,amount FROM dividend').fetchall() == [(63, '25')]
        assert connection.execute('PRAGMA user_version').fetchone()[0] == TARGET_SCHEMA_VERSION


def test_historical_reader_does_not_reformat_or_apply_action_limits(monkeypatch):
    import portfolio_app.utils.exact_decimal as storage
    text = '0.' + '0' * 8192 + '1'
    monkeypatch.setattr(storage, 'format', lambda *a: pytest.fail('Re-expanded stored text'), raising=False)
    assert ExactDecimalText().process_result_value(text, None) == D('1e-8193')
    with pytest.raises(ValueError, match='Financial number exceeds'):
        parse_financial_decimal(text)


@pytest.mark.parametrize('text', [
    '1e1000000000', '1e-1000000000', 'NaN', 'sNaN', 'Infinity', '-Infinity',
    '0.' + '0' * 32768 + '1',
], ids=['positive-exponent', 'negative-exponent', 'nan', 'snan', 'inf', 'negative-inf', 'oversized'])
def test_historical_reader_rejects_unsafe_text_before_decimal_construction(monkeypatch, text):
    import portfolio_app.utils.exact_decimal as storage
    monkeypatch.setattr(storage, 'Decimal', lambda *a: pytest.fail('Parsed unsafe stored text'))
    with pytest.raises(ValueError):
        storage.read_stored_decimal(text)


@pytest.mark.parametrize('text', ['9' * 32768, '0.' + '0' * 32765 + '1'], ids=['integer', 'fraction'])
def test_storage_budget_measures_representation_and_preserves_boundary(text):
    value = D(text)
    assert ExactDecimalText().process_result_value(text, None) == value
    assert canonical_decimal_text(value) == text


def test_storage_budget_includes_sign_and_decimal_point_before_format(monkeypatch):
    import portfolio_app.utils.exact_decimal as storage
    monkeypatch.setattr(storage, 'format', lambda *a: pytest.fail('Expanded oversized result'), raising=False)
    with pytest.raises(ValueError):
        canonical_decimal_text(D('1e-32767'))
    with pytest.raises(ValueError):
        canonical_decimal_text(D('-1e32767'))


def test_old_numeric_history_is_checked_before_any_legacy_writes(tmp_path):
    path = tmp_path / 'old-numeric.sqlite'
    _create_version_33_no_action_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE dividend SET amount=1e999 WHERE id=63")
    before = dump(path)
    with pytest.raises(RuntimeError, match=r'historical decimal.*dividend.*63.*amount'):
        create_app(_config_for(path))
    assert dump(path) == before


def test_legacy_opening_balance_is_checked_before_backfill_or_rename(tmp_path):
    path = tmp_path / 'legacy-opening.sqlite'
    _create_capital_era_database(path)
    _attribute_capital_dividend(path)
    with sqlite3.connect(path) as connection:
        connection.execute('DELETE FROM capital_event')
        connection.execute('UPDATE capital SET amount=1e999 WHERE id=1')
    before = dump(path)
    with pytest.raises(RuntimeError, match=r'historical decimal.*capital.*1.*amount'):
        create_app(_config_for(path))
    assert dump(path) == before


def _padded_one(length, side):
    padding = ' ' * (length - 1)
    if side == 'leading':
        return padding + '1'
    if side == 'trailing':
        return '1' + padding
    middle = len(padding) // 2
    return padding[:middle] + '1' + padding[middle:]


@pytest.mark.parametrize('length', [256, 257])
@pytest.mark.parametrize('side', ['leading', 'trailing', 'both'])
def test_financial_field_original_length_boundary(length, side):
    raw = _padded_one(length, side)
    value, error = parse_decimal_field(raw)
    form = PortfolioDepositForm({'amount_delta': raw, 'deposit_date': '2024-01-01'}, 1)
    if length == 256:
        assert (value, error) == (D('1'), None)
        assert form.validate()
        assert form.cleaned_data['amount_delta'] == D('1')
    else:
        assert value is None and '256' in error
        assert not form.validate()
        assert '256' in form.errors['amount_delta']


@pytest.mark.parametrize('length', [256, 257])
@pytest.mark.parametrize('field', ['edit_price', 'edit_quantity', 'edit_fees'])
def test_optional_edit_financial_blanks_still_obey_original_length(length, field):
    form = TransactionEditForm({field: ' ' * length}, 1, 'Buy')
    assert form.validate() == (length == 256)
    cleaned_field = field[len('edit_'):] if field.startswith('edit_') else field
    assert cleaned_field not in form.cleaned_data
    if length == 257:
        assert '256' in form.errors[field]


@pytest.mark.parametrize('length', [256, 257])
@pytest.mark.parametrize('field', ['price', 'quantity', 'fees'])
def test_preview_uses_original_financial_text_length(length, field):
    values = {'price': '1', 'quantity': '1', 'fees': '0'}
    values[field] = _padded_one(length, 'both')
    if length == 256:
        assert preview_values(values)[field] == D('1')
    else:
        with pytest.raises(PreviewUnavailable):
            preview_values(values)


@pytest.mark.parametrize('length', [256, 257])
def test_optional_preview_fees_check_length_before_blank_default(length):
    values = {'price': '1', 'quantity': '1', 'fees': ' ' * length}
    if length == 256:
        assert preview_values(values)['fees'] == D('0')
    else:
        with pytest.raises(PreviewUnavailable):
            preview_values(values)


def test_oversized_financial_text_is_rejected_before_any_strip():
    class Unstrippable(str):
        def strip(self, *args):
            pytest.fail('Normalized oversized financial input before length validation')

    raw = Unstrippable(' ' * 256 + '1')
    value, error = parse_decimal_field(raw)
    assert value is None and '256' in error
    form = PortfolioDepositForm({'amount_delta': raw}, 1)
    assert not form.validate() and '256' in form.errors['amount_delta']
    form = TransactionEditForm({'edit_price': raw}, 1, 'Buy')
    assert not form.validate() and '256' in form.errors['edit_price']
    with pytest.raises(PreviewUnavailable):
        preview_values({'price': raw, 'quantity': '1', 'fees': '0'})


@pytest.mark.parametrize('side', ['leading', 'trailing'])
def test_deposit_rejects_oversized_original_text_without_changing_balance(ledger, app, side):
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('10'), date=datetime(2024, 1, 1))
    before = PortfolioCalculator.get_portfolio_snapshot(ledger.pid, user_id=ledger.uid)
    client = app.test_client()
    authenticate_client(client, ledger.uid)
    response = client.post(f'/portfolios/deposit/{ledger.pid}', data={
        'amount_delta': _padded_one(257, side), 'deposit_date': '2024-01-01',
    }, headers={'X-Requested-With': 'XMLHttpRequest'})
    assert not response.json['success']
    assert '256' in response.json['errors']['amount_delta']
    db.session.expire_all()
    assert PortfolioEvent.query.count() == 1
    assert PortfolioCalculator.get_portfolio_snapshot(ledger.pid, user_id=ledger.uid) == before
    assert before.cash_balance == D('10')
