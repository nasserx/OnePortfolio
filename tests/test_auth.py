"""Public passwordless authentication and session-security contracts."""

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import SQLAlchemyError

from config import Config
from portfolio_app import create_app, db, limiter
from portfolio_app.models.auth_challenge import AuthChallenge
from portfolio_app.models.oauth_identity import OAuthIdentity
from portfolio_app.models.pending_registration import PendingRegistration
from portfolio_app.models.portfolio import Portfolio
from portfolio_app.models.user import User
from portfolio_app.services.factory import Services
from portfolio_app.utils import email as email_utils
from portfolio_app.utils.auth_session import (
    AUTH_ISSUED_AT_KEY,
    AUTH_LAST_SEEN_AT_KEY,
    RECENT_AUTH_AT_KEY,
)
from portfolio_app.utils.messages import MESSAGES


class _Config(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'passwordless-test-secret'
    MAIL_SUPPRESS_SEND = True
    RATELIMIT_ENABLED = False
    SQLALCHEMY_DATABASE_URI = None


@pytest.fixture
def app(tmp_path):
    class TestConfig(_Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'auth.sqlite').as_posix()}"

    application = create_app(TestConfig)
    yield application
    with application.app_context():
        db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def mail_log(monkeypatch):
    delivered = []

    def capture(recipient, code):
        delivered.append((recipient, code))
        return True

    monkeypatch.setattr('portfolio_app.routes.auth.send_authentication_email', capture)
    monkeypatch.setattr('portfolio_app.routes.auth.send_verification_email', capture)
    monkeypatch.setattr('portfolio_app.routes.auth.send_deletion_confirmation_email', capture)
    return delivered


def _create_user(app, email='alice@example.com', username='alice', password=True):
    with app.app_context():
        user = User(username=username, email=email, is_verified=True)
        if password:
            user.password_hash = 'preserved-rollback-hash'
        db.session.add(user)
        db.session.commit()
        return user.id, user.password_hash, user.auth_generation


def _begin(client, mail_log, email='alice@example.com', next_page=None):
    path = '/login' + (f'?next={next_page}' if next_page else '')
    response = client.post(path, data={'email': email}, follow_redirects=False)
    assert response.status_code in (302, 303)
    assert response.headers['Location'].endswith('/verify-code')
    assert mail_log[-1][0] == email.lower()
    return mail_log[-1][1]


def _verify(client, code, follow=False):
    return client.post(
        '/verify-code', data={'code': code}, follow_redirects=follow,
    )


def _auth_session(client):
    with client.session_transaction() as state:
        return dict(state)


def _csrf_token(response):
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.get_data(as_text=True))
    assert match
    return match.group(1)


def _freeze_auth_service_time(monkeypatch, moment):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return moment.replace(tzinfo=None)
            return moment.astimezone(tz)

    monkeypatch.setattr(
        'portfolio_app.services.auth_service.datetime', FrozenDateTime,
    )


def test_email_entry_ui_is_single_accessible_passwordless_flow(client):
    html = client.get('/login').get_data(as_text=True)
    assert 'name="email"' in html
    assert 'type="email"' in html
    assert '<label class="visually-hidden" for="email">Email address</label>' in html
    assert 'name="password"' not in html
    assert 'remember' not in html.lower()
    assert 'Continue with Google' not in html
    assert 'bi-google' not in html
    assert '>or<' not in html
    assert '6-digit' not in html
    assert 'We’ll email you a verification code.' in html
    assert client.get('/register', follow_redirects=False).headers['Location'].endswith('/login')


def test_verification_ui_uses_concise_generic_copy_and_accessible_controls(
    app, client, mail_log,
):
    _create_user(app)
    _begin(client, mail_log)
    html = client.get('/verify-code').get_data(as_text=True)
    assert '<h1 class="h4 fw-500 mb-1">Verification code</h1>' in html
    assert MESSAGES['AUTH_CODE_REQUEST_RESULT'] == (
        'Check your email for a verification code.'
    )
    assert MESSAGES['AUTH_CODE_REQUEST_RESULT'] in html
    assert '<label class="visually-hidden" for="code">Verification code</label>' in html
    assert 'autocomplete="one-time-code"' in html
    assert 'Send a new code' in html
    assert '>Back</a>' in html
    assert 'alice@example.com' not in html
    assert '6-digit' not in html
    assert 'sent to' not in html.lower()


