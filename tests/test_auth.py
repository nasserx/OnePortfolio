"""Authentication test suite — sign-up, login, OTP, sessions, rate limits.

Covers the ``feat/auth-refactor`` flow:

* Sign-ups stage in ``pending_registration``; the live ``user`` row is only
  created after the 6-digit OTP is confirmed.
* Login is blocked for unverified accounts, lets verified accounts in,
  hides the existence of accounts behind a single generic error, and
  trips a 30-minute lockout after 5 consecutive wrong passwords.
* Rate limiting protects ``/register`` (5/h/IP), ``/resend-code``
  (3/h/email), and ``/forgot-password`` (10/h/IP and 3/h/email).

The test file is self-contained: it builds its own Flask app per test so
DB state, the rate-limiter store, and email mocks never leak across tests.
The mail layer is monkey-patched (``send_verification_email`` /
``send_reset_email``) so no SMTP is ever attempted.
"""

import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash

from config import Config
from portfolio_app import create_app, db, limiter
from portfolio_app.models.dividend import Dividend
from portfolio_app.models.oauth_identity import OAuthIdentity
from portfolio_app.models.portfolio import Portfolio
from portfolio_app.models.portfolio_event import PortfolioEvent
from portfolio_app.models.symbol import Symbol
from portfolio_app.models.transaction import Transaction
from portfolio_app.models.user import User
from portfolio_app.models.pending_registration import PendingRegistration
from portfolio_app.repositories.user_repository import UserRepository
from portfolio_app.services.auth_service import AuthService, MAX_OTP_ATTEMPTS
from portfolio_app.services.factory import Services
from portfolio_app.utils import email as email_utils
from portfolio_app.utils.messages import MESSAGES


# ---------------------------------------------------------------------------
# Test configuration
# ---------------------------------------------------------------------------

class _BaseTestConfig(Config):
    """Shared base: in-process SQLite file, CSRF off, rate limiting off."""
    TESTING = True
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key'
    MAIL_SUPPRESS_SEND = True
    RATELIMIT_ENABLED = False
    SQLALCHEMY_DATABASE_URI = None


class _RateLimitedTestConfig(_BaseTestConfig):
    """Used only by the rate-limit tests so the rest of the suite is fast."""
    RATELIMIT_ENABLED = True


class _CsrfTestConfig(_BaseTestConfig):
    """Exercise state-changing auth routes with normal CSRF protection."""
    WTF_CSRF_ENABLED = True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    """Point each test at its own SQLite file and reset the limiter store.

    autouse so any test that builds an app in this module gets fresh state.
    """
    db_path = tmp_path / 'auth.db'
    monkeypatch.setenv('DATABASE_URL', f"sqlite:///{db_path.as_posix()}")
    _BaseTestConfig.SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path.as_posix()}"
    _RateLimitedTestConfig.SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path.as_posix()}"
    # Drain any leftover counters from a previous test.
    try:
        limiter.reset()
    except Exception:
        pass
    yield


@pytest.fixture
def email_log(monkeypatch):
    """Capture every (email, code) pair the app would have sent.

    The app calls ``send_verification_email`` from
    ``portfolio_app.routes.auth`` (and the email module). Patch that
    binding to push into a list and return success.
    """
    captured = []

    def _fake_send_verification(to_email, code):
        captured.append((to_email, code))
        return True

    def _fake_send_reset(to_email, token):
        captured.append((to_email, f'reset:{token}'))
        return True

    def _fake_send_deletion(to_email, code):
        captured.append((to_email, f'deletion:{code}'))
        return True

    monkeypatch.setattr(
        'portfolio_app.routes.auth.send_verification_email', _fake_send_verification
    )
    monkeypatch.setattr(
        'portfolio_app.routes.auth.send_reset_email', _fake_send_reset
    )
    monkeypatch.setattr(
        'portfolio_app.routes.auth.send_deletion_confirmation_email', _fake_send_deletion
    )
    return captured


@pytest.fixture
def app(_isolate_db):
    """Build a fresh Flask app with rate limiting OFF for the bulk of tests."""
    app = create_app(_BaseTestConfig)
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def rate_limited_app(_isolate_db):
    """Same as ``app`` but with rate limiting ENABLED for the limit tests."""
    app = create_app(_RateLimitedTestConfig)
    with app.app_context():
        db.drop_all()
        db.create_all()
    try:
        limiter.reset()
    except Exception:
        pass
    yield app
    with app.app_context():
        db.session.remove()


@pytest.fixture
def rate_limited_client(rate_limited_app):
    return rate_limited_app.test_client()


@pytest.fixture
def csrf_app(_isolate_db):
    app = create_app(_CsrfTestConfig)
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()


@pytest.fixture
def csrf_client(csrf_app):
    return csrf_app.test_client()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register(client, **overrides):
    payload = {
        'email': 'alice@example.com',
        'password': 'CorrectHorse9',
    }
    payload.update(overrides)
    return client.post('/register', data=payload, follow_redirects=False)


def _csrf_token_from(response):
    match = re.search(
        r'name="csrf_token"\s+value="([^"]+)"',
        response.get_data(as_text=True),
    )
    assert match is not None
    return match.group(1)


def _register_with_csrf(client, **overrides):
    token = _csrf_token_from(client.get('/register'))
    payload = {
        'email': 'alice@example.com',
        'password': 'CorrectHorse9',
        'csrf_token': token,
    }
    payload.update(overrides)
    return client.post('/register', data=payload, follow_redirects=False)


def _last_pending(app, email):
    with app.app_context():
        return PendingRegistration.query.filter_by(email=email.lower()).first()


def _pending_verification_state(app, email):
    with app.app_context():
        pending = PendingRegistration.query.filter_by(email=email.lower()).one()
        return (
            pending.verification_code,
            pending.verification_code_expires_at,
            pending.failed_otp_attempts,
        )


def _assert_no_registration_started(app, email_log):
    assert email_log == []
    with app.app_context():
        assert PendingRegistration.query.count() == 0
        assert User.query.count() == 0


def _expire_pending_otp(app, email):
    """Push the OTP expiry into the past so we can exercise the expiry branch."""
    with app.app_context():
        row = PendingRegistration.query.filter_by(email=email.lower()).first()
        assert row is not None
        row.verification_code_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.session.commit()


def _pending_email_state(app, current_email):
    with app.app_context():
        user = User.query.filter_by(email=current_email.lower()).one()
        return (
            user.pending_email,
            user.verification_code,
            user.verification_code_expires_at,
            user.verification_code_failed_attempts,
        )


def _login(client, email, password):
    response = client.post(
        '/login',
        data={'username': email, 'password': password},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)


def _create_persisted_unverified_user(
    app,
    *,
    password='UnverifiedHorse9',
    password_hash=None,
    failed_login_attempts=0,
    locked_until=None,
    last_login=None,
):
    """Create the legacy/import state that current registration avoids."""
    with app.app_context():
        user = User(
            username='persisted_unverified',
            email='persisted-unverified@example.com',
            is_verified=False,
            failed_login_attempts=failed_login_attempts,
            locked_until=locked_until,
            last_login=last_login,
        )
        if password_hash is None:
            user.set_password(password)
        else:
            user.password_hash = password_hash
        db.session.add(user)
        db.session.commit()
        return user.id


def _stage_email_change(client, target_email, password):
    return client.post(
        '/update-email',
        data={'email': target_email, 'password': password},
        follow_redirects=False,
    )


def _assert_stored_otp_digest(stored_value, delivered_code):
    assert delivered_code.isdigit()
    assert len(delivered_code) == 6
    assert stored_value != delivered_code
    assert re.fullmatch(r'[0-9a-f]{64}', stored_value)


def _resend_public_result(client, email):
    """Return the externally visible redirect and flash for one resend."""
    with client.session_transaction() as session:
        session.pop('_flashes', None)
    response = client.post(
        f'/resend-code?email={email}',
        follow_redirects=False,
    )
    with client.session_transaction() as session:
        flashes = tuple(session.pop('_flashes', ()))
    return response.status_code, response.headers.get('Location'), flashes


# ---------------------------------------------------------------------------
# Sign-up tests
# ---------------------------------------------------------------------------

