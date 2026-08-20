"""RCR-07 regression coverage: one authoritative submit owner for Edit Income.

The Edit Income modal (`#editDividendForm`) previously had two competing
frontend submit owners: a bespoke ``XMLHttpRequest`` handler inline in
``assets.html`` and the shared ``ModalAjaxHandler`` registration in
``static/js/main.js``. Neither stopped propagation, so a valid Save fired
both listeners and the edit was POSTed twice.

These tests pin the ownership contract (shared JS is the only submit owner,
template JS only opens/pre-fills the modal) and the server-side JSON
response contract the shared handler consumes.
"""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
import re

from portfolio_app import db
from portfolio_app.models.dividend import Dividend
from portfolio_app.models.user import User
from tests._auth import authenticate_client
from portfolio_app.services.factory import Services
from portfolio_app.utils.messages import MESSAGES


TEMPLATES_DIR = Path(__file__).resolve().parents[1] / 'portfolio_app' / 'templates'
JS_DIR = Path(__file__).resolve().parents[1] / 'portfolio_app' / 'static' / 'js'
ASSETS_TEMPLATE = TEMPLATES_DIR / 'assets.html'
MAIN_JS = JS_DIR / 'main.js'

SUBMIT_LISTENER_RE = re.compile(r"""addEventListener\(\s*['"]submit['"]""")


def _dec(value):
    return Decimal(str(value))


def _seed_user(username='edit_income_user'):
    user = User(username=username, email=f'{username}@example.com', is_verified=True)
    user.password_hash = 'legacy-test-hash'
    db.session.add(user)
    db.session.commit()
    return user.id


def _login(client, user_id):
    authenticate_client(client, user_id)


def _seed_dividend(uid, *, amount='75'):
    svc = Services(user_id=uid)
    portfolio = svc.portfolio_service.create_portfolio('Growth', user_id=uid)
    svc.portfolio_service.deposit_funds(portfolio.id, _dec('5000'), date=datetime(2024, 1, 1))
    svc.transaction_service.add_transaction(
        portfolio_id=portfolio.id,
        transaction_type='Buy',
        symbol='AAPL',
        price=_dec('100'),
        quantity=_dec('10'),
        fees=_dec('0'),
        date=datetime(2024, 1, 2),
    )
    dividend = svc.transaction_service.add_dividend(
        portfolio_id=portfolio.id,
        symbol='AAPL',
        amount=_dec(amount),
        date=datetime(2024, 1, 4),
        notes='seed income',
    )
    dividend_id = dividend.id if dividend is not None else (
        Dividend.query.filter_by(portfolio_id=portfolio.id).one().id
    )
    return portfolio.id, dividend_id


def _modal_forms_block(js_source):
    """Return the source of ModalAjaxHandler's ``modalForms`` array."""
    start = js_source.index('const modalForms = [')
    end = js_source.index('];', start)
    return js_source[start:end]


# ---------------------------------------------------------------------------
# Submit ownership
# ---------------------------------------------------------------------------

def test_assets_template_declares_no_submit_handler():
    """Template JS opens/pre-fills modals only; it never owns submission."""
    source = ASSETS_TEMPLATE.read_text(encoding='utf-8')

    assert SUBMIT_LISTENER_RE.search(source) is None, (
        'assets.html must not attach form submit listeners — submission is '
        'owned by ModalAjaxHandler in static/js/main.js (RCR-07).'
    )
    assert 'new XMLHttpRequest' not in source, (
        'assets.html must not issue its own form POSTs (RCR-07).'
    )
    # The dead banner element the removed handler wrote to never existed in
    # the markup; errors are rendered by ModalAjaxHandler instead.
    assert 'edit_dividend_error' not in source


def test_no_template_or_side_js_owns_form_submission():
    """main.js is the single authoritative submit owner across the frontend."""
    offenders = []
    for path in list(TEMPLATES_DIR.rglob('*.html')) + list(JS_DIR.rglob('*.js')):
        if path == MAIN_JS:
            continue
        if SUBMIT_LISTENER_RE.search(path.read_text(encoding='utf-8')):
            offenders.append(str(path.relative_to(TEMPLATES_DIR.parent.parent)))

    assert offenders == [], (
        f'Competing submit owners found outside main.js: {offenders} (RCR-07).'
    )