def test_settings_remains_protected_and_exposes_only_passwordless_controls(
    app, client, mail_log,
):
    assert client.get('/settings', follow_redirects=False).status_code in (302, 303)
    _create_user(app)
    _verify(client, _begin(client, mail_log))
    html = client.get('/settings?tab=security').get_data(as_text=True)
    assert 'Email verification code' in html
    assert 'Update Email' in html
    assert 'Delete account' in html
    assert 'name="password"' not in html
    assert '/change-password' not in html
    assert '/auth/google' not in html
    assert '/settings/google/disconnect' not in html
    assert 'bi-google' not in html
    assert 'client_secret' not in html.lower()


def test_signed_session_configuration_uses_seven_day_rolling_lifetime():
    assert Config.PERMANENT_SESSION_LIFETIME == timedelta(days=7)
    assert Config.SESSION_REFRESH_EACH_REQUEST is True


def test_existing_user_authenticates_by_email_otp_and_preserves_hash(
    app, client, mail_log,
):
    user_id, original_hash, _ = _create_user(app)
    code = _begin(client, mail_log)
    response = _verify(client, code)
    assert response.status_code in (302, 303)
    assert response.headers['Location'].endswith('/')
    state = _auth_session(client)
    assert state['_user_id'].startswith(f'v1:{user_id}:')
    assert state['_fresh'] is True
    assert AUTH_ISSUED_AT_KEY in state
    assert AUTH_LAST_SEEN_AT_KEY in state
    assert RECENT_AUTH_AT_KEY in state
    assert '_remember' not in state
    with client.session_transaction() as signed_session:
        assert signed_session.permanent is True
    with app.app_context():
        assert db.session.get(User, user_id).password_hash == original_hash


def test_new_email_uses_same_flow_and_creates_passwordless_user(
    app, client, mail_log,
):
    code = _begin(client, mail_log, 'new@example.com')
    with app.app_context():
        pending = PendingRegistration.query.one()
        assert pending.email == 'new@example.com'
        assert not hasattr(pending, 'password_hash')
        assert User.query.count() == 0
    assert _verify(client, code).status_code in (302, 303)
    with app.app_context():
        user = User.query.one()
        assert user.email == 'new@example.com'
        assert user.is_verified is True
        assert user.password_hash is None
        assert PendingRegistration.query.count() == 0


def test_registration_challenge_expiry_is_capped_by_pending_registration(app):
    cutoff = (datetime.now(timezone.utc) + timedelta(minutes=2)).replace(
        microsecond=0,
    )
    with app.app_context():
        pending = PendingRegistration(
            username='near_cutoff',
            email='near-cutoff@example.com',
            created_at=cutoff - timedelta(hours=24),
            expires_at=cutoff,
        )
        db.session.add(pending)
        db.session.commit()

        issue = Services().auth_service.begin_authentication(pending.email)
        challenge = AuthChallenge.query.filter_by(token=issue.token).one()
        assert challenge.expires_at.replace(tzinfo=timezone.utc) == cutoff


def test_registration_resend_stays_capped_without_extending_pending_lifetime(app):
    cutoff = (datetime.now(timezone.utc) + timedelta(minutes=2)).replace(
        microsecond=0,
    )
    with app.app_context():
        pending = PendingRegistration(
            username='resend_cutoff',
            email='resend-cutoff@example.com',
            created_at=cutoff - timedelta(hours=24),
            expires_at=cutoff,
        )
        db.session.add(pending)
        db.session.commit()

        service = Services().auth_service
        issue = service.begin_authentication(pending.email)
        challenge = AuthChallenge.query.filter_by(token=issue.token).one()
        challenge.expires_at = cutoff - timedelta(minutes=1)
        challenge.failed_attempts = 2
        db.session.commit()

        resent = service.resend_challenge(issue.token, 'authentication')
        assert resent is not None
        db.session.refresh(challenge)
        db.session.refresh(pending)
        assert challenge.expires_at.replace(tzinfo=timezone.utc) == cutoff
        assert challenge.failed_attempts == 0
        assert pending.expires_at.replace(tzinfo=timezone.utc) == cutoff