class TestSignup:

    def test_valid_signup_creates_pending_only(self, app, client, email_log):
        resp = _register(client)
        assert resp.status_code in (302, 303)

        with app.app_context():
            assert User.query.count() == 0, "no user row should exist before OTP"
            pending = PendingRegistration.query.filter_by(email='alice@example.com').first()
            assert pending is not None
            assert pending.username == 'alice'
            # Stored hash is bcrypt — never plaintext.
            assert pending.password_hash.startswith('$2')
            assert pending.password_hash != 'CorrectHorse9'
            _assert_stored_otp_digest(
                pending.verification_code,
                email_log[-1][1],
            )

        # Exactly one verification email was queued.
        assert len(email_log) == 1
        assert email_log[0][0] == 'alice@example.com'

    def test_signup_does_not_require_username_or_confirm_password(self, app, client, email_log):
        resp = client.post(
            '/register',
            data={'email': 'simple@example.com', 'password': 'CorrectHorse9'},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)
        with app.app_context():
            pending = PendingRegistration.query.filter_by(email='simple@example.com').one()
            assert pending.username == 'simple'
        assert email_log[-1][0] == 'simple@example.com'

    def test_duplicate_email_blocked_before_db_write(self, app, client, email_log):
        # First sign-up succeeds and verifies, becoming a real user.
        _register(client)
        pending_code = email_log[-1][1]
        client.post('/verify-code?email=alice@example.com', data={'code': pending_code})
        client.post('/logout')  # verify auto-logs-in; drop the session

        # Second sign-up with the same email is rejected before any DB write
        # happens for the new attempt.
        resp = _register(
            client, email='alice@example.com', password='AnotherPw9999',
        )
        assert resp.status_code == 200  # form re-rendered with error
        with app.app_context():
            # Still exactly one user, no pending rows.
            assert User.query.count() == 1
            assert PendingRegistration.query.count() == 0

    def test_generated_username_gets_suffix_on_collision(self, app, client, email_log):
        _register(client)
        pending_code = email_log[-1][1]
        client.post('/verify-code?email=alice@example.com', data={'code': pending_code})
        client.post('/logout')

        resp = _register(
            client, email='alice@different.example',
            password='AnotherPw9999',
        )
        assert resp.status_code in (302, 303)
        with app.app_context():
            assert User.query.count() == 1
            pending = PendingRegistration.query.filter_by(email='alice@different.example').one()
            assert pending.username == 'alice_2'

    def test_weak_password_rejected_at_form_layer(self, app, client, email_log):
        resp = _register(client, password='short')
        assert resp.status_code == 200  # form rendered with error, not a redirect
        with app.app_context():
            assert PendingRegistration.query.count() == 0
            assert User.query.count() == 0
        # Email service was never invoked.
        assert email_log == []

    def test_expired_otp_rejected(self, app, client, email_log):
        _register(client)
        _expire_pending_otp(app, 'alice@example.com')
        code = email_log[-1][1]

        resp = client.post('/verify-code?email=alice@example.com', data={'code': code})
        # Verification page re-rendered with the expiry error.
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert 'expired' in body.lower()
        with app.app_context():
            # Still pending, no user created.
            assert User.query.count() == 0
            assert PendingRegistration.query.count() == 1

    def test_failed_pending_registration_otp_attempts_increment_and_lock_out(
        self, app, client, email_log,
    ):
        _register(client)

        for attempt in range(1, MAX_OTP_ATTEMPTS):
            resp = client.post(
                '/verify-code?email=alice@example.com',
                data={'code': '000000'},
            )
            assert resp.status_code == 200
            with app.app_context():
                pending = PendingRegistration.query.filter_by(
                    email='alice@example.com',
                ).one()
                assert pending.failed_otp_attempts == attempt

        resp = client.post(
            '/verify-code?email=alice@example.com',
            data={'code': '000000'},
        )
        assert resp.status_code == 200
        with app.app_context():
            assert PendingRegistration.query.filter_by(
                email='alice@example.com',
            ).count() == 0
            assert User.query.count() == 0

    def test_valid_otp_creates_user_deletes_pending(self, app, client, email_log):
        _register(client)
        code = email_log[-1][1]

        resp = client.post(
            '/verify-code?email=alice@example.com',
            data={'code': code},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

        with app.app_context():
            assert PendingRegistration.query.count() == 0
            user = User.query.filter_by(email='alice@example.com').first()
            assert user is not None
            assert user.is_verified is True
            assert user.password_hash.startswith('$2')

    def test_resignup_cannot_replace_pending_credentials(self, app, client, email_log):
        original_password = 'CorrectHorse9'
        substituted_password = 'SecondPw9999'

        _register(client, password=original_password)
        original_code = email_log[-1][1]

        # A second unauthenticated attempt cannot replace either the staged
        # password or the verification path for the original registration.
        attacker = app.test_client()
        resp = _register(
            attacker,
            email='alice@example.com',
            password=substituted_password,
        )
        assert resp.status_code == 200
        assert len(email_log) == 1

        resp = client.post(
            '/verify-code?email=alice@example.com',
            data={'code': original_code},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)
        client.post('/logout')

        # The attacker's substituted password cannot authenticate the
        # resulting account, while the victim's original password still can.
        resp = attacker.post(
            '/login',
            data={
                'username': 'alice@example.com',
                'password': substituted_password,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 200
        with attacker.session_transaction() as sess:
            assert sess.get('_user_id') is None

        fresh_client = app.test_client()
        resp = fresh_client.post(
            '/login',
            data={
                'username': 'alice@example.com',
                'password': original_password,
            },
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)
        with fresh_client.session_transaction() as sess:
            assert sess.get('_user_id') is not None


class TestResendVerificationCode:

    def test_get_is_not_allowed_and_does_not_mutate_or_send(
        self, app, client, email_log,
    ):
        _register(client)
        state_before = _pending_verification_state(app, 'alice@example.com')
        emails_before = list(email_log)

        response = client.get(
            '/resend-code?email=alice@example.com',
            follow_redirects=False,
        )

        assert response.status_code == 405
        assert email_log == emails_before
        assert _pending_verification_state(
            app, 'alice@example.com',
        ) == state_before

    def test_csrf_protected_post_resends_once_and_new_code_verifies(
        self, csrf_app, csrf_client, email_log, monkeypatch,
    ):
        codes = iter((1, 2))
        monkeypatch.setattr(
            'portfolio_app.services.auth_service.secrets.randbelow',
            lambda upper_bound: next(codes),
        )
        _register_with_csrf(csrf_client)
        assert email_log == [('alice@example.com', '100001')]
        state_before_resend = _pending_verification_state(
            csrf_app, 'alice@example.com',
        )

        verify_page = csrf_client.get(
            '/verify-code?email=alice@example.com',
        )
        verify_html = verify_page.get_data(as_text=True)
        resend_form = re.search(
            r'<form\b[^>]*action="([^"]*resend-code[^"]*)"[^>]*>(.*?)</form>',
            verify_html,
            re.DOTALL,
        )
        assert resend_form is not None
        assert re.search(r'\bmethod="POST"', resend_form.group(0), re.IGNORECASE)
        assert 'href="/resend-code' not in verify_html
        csrf_match = re.search(
            r'name="csrf_token"\s+value="([^"]+)"',
            resend_form.group(2),
        )
        assert csrf_match is not None
        response = csrf_client.post(
            resend_form.group(1),
            data={'csrf_token': csrf_match.group(1)},
            follow_redirects=False,
        )

        assert response.status_code in (302, 303)
        assert '/verify-code' in response.headers['Location']
        assert email_log == [
            ('alice@example.com', '100001'),
            ('alice@example.com', '100002'),
        ]
        state_after_resend = _pending_verification_state(
            csrf_app, 'alice@example.com',
        )
        assert state_after_resend[0] != state_before_resend[0]
        _assert_stored_otp_digest(state_after_resend[0], '100002')

        verify_page = csrf_client.get(response.headers['Location'])
        verify_token = _csrf_token_from(verify_page)
        verified = csrf_client.post(
            '/verify-code?email=alice@example.com',
            data={'code': '100002', 'csrf_token': verify_token},
            follow_redirects=False,
        )
        assert verified.status_code in (302, 303)
        with csrf_app.app_context():
            assert PendingRegistration.query.filter_by(
                email='alice@example.com',
            ).first() is None
            assert User.query.filter_by(email='alice@example.com').one()

    def test_post_without_csrf_does_not_mutate_or_send(
        self, csrf_app, csrf_client, email_log,
    ):
        _register_with_csrf(csrf_client)
        state_before = _pending_verification_state(
            csrf_app, 'alice@example.com',
        )
        emails_before = list(email_log)

        response = csrf_client.post(
            '/resend-code?email=alice@example.com',
            follow_redirects=False,
        )

        assert response.status_code in (302, 303)
        assert email_log == emails_before
        assert _pending_verification_state(
            csrf_app, 'alice@example.com',
        ) == state_before

    def test_post_without_email_does_not_mutate_or_send(
        self, app, client, email_log,
    ):
        _register(client)
        state_before = _pending_verification_state(app, 'alice@example.com')
        emails_before = list(email_log)

        response = client.post('/resend-code', follow_redirects=False)

        assert response.status_code in (302, 303)
        assert '/register' in response.headers['Location']
        assert email_log == emails_before
        assert _pending_verification_state(
            app, 'alice@example.com',
        ) == state_before


class TestResendEnumerationNormalization:

    def test_pending_registration_and_unknown_share_public_result(
        self, app, client, email_log, monkeypatch,
    ):
        codes = iter(('111111', '222222'))
        monkeypatch.setattr(
            AuthService,
            '_make_verification_code',
            staticmethod(lambda: next(codes)),
        )
        _register(client)
        original_digest = _pending_verification_state(
            app, 'alice@example.com',
        )[0]
        _expire_pending_otp(app, 'alice@example.com')

        live_result = _resend_public_result(client, 'alice@example.com')

        assert live_result[2] == ((
            'info', MESSAGES['VERIFICATION_CODE_RESEND_RESULT'],
        ),)
        rotated_digest = _pending_verification_state(
            app, 'alice@example.com',
        )[0]
        assert rotated_digest != original_digest
        _assert_stored_otp_digest(rotated_digest, '222222')
        assert email_log == [
            ('alice@example.com', '111111'),
            ('alice@example.com', '222222'),
        ]

        emails_before_unknown = list(email_log)
        unknown_result = _resend_public_result(client, 'unknown@example.com')

        assert unknown_result[0] == live_result[0]
        assert unknown_result[1].split('?', 1)[0] == live_result[1].split('?', 1)[0]
        assert unknown_result[2] == live_result[2]
        assert email_log == emails_before_unknown
        with app.app_context():
            assert PendingRegistration.query.count() == 1
            assert User.query.count() == 0

        rejected_old_code = client.post(
            '/verify-code?email=alice@example.com',
            data={'code': '111111'},
        )
        assert rejected_old_code.status_code == 200
        accepted_new_code = client.post(
            '/verify-code?email=alice@example.com',
            data={'code': '222222'},
            follow_redirects=False,
        )
        assert accepted_new_code.status_code in (302, 303)
        with app.app_context():
            assert PendingRegistration.query.count() == 0
            assert User.query.filter_by(email='alice@example.com').one()

    def test_pending_email_and_unknown_share_public_result(
        self, app, client, email_log, monkeypatch,
    ):
        password = 'CorrectHorse9'
        _signup_and_verify(app, client, email_log, password=password)
        _login(client, 'alice@example.com', password)
        codes = iter(('333333', '444444'))
        monkeypatch.setattr(
            AuthService,
            '_make_verification_code',
            staticmethod(lambda: next(codes)),
        )
        _stage_email_change(client, 'target@example.com', password)
        original_digest = _pending_email_state(
            app, 'alice@example.com',
        )[1]

        live_result = _resend_public_result(client, 'target@example.com')

        assert live_result[2] == ((
            'info', MESSAGES['VERIFICATION_CODE_RESEND_RESULT'],
        ),)
        pending_state = _pending_email_state(app, 'alice@example.com')
        assert pending_state[1] != original_digest
        _assert_stored_otp_digest(pending_state[1], '444444')
        assert email_log[-2:] == [
            ('target@example.com', '333333'),
            ('target@example.com', '444444'),
        ]

        emails_before_unknown = list(email_log)
        unknown_result = _resend_public_result(client, 'unknown@example.com')

        assert unknown_result[0] == live_result[0]
        assert unknown_result[1].split('?', 1)[0] == live_result[1].split('?', 1)[0]
        assert unknown_result[2] == live_result[2]
        assert email_log == emails_before_unknown
        assert _pending_email_state(
            app, 'alice@example.com',
        ) == pending_state

        rejected_old_code = client.post(
            '/verify-code?email=target@example.com',
            data={'code': '333333'},
        )
        assert rejected_old_code.status_code == 200
        accepted_new_code = client.post(
            '/verify-code?email=target@example.com',
            data={'code': '444444'},
            follow_redirects=False,
        )
        assert accepted_new_code.status_code in (302, 303)
        with app.app_context():
            user = User.query.filter_by(email='target@example.com').one()
            assert user.pending_email is None
            assert user.verification_code is None

    def test_expired_pending_email_and_unknown_share_public_result(
        self, app, client, email_log,
    ):
        password = 'CorrectHorse9'
        _signup_and_verify(app, client, email_log, password=password)
        _login(client, 'alice@example.com', password)
        _stage_email_change(client, 'expired@example.com', password)
        with app.app_context():
            user = User.query.filter_by(email='alice@example.com').one()
            user.verification_code_expires_at = (
                datetime.now(timezone.utc) - timedelta(minutes=1)
            )
            db.session.commit()
        emails_before = list(email_log)

        expired_result = _resend_public_result(client, 'expired@example.com')
        unknown_result = _resend_public_result(client, 'expired@example.com')

        assert expired_result == unknown_result
        assert expired_result[2] == ((
            'info', MESSAGES['VERIFICATION_CODE_RESEND_RESULT'],
        ),)
        assert email_log == emails_before
        assert _pending_email_state(app, 'alice@example.com') == (
            None, None, None, 0,
        )

    def test_expired_registration_is_purged_without_public_disclosure(
        self, app, client, email_log,
    ):
        _register(client, email='expired-registration@example.com')
        with app.app_context():
            pending = PendingRegistration.query.filter_by(
                email='expired-registration@example.com',
            ).one()
            pending.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            db.session.commit()
        emails_before = list(email_log)

        expired_result = _resend_public_result(
            client, 'expired-registration@example.com',
        )
        unknown_result = _resend_public_result(
            client, 'expired-registration@example.com',
        )

        assert expired_result == unknown_result
        assert email_log == emails_before
        with app.app_context():
            assert PendingRegistration.query.filter_by(
                email='expired-registration@example.com',
            ).first() is None
            assert User.query.count() == 0

    def test_delivery_success_and_failure_share_public_result(
        self, app, client, email_log, monkeypatch,
    ):
        _register(client, email='delivery@example.com')
        codes = iter(('555555', '666666'))
        monkeypatch.setattr(
            AuthService,
            '_make_verification_code',
            staticmethod(lambda: next(codes)),
        )
        delivery_attempts = []

        def failed_delivery(email, code):
            delivery_attempts.append(('failed', email, code))
            return False

        monkeypatch.setattr(
            'portfolio_app.routes.auth.send_verification_email',
            failed_delivery,
        )
        failed_result = _resend_public_result(client, 'delivery@example.com')
        failed_digest = _pending_verification_state(
            app, 'delivery@example.com',
        )[0]
        _assert_stored_otp_digest(failed_digest, '555555')

        def successful_delivery(email, code):
            delivery_attempts.append(('sent', email, code))
            return True

        monkeypatch.setattr(
            'portfolio_app.routes.auth.send_verification_email',
            successful_delivery,
        )
        successful_result = _resend_public_result(
            client, 'delivery@example.com',
        )
        successful_digest = _pending_verification_state(
            app, 'delivery@example.com',
        )[0]

        assert successful_result == failed_result
        assert delivery_attempts == [
            ('failed', 'delivery@example.com', '555555'),
            ('sent', 'delivery@example.com', '666666'),
        ]
        assert successful_digest != failed_digest
        _assert_stored_otp_digest(successful_digest, '666666')

    def test_message_construction_failure_shares_unknown_public_result(
        self, app, client, email_log, monkeypatch, caplog,
    ):
        _register(client, email='construction@example.com')
        monkeypatch.setattr(
            AuthService,
            '_make_verification_code',
            staticmethod(lambda: '777777'),
        )

        def failed_message_construction(*args, **kwargs):
            raise RuntimeError('simulated message construction failure')

        monkeypatch.setattr(email_utils, 'Message', failed_message_construction)
        monkeypatch.setattr(
            'portfolio_app.routes.auth.send_verification_email',
            email_utils.send_verification_email,
        )

        live_result = _resend_public_result(client, 'construction@example.com')
        stored_digest = _pending_verification_state(
            app, 'construction@example.com',
        )[0]
        unknown_result = _resend_public_result(client, 'unknown@example.com')

        assert unknown_result[0] == live_result[0]
        assert unknown_result[1].split('?', 1)[0] == live_result[1].split('?', 1)[0]
        assert unknown_result[2] == live_result[2]
        _assert_stored_otp_digest(stored_digest, '777777')
        assert 'Failed to send verification code to construction@example.com' in caplog.text
        assert '777777' not in caplog.text
        assert stored_digest not in caplog.text

    def test_unknown_resend_creates_no_state_or_delivery(
        self, app, client, email_log,
    ):
        result = _resend_public_result(client, 'unknown@example.com')

        assert result[2] == ((
            'info', MESSAGES['VERIFICATION_CODE_RESEND_RESULT'],
        ),)
        assert email_log == []
        with app.app_context():
            assert User.query.count() == 0
            assert PendingRegistration.query.count() == 0


class TestCsrfRedirectSafety:

    def test_local_referrer_is_preserved_with_feedback_and_no_mutation(
        self, csrf_app, csrf_client, email_log,
    ):
        response = csrf_client.post(
            '/register',
            data={
                'email': 'alice@example.com',
                'password': 'CorrectHorse9',
            },
            headers={'Referer': '/register?source=csrf'},
            follow_redirects=False,
        )

        assert response.status_code in (302, 303)
        assert response.headers['Location'] == '/register?source=csrf'
        _assert_no_registration_started(csrf_app, email_log)

        destination = csrf_client.get(response.headers['Location'])
        assert MESSAGES['CSRF_CHECK_FAILED'] in destination.get_data(as_text=True)

    @pytest.mark.parametrize(
        'referrer',
        (
            'https://evil.example/phish',
            '//evil.example/phish',
            'http://[malformed',
            'http://localhost/register?source=csrf',
            None,
        ),
        ids=(
            'external-https',
            'scheme-relative-external',
            'malformed',
            'same-origin-absolute-not-in-local-helper-contract',
            'missing',
        ),
    )
    def test_unsafe_or_absent_referrer_uses_internal_fallback_without_mutation(
        self, csrf_app, csrf_client, email_log, referrer,
    ):
        headers = {'Referer': referrer} if referrer is not None else {}
        response = csrf_client.post(
            '/register',
            data={
                'email': 'alice@example.com',
                'password': 'CorrectHorse9',
            },
            headers=headers,
            follow_redirects=False,
        )

        assert response.status_code in (302, 303)
        assert response.headers['Location'] == '/'
        assert response.headers['Location'] != referrer
        _assert_no_registration_started(csrf_app, email_log)

    def test_json_csrf_failure_preserves_json_response_without_redirect_or_mutation(
        self, csrf_app, csrf_client, email_log,
    ):
        response = csrf_client.post(
            '/register',
            json={
                'email': 'alice@example.com',
                'password': 'CorrectHorse9',
            },
            headers={'Referer': 'https://evil.example/phish'},
            follow_redirects=False,
        )

        assert response.status_code == 400
        assert response.get_json() == {
            'success': False,
            'error': MESSAGES['SESSION_EXPIRED'],
        }
        assert 'Location' not in response.headers
        _assert_no_registration_started(csrf_app, email_log)


# ---------------------------------------------------------------------------
# Login tests
# ---------------------------------------------------------------------------

def _signup_and_verify(app, client, email_log, **kw):
    """Register → verify → logout, leaving a clean unauthenticated client."""
    _register(client, **kw)
    code = email_log[-1][1]
    email = kw.get('email', 'alice@example.com')
    client.post(f'/verify-code?email={email}', data={'code': code})
    # Verification auto-logs the user in; drop the session so callers start
    # from an unauthenticated state.
    client.post('/logout')
    return 'alice'


class TestPendingEmailReservationLifecycle:

    def test_initiation_requires_password_and_stores_normalized_live_state(
        self, app, client, email_log,
    ):
        password = 'CorrectHorse9'
        _signup_and_verify(app, client, email_log, password=password)
        _login(client, 'alice@example.com', password)
        emails_before = list(email_log)

        rejected = _stage_email_change(
            client,
            'Target@Example.com',
            'WrongPassword9',
        )
        assert rejected.status_code == 200
        assert _pending_email_state(app, 'alice@example.com') == (
            None, None, None, 0,
        )
        assert email_log == emails_before

        accepted = _stage_email_change(
            client,
            ' Target@Example.com ',
            password,
        )
        assert accepted.status_code in (302, 303)
        assert '/verify-code' in accepted.headers['Location']

        pending_email, code, expires_at, failed_attempts = _pending_email_state(
            app, 'alice@example.com',
        )
        assert pending_email == 'target@example.com'
        assert code
        assert expires_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)
        assert failed_attempts == 0
        delivered_code = email_log[-1][1]
        assert email_log[-1][0] == 'target@example.com'
        _assert_stored_otp_digest(code, delivered_code)

    def test_successful_verification_applies_email_and_clears_pending_state(
        self, app, client, email_log,
    ):
        password = 'CorrectHorse9'
        _signup_and_verify(app, client, email_log, password=password)
        _login(client, 'alice@example.com', password)
        assert _stage_email_change(
            client, 'new-alice@example.com', password,
        ).status_code in (302, 303)
        code = email_log[-1][1]

        response = client.post(
            '/verify-code?email=new-alice@example.com',
            data={'code': code},
            follow_redirects=False,
        )

        assert response.status_code in (302, 303)
        with app.app_context():
            user = User.query.filter_by(email='new-alice@example.com').one()
            assert user.pending_email is None
            assert user.verification_code is None
            assert user.verification_code_expires_at is None
            assert user.verification_code_failed_attempts == 0
            assert User.query.filter_by(email='alice@example.com').first() is None

    def test_live_pending_email_blocks_another_users_email_change(
        self, app, client, email_log,
    ):
        alice_password = 'CorrectHorse9'
        bob_password = 'CorrectHorse10'
        _signup_and_verify(app, client, email_log, password=alice_password)
        bob_client = app.test_client()
        _signup_and_verify(
            app,
            bob_client,
            email_log,
            email='bob@example.com',
            password=bob_password,
        )

        _login(client, 'alice@example.com', alice_password)
        assert _stage_email_change(
            client, 'claimed@example.com', alice_password,
        ).status_code in (302, 303)
        _login(bob_client, 'bob@example.com', bob_password)
        rejected = _stage_email_change(
            bob_client, 'CLAIMED@example.com', bob_password,
        )

        assert rejected.status_code == 200
        assert _pending_email_state(app, 'bob@example.com') == (
            None, None, None, 0,
        )
        assert _pending_email_state(app, 'alice@example.com')[0] == (
            'claimed@example.com'
        )

    def test_expired_pending_email_is_cleaned_and_does_not_block_email_change(
        self, app, client, email_log,
    ):
        alice_password = 'CorrectHorse9'
        bob_password = 'CorrectHorse10'
        _signup_and_verify(app, client, email_log, password=alice_password)
        bob_client = app.test_client()
        _signup_and_verify(
            app,
            bob_client,
            email_log,
            email='bob@example.com',
            password=bob_password,
        )

        _login(client, 'alice@example.com', alice_password)
        _stage_email_change(client, 'released@example.com', alice_password)
        with app.app_context():
            alice = User.query.filter_by(email='alice@example.com').one()
            alice.verification_code_failed_attempts = 3
            alice.verification_code_expires_at = (
                datetime.now(timezone.utc) - timedelta(minutes=1)
            )
            db.session.commit()

        _login(bob_client, 'bob@example.com', bob_password)
        accepted = _stage_email_change(
            bob_client, 'Released@Example.com', bob_password,
        )

        assert accepted.status_code in (302, 303)
        assert _pending_email_state(app, 'alice@example.com') == (
            None, None, None, 0,
        )
        bob_state = _pending_email_state(app, 'bob@example.com')
        assert bob_state[0] == 'released@example.com'
        assert bob_state[1]
        assert bob_state[2]
        assert bob_state[3] == 0

    def test_live_pending_email_blocks_registration(
        self, app, client, email_log,
    ):
        password = 'CorrectHorse9'
        _signup_and_verify(app, client, email_log, password=password)
        _login(client, 'alice@example.com', password)
        _stage_email_change(client, 'reserved@example.com', password)
        emails_before = list(email_log)

        response = _register(
            app.test_client(),
            email='RESERVED@example.com',
            password='AnotherHorse9',
        )

        assert response.status_code == 200
        assert email_log == emails_before
        with app.app_context():
            assert PendingRegistration.query.filter_by(
                email='reserved@example.com',
            ).first() is None
        assert _pending_email_state(app, 'alice@example.com')[0] == (
            'reserved@example.com'
        )

    @pytest.mark.parametrize(
        'missing_field',
        ['verification_code', 'verification_code_expires_at'],
    )
    def test_incomplete_pending_email_state_is_non_reserving(
        self, app, client, email_log, missing_field,
    ):
        password = 'CorrectHorse9'
        _signup_and_verify(app, client, email_log, password=password)
        _login(client, 'alice@example.com', password)
        _stage_email_change(client, 'released@example.com', password)
        with app.app_context():
            alice = User.query.filter_by(email='alice@example.com').one()
            alice.verification_code_failed_attempts = 3
            setattr(alice, missing_field, None)
            db.session.commit()

        response = _register(
            app.test_client(),
            email='released@example.com',
            password='AnotherHorse9',
        )

        assert response.status_code in (302, 303)
        assert _pending_email_state(app, 'alice@example.com') == (
            None, None, None, 0,
        )
        with app.app_context():
            assert PendingRegistration.query.filter_by(
                email='released@example.com',
            ).one()

    def test_expired_pending_email_does_not_block_registration(
        self, app, client, email_log,
    ):
        password = 'CorrectHorse9'
        _signup_and_verify(app, client, email_log, password=password)
        _login(client, 'alice@example.com', password)
        _stage_email_change(client, 'released@example.com', password)
        with app.app_context():
            alice = User.query.filter_by(email='alice@example.com').one()
            alice.verification_code_expires_at = (
                datetime.now(timezone.utc) - timedelta(minutes=1)
            )
            db.session.commit()

        response = _register(
            app.test_client(),
            email='Released@Example.com',
            password='AnotherHorse9',
        )

        assert response.status_code in (302, 303)
        assert _pending_email_state(app, 'alice@example.com') == (
            None, None, None, 0,
        )
        with app.app_context():
            pending = PendingRegistration.query.filter_by(
                email='released@example.com',
            ).one()
            assert pending.verification_code
            assert pending.expires_at

    def test_expired_pending_email_cannot_shadow_registration_verification(
        self, app, client, email_log,
    ):
        password = 'CorrectHorse9'
        _signup_and_verify(app, client, email_log, password=password)
        registration_client = app.test_client()
        assert _register(
            registration_client,
            email='future-owner@example.com',
            password='AnotherHorse9',
        ).status_code in (302, 303)
        registration_code = email_log[-1][1]

        # Represent stale overlapping state from an older deployment/race.
        with app.app_context():
            alice = User.query.filter_by(email='alice@example.com').one()
            alice.pending_email = 'future-owner@example.com'
            alice.verification_code = 'a' * 64
            alice.verification_code_expires_at = (
                datetime.now(timezone.utc) - timedelta(minutes=1)
            )
            alice.verification_code_failed_attempts = 2
            db.session.commit()

        verified = registration_client.post(
            '/verify-code?email=future-owner@example.com',
            data={'code': registration_code},
            follow_redirects=False,
        )

        assert verified.status_code in (302, 303)
        assert _pending_email_state(app, 'alice@example.com') == (
            None, None, None, 0,
        )
        with app.app_context():
            assert User.query.filter_by(email='future-owner@example.com').one()
            assert PendingRegistration.query.filter_by(
                email='future-owner@example.com',
            ).first() is None

    def test_live_pending_registration_blocks_email_change(
        self, app, client, email_log,
    ):
        password = 'CorrectHorse9'
        _signup_and_verify(app, client, email_log, password=password)
        assert _register(
            app.test_client(),
            email='staged@example.com',
            password='AnotherHorse9',
        ).status_code in (302, 303)

        _login(client, 'alice@example.com', password)
        rejected = _stage_email_change(
            client, 'STAGED@example.com', password,
        )

        assert rejected.status_code == 200
        assert _pending_email_state(app, 'alice@example.com') == (
            None, None, None, 0,
        )
        with app.app_context():
            assert PendingRegistration.query.filter_by(
                email='staged@example.com',
            ).one()

    def test_expired_pending_registration_does_not_block_email_change(
        self, app, client, email_log,
    ):
        password = 'CorrectHorse9'
        _signup_and_verify(app, client, email_log, password=password)
        _register(
            app.test_client(),
            email='staged@example.com',
            password='AnotherHorse9',
        )
        with app.app_context():
            pending = PendingRegistration.query.filter_by(
                email='staged@example.com',
            ).one()
            pending.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            db.session.commit()

        _login(client, 'alice@example.com', password)
        accepted = _stage_email_change(client, 'staged@example.com', password)

        assert accepted.status_code in (302, 303)
        with app.app_context():
            assert PendingRegistration.query.filter_by(
                email='staged@example.com',
            ).first() is None
        state = _pending_email_state(app, 'alice@example.com')
        assert state[0] == 'staged@example.com'
        assert state[1]
        assert state[2]

    def test_live_email_change_resend_rotates_code_and_resets_attempts(
        self, app, client, email_log, monkeypatch,
    ):
        password = 'CorrectHorse9'
        _signup_and_verify(app, client, email_log, password=password)
        _login(client, 'alice@example.com', password)
        monkeypatch.setattr(
            AuthService,
            '_make_verification_code',
            staticmethod(lambda: '111111'),
        )
        _stage_email_change(client, 'resend@example.com', password)
        assert email_log[-1] == ('resend@example.com', '111111')
        with app.app_context():
            alice = User.query.filter_by(email='alice@example.com').one()
            alice.verification_code_failed_attempts = 3
            old_expiry = datetime.now(timezone.utc) + timedelta(minutes=1)
            alice.verification_code_expires_at = old_expiry
            old_digest = alice.verification_code
            db.session.commit()
        monkeypatch.setattr(
            AuthService,
            '_make_verification_code',
            staticmethod(lambda: '222222'),
        )
        emails_before = len(email_log)

        response = client.post(
            '/resend-code?email=resend@example.com',
            follow_redirects=False,
        )

        assert response.status_code in (302, 303)
        state = _pending_email_state(app, 'alice@example.com')
        assert state[0] == 'resend@example.com'
        assert state[1] != old_digest
        _assert_stored_otp_digest(state[1], '222222')
        assert state[2].replace(tzinfo=timezone.utc) > old_expiry
        assert state[3] == 0
        assert len(email_log) == emails_before + 1
        assert email_log[-1] == ('resend@example.com', '222222')

    def test_expired_email_change_resend_cleans_state_and_restart_reclaims(
        self, app, client, email_log,
    ):
        password = 'CorrectHorse9'
        _signup_and_verify(app, client, email_log, password=password)
        _login(client, 'alice@example.com', password)
        _stage_email_change(client, 'restart@example.com', password)
        with app.app_context():
            alice = User.query.filter_by(email='alice@example.com').one()
            alice.verification_code_failed_attempts = 4
            alice.verification_code_expires_at = (
                datetime.now(timezone.utc) - timedelta(minutes=1)
            )
            db.session.commit()
        emails_before = list(email_log)

        resend = client.post(
            '/resend-code?email=restart@example.com',
            follow_redirects=False,
        )

        assert resend.status_code in (302, 303)
        assert email_log == emails_before
        assert _pending_email_state(app, 'alice@example.com') == (
            None, None, None, 0,
        )

        restarted = _stage_email_change(client, 'restart@example.com', password)
        assert restarted.status_code in (302, 303)
        state = _pending_email_state(app, 'alice@example.com')
        assert state[0] == 'restart@example.com'
        assert state[1]
        assert state[2]
        assert state[3] == 0
        assert len(email_log) == len(emails_before) + 1

    def test_five_live_incorrect_codes_clear_complete_pending_email_state(
        self, app, client, email_log,
    ):
        password = 'CorrectHorse9'
        _signup_and_verify(app, client, email_log, password=password)
        _login(client, 'alice@example.com', password)
        _stage_email_change(client, 'attempts@example.com', password)

        for _ in range(MAX_OTP_ATTEMPTS):
            response = client.post(
                '/verify-code?email=attempts@example.com',
                data={'code': '000000'},
                follow_redirects=False,
            )
            assert response.status_code == 200

        assert _pending_email_state(app, 'alice@example.com') == (
            None, None, None, 0,
        )


class TestEmailChangeEnumerationHardening:

    @staticmethod
    def _assert_current_password_failure(response):
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert MESSAGES['CURRENT_PASSWORD_INCORRECT'] in body
        assert MESSAGES['EMAIL_IN_USE'] not in body

    def test_wrong_password_hides_all_target_availability_states(
        self, app, client, email_log,
    ):
        alice_password = 'CorrectHorse9'
        bob_password = 'CorrectHorse10'
        _signup_and_verify(app, client, email_log, password=alice_password)

        bob_client = app.test_client()
        _signup_and_verify(
            app,
            bob_client,
            email_log,
            email='bob@example.com',
            password=bob_password,
        )
        _login(bob_client, 'bob@example.com', bob_password)
        assert _stage_email_change(
            bob_client,
            'reserved@example.com',
            bob_password,
        ).status_code in (302, 303)

        assert _register(
            app.test_client(),
            email='staged@example.com',
            password='AnotherHorse9',
        ).status_code in (302, 303)

        _login(client, 'alice@example.com', alice_password)
        emails_before = list(email_log)
        bob_pending_before = _pending_email_state(app, 'bob@example.com')
        with app.app_context():
            staged = PendingRegistration.query.filter_by(
                email='staged@example.com',
            ).one()
            staged_before = (
                staged.password_hash,
                staged.verification_code,
                staged.verification_code_expires_at,
                staged.failed_otp_attempts,
            )

        targets = (
            'available@example.com',
            'bob@example.com',
            'reserved@example.com',
            'staged@example.com',
            'alice@example.com',
        )
        for target in targets:
            response = _stage_email_change(
                client,
                target,
                'WrongPassword9',
            )
            self._assert_current_password_failure(response)

        assert email_log == emails_before
        assert _pending_email_state(app, 'alice@example.com') == (
            None, None, None, 0,
        )
        assert _pending_email_state(app, 'bob@example.com') == bob_pending_before
        with app.app_context():
            staged = PendingRegistration.query.filter_by(
                email='staged@example.com',
            ).one()
            assert (
                staged.password_hash,
                staged.verification_code,
                staged.verification_code_expires_at,
                staged.failed_otp_attempts,
            ) == staged_before

    def test_wrong_password_skips_availability_and_otp_generation(
        self, app, client, email_log, monkeypatch,
    ):
        password = 'CorrectHorse9'
        _signup_and_verify(app, client, email_log, password=password)
        _login(client, 'alice@example.com', password)
        emails_before = list(email_log)

        monkeypatch.setattr(
            AuthService,
            'email_is_unavailable',
            lambda *args, **kwargs: pytest.fail(
                'availability must not be evaluated before password verification'
            ),
        )
        monkeypatch.setattr(
            AuthService,
            '_make_verification_code',
            staticmethod(lambda: pytest.fail(
                'wrong-password email change must not generate an OTP'
            )),
        )

        response = _stage_email_change(
            client,
            'available@example.com',
            'WrongPassword9',
        )

        self._assert_current_password_failure(response)
        assert email_log == emails_before
        assert _pending_email_state(app, 'alice@example.com') == (
            None, None, None, 0,
        )

    def test_correct_password_preserves_unavailable_and_success_contracts(
        self, app, client, email_log,
    ):
        alice_password = 'CorrectHorse9'
        _signup_and_verify(app, client, email_log, password=alice_password)
        _signup_and_verify(
            app,
            app.test_client(),
            email_log,
            email='bob@example.com',
            password='CorrectHorse10',
        )
        _login(client, 'alice@example.com', alice_password)
        emails_before = list(email_log)

        for target in ('bob@example.com', 'alice@example.com'):
            rejected = _stage_email_change(client, target, alice_password)
            assert rejected.status_code == 200
            body = rejected.get_data(as_text=True)
            assert MESSAGES['EMAIL_IN_USE'] in body
            assert MESSAGES['CURRENT_PASSWORD_INCORRECT'] not in body

        assert email_log == emails_before
        assert _pending_email_state(app, 'alice@example.com') == (
            None, None, None, 0,
        )

        accepted = _stage_email_change(
            client,
            ' Available@Example.com ',
            alice_password,
        )

        assert accepted.status_code in (302, 303)
        assert '/verify-code' in accepted.headers['Location']
        assert email_log[-1][0] == 'available@example.com'
        pending_email, digest, expires_at, failed_attempts = (
            _pending_email_state(app, 'alice@example.com')
        )
        assert pending_email == 'available@example.com'
        assert digest
        assert expires_at
        assert failed_attempts == 0

    def test_malformed_email_is_rejected_before_service_execution(
        self, app, client, email_log, monkeypatch,
    ):
        password = 'CorrectHorse9'
        _signup_and_verify(app, client, email_log, password=password)
        _login(client, 'alice@example.com', password)
        emails_before = list(email_log)

        monkeypatch.setattr(
            AuthService,
            'update_email',
            lambda *args, **kwargs: pytest.fail(
                'malformed email must be rejected by form validation'
            ),
        )

        response = _stage_email_change(
            client,
            'not-an-email',
            password,
        )

        assert response.status_code == 200
        assert MESSAGES['EMAIL_INVALID'] in response.get_data(as_text=True)
        assert email_log == emails_before
        assert _pending_email_state(app, 'alice@example.com') == (
            None, None, None, 0,
        )


class TestOtpHmacStorage:

    def test_identical_raw_code_is_bound_to_purpose_and_stable_context(
        self, app, client, email_log, monkeypatch,
    ):
        raw_code = '123456'
        monkeypatch.setattr(
            AuthService,
            '_make_verification_code',
            staticmethod(lambda: raw_code),
        )

        assert _register(client).status_code in (302, 303)
        bob_client = app.test_client()
        assert _register(
            bob_client,
            email='bob@example.com',
            password='AnotherHorse9',
        ).status_code in (302, 303)
        with app.app_context():
            registration_digests = [
                row.verification_code
                for row in PendingRegistration.query.order_by(
                    PendingRegistration.email,
                ).all()
            ]
        assert len(set(registration_digests)) == 2
        for digest in registration_digests:
            _assert_stored_otp_digest(digest, raw_code)

        verified = client.post(
            '/verify-code?email=alice@example.com',
            data={'code': raw_code},
            follow_redirects=False,
        )
        assert verified.status_code in (302, 303)

        changed = _stage_email_change(
            client,
            'new-alice@example.com',
            'CorrectHorse9',
        )
        assert changed.status_code in (302, 303)
        with app.app_context():
            email_change_digest = User.query.filter_by(
                email='alice@example.com',
            ).one().verification_code
        _assert_stored_otp_digest(email_change_digest, raw_code)

        verified_change = client.post(
            '/verify-code?email=new-alice@example.com',
            data={'code': raw_code},
            follow_redirects=False,
        )
        assert verified_change.status_code in (302, 303)

        requested_deletion = client.post(
            '/settings/delete/request',
            follow_redirects=False,
        )
        assert requested_deletion.status_code in (302, 303)
        with app.app_context():
            deletion_digest = User.query.filter_by(
                email='new-alice@example.com',
            ).one().deletion_code
        _assert_stored_otp_digest(deletion_digest, raw_code)

        all_digests = {
            *registration_digests,
            email_change_digest,
            deletion_digest,
        }
        assert len(all_digests) == 4
        delivered_values = [
            value.split(':', 1)[1]
            if value.startswith('deletion:')
            else value
            for _, value in email_log
        ]
        assert delivered_values
        assert all(delivered == raw_code for delivered in delivered_values)

        deleted = client.post(
            '/settings/delete/verify',
            data={'code': raw_code},
            follow_redirects=False,
        )
        assert deleted.status_code in (302, 303)
        with app.app_context():
            assert User.query.filter_by(email='new-alice@example.com').first() is None


class TestRemovedAdminSurface:

    def test_authenticated_user_has_no_admin_web_capability(self, app, client):
        with app.app_context():
            user = User(
                username='alice',
                email='alice@example.com',
                is_verified=True,
            )
            user.set_password('CorrectHorse9')
            db.session.add(user)
            db.session.commit()
            user_id = user.id

        login_response = client.post(
            '/login',
            data={
                'username': 'alice@example.com',
                'password': 'CorrectHorse9',
            },
            follow_redirects=False,
        )
        assert login_response.status_code in (302, 303)

        assert not any(
            rule.endpoint.startswith('admin.')
            for rule in app.url_map.iter_rules()
        )
        for method, path in (
            ('GET', '/admin/users'),
            ('POST', f'/admin/users/{user_id}/send-reset-email'),
            ('POST', f'/admin/users/{user_id}/toggle-admin'),
            ('POST', f'/admin/users/{user_id}/delete'),
        ):
            response = client.open(path, method=method)
            assert response.status_code == 404

        dashboard = client.get('/')
        settings = client.get('/settings')
        assert dashboard.status_code == 200
        assert settings.status_code == 200
        rendered = dashboard.get_data(as_text=True) + settings.get_data(as_text=True)
        assert 'href="/admin/users"' not in rendered
        assert 'Administrator' not in rendered
        assert 'nav-admin-badge' not in rendered


class TestLogin:

    def test_correct_credentials_logs_in(self, app, client, email_log):
        _signup_and_verify(app, client, email_log)
        resp = client.post(
            '/login',
            data={'username': 'alice@example.com', 'password': 'CorrectHorse9'},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)
        # Session cookie was issued.
        with client.session_transaction() as sess:
            assert sess.get('_user_id') is not None

    def test_existing_username_login_still_works(self, app, client, email_log):
        _signup_and_verify(app, client, email_log)
        resp = client.post(
            '/login',
            data={'username': 'alice', 'password': 'CorrectHorse9'},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_wrong_password_returns_generic_error(self, app, client, email_log):
        _signup_and_verify(app, client, email_log)
        resp = client.post(
            '/login',
            data={'username': 'alice@example.com', 'password': 'WrongPw9999'},
        )
        assert resp.status_code == 200
        body = resp.get_data(as_text=True).lower()
        # Generic "invalid email or password" — no leak about which.
        assert 'invalid' in body
        assert 'password' in body
        assert 'no account' not in body

    def test_nonexistent_user_returns_same_error(self, app, client):
        resp = client.post(
            '/login',
            data={'username': 'ghost', 'password': 'WhateverPw9'},
        )
        assert resp.status_code == 200
        body = resp.get_data(as_text=True).lower()
        # Same generic invalid-credentials message; no "user not found".
        assert 'invalid' in body
        assert 'no account' not in body

    def test_unverified_login_returns_generic_error_no_redirect(self, app, client, email_log):
        # Sign up but don't verify — no User row yet, only a pending record.
        # We deliberately do NOT redirect to /verify-code here: that would
        # leak that the email exists in pending state (account enumeration).
        _register(client)
        resp = client.post(
            '/login',
            data={'username': 'alice@example.com', 'password': 'CorrectHorse9'},
            follow_redirects=False,
        )
        # Same shape as test_nonexistent_user_returns_same_error: the
        # response is the form with the generic "invalid credentials"
        # message — no Location header to verify-code.
        assert resp.status_code == 200
        body = resp.get_data(as_text=True).lower()
        assert 'invalid' in body
        assert 'verify-code' not in body
        # Header must not redirect into the OTP page either.
        assert 'Location' not in resp.headers

    def test_lockout_after_five_failed_attempts(self, app, client, email_log):
        _signup_and_verify(app, client, email_log)

        # Five consecutive wrong-password attempts must trip the lockout.
        for attempt in range(1, 6):
            response = client.post(
                '/login',
                data={
                    'username': 'alice@example.com',
                    'password': 'Bad9999999',
                },
            )
            assert MESSAGES['INVALID_CREDENTIALS'] in response.get_data(as_text=True)
            assert MESSAGES['ACCOUNT_LOCKED'] not in response.get_data(as_text=True)
            with app.app_context():
                user = User.query.filter_by(username='alice').one()
                assert user.failed_login_attempts == attempt

        # The 6th attempt — even with the *correct* password — is locked.
        resp = client.post(
            '/login',
            data={'username': 'alice@example.com', 'password': 'CorrectHorse9'},
        )
        assert resp.status_code == 200
        body = resp.get_data(as_text=True).lower()
        assert 'too many' in body or 'locked' in body or 'try again' in body

        with app.app_context():
            user = User.query.filter_by(username='alice').one()
            assert user.locked_until is not None


class TestLoginEnumerationHardening:

    @staticmethod
    def _assert_generic_html_failure(response):
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert MESSAGES['INVALID_CREDENTIALS'] in body
        assert MESSAGES['ACCOUNT_LOCKED'] not in body
        assert 'Location' not in response.headers

    def test_unknown_and_pending_identifiers_match_real_wrong_password_without_state(
        self, app, client, email_log,
    ):
        _signup_and_verify(app, client, email_log)
        pending_client = app.test_client()
        _register(
            pending_client,
            email='pending@example.com',
            password='PendingHorse9',
        )

        with app.app_context():
            pending = PendingRegistration.query.filter_by(
                email='pending@example.com',
            ).one()
            pending_state = (
                pending.password_hash,
                pending.verification_code,
                pending.failed_otp_attempts,
            )

        responses = (
            client.post('/login', data={
                'username': 'alice@example.com',
                'password': 'WrongHorse99',
            }),
            client.post('/login', data={
                'username': 'unknown@example.com',
                'password': 'WrongHorse99',
            }),
            client.post('/login', data={
                'username': 'unknown_username',
                'password': 'WrongHorse99',
            }),
            client.post('/login', data={
                'username': 'pending@example.com',
                'password': 'PendingHorse9',
            }),
        )

        for response in responses:
            self._assert_generic_html_failure(response)

        with app.app_context():
            user = User.query.filter_by(email='alice@example.com').one()
            assert user.failed_login_attempts == 1
            assert User.query.count() == 1
            pending = PendingRegistration.query.filter_by(
                email='pending@example.com',
            ).one()
            assert (
                pending.password_hash,
                pending.verification_code,
                pending.failed_otp_attempts,
            ) == pending_state

    def test_real_unknown_pending_and_locked_wrong_paths_use_same_bcrypt_checks(
        self, app, client, email_log, monkeypatch,
    ):
        _signup_and_verify(app, client, email_log)
        _register(
            app.test_client(),
            email='pending@example.com',
            password='PendingHorse9',
        )

        checkpw_calls = []

        def reject_password(candidate, stored_hash):
            checkpw_calls.append((candidate, stored_hash))
            return False

        monkeypatch.setattr(
            'portfolio_app.models.user.bcrypt.checkpw',
            reject_password,
        )
        monkeypatch.setattr(
            'portfolio_app.models.user.bcrypt.hashpw',
            lambda *args, **kwargs: pytest.fail(
                'login verification must not generate a bcrypt hash'
            ),
        )

        identifiers = (
            'alice@example.com',
            'unknown@example.com',
            'pending@example.com',
        )
        call_groups = []
        for identifier in identifiers:
            before = len(checkpw_calls)
            response = client.post('/login', data={
                'username': identifier,
                'password': 'WrongHorse99',
            })
            self._assert_generic_html_failure(response)
            call_groups.append(checkpw_calls[before:])

        with app.app_context():
            user = User.query.filter_by(email='alice@example.com').one()
            user.failed_login_attempts = 5
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=20)
            db.session.commit()

        before = len(checkpw_calls)
        locked_response = client.post('/login', data={
            'username': 'alice@example.com',
            'password': 'WrongHorse99',
        })
        self._assert_generic_html_failure(locked_response)
        call_groups.append(checkpw_calls[before:])

        # Current bcrypt misses perform the prehashed check and the retained
        # raw-bcrypt compatibility fallback. Dummy and locked paths do both.
        assert [len(group) for group in call_groups] == [2, 2, 2, 2]
        costs = []
        for group in call_groups:
            assert group[0][1] == group[1][1]
            costs.append(group[0][1].split(b'$')[2])
        assert costs == [costs[0]] * len(costs)

    def test_locked_password_is_verified_without_mutating_lockout(
        self, app, client, email_log, monkeypatch,
    ):
        _signup_and_verify(app, client, email_log)
        with app.app_context():
            user = User.query.filter_by(email='alice@example.com').one()
            user.failed_login_attempts = 5
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=20)
            db.session.commit()
            user_id = user.id
            failed_attempts_before = user.failed_login_attempts
            locked_until_before = user.locked_until

        original_check_password = User.check_password
        checked_users = []

        def record_check(user, password):
            checked_users.append((user.id, password))
            return original_check_password(user, password)

        monkeypatch.setattr(User, 'check_password', record_check)

        wrong = client.post('/login', data={
            'username': 'alice@example.com',
            'password': 'WrongHorse99',
        })
        self._assert_generic_html_failure(wrong)

        correct = client.post('/login', data={
            'username': 'alice@example.com',
            'password': 'CorrectHorse9',
        })
        assert correct.status_code == 200
        correct_body = correct.get_data(as_text=True)
        assert MESSAGES['ACCOUNT_LOCKED'] in correct_body
        assert MESSAGES['INVALID_CREDENTIALS'] not in correct_body

        assert checked_users == [
            (user_id, 'WrongHorse99'),
            (user_id, 'CorrectHorse9'),
        ]
        with client.session_transaction() as session:
            assert session.get('_user_id') is None
        with app.app_context():
            user = User.query.filter_by(email='alice@example.com').one()
            assert user.failed_login_attempts == failed_attempts_before
            assert user.locked_until == locked_until_before

    def test_modal_failures_match_html_semantics(self, app, client, email_log):
        _signup_and_verify(app, client, email_log)
        _register(
            app.test_client(),
            email='pending@example.com',
            password='PendingHorse9',
        )

        expected_invalid = {
            'ok': False,
            'errors': {'__all__': MESSAGES['INVALID_CREDENTIALS']},
        }
        for identifier in (
            'alice@example.com',
            'unknown@example.com',
            'pending@example.com',
        ):
            response = client.post('/login', data={
                '_modal': '1',
                'username': identifier,
                'password': 'WrongHorse99',
            })
            assert response.status_code == 422
            assert response.get_json() == expected_invalid

        with app.app_context():
            user = User.query.filter_by(email='alice@example.com').one()
            user.failed_login_attempts = 5
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=20)
            db.session.commit()

        locked_wrong = client.post('/login', data={
            '_modal': '1',
            'username': 'alice@example.com',
            'password': 'WrongHorse99',
        })
        assert locked_wrong.status_code == 422
        assert locked_wrong.get_json() == expected_invalid

        locked_correct = client.post('/login', data={
            '_modal': '1',
            'username': 'alice@example.com',
            'password': 'CorrectHorse9',
        })
        assert locked_correct.status_code == 422
        assert locked_correct.get_json() == {
            'ok': False,
            'errors': {'__all__': MESSAGES['ACCOUNT_LOCKED']},
        }
        with client.session_transaction() as session:
            assert session.get('_user_id') is None


