"""Shared OTP sending budgets with real limiting, isolated DBs and mocked mail."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import time
from unittest.mock import Mock

import pytest
from limits.storage import memory

from portfolio_app import create_app, db, limiter
from portfolio_app.models import User, PendingRegistration, AuthChallenge
from portfolio_app.services.auth_service import AuthService
from portfolio_app.utils.auth_session import RECENT_AUTH_AT_KEY
from portfolio_app.utils.messages import MESSAGES
from tests._auth import authenticate_client
from tests.test_auth import _Config, _create_user, mail_log


@pytest.fixture
def app(tmp_path):
    class LimitedConfig(_Config):
        RATELIMIT_ENABLED = True
        RATELIMIT_STORAGE_URI = 'memory://'
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'send-limits.sqlite').as_posix()}"
    application = create_app(LimitedConfig)
    limiter.reset()
    yield application
    with application.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def limit_clock(monkeypatch):
    now = [time.time()]
    # Advance only the limiter's clock, not Flask session/OTP timestamps.
    monkeypatch.setattr(memory, 'time', SimpleNamespace(time=lambda: now[0]))
    return now


def _browser(app, flow, name='alice'):
    browser = app.test_client()
    if flow != 'authentication':
        uid, _, _ = _create_user(app, f'{name}@example.com', name)
        authenticate_client(browser, uid)
        if flow == 'recent_auth':
            with browser.session_transaction() as state:
                state[RECENT_AUTH_AT_KEY] = (
                    datetime.now(timezone.utc) - timedelta(minutes=16)
                ).timestamp()
    return browser


def _send(browser, flow, action, index=0, *, json_response=True):
    paths = {
        'authentication': ('/login', '/resend-code'),
        'recent_auth': ('/reauthenticate', '/reauthenticate/resend'),
        'email_change': ('/update-email', '/settings/email/resend'),
        # The same endpoint starts and resends account-deletion codes.
        'deletion': ('/settings/delete/request', '/settings/delete/request'),
    }
    data = {}
    if action == 'start':
        if flow == 'authentication':
            data['email'] = 'target@example.com'
        elif flow == 'email_change':
            data['email'] = f'target-{index}@example.com'
    return browser.post(
        paths[flow][action == 'resend'], data=data,
        headers={'Accept': 'application/json'} if json_response else {},
    )


def _snapshot(app):
    with app.app_context():
        return tuple(
            tuple(tuple(row) for row in db.session.execute(
                db.select(model.__table__).order_by(model.id)
            ).all())
            for model in (User, PendingRegistration, AuthChallenge)
        )


FLOWS = ('authentication', 'recent_auth', 'email_change', 'deletion')


@pytest.mark.parametrize('flow', FLOWS)
@pytest.mark.parametrize('blocked_action', ['start', 'resend'])
def test_start_and_resend_share_budget_and_rejection_preserves_state(
    app, mail_log, monkeypatch, flow, blocked_action,
):
    browser = _browser(app, flow)
    for index, action in enumerate(('start', 'resend', 'start')):
        assert _send(browser, flow, action, index).status_code == 302
    assert len(mail_log) == 3
    before = _snapshot(app)
    generate = Mock(side_effect=AssertionError('A rejected request must not generate an OTP'))
    monkeypatch.setattr(AuthService, '_make_verification_code', generate)
    response = _send(browser, flow, blocked_action, 3)
    assert response.status_code == 429
    assert response.json['errors']['__all__'] == MESSAGES['RATE_LIMIT_AUTH_REQUEST']
    assert _snapshot(app) == before
    assert len(mail_log) == 3
    generate.assert_not_called()


def test_changing_target_address_does_not_reset_account_budget(app, mail_log):
    browser = _browser(app, 'email_change')
    for index in range(3):
        assert _send(browser, 'email_change', 'start', index).status_code == 302
    before = _snapshot(app)
    assert _send(browser, 'email_change', 'start', 3).status_code == 429
    assert _snapshot(app) == before
    assert len(mail_log) == 3


@pytest.mark.parametrize('flow', FLOWS)
def test_sending_resumes_when_shared_window_expires(app, mail_log, limit_clock, flow):
    browser = _browser(app, flow)
    for index, action in enumerate(('start', 'resend', 'start')):
        assert _send(browser, flow, action, index).status_code == 302
    assert _send(browser, flow, 'resend').status_code == 429
    limit_clock[0] += 3601
    assert _send(browser, flow, 'resend').status_code == 302
    assert len(mail_log) == 4


@pytest.mark.parametrize('flow', ('recent_auth', 'email_change', 'deletion'))
def test_one_account_does_not_consume_another_accounts_budget(app, mail_log, flow):
    alice = _browser(app, flow)
    bob = _browser(app, flow, 'bob')
    for index, action in enumerate(('start', 'resend', 'start')):
        assert _send(alice, flow, action, index).status_code == 302
    assert _send(alice, flow, 'resend').status_code == 429
    # Same client IP; Bob still has his full three-request account budget.
    for index, action in enumerate(('start', 'resend', 'start'), start=10):
        assert _send(bob, flow, action, index).status_code == 302
    assert _send(bob, flow, 'resend').status_code == 429
    assert len(mail_log) == 6


@pytest.mark.parametrize('flow', ('email_change', 'deletion', 'recent_auth'))
def test_confirmed_email_change_does_not_reset_account_budget(app, mail_log, flow):
    browser = _browser(app, flow)
    for index, action in enumerate(('start', 'resend', 'start')):
        assert _send(browser, flow, action, index).status_code == 302
    # A successful email change keeps the immutable account identity.
    if flow == 'recent_auth':
        with browser.session_transaction() as state:
            state[RECENT_AUTH_AT_KEY] = datetime.now(timezone.utc).timestamp()
    if flow != 'email_change':
        assert _send(browser, 'email_change', 'start', 10).status_code == 302
    assert browser.post('/settings/email/verify', data={'code': mail_log[-1][1]}).status_code == 302
    if flow == 'recent_auth':
        with browser.session_transaction() as state:
            state[RECENT_AUTH_AT_KEY] = (
                datetime.now(timezone.utc) - timedelta(minutes=16)
            ).timestamp()
    before = _snapshot(app)
    delivered = len(mail_log)
    assert _send(browser, flow, 'start', 20).status_code == 429
    assert _snapshot(app) == before
    assert len(mail_log) == delivered


def test_public_start_and_resend_share_origin_budget(app, mail_log):
    for index in range(5):
        browser = app.test_client()
        assert browser.post('/login', data={'email': f'person-{index}@example.com'}).status_code == 302
        assert _send(browser, 'authentication', 'resend').status_code == 302
    before = _snapshot(app)
    blocked = app.test_client().post('/login', data={'email': 'extra@example.com'})
    assert blocked.status_code == 429
    assert len(mail_log) == 10
    assert _snapshot(app) == before


@pytest.mark.parametrize('flow', ('authentication', 'recent_auth'))
def test_start_keeps_short_origin_limit_across_hourly_boundary(app, mail_log, limit_clock, flow):
    def start(index):
        browser = _browser(app, flow, f'person{index}')
        if flow == 'authentication':
            return browser.post('/login', data={'email': f'person{index}@example.com'})
        return _send(browser, flow, 'start')

    assert start(0).status_code == 302
    limit_clock[0] += 3590
    for index in range(1, 10):
        assert start(index).status_code == 302
    limit_clock[0] += 11
    assert start(10).status_code == 302  # New hourly window, tenth in 15 minutes.
    assert start(11).status_code == 429
    assert len(mail_log) == 11


@pytest.mark.parametrize('flow', FLOWS)
def test_html_rate_limit_response_keeps_existing_application_behavior(app, mail_log, flow):
    browser = _browser(app, flow)
    for index, action in enumerate(('start', 'resend', 'start')):
        assert _send(browser, flow, action, index).status_code == 302
    before = _snapshot(app)
    response = _send(browser, flow, 'resend', json_response=False)
    if flow == 'authentication':
        assert response.status_code == 302 and response.location.endswith('/verify-code')
        with browser.session_transaction() as state:
            assert ('warning', MESSAGES['RATE_LIMIT_AUTH_REQUEST']) in state['_flashes']
    else:
        assert response.status_code == 429
        assert MESSAGES['RATE_LIMIT_AUTH_REQUEST'] in response.text
    assert _snapshot(app) == before
    assert len(mail_log) == 3


@pytest.mark.parametrize('flow', ('recent_auth', 'email_change', 'deletion'))
def test_account_send_limits_preserve_login_requirement(app, mail_log, flow):
    browser = app.test_client()
    before = _snapshot(app)
    response = _send(browser, flow, 'start')
    assert response.status_code == 302 and '/login' in response.location
    assert _snapshot(app) == before and mail_log == []


@pytest.mark.parametrize('flow', FLOWS)
def test_csrf_rejection_changes_no_state_and_spends_no_send_budget(app, mail_log, flow):
    browser = _browser(app, flow)
    app.config['WTF_CSRF_ENABLED'] = True
    before = _snapshot(app)
    assert _send(browser, flow, 'start').status_code == 302
    with browser.session_transaction() as state:
        assert ('warning', MESSAGES['CSRF_CHECK_FAILED']) in state['_flashes']
    assert _snapshot(app) == before and mail_log == []
    app.config['WTF_CSRF_ENABLED'] = False
    for index, action in enumerate(('start', 'resend', 'start')):
        assert _send(browser, flow, action, index).status_code == 302
    assert len(mail_log) == 3


@pytest.mark.parametrize('action', ('start', 'resend'))
def test_email_sending_still_requires_recent_authentication(app, mail_log, action):
    browser = _browser(app, 'email_change')
    assert _send(browser, 'email_change', 'start').status_code == 302
    with browser.session_transaction() as state:
        state[RECENT_AUTH_AT_KEY] = (
            datetime.now(timezone.utc) - timedelta(minutes=16)
        ).timestamp()
    before = _snapshot(app)
    response = _send(browser, 'email_change', action, 1)
    assert response.status_code == 302 and '/reauthenticate' in response.location
    assert _snapshot(app) == before and len(mail_log) == 1


@pytest.mark.parametrize('flow', ('email_change', 'deletion'))
def test_cancellation_does_not_restore_send_budget(app, mail_log, flow):
    browser = _browser(app, flow)
    for index, action in enumerate(('start', 'resend', 'start')):
        assert _send(browser, flow, action, index).status_code == 302
    path = '/settings/email/cancel' if flow == 'email_change' else '/settings/delete/cancel'
    assert browser.post(path).status_code == 302
    before = _snapshot(app)
    assert _send(browser, flow, 'start', 3).status_code == 429
    assert _snapshot(app) == before and len(mail_log) == 3