def test_live_otp_cannot_promote_an_expired_pending_registration(
    app, client, mail_log,
):
    code = _begin(client, mail_log, 'expired-pending@example.com')
    with app.app_context():
        pending = PendingRegistration.query.one()
        challenge = AuthChallenge.query.one()
        pending.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        challenge.expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        db.session.commit()

    response = _verify(client, code, follow=True)
    assert MESSAGES['VERIFICATION_CODE_INVALID_OR_EXPIRED'] in response.get_data(as_text=True)
    with app.app_context():
        assert User.query.filter_by(email='expired-pending@example.com').count() == 0
        assert PendingRegistration.query.count() == 1
        assert AuthChallenge.query.one().consumed_at is None


@pytest.mark.parametrize(
    'verification_offset',
    (timedelta(microseconds=1), timedelta(0)),
    ids=('immediately-before-cutoff', 'exact-cutoff'),
)
def test_registration_succeeds_through_the_inclusive_hard_cutoff(
    app, client, mail_log, monkeypatch, verification_offset,
):
    code = _begin(client, mail_log, 'boundary@example.com')
    cutoff = (datetime.now(timezone.utc) + timedelta(minutes=2)).replace(
        microsecond=0,
    )
    with app.app_context():
        pending = PendingRegistration.query.one()
        challenge = AuthChallenge.query.one()
        pending.expires_at = cutoff
        challenge.expires_at = cutoff
        db.session.commit()

    _freeze_auth_service_time(monkeypatch, cutoff - verification_offset)
    assert _verify(client, code).status_code in (302, 303)
    with app.app_context():
        assert User.query.filter_by(email='boundary@example.com').count() == 1
        assert PendingRegistration.query.count() == 0


def test_resend_cannot_revive_an_expired_pending_registration(app):
    with app.app_context():
        service = Services().auth_service
        issue = service.begin_authentication('expired-resend@example.com')
        pending = PendingRegistration.query.one()
        challenge = AuthChallenge.query.one()
        pending.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        challenge.expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        challenge.failed_attempts = 2
        db.session.commit()
        db.session.refresh(challenge)
        db.session.refresh(pending)
        original_state = (
            challenge.code_digest,
            challenge.expires_at,
            challenge.failed_attempts,
            pending.expires_at,
        )

        assert service.resend_challenge(issue.token, 'authentication') is None
        db.session.refresh(challenge)
        db.session.refresh(pending)
        assert (
            challenge.code_digest,
            challenge.expires_at,
            challenge.failed_attempts,
            pending.expires_at,
        ) == original_state
        assert User.query.filter_by(email='expired-resend@example.com').count() == 0


def test_new_user_registration_resolves_existing_username_collision(
    app, client, mail_log,
):
    _create_user(app, email='existing@example.com', username='new')
    code = _begin(client, mail_log, 'new@example.com')
    assert _verify(client, code).status_code in (302, 303)
    with app.app_context():
        created = User.query.filter_by(email='new@example.com').one()
        assert created.username == 'new_2'


def test_known_and_unknown_email_requests_have_identical_public_contract(
    app, mail_log,
):
    _create_user(app)
    results = []
    for email in ('alice@example.com', 'unknown@example.com'):
        browser = app.test_client()
        response = browser.post('/login', data={'email': email}, follow_redirects=False)
        with browser.session_transaction() as state:
            results.append((
                response.status_code,
                response.headers['Location'],
                tuple(state.get('_flashes', ())),
            ))
    assert results[0] == results[1]
    assert results[0][2] == (('info', MESSAGES['AUTH_CODE_REQUEST_RESULT']),)


def test_known_and_unknown_resend_and_invalid_verification_are_generic(
    app, mail_log,
):
    _create_user(app)
    results = []
    for email in ('alice@example.com', 'unknown@example.com'):
        browser = app.test_client()
        _begin(browser, mail_log, email)
        resend = browser.post('/resend-code', follow_redirects=False)
        invalid = browser.post(
            '/verify-code', data={'code': '000000'}, follow_redirects=True,
        )
        results.append((
            resend.status_code,
            resend.headers['Location'],
            MESSAGES['AUTH_CODE_REQUEST_RESULT'] in invalid.get_data(as_text=True),
            MESSAGES['VERIFICATION_CODE_INVALID_OR_EXPIRED']
            in invalid.get_data(as_text=True),
        ))
    assert results[0] == results[1]