class TestUnverifiedAuthenticationInvariant:

    PASSWORD = 'UnverifiedHorse9'

    @staticmethod
    def _assert_generic_html_failure(response):
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert MESSAGES['INVALID_CREDENTIALS'] in body
        assert MESSAGES['ACCOUNT_LOCKED'] not in body
        assert 'Location' not in response.headers

    @pytest.mark.parametrize(
        'identifier',
        ('persisted_unverified', 'persisted-unverified@example.com'),
    )
    def test_correct_password_is_generic_and_cannot_access_protected_route(
        self, app, client, identifier,
    ):
        _create_persisted_unverified_user(app, password=self.PASSWORD)

        response = client.post('/login', data={
            'username': identifier,
            'password': self.PASSWORD,
        }, follow_redirects=False)

        self._assert_generic_html_failure(response)
        with client.session_transaction() as session:
            assert session.get('_user_id') is None

        protected = client.get('/settings', follow_redirects=False)
        assert protected.status_code in (302, 303)
        assert '/login' in protected.headers['Location']

    def test_modal_correct_password_uses_generic_invalid_contract(self, app, client):
        _create_persisted_unverified_user(app, password=self.PASSWORD)

        response = client.post('/login', data={
            '_modal': '1',
            'username': 'persisted-unverified@example.com',
            'password': self.PASSWORD,
        })

        assert response.status_code == 422
        assert response.get_json() == {
            'ok': False,
            'errors': {'__all__': MESSAGES['INVALID_CREDENTIALS']},
        }
        with client.session_transaction() as session:
            assert session.get('_user_id') is None

    def test_correct_password_checks_real_hash_without_success_mutation_or_rehash(
        self, app, client, monkeypatch,
    ):
        original_last_login = datetime(2025, 6, 1, 12, 30)
        legacy_hash = generate_password_hash(
            self.PASSWORD,
            method='pbkdf2:sha256:1000',
        )
        user_id = _create_persisted_unverified_user(
            app,
            password_hash=legacy_hash,
            failed_login_attempts=3,
            last_login=original_last_login,
        )

        original_check_password = User.check_password
        checked_users = []

        def record_check(user, password):
            checked_users.append((user.id, password))
            return original_check_password(user, password)

        monkeypatch.setattr(User, 'check_password', record_check)

        response = client.post('/login', data={
            'username': 'persisted_unverified',
            'password': self.PASSWORD,
        })
        self._assert_generic_html_failure(response)
        assert checked_users == [(user_id, self.PASSWORD)]

        with app.app_context():
            user = db.session.get(User, user_id)
            assert user.password_hash == legacy_hash
            assert user.failed_login_attempts == 3
            assert user.locked_until is None
            assert user.last_login == original_last_login

    def test_wrong_password_and_locked_state_keep_existing_semantics(self, app, client):
        user_id = _create_persisted_unverified_user(app, password=self.PASSWORD)

        for attempt in range(1, 6):
            response = client.post('/login', data={
                'username': 'persisted_unverified',
                'password': 'WrongHorse99',
            })
            self._assert_generic_html_failure(response)
            with app.app_context():
                assert db.session.get(User, user_id).failed_login_attempts == attempt

        with app.app_context():
            user = db.session.get(User, user_id)
            locked_state = (
                user.failed_login_attempts,
                user.locked_until,
                user.last_login,
                user.password_hash,
            )
            assert locked_state[1] is not None

        for password in (self.PASSWORD, 'WrongHorse99'):
            response = client.post('/login', data={
                'username': 'persisted_unverified',
                'password': password,
            })
            self._assert_generic_html_failure(response)

        with client.session_transaction() as session:
            assert session.get('_user_id') is None
        with app.app_context():
            user = db.session.get(User, user_id)
            assert (
                user.failed_login_attempts,
                user.locked_until,
                user.last_login,
                user.password_hash,
            ) == locked_state

    def test_loader_rejects_existing_session_and_remember_cookie_after_unverify(
        self, app, client, email_log,
    ):
        _signup_and_verify(app, client, email_log)
        login_response = client.post('/login', data={
            'username': 'alice@example.com',
            'password': 'CorrectHorse9',
            'remember': 'on',
        }, follow_redirects=False)
        assert login_response.status_code in (302, 303)
        assert client.get('/settings').status_code == 200

        remember_cookie = client.get_cookie('remember_token')
        assert remember_cookie is not None
        remember_only_client = app.test_client()
        remember_only_client.set_cookie('remember_token', remember_cookie.value)

        with app.app_context():
            user = User.query.filter_by(email='alice@example.com').one()
            user_id = user.id
            generation_before = user.auth_generation
            user.is_verified = False
            db.session.commit()

        for authenticated_client in (client, remember_only_client):
            response = authenticated_client.get('/settings', follow_redirects=False)
            assert response.status_code in (302, 303)
            assert '/login' in response.headers['Location']

        with app.app_context():
            user = db.session.get(User, user_id)
            assert user.is_verified is False
            assert user.auth_generation == generation_before