def test_edit_income_form_registered_once_with_modal_ajax_handler():
    source = MAIN_JS.read_text(encoding='utf-8')
    block = _modal_forms_block(source)

    assert block.count('editDividendForm') == 1, (
        'ModalAjaxHandler must own #editDividendForm exactly once.'
    )
    assert "modalId: 'editDividendModal'" in block


def test_edit_income_client_validation_preserved():
    """FormValidator still guards amount/date and runs before the AJAX owner."""
    source = MAIN_JS.read_text(encoding='utf-8')

    assert source.count("this.initValidator('#editDividendForm'") == 1
    validator_start = source.index("this.initValidator('#editDividendForm'")
    validator_block = source[validator_start:source.index(']);', validator_start)]
    assert "selector: '#edit_amount'" in validator_block
    assert "selector: '#edit_dividend_date'" in validator_block

    # Ordering matters: the validator's stopImmediatePropagation() only
    # blocks the AJAX submit if its listener is attached first.
    assert (
        source.index('new FormValidatorsInitializer()')
        < source.index('new ModalAjaxHandler()')
    )
    assert 'stopImmediatePropagation' in source


def test_rendered_edit_income_form_is_unique_and_csrf_protected(app):
    with app.app_context():
        uid = _seed_user('edit_income_render')
        _seed_dividend(uid)

    client = app.test_client()
    _login(client, uid)
    response = client.get('/transactions/')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert html.count('id="editDividendForm"') == 1
    form_html = html[html.index('id="editDividendForm"'):]
    form_html = form_html[:form_html.index('</form>')]
    assert 'name="csrf_token"' in form_html
    assert 'name="edit_amount"' in form_html
    assert 'name="edit_date"' in form_html


# ---------------------------------------------------------------------------
# Response contract consumed by ModalAjaxHandler
# ---------------------------------------------------------------------------

def test_edit_income_ajax_success_contract(app):
    with app.app_context():
        uid = _seed_user('edit_income_ok')
        _, dividend_id = _seed_dividend(uid, amount='75')

    client = app.test_client()
    _login(client, uid)
    response = client.post(
        f'/transactions/dividends/edit/{dividend_id}',
        data={'edit_amount': '125.50', 'edit_date': '2024-01-05', 'edit_notes': 'updated'},
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['message'] == MESSAGES['DIVIDEND_UPDATED']

    with app.app_context():
        dividend = db.session.get(Dividend, dividend_id)
        assert dividend.amount == _dec('125.50')
        assert dividend.notes == 'updated'


def test_edit_income_ajax_field_error_contract(app):
    """Invalid input returns the per-field ``errors`` shape, not ``error``."""
    with app.app_context():
        uid = _seed_user('edit_income_invalid')
        _, dividend_id = _seed_dividend(uid, amount='75')

    client = app.test_client()
    _login(client, uid)
    response = client.post(
        f'/transactions/dividends/edit/{dividend_id}',
        data={'edit_amount': '0', 'edit_date': '2024-01-05', 'edit_notes': ''},
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )

    payload = response.get_json()
    assert payload['success'] is False
    assert 'edit_amount' in payload['errors']

    with app.app_context():
        assert db.session.get(Dividend, dividend_id).amount == _dec('75')


def test_edit_income_replayed_post_does_not_compound(app):
    """A duplicated submit must never accumulate — the edit is a set, not a delta."""
    with app.app_context():
        uid = _seed_user('edit_income_replay')
        _, dividend_id = _seed_dividend(uid, amount='75')

    client = app.test_client()
    _login(client, uid)
    payload = {'edit_amount': '200', 'edit_date': '2024-01-05', 'edit_notes': 'x'}
    for _ in range(2):
        response = client.post(
            f'/transactions/dividends/edit/{dividend_id}',
            data=payload,
            headers={'X-Requested-With': 'XMLHttpRequest'},
        )
        assert response.get_json()['success'] is True

    with app.app_context():
        assert db.session.get(Dividend, dividend_id).amount == _dec('200')
        assert Dividend.query.count() == 1