def test_auth_code_is_hmac_only_and_context_bound(app, client, mail_log):
    _create_user(app)
    code = _begin(client, mail_log)
    with app.app_context():
        challenge = AuthChallenge.query.one()
        assert challenge.code_digest != code
        assert re.fullmatch(r'[0-9a-f]{64}', challenge.code_digest)
        assert code not in repr(challenge)


def test_challenge_result_repr_excludes_token_recipient_and_code(app):
    with app.app_context():
        issue = Services().auth_service.begin_authentication('private@example.com')
        rendered = repr(issue)
        assert issue.token not in rendered
        assert issue.recipient not in rendered
        assert issue.code not in rendered


def test_expired_code_is_rejected(app, client, mail_log):
    _create_user(app)
    code = _begin(client, mail_log)
    with app.app_context():
        challenge = AuthChallenge.query.one()
        challenge.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.session.commit()
    response = _verify(client, code, follow=True)
    assert MESSAGES['VERIFICATION_CODE_INVALID_OR_EXPIRED'] in response.get_data(as_text=True)
    assert client.get('/settings').status_code in (302, 303)


def test_five_bad_attempts_exhaust_challenge(app, client, mail_log):
    _create_user(app)
    correct = _begin(client, mail_log)
    wrong = '000000' if correct != '000000' else '111111'
    for _ in range(5):
        _verify(client, wrong)
    with app.app_context():
        assert AuthChallenge.query.one().failed_attempts == 5
    assert MESSAGES['VERIFICATION_CODE_INVALID_OR_EXPIRED'] in _verify(
        client, correct, follow=True,
    ).get_data(as_text=True)


def test_resend_rotates_code_expiry_and_attempts(app, client, mail_log):
    _create_user(app)
    old_code = _begin(client, mail_log)
    _verify(client, '000000' if old_code != '000000' else '111111')
    with app.app_context():
        old_digest = AuthChallenge.query.one().code_digest
    response = client.post('/resend-code', follow_redirects=False)
    assert response.status_code in (302, 303)
    new_code = mail_log[-1][1]
    with app.app_context():
        challenge = AuthChallenge.query.one()
        assert challenge.code_digest != old_digest
        assert challenge.failed_attempts == 0
    assert MESSAGES['VERIFICATION_CODE_INVALID_OR_EXPIRED'] in _verify(
        client, old_code, follow=True,
    ).get_data(as_text=True)
    assert _verify(client, new_code).status_code in (302, 303)


def test_consumed_code_cannot_replay_even_through_service(app, client, mail_log):
    _create_user(app)
    code = _begin(client, mail_log)
    with client.session_transaction() as state:
        token = state['auth_challenge_token']
    assert _verify(client, code).status_code in (302, 303)
    with app.app_context():
        assert Services().auth_service.verify_challenge(
            token, code, 'authentication',
        ) is None


def test_concurrent_verification_has_exactly_one_consumer(
    app, client, mail_log,
):
    user_id, _, _ = _create_user(app)
    code = _begin(client, mail_log)
    with client.session_transaction() as state:
        token = state['auth_challenge_token']

    def consume():
        with app.app_context():
            user = Services().auth_service.verify_challenge(
                token, code, 'authentication',
            )
            return user.id if user else None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: consume(), range(2)))
    assert sorted(result for result in results if result is not None) == [user_id]


def test_safe_redirect_preserved_and_external_redirect_rejected(app, mail_log):
    _create_user(app)
    local = app.test_client()
    code = _begin(local, mail_log, next_page='/settings')
    assert _verify(local, code).headers['Location'].endswith('/settings')
    external = app.test_client()
    code = _begin(external, mail_log, next_page='https://evil.example')
    assert _verify(external, code).headers['Location'].endswith('/')


def test_successful_login_clears_fixated_session_state(app, client, mail_log):
    _create_user(app)
    code = _begin(client, mail_log)
    with client.session_transaction() as state:
        state['attacker_marker'] = 'fixed'
    _verify(client, code)
    assert 'attacker_marker' not in _auth_session(client)


def test_mail_failure_keeps_generic_response_and_retryable_challenge(
    app, client, monkeypatch,
):
    _create_user(app)
    monkeypatch.setattr(
        'portfolio_app.routes.auth.send_authentication_email', lambda *_: False,
    )
    response = client.post('/login', data={'email': 'alice@example.com'})
    assert response.status_code in (302, 303)
    with client.session_transaction() as state:
        assert state['_flashes'] == [('info', MESSAGES['AUTH_CODE_REQUEST_RESULT'])]
    with app.app_context():
        assert AuthChallenge.query.count() == 1