# ---------------------------------------------------------------------------
# Auth UI and Google placeholder tests
# ---------------------------------------------------------------------------

class TestAuthUiAndGoogle:

    def test_landing_auth_actions_link_to_dedicated_pages(self, client):
        resp = client.get('/')
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)

        # Auth actions are plain links to the dedicated pages — never a modal
        # or an inline form. Class names are presentation and not asserted.
        login_links = re.findall(r'<a[^>]*href="/login"', body)
        register_links = re.findall(r'<a[^>]*href="/register"', body)

        # Header and closing call-to-action, at minimum.
        assert len(login_links) >= 2
        assert len(register_links) >= 2

        assert 'Log in' in body
        assert 'Sign up' in body
        assert 'Create Account' not in body
        assert 'dashboard-mockup' not in body
        assert 'Symbol Performance' not in body
        assert 'heatmap' not in body

    def test_landing_no_longer_renders_auth_modal(self, client):
        resp = client.get('/')
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)

        assert 'id="authModal"' not in body
        assert 'data-bs-target="#authModal"' not in body
        assert 'id="loginForm"' not in body
        assert 'id="registerForm"' not in body

    def test_register_page_uses_email_password_only(self, client):
        resp = client.get('/register')
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert 'Continue with Google' not in body
        assert 'Email address' in body
        assert 'name="username"' not in body
        assert 'name="confirm_password"' not in body

    def test_login_page_uses_email_label_and_reset_password_text(self, client):
        resp = client.get('/login')
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert 'Continue with Google' not in body
        assert 'Email address' in body
        assert 'Reset password' in body
        assert 'Forgot password?' not in body

    def test_dedicated_auth_pages_still_render(self, client):
        login_resp = client.get('/login')
        register_resp = client.get('/register')

        assert login_resp.status_code == 200
        assert register_resp.status_code == 200
        assert 'Welcome back' in login_resp.get_data(as_text=True)
        assert 'Create your account' in register_resp.get_data(as_text=True)

    def test_google_config_defaults_disabled(self, app):
        assert app.config['GOOGLE_OAUTH_ENABLED'] is False
        assert app.config['GOOGLE_CLIENT_ID'] == ''
        assert app.config['GOOGLE_CLIENT_SECRET'] == ''
        assert app.config['GOOGLE_REDIRECT_URI'] == ''

    def test_google_oauth_disabled_route_is_unavailable(self, client):
        resp = client.get('/auth/google')
        assert resp.status_code == 404

    def test_reset_password_request_keeps_generic_response(self, client, email_log):
        resp = client.post(
            '/forgot-password',
            data={'email': 'nobody@example.com'},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "If an account with that email exists" in body
        assert email_log == []


# ---------------------------------------------------------------------------
# Settings and account deletion tests
# ---------------------------------------------------------------------------

class TestSettingsAndDeletion:

    def test_profile_labels_name_not_username(self, app, client, email_log):
        _signup_and_verify(app, client, email_log)
        client.post(
            '/login',
            data={'username': 'alice@example.com', 'password': 'CorrectHorse9'},
        )

        resp = client.get('/settings')
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert '>Name<' in body
        assert '>Username<' not in body
        assert 'Cannot be changed.' not in body

    def test_account_page_initially_hides_deletion_code_and_typed_confirmation(self, app, client, email_log):
        _signup_and_verify(app, client, email_log)
        client.post(
            '/login',
            data={'username': 'alice@example.com', 'password': 'CorrectHorse9'},
        )

        resp = client.get('/settings?tab=account')
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert 'id="delete-code"' not in body
        assert 'name="delete_confirm"' not in body
        assert 'Delete permanently' not in body
        assert 'Type "delete"' not in body

    def test_after_sending_deletion_code_shows_code_delete_button_only(self, app, client, email_log):
        _signup_and_verify(app, client, email_log)
        client.post(
            '/login',
            data={'username': 'alice@example.com', 'password': 'CorrectHorse9'},
        )

        resp = client.post('/settings/delete/request')
        assert resp.status_code in (302, 303)
        resp = client.get(resp.headers['Location'])
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert 'id="delete-code"' in body
        assert 'Delete account' in body
        assert 'name="delete_confirm"' not in body
        assert 'Delete permanently' not in body
        assert 'Type "delete"' not in body
        deletion_code = next(
            value.split(':', 1)[1]
            for _, value in reversed(email_log)
            if value.startswith('deletion:')
        )
        with app.app_context():
            stored = User.query.filter_by(
                email='alice@example.com',
            ).one().deletion_code
            _assert_stored_otp_digest(stored, deletion_code)

    def test_invalid_deletion_code_does_not_delete_or_logout(self, app, client, email_log):
        _signup_and_verify(app, client, email_log)
        client.post(
            '/login',
            data={'username': 'alice@example.com', 'password': 'CorrectHorse9'},
        )
        client.post('/settings/delete/request')

        resp = client.post(
            '/settings/delete/verify',
            data={'code': '000000'},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert 'The code is incorrect or has expired. Please request a new one.' in resp.get_data(as_text=True)
        with app.app_context():
            user = User.query.filter_by(email='alice@example.com').one()
            expected_identity = user.get_id()
        with client.session_transaction() as sess:
            assert sess.get('_user_id') == expected_identity

    def test_expired_deletion_code_does_not_delete_or_logout(self, app, client, email_log):
        _signup_and_verify(app, client, email_log)
        client.post(
            '/login',
            data={'username': 'alice@example.com', 'password': 'CorrectHorse9'},
        )
        client.post('/settings/delete/request')
        deletion_code = [
            value.split(':', 1)[1]
            for _, value in email_log
            if value.startswith('deletion:')
        ][-1]
        with app.app_context():
            user = User.query.filter_by(email='alice@example.com').one()
            user.deletion_code_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            db.session.commit()

        resp = client.post(
            '/settings/delete/verify',
            data={'code': deletion_code},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert 'The code is incorrect or has expired. Please request a new one.' in resp.get_data(as_text=True)
        with app.app_context():
            user = User.query.filter_by(email='alice@example.com').one()
            expected_identity = user.get_id()
        with client.session_transaction() as sess:
            assert sess.get('_user_id') == expected_identity

    def test_correct_deletion_code_deletes_account_immediately_and_logs_out(
        self, app, client, email_log,
    ):
        _signup_and_verify(app, client, email_log)
        client.post(
            '/login',
            data={'username': 'alice@example.com', 'password': 'CorrectHorse9'},
        )
        client.post('/settings/delete/request')
        deletion_code = [
            value.split(':', 1)[1]
            for _, value in email_log
            if value.startswith('deletion:')
        ][-1]

        resp = client.post(
            '/settings/delete/verify',
            data={'code': deletion_code},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)
        assert resp.headers.get('Location', '').endswith('/login')
        with app.app_context():
            assert User.query.filter_by(email='alice@example.com').count() == 0
        with client.session_transaction() as sess:
            assert sess.get('_user_id') is None

    def test_deletion_removes_current_user_and_associated_data_only(
        self, app, client, email_log,
    ):
        _signup_and_verify(app, client, email_log)
        with app.app_context():
            alice = User.query.filter_by(email='alice@example.com').one()
            bob = User(
                username='bob',
                email='bob@example.com',
                is_verified=True,
                created_at=datetime.now(timezone.utc),
            )
            bob.set_password('CorrectHorse9')
            db.session.add(bob)
            db.session.flush()

            alice_portfolio = Portfolio(user_id=alice.id, name='Alice Portfolio')
            bob_portfolio = Portfolio(user_id=bob.id, name='Bob Portfolio')
            db.session.add_all([alice_portfolio, bob_portfolio])
            db.session.flush()
            db.session.add_all([
                PortfolioEvent(
                    portfolio_id=alice_portfolio.id,
                    event_type='Deposit',
                    amount_delta=1000,
                ),
                Transaction(
                    portfolio_id=alice_portfolio.id,
                    transaction_type='Buy',
                    symbol='AAPL',
                    price=100,
                    quantity=1,
                    fees=0,
                    net_amount=100,
                    average_cost=100,
                ),
                Dividend(
                    portfolio_id=alice_portfolio.id,
                    symbol='AAPL',
                    amount=5,
                ),
                Symbol(portfolio_id=alice_portfolio.id, symbol='AAPL'),
                PortfolioEvent(
                    portfolio_id=bob_portfolio.id,
                    event_type='Deposit',
                    amount_delta=500,
                ),
            ])
            db.session.commit()
            bob_id = bob.id

        client.post(
            '/login',
            data={'username': 'alice@example.com', 'password': 'CorrectHorse9'},
        )
        client.post('/settings/delete/request')
        deletion_code = [
            value.split(':', 1)[1]
            for _, value in email_log
            if value.startswith('deletion:')
        ][-1]
        resp = client.post(
            '/settings/delete/verify',
            data={'code': deletion_code},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)
        with app.app_context():
            assert User.query.filter_by(email='alice@example.com').count() == 0
            assert User.query.filter_by(email='bob@example.com').count() == 1
            assert Portfolio.query.filter_by(user_id=bob_id).count() == 1
            assert Portfolio.query.filter_by(name='Alice Portfolio').count() == 0
            assert Transaction.query.count() == 0
            assert Dividend.query.count() == 0
            assert Symbol.query.count() == 0
            assert PortfolioEvent.query.count() == 1

    def test_reused_deletion_code_cannot_delete_another_account(self, app, client, email_log):
        _signup_and_verify(app, client, email_log)
        client.post(
            '/login',
            data={'username': 'alice@example.com', 'password': 'CorrectHorse9'},
        )
        client.post('/settings/delete/request')
        deletion_code = [
            value.split(':', 1)[1]
            for _, value in email_log
            if value.startswith('deletion:')
        ][-1]
        client.post('/settings/delete/verify', data={'code': deletion_code})

        _signup_and_verify(
            app,
            client,
            email_log,
            email='bob@example.com',
            password='CorrectHorse9',
        )
        client.post(
            '/login',
            data={'username': 'bob@example.com', 'password': 'CorrectHorse9'},
        )

        resp = client.post(
            '/settings/delete/verify',
            data={'code': deletion_code},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert 'The code is incorrect or has expired. Please request a new one.' in resp.get_data(as_text=True)
        with app.app_context():
            bob = User.query.filter_by(email='bob@example.com').one()
            expected_identity = bob.get_id()
        with client.session_transaction() as sess:
            assert sess.get('_user_id') == expected_identity

    def test_another_users_deletion_code_cannot_delete_current_user(self, app, client, email_log):
        _signup_and_verify(app, client, email_log)
        with app.app_context():
            bob = User(
                username='bob',
                email='bob@example.com',
                is_verified=True,
                created_at=datetime.now(timezone.utc),
            )
            bob.set_password('CorrectHorse9')
            db.session.add(bob)
            db.session.commit()
            bob_code = Services().auth_service.request_account_deletion(bob)

        client.post(
            '/login',
            data={'username': 'alice@example.com', 'password': 'CorrectHorse9'},
        )
        resp = client.post(
            '/settings/delete/verify',
            data={'code': bob_code},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert 'The code is incorrect or has expired. Please request a new one.' in resp.get_data(as_text=True)
        with app.app_context():
            assert User.query.filter_by(email='alice@example.com').count() == 1
            assert User.query.filter_by(email='bob@example.com').count() == 1

    def test_account_deletion_commit_failure_rolls_back_and_preserves_account(
        self, app, client, email_log, monkeypatch,
    ):
        _signup_and_verify(app, client, email_log)
        client.post(
            '/login',
            data={'username': 'alice@example.com', 'password': 'CorrectHorse9'},
        )
        client.post('/settings/delete/request')
        deletion_code = [
            value.split(':', 1)[1]
            for _, value in email_log
            if value.startswith('deletion:')
        ][-1]
        with app.app_context():
            stored_deletion_digest = User.query.filter_by(
                email='alice@example.com',
            ).one().deletion_code
            _assert_stored_otp_digest(stored_deletion_digest, deletion_code)

        original_commit = UserRepository.commit

        def fail_user_delete_commit(self):
            if any(isinstance(obj, User) for obj in self.db.session.deleted):
                raise SQLAlchemyError('delete commit failed')
            return original_commit(self)

        monkeypatch.setattr(UserRepository, 'commit', fail_user_delete_commit)
        resp = client.post(
            '/settings/delete/verify',
            data={'code': deletion_code},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with app.app_context():
            user = User.query.filter_by(email='alice@example.com').one()
            assert user.deletion_code == stored_deletion_digest
            expected_identity = user.get_id()
        with client.session_transaction() as sess:
            assert sess.get('_user_id') == expected_identity

        monkeypatch.setattr(UserRepository, 'commit', original_commit)
        resp = client.post(
            '/settings/delete/verify',
            data={'code': deletion_code},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)
        assert resp.headers.get('Location', '').endswith('/login')
        with app.app_context():
            assert User.query.filter_by(email='alice@example.com').count() == 0
        with client.session_transaction() as sess:
            assert sess.get('_user_id') is None


# ---------------------------------------------------------------------------
# Token & session tests
# ---------------------------------------------------------------------------

class TestPasswordResetAtomicConsumption:

    def test_matching_jti_consumes_reset_state_exactly_once(
        self, app, client, email_log, monkeypatch,
    ):
        _signup_and_verify(app, client, email_log)
        locked_until = datetime.now(timezone.utc) + timedelta(minutes=20)

        with app.app_context():
            user = User.query.filter_by(email='alice@example.com').one()
            user.failed_login_attempts = 5
            user.locked_until = locked_until
            db.session.commit()

            service = Services().auth_service
            live_jti = service.begin_password_reset(user)
            original_generation = user.auth_generation

            first_result = service.reset_password_with_token(
                user.email,
                live_jti,
                'ResetHorse123',
            )
            assert first_result is not None

            db.session.expire_all()
            reset_user = User.query.filter_by(email='alice@example.com').one()
            assert reset_user.check_password('ResetHorse123')
            assert reset_user.password_reset_jti is None
            assert reset_user.auth_generation == original_generation + 1
            assert reset_user.failed_login_attempts == 0
            assert reset_user.locked_until is None

            generation_after_first_reset = reset_user.auth_generation

            def fail_if_replay_hashes(_user, _password):
                pytest.fail('consumed reset state must be rejected before hashing')

            monkeypatch.setattr(User, 'set_password', fail_if_replay_hashes)
            replay_result = service.reset_password_with_token(
                reset_user.email,
                live_jti,
                'SubstituteHorse456',
            )
            assert replay_result is None

            db.session.expire_all()
            replayed_user = User.query.filter_by(email='alice@example.com').one()
            assert replayed_user.check_password('ResetHorse123')
            assert not replayed_user.check_password('SubstituteHorse456')
            assert replayed_user.password_reset_jti is None
            assert replayed_user.auth_generation == generation_after_first_reset
            assert replayed_user.failed_login_attempts == 0
            assert replayed_user.locked_until is None

    @pytest.mark.parametrize('submitted_jti', ['nonmatching-jti', ''])
    def test_nonmatching_or_empty_jti_preserves_all_reset_state(
        self, app, client, email_log, submitted_jti, monkeypatch,
    ):
        _signup_and_verify(app, client, email_log)

        with app.app_context():
            user = User.query.filter_by(email='alice@example.com').one()
            user.failed_login_attempts = 4
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=20)
            db.session.commit()

            service = Services().auth_service
            live_jti = service.begin_password_reset(user)
            db.session.expire_all()
            unchanged_user = User.query.filter_by(email='alice@example.com').one()
            original_generation = unchanged_user.auth_generation
            original_failed_attempts = unchanged_user.failed_login_attempts
            original_locked_until = unchanged_user.locked_until

            hash_calls = []

            def record_password_hash(_user, password):
                hash_calls.append(password)

            monkeypatch.setattr(User, 'set_password', record_password_hash)
            result = service.reset_password_with_token(
                unchanged_user.email,
                submitted_jti,
                'SubstituteHorse456',
            )
            assert result is None
            assert hash_calls == []

            db.session.expire_all()
            preserved_user = User.query.filter_by(email='alice@example.com').one()
            assert preserved_user.check_password('CorrectHorse9')
            assert not preserved_user.check_password('SubstituteHorse456')
            assert preserved_user.password_reset_jti == live_jti
            assert preserved_user.auth_generation == original_generation
            assert preserved_user.failed_login_attempts == original_failed_attempts
            assert preserved_user.locked_until == original_locked_until

    def test_http_reset_replay_uses_existing_generic_invalid_link_flow(
        self, app, client, email_log,
    ):
        _signup_and_verify(app, client, email_log)
        reset_client = app.test_client()
        request_response = reset_client.post(
            '/forgot-password',
            data={'email': 'alice@example.com'},
            follow_redirects=False,
        )
        assert request_response.status_code in (302, 303)
        reset_token = next(
            value.split(':', 1)[1]
            for _, value in reversed(email_log)
            if value.startswith('reset:')
        )

        success = reset_client.post(
            f'/reset-password/{reset_token}',
            data={
                'password': 'ResetHorse123',
                'confirm_password': 'ResetHorse123',
            },
            follow_redirects=False,
        )
        assert success.status_code in (302, 303)
        assert success.headers['Location'].endswith('/login')

        replay = reset_client.post(
            f'/reset-password/{reset_token}',
            data={
                'password': 'SubstituteHorse456',
                'confirm_password': 'SubstituteHorse456',
            },
            follow_redirects=False,
        )
        assert replay.status_code in (302, 303)
        assert replay.headers['Location'].endswith('/forgot-password')

        with reset_client.session_transaction() as session:
            assert (
                'danger',
                MESSAGES['PASSWORD_RESET_LINK_INVALID'],
            ) in session.get('_flashes', [])

        assert reset_client.post('/login', data={
            'username': 'alice@example.com',
            'password': 'ResetHorse123',
        }).status_code in (302, 303)
        failed_login_client = app.test_client()
        failed_login = failed_login_client.post(
            '/login',
            data={
                'username': 'alice@example.com',
                'password': 'SubstituteHorse456',
            },
            follow_redirects=True,
        )
        assert MESSAGES['INVALID_CREDENTIALS'] in failed_login.get_data(as_text=True)


class TestTokenAndSession:

    def test_password_change_revokes_existing_sessions_and_remember_state(
        self, app, client, email_log,
    ):
        old_password = 'CorrectHorse9'
        new_password = 'ChangedHorse10'
        _signup_and_verify(app, client, email_log)

        with app.app_context():
            user = User.query.filter_by(email='alice@example.com').one()
            user_id = user.id
            original_generation = user.auth_generation
            db.session.add(OAuthIdentity(
                user_id=user.id,
                provider='google',
                provider_subject='google-sub-alice',
            ))
            db.session.commit()

        client_b = app.test_client()
        assert client.post('/login', data={
            'username': 'alice@example.com',
            'password': old_password,
        }).status_code in (302, 303)
        assert client_b.post('/login', data={
            'username': 'alice@example.com',
            'password': old_password,
            'remember': 'on',
        }).status_code in (302, 303)

        remember_cookie = client_b.get_cookie('remember_token')
        assert remember_cookie is not None
        remember_only_client = app.test_client()
        remember_only_client.set_cookie('remember_token', remember_cookie.value)
        remember_control_client = app.test_client()
        remember_control_client.set_cookie('remember_token', remember_cookie.value)

        # Prove the copied cookie can restore authentication before revocation.
        # The untouched remember_only_client remains cookie-only until after
        # the generation advances.
        assert remember_control_client.get('/settings').status_code == 200

        # Pre-release id-only identities are deliberately compatible only
        # while the database-backed generation is still zero.
        legacy_client = app.test_client()
        with legacy_client.session_transaction() as sess:
            sess['_user_id'] = str(user_id)
            sess['_fresh'] = True
        assert legacy_client.get('/settings').status_code == 200

        response = client.post('/change-password', data={
            'current_password': old_password,
            'new_password': new_password,
            'confirm_new_password': new_password,
        }, follow_redirects=False)

        assert response.status_code in (302, 303)
        assert response.headers['Location'].endswith('/login')
        with client.session_transaction() as sess:
            assert sess.get('_user_id') is None

        # Client B's normal session and an independent remember-only client
        # both carry authentication issued before the password changed.
        for stale_client in (client_b, remember_only_client):
            stale_response = stale_client.get('/settings', follow_redirects=False)
            assert stale_response.status_code in (302, 303)
            assert '/login' in stale_response.headers['Location']

        # The same signed legacy identity must fail after generation zero.
        legacy_response = legacy_client.get('/settings', follow_redirects=False)
        assert legacy_response.status_code in (302, 303)
        assert '/login' in legacy_response.headers['Location']

        with app.app_context():
            user = db.session.get(User, user_id)
            assert user.auth_generation == original_generation + 1
            assert OAuthIdentity.query.filter_by(
                user_id=user_id,
                provider='google',
                provider_subject='google-sub-alice',
            ).count() == 1

        fresh_client = app.test_client()
        assert fresh_client.post('/login', data={
            'username': 'alice@example.com',
            'password': new_password,
        }).status_code in (302, 303)
        assert fresh_client.get('/settings').status_code == 200

        # Loading and using a current identity is read-only with respect to
        # the server-authoritative generation.
        assert fresh_client.get('/settings').status_code == 200
        with app.app_context():
            assert db.session.get(User, user_id).auth_generation == original_generation + 1

    def test_password_reset_revokes_existing_sessions_and_remember_state(
        self, app, client, email_log,
    ):
        old_password = 'CorrectHorse9'
        new_password = 'ResetHorse123'
        _signup_and_verify(app, client, email_log)

        with app.app_context():
            user = User.query.filter_by(email='alice@example.com').one()
            user_id = user.id
            original_generation = user.auth_generation

        session_client = app.test_client()
        assert session_client.post('/login', data={
            'username': 'alice@example.com',
            'password': old_password,
            'remember': 'on',
        }).status_code in (302, 303)

        remember_cookie = session_client.get_cookie('remember_token')
        assert remember_cookie is not None
        remember_only_client = app.test_client()
        remember_only_client.set_cookie('remember_token', remember_cookie.value)
        remember_control_client = app.test_client()
        remember_control_client.set_cookie('remember_token', remember_cookie.value)

        # This separate control proves restoration works while preserving an
        # untouched remember-only client for the post-reset assertion.
        assert remember_control_client.get('/settings').status_code == 200

        reset_client = app.test_client()
        reset_request = reset_client.post(
            '/forgot-password',
            data={'email': 'alice@example.com'},
            follow_redirects=False,
        )
        assert reset_request.status_code in (302, 303)
        reset_token = next(
            value.split(':', 1)[1]
            for _, value in reversed(email_log)
            if value.startswith('reset:')
        )
        reset_response = reset_client.post(
            f'/reset-password/{reset_token}',
            data={
                'password': new_password,
                'confirm_password': new_password,
            },
            follow_redirects=False,
        )
        assert reset_response.status_code in (302, 303)
        assert reset_response.headers['Location'].endswith('/login')

        for stale_client in (session_client, remember_only_client):
            stale_response = stale_client.get('/settings', follow_redirects=False)
            assert stale_response.status_code in (302, 303)
            assert '/login' in stale_response.headers['Location']

        with app.app_context():
            assert db.session.get(User, user_id).auth_generation == original_generation + 1

        fresh_client = app.test_client()
        assert fresh_client.post('/login', data={
            'username': 'alice@example.com',
            'password': new_password,
        }).status_code in (302, 303)
        assert fresh_client.get('/settings').status_code == 200

    def test_otp_is_single_use(self, app, client, email_log):
        _register(client)
        code = email_log[-1][1]

        # First use: succeeds.
        resp1 = client.post(
            '/verify-code?email=alice@example.com',
            data={'code': code},
            follow_redirects=False,
        )
        assert resp1.status_code in (302, 303)

        # Second use: pending record is gone, so the same code should fail.
        resp2 = client.post(
            '/verify-code?email=alice@example.com',
            data={'code': code},
        )
        assert resp2.status_code == 200
        # We are not redirected back to dashboard — the response renders an
        # error in-page.
        body = resp2.get_data(as_text=True).lower()
        assert 'verified' in body or 'no account' in body or 'expired' in body

    def test_logout_invalidates_session(self, app, client, email_log):
        _signup_and_verify(app, client, email_log)
        client.post('/login', data={'username': 'alice@example.com', 'password': 'CorrectHorse9'})

        with client.session_transaction() as sess:
            assert sess.get('_user_id') is not None

        client.post('/logout')

        with client.session_transaction() as sess:
            assert sess.get('_user_id') is None

    def test_remember_me_sets_persistent_cookie(self, app, client, email_log):
        _signup_and_verify(app, client, email_log)
        resp = client.post(
            '/login',
            data={'username': 'alice@example.com', 'password': 'CorrectHorse9', 'remember': 'on'},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)
        # Flask-Login emits a "remember_token" cookie when remember=True.
        cookies = resp.headers.getlist('Set-Cookie')
        assert any('remember_token' in c for c in cookies), \
            f"expected remember_token cookie, got {cookies}"

    def test_session_without_remember_has_no_persistent_cookie(self, app, client, email_log):
        _signup_and_verify(app, client, email_log)
        resp = client.post(
            '/login',
            data={'username': 'alice@example.com', 'password': 'CorrectHorse9'},
            follow_redirects=False,
        )
        cookies = resp.headers.getlist('Set-Cookie')
        assert not any('remember_token' in c for c in cookies)


# ---------------------------------------------------------------------------
# Rate limiting tests
# ---------------------------------------------------------------------------

class TestRateLimits:

    def test_forgot_password_target_limit_preserves_last_reset_link(
        self, rate_limited_app, rate_limited_client, email_log,
    ):
        _signup_and_verify(rate_limited_app, rate_limited_client, email_log)
        email_log.clear()

        email_variants = (
            'alice@example.com',
            'ALICE@EXAMPLE.COM',
            ' Alice@Example.com ',
        )
        for attempt, email in enumerate(email_variants, start=1):
            request_client = rate_limited_app.test_client()
            response = request_client.post(
                '/forgot-password',
                data={'email': email},
                environ_overrides={'REMOTE_ADDR': f'198.51.100.{attempt}'},
                follow_redirects=True,
            )
            assert response.status_code == 200
            assert "If an account with that email exists" in response.get_data(as_text=True)

        reset_messages = [
            value for recipient, value in email_log
            if recipient == 'alice@example.com' and value.startswith('reset:')
        ]
        assert len(reset_messages) == 3
        last_token = reset_messages[-1].split(':', 1)[1]

        with rate_limited_app.app_context():
            jti_before_rejection = User.query.filter_by(
                email='alice@example.com',
            ).one().password_reset_jti
            assert jti_before_rejection

        # A fourth equivalent spelling comes from another origin, proving the
        # normalized target bucket cannot be bypassed by client rotation.
        rejected = rate_limited_app.test_client().post(
            '/forgot-password',
            data={'email': 'aLiCe@eXaMpLe.CoM'},
            environ_overrides={'REMOTE_ADDR': '198.51.100.4'},
        )
        assert rejected.status_code == 429
        assert len(email_log) == 3

        with rate_limited_app.app_context():
            assert User.query.filter_by(
                email='alice@example.com',
            ).one().password_reset_jti == jti_before_rejection

        new_password = 'ResetHorse123'
        reset_client = rate_limited_app.test_client()
        reset_response = reset_client.post(
            f'/reset-password/{last_token}',
            data={
                'password': new_password,
                'confirm_password': new_password,
            },
            follow_redirects=False,
        )
        assert reset_response.status_code in (302, 303)
        assert reset_response.headers['Location'].endswith('/login')
        assert reset_client.post('/login', data={
            'username': 'alice@example.com',
            'password': new_password,
        }).status_code in (302, 303)

    def test_forgot_password_keeps_generic_known_and_unknown_responses(
        self, rate_limited_app, rate_limited_client, email_log,
    ):
        _signup_and_verify(rate_limited_app, rate_limited_client, email_log)
        email_log.clear()

        responses = []
        for address, remote_addr in (
            ('alice@example.com', '198.51.100.20'),
            ('nobody@example.com', '198.51.100.21'),
        ):
            responses.append(rate_limited_app.test_client().post(
                '/forgot-password',
                data={'email': address},
                environ_overrides={'REMOTE_ADDR': remote_addr},
                follow_redirects=True,
            ))

        for response in responses:
            assert response.status_code == 200
            assert "If an account with that email exists" in response.get_data(as_text=True)
        assert [recipient for recipient, value in email_log if value.startswith('reset:')] == [
            'alice@example.com',
        ]

    def test_forgot_password_client_origin_limit_is_independent(
        self, rate_limited_app, email_log,
    ):
        client = rate_limited_app.test_client()
        for attempt in range(10):
            response = client.post(
                '/forgot-password',
                data={'email': f'unknown-{attempt}@example.com'},
                follow_redirects=False,
            )
            assert response.status_code in (302, 303)

        rejected = client.post(
            '/forgot-password',
            data={'email': 'unknown-10@example.com'},
            follow_redirects=False,
        )
        assert rejected.status_code == 429
        assert email_log == []

    def test_signup_blocked_after_five_per_hour(self, rate_limited_client, email_log):
        # Five attempts succeed; the 6th comes back 429.
        for i in range(5):
            resp = rate_limited_client.post(
                '/register',
                data={
                    'email': f'user{i}@example.com',
                    'password': 'CorrectHorse9',
                },
            )
            assert resp.status_code in (200, 302, 303), f"attempt {i}: {resp.status_code}"

        resp = rate_limited_client.post(
            '/register',
            data={
                'email': 'user6@example.com',
                'password': 'CorrectHorse9',
            },
        )
        assert resp.status_code == 429

    def test_resend_blocked_after_three_per_email(
        self, rate_limited_app, rate_limited_client, email_log,
    ):
        # Stage a pending sign-up so the resend has something to refresh.
        rate_limited_client.post(
            '/register',
            data={
                'email': 'bob@example.com',
                'password': 'CorrectHorse9',
            },
        )
        # 1 verification email was sent during registration.
        emails_for_bob_before = sum(
            1 for row in email_log if row[0].lower() == 'bob@example.com'
        )

        # Three resends are allowed. Equivalent email casing shares the
        # existing normalized per-email limiter key.
        for i, email in enumerate((
            'bob@example.com',
            'Bob@Example.com',
            'BOB@EXAMPLE.COM',
        )):
            resp = rate_limited_client.post(f'/resend-code?email={email}')
            assert resp.status_code in (200, 302, 303), f"resend {i}: {resp.status_code}"

        state_after_third = _pending_verification_state(
            rate_limited_app, 'bob@example.com',
        )

        # The 4th POST is rate-limited. The route-aware 429 handler flashes a
        # warning and redirects to the verify-code screen.
        resp = rate_limited_client.post(
            '/resend-code?email=Bob@Example.com', follow_redirects=False,
        )
        assert resp.status_code in (302, 303)
        assert '/verify-code' in resp.headers.get('Location', '')

        # The rejected request neither sends another message nor rotates the
        # code, expiry, or failed-attempt state.
        emails_for_bob_after = sum(
            1 for row in email_log if row[0].lower() == 'bob@example.com'
        )
        assert emails_for_bob_after - emails_for_bob_before == 3
        assert _pending_verification_state(
            rate_limited_app, 'bob@example.com',
        ) == state_after_third