def test_delivery_logging_excludes_recipient_code_and_exception(
    app, monkeypatch, caplog,
):
    secret_code = '739201'
    recipient = 'private@example.com'
    provider_detail = 'provider-secret-detail'

    def fail(_message):
        raise RuntimeError(provider_detail)

    monkeypatch.setattr(email_utils.mail, 'send', fail)
    caplog.set_level(logging.WARNING)
    with app.app_context():
        assert email_utils.send_authentication_email(recipient, secret_code) is False
    rendered = caplog.text
    assert recipient not in rendered
    assert secret_code not in rendered
    assert provider_detail not in rendered


def test_route_failure_logging_excludes_authentication_secrets(
    app, client, monkeypatch, caplog,
):
    sensitive = 'private@example.com token-abc 739201 provider-detail'

    def fail(_service, _email):
        raise RuntimeError(sensitive)

    monkeypatch.setattr(
        'portfolio_app.services.auth_service.AuthService.begin_authentication',
        fail,
    )
    caplog.set_level(logging.WARNING)
    response = client.post('/login', data={'email': 'private@example.com'})
    assert response.status_code == 200
    assert sensitive not in caplog.text
    assert 'private@example.com' not in caplog.text


def test_csrf_blocks_auth_posts_without_creating_state(tmp_path):
    class CsrfConfig(_Config):
        WTF_CSRF_ENABLED = True
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'csrf.sqlite').as_posix()}"

    application = create_app(CsrfConfig)
    browser = application.test_client()
    response = browser.post('/login', data={'email': 'new@example.com'})
    assert response.status_code in (302, 303, 400)
    with application.app_context():
        assert AuthChallenge.query.count() == 0
        assert PendingRegistration.query.count() == 0
    token = _csrf_token(browser.get('/login'))
    assert browser.post('/login', data={
        'email': 'new@example.com', 'csrf_token': token,
    }).status_code in (302, 303)
    with application.app_context():
        challenge = AuthChallenge.query.one()
        before = (
            challenge.code_digest,
            challenge.expires_at,
            challenge.failed_attempts,
            challenge.consumed_at,
        )
    for path, data in (
        ('/resend-code', {}),
        ('/verify-code', {'code': '000000'}),
    ):
        response = browser.post(path, data=data, follow_redirects=False)
        assert response.status_code in (302, 303, 400)
    with application.app_context():
        challenge = AuthChallenge.query.one()
        assert (
            challenge.code_digest,
            challenge.expires_at,
            challenge.failed_attempts,
            challenge.consumed_at,
        ) == before


def test_resend_is_post_only_and_get_does_not_rotate_challenge(
    app, client, mail_log,
):
    _create_user(app)
    _begin(client, mail_log)
    with app.app_context():
        before = AuthChallenge.query.one().code_digest
    assert client.get('/resend-code').status_code == 405
    with app.app_context():
        assert AuthChallenge.query.one().code_digest == before


def test_origin_and_normalized_target_rate_limits(tmp_path, monkeypatch):
    class LimitedConfig(_Config):
        RATELIMIT_ENABLED = True
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'limited.sqlite').as_posix()}"

    monkeypatch.setattr(
        'portfolio_app.routes.auth.send_authentication_email', lambda *_: True,
    )
    application = create_app(LimitedConfig)
    limiter.reset()
    for index, spelling in enumerate((
        'rate@example.com', 'RATE@example.com', 'Rate@Example.com',
        'rate@EXAMPLE.COM', 'rAtE@example.com',
    )):
        response = application.test_client().post(
            '/login', data={'email': spelling},
            environ_overrides={'REMOTE_ADDR': f'198.51.100.{index + 1}'},
        )
        assert response.status_code in (302, 303)
    blocked = application.test_client().post(
        '/login', data={'email': 'rate@example.com'},
        environ_overrides={'REMOTE_ADDR': '198.51.100.99'},
    )
    assert blocked.status_code == 429

    limiter.reset()
    origin = application.test_client()
    for index in range(10):
        assert origin.post('/login', data={
            'email': f'origin-{index}@example.com',
        }).status_code in (302, 303)
    assert origin.post('/login', data={'email': 'origin-10@example.com'}).status_code == 429


def test_idle_and_absolute_expiry_fail_closed(app, mail_log):
    _create_user(app)
    for key, age in (
        (AUTH_LAST_SEEN_AT_KEY, timedelta(days=7, seconds=1)),
        (AUTH_ISSUED_AT_KEY, timedelta(days=30, seconds=1)),
    ):
        browser = app.test_client()
        code = _begin(browser, mail_log)
        _verify(browser, code)
        with browser.session_transaction() as state:
            state[key] = (datetime.now(timezone.utc) - age).timestamp()
        assert browser.get('/settings', follow_redirects=False).status_code in (302, 303)
        assert '_user_id' not in _auth_session(browser)


def test_missing_legacy_timestamps_fail_closed(app):
    user_id, _, generation = _create_user(app)
    browser = app.test_client()
    with browser.session_transaction() as state:
        state['_user_id'] = f'v1:{user_id}:{generation}'
        state['_fresh'] = True
    assert browser.get('/settings').status_code in (302, 303)
    assert '_user_id' not in _auth_session(browser)


def test_stale_recent_auth_requires_current_email_otp(app, client, mail_log):
    _create_user(app)
    _verify(client, _begin(client, mail_log))
    with client.session_transaction() as state:
        state[RECENT_AUTH_AT_KEY] = (
            datetime.now(timezone.utc) - timedelta(minutes=16)
        ).timestamp()
    response = client.get('/update-email', follow_redirects=False)
    assert response.status_code in (302, 303)
    assert '/reauthenticate' in response.headers['Location']
    assert client.post('/reauthenticate').status_code in (302, 303)
    code = mail_log[-1][1]
    assert client.post('/reauthenticate/verify', data={'code': code}).status_code in (302, 303)
    assert client.get('/update-email').status_code == 200


def test_email_change_uses_recent_auth_then_separate_new_email_proof(
    app, client, mail_log,
):
    user_id, _, _ = _create_user(app)
    _verify(client, _begin(client, mail_log))
    response = client.post('/update-email', data={'email': 'new@example.com'})
    assert response.status_code in (302, 303)
    assert response.headers['Location'].endswith('/settings/email/verify')
    new_email_code = mail_log[-1][1]
    assert client.post(
        '/settings/email/verify', data={'code': new_email_code},
    ).status_code in (302, 303)
    with app.app_context():
        assert db.session.get(User, user_id).email == 'new@example.com'


def test_email_change_verification_rechecks_recent_auth(
    app, client, mail_log,
):
    user_id, _, _ = _create_user(app)
    _verify(client, _begin(client, mail_log))
    client.post('/update-email', data={'email': 'new@example.com'})
    new_email_code = mail_log[-1][1]
    with client.session_transaction() as state:
        state[RECENT_AUTH_AT_KEY] = (
            datetime.now(timezone.utc) - timedelta(minutes=16)
        ).timestamp()

    response = client.post(
        '/settings/email/verify', data={'code': new_email_code},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)
    assert '/reauthenticate' in response.headers['Location']
    with app.app_context():
        assert db.session.get(User, user_id).email == 'alice@example.com'

    client.post('/reauthenticate')
    current_email_code = mail_log[-1][1]
    client.post('/reauthenticate/verify', data={'code': current_email_code})
    client.post('/settings/email/verify', data={'code': new_email_code})
    with app.app_context():
        assert db.session.get(User, user_id).email == 'new@example.com'


def test_email_change_rejects_existing_and_pending_registration_addresses(
    app, client, mail_log,
):
    user_id, _, _ = _create_user(app)
    _create_user(app, email='owned@example.com', username='owner')
    pending_browser = app.test_client()
    _begin(pending_browser, mail_log, 'reserved@example.com')

    _verify(client, _begin(client, mail_log))
    for unavailable in ('OWNED@example.com', 'RESERVED@example.com'):
        response = client.post(
            '/update-email', data={'email': unavailable}, follow_redirects=True,
        )
        assert MESSAGES['EMAIL_IN_USE'] in response.get_data(as_text=True)
    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.email == 'alice@example.com'
        assert user.pending_email is None


def test_email_change_five_attempts_clear_pending_state(
    app, client, mail_log,
):
    user_id, _, _ = _create_user(app)
    _verify(client, _begin(client, mail_log))
    client.post('/update-email', data={'email': 'new@example.com'})
    correct = mail_log[-1][1]
    wrong = '000000' if correct != '000000' else '111111'
    for _ in range(5):
        client.post('/settings/email/verify', data={'code': wrong})
    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.email == 'alice@example.com'
        assert user.pending_email is None
        assert user.verification_code is None
        assert user.verification_code_expires_at is None
        assert user.verification_code_failed_attempts == 0


def test_email_change_resend_rotates_code_and_resets_attempts(
    app, client, mail_log,
):
    user_id, _, _ = _create_user(app)
    _verify(client, _begin(client, mail_log))
    client.post('/update-email', data={'email': 'new@example.com'})
    old_code = mail_log[-1][1]
    wrong = '000000' if old_code != '000000' else '111111'
    client.post('/settings/email/verify', data={'code': wrong})
    with app.app_context():
        old_digest = db.session.get(User, user_id).verification_code

    response = client.post('/settings/email/resend', follow_redirects=True)
    assert MESSAGES['VERIFICATION_CODE_RESEND_RESULT'] in response.get_data(as_text=True)
    new_code = mail_log[-1][1]
    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.verification_code != old_digest
        assert user.verification_code_failed_attempts == 0
    assert MESSAGES['VERIFICATION_CODE_INVALID_OR_EXPIRED'] in client.post(
        '/settings/email/verify', data={'code': old_code}, follow_redirects=True,
    ).get_data(as_text=True)
    client.post('/settings/email/verify', data={'code': new_code})
    with app.app_context():
        assert db.session.get(User, user_id).email == 'new@example.com'


def test_deletion_otp_does_not_require_redundant_recent_auth(
    app, client, mail_log,
):
    user_id, _, _ = _create_user(app)
    _verify(client, _begin(client, mail_log))
    with client.session_transaction() as state:
        state[RECENT_AUTH_AT_KEY] = (
            datetime.now(timezone.utc) - timedelta(days=1)
        ).timestamp()
    assert client.post('/settings/delete/request').status_code in (302, 303)
    code = mail_log[-1][1]
    assert client.post('/settings/delete/verify', data={'code': code}).status_code in (302, 303)
    with app.app_context():
        assert db.session.get(User, user_id) is None


def test_deletion_cancel_invalidates_issued_code(app, client, mail_log):
    user_id, _, _ = _create_user(app)
    _verify(client, _begin(client, mail_log))
    client.post('/settings/delete/request')
    issued_code = mail_log[-1][1]
    assert client.post('/settings/delete/cancel').status_code in (302, 303)
    assert client.post(
        '/settings/delete/verify', data={'code': issued_code},
    ).status_code in (302, 303)
    with app.app_context():
        user = db.session.get(User, user_id)
        assert user is not None
        assert user.deletion_code is None
        assert user.deletion_code_expires_at is None


def test_expired_deletion_code_cannot_delete_account(app, client, mail_log):
    user_id, _, _ = _create_user(app)
    _verify(client, _begin(client, mail_log))
    client.post('/settings/delete/request')
    code = mail_log[-1][1]
    with app.app_context():
        user = db.session.get(User, user_id)
        user.deletion_code_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.session.commit()
    client.post('/settings/delete/verify', data={'code': code})
    with app.app_context():
        assert db.session.get(User, user_id) is not None


def test_deletion_code_is_bound_to_issuing_account(
    app, mail_log, monkeypatch,
):
    alice_id, _, _ = _create_user(app)
    bob_id, _, _ = _create_user(app, email='bob@example.com', username='bob')
    alice = app.test_client()
    bob = app.test_client()
    _verify(alice, _begin(alice, mail_log, 'alice@example.com'))
    _verify(bob, _begin(bob, mail_log, 'bob@example.com'))
    values = iter((111111, 222222))
    monkeypatch.setattr(
        'portfolio_app.services.auth_service.secrets.randbelow',
        lambda _limit: next(values),
    )
    alice.post('/settings/delete/request')
    alice_code = mail_log[-1][1]
    bob.post('/settings/delete/request')
    bob.post('/settings/delete/verify', data={'code': alice_code})
    with app.app_context():
        assert db.session.get(User, alice_id) is not None
        assert db.session.get(User, bob_id) is not None


def test_account_deletion_cascades_owned_data_without_affecting_other_tenants(
    app, client, mail_log,
):
    alice_id, _, _ = _create_user(app)
    bob_id, _, _ = _create_user(app, email='bob@example.com', username='bob')
    with app.app_context():
        alice_portfolio = Portfolio(user_id=alice_id, name='Alice Portfolio')
        bob_portfolio = Portfolio(user_id=bob_id, name='Bob Portfolio')
        db.session.add_all((
            alice_portfolio,
            bob_portfolio,
            OAuthIdentity(
                user_id=alice_id,
                provider='google',
                provider_subject='preserved-legacy-subject',
            ),
        ))
        db.session.commit()
        alice_portfolio_id = alice_portfolio.id
        bob_portfolio_id = bob_portfolio.id

    _verify(client, _begin(client, mail_log))
    client.post('/settings/delete/request')
    client.post('/settings/delete/verify', data={'code': mail_log[-1][1]})
    with app.app_context():
        assert db.session.get(User, alice_id) is None
        assert db.session.get(Portfolio, alice_portfolio_id) is None
        assert OAuthIdentity.query.filter_by(user_id=alice_id).count() == 0
        assert db.session.get(User, bob_id) is not None
        assert db.session.get(Portfolio, bob_portfolio_id) is not None


def test_account_deletion_rolls_back_when_commit_fails(
    app, client, mail_log, monkeypatch,
):
    user_id, _, _ = _create_user(app)
    _verify(client, _begin(client, mail_log))
    client.post('/settings/delete/request')
    code = mail_log[-1][1]

    def fail_commit(_repository):
        raise SQLAlchemyError('forced commit failure')

    monkeypatch.setattr(
        'portfolio_app.repositories.user_repository.UserRepository.commit',
        fail_commit,
    )
    response = client.post('/settings/delete/verify', data={'code': code})
    assert response.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(User, user_id) is not None


def test_logout_clears_session_and_no_remember_cookie(app, client, mail_log):
    _create_user(app)
    response = _verify(client, _begin(client, mail_log))
    assert not any('remember_token=' in value and 'Expires=' not in value
                   for value in response.headers.getlist('Set-Cookie'))
    assert client.post('/logout').status_code in (302, 303)
    assert '_user_id' not in _auth_session(client)


def test_legacy_remember_cookie_is_expired_on_contact(client):
    client.set_cookie('remember_token', 'pre-cutover-identity')
    response = client.get('/login')
    cookies = response.headers.getlist('Set-Cookie')
    assert any(
        value.startswith('remember_token=;') and 'Expires=' in value
        for value in cookies
    )


def test_auth_generation_rejects_old_identity_even_with_valid_timestamps(app):
    user_id, _, generation = _create_user(app)
    with app.app_context():
        user = db.session.get(User, user_id)
        user.auth_generation += 1
        db.session.commit()
    browser = app.test_client()
    now = datetime.now(timezone.utc).timestamp()
    with browser.session_transaction() as state:
        state['_user_id'] = f'v1:{user_id}:{generation}'
        state['_fresh'] = True
        state[AUTH_ISSUED_AT_KEY] = now
        state[AUTH_LAST_SEEN_AT_KEY] = now
        state[RECENT_AUTH_AT_KEY] = now
    assert browser.get('/settings').status_code in (302, 303)


@pytest.mark.parametrize('path', (
    '/forgot-password', '/reset-password/token', '/change-password',
    '/auth/google', '/auth/google/callback', '/settings/google/disconnect',
))
def test_legacy_auth_routes_are_unavailable(client, path):
    assert client.get(path).status_code == 404
    assert client.post(path).status_code == 404


def test_demo_username_has_no_special_runtime_behavior(app, client, mail_log):
    _create_user(app, email='private-demo@example.com', username='demo')
    _verify(client, _begin(client, mail_log, 'private-demo@example.com'))
    assert client.get('/update-email').status_code == 200


def test_legacy_auth_configuration_and_password_verifiers_are_absent():
    for setting in (
        'GOOGLE_OAUTH_ENABLED', 'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET',
        'GOOGLE_REDIRECT_URI', 'PASSWORD_RESET_TOKEN_EXPIRY_SECONDS',
    ):
        assert not hasattr(Config, setting)
    assert not hasattr(User, 'check_password')
    assert not hasattr(User, 'set_password')
