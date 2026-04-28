"""Authentication test suite — sign-up, login, OTP, sessions, rate limits.

Covers the ``feat/auth-refactor`` flow:

* Sign-ups stage in ``pending_registration``; the live ``user`` row is only
  created after the 6-digit OTP is confirmed.
* Login is blocked for unverified accounts, lets verified accounts in,
  hides the existence of accounts behind a single generic error, and
  trips a 30-minute lockout after 5 consecutive wrong passwords.
* Rate limiting protects ``/register`` (5/h/IP) and ``/resend-code``
  (3/h/email).

The test file is self-contained: it builds its own Flask app per test so
DB state, the rate-limiter store, and email mocks never leak across tests.
The mail layer is monkey-patched (``send_verification_email`` /
``send_reset_email``) so no SMTP is ever attempted.
"""

import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from config import Config
from portfolio_app import create_app, db, limiter
from portfolio_app.models.user import User
from portfolio_app.models.pending_registration import PendingRegistration


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
    SQLALCHEMY_DATABASE_URI = (
        f"sqlite:///{(Path(__file__).resolve().parent / 'test_auth.db').as_posix()}"
    )


class _RateLimitedTestConfig(_BaseTestConfig):
    """Used only by the rate-limit tests so the rest of the suite is fast."""
    RATELIMIT_ENABLED = True


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

    monkeypatch.setattr(
        'portfolio_app.routes.auth.send_verification_email', _fake_send_verification
    )
    monkeypatch.setattr(
        'portfolio_app.routes.auth.send_reset_email', _fake_send_reset
    )
    return captured


@pytest.fixture
def app():
    """Build a fresh Flask app with rate limiting OFF for the bulk of tests."""
    app = create_app(_BaseTestConfig)
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def rate_limited_app():
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


@pytest.fixture
def rate_limited_client(rate_limited_app):
    return rate_limited_app.test_client()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register(client, **overrides):
    payload = {
        'username': 'alice',
        'email': 'alice@example.com',
        'password': 'CorrectHorse9',
        'confirm_password': 'CorrectHorse9',
    }
    payload.update(overrides)
    return client.post('/register', data=payload, follow_redirects=False)


def _last_pending(app, email):
    with app.app_context():
        return PendingRegistration.query.filter_by(email=email.lower()).first()


def _expire_pending_otp(app, email):
    """Push the OTP expiry into the past so we can exercise the expiry branch."""
    with app.app_context():
        row = PendingRegistration.query.filter_by(email=email.lower()).first()
        assert row is not None
        row.verification_code_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.session.commit()


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
            assert len(pending.verification_code) == 6

        # Exactly one verification email was queued.
        assert len(email_log) == 1
        assert email_log[0][0] == 'alice@example.com'

    def test_duplicate_email_blocked_before_db_write(self, app, client, email_log):
        # First sign-up succeeds and verifies, becoming a real user.
        _register(client)
        pending_code = email_log[-1][1]
        client.post('/verify-code?email=alice@example.com', data={'code': pending_code})
        client.post('/logout')  # verify auto-logs-in; drop the session

        # Second sign-up with the same email but different username is rejected
        # before any DB write happens for the new attempt.
        resp = _register(
            client, username='alice2', email='alice@example.com',
            password='AnotherPw99', confirm_password='AnotherPw99',
        )
        assert resp.status_code == 200  # form re-rendered with error
        with app.app_context():
            # Still exactly one user, no pending rows.
            assert User.query.count() == 1
            assert PendingRegistration.query.count() == 0

    def test_duplicate_username_blocked(self, app, client, email_log):
        _register(client)
        pending_code = email_log[-1][1]
        client.post('/verify-code?email=alice@example.com', data={'code': pending_code})
        client.post('/logout')

        resp = _register(
            client, username='alice', email='different@example.com',
            password='AnotherPw99', confirm_password='AnotherPw99',
        )
        assert resp.status_code == 200
        with app.app_context():
            assert User.query.count() == 1
            assert PendingRegistration.query.count() == 0

    def test_weak_password_rejected_at_form_layer(self, app, client, email_log):
        resp = _register(client, password='short', confirm_password='short')
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

    def test_resignup_invalidates_previous_token(self, app, client, email_log):
        _register(client)
        first_code = email_log[-1][1]

        # Same email signs up again — old OTP must no longer work.
        _register(
            client, username='alice', email='alice@example.com',
            password='SecondPw9999', confirm_password='SecondPw9999',
        )
        new_code = email_log[-1][1]
        assert new_code != first_code  # very high probability — 1-in-900k otherwise

        # Old code is rejected.
        resp = client.post(
            '/verify-code?email=alice@example.com',
            data={'code': first_code},
        )
        assert resp.status_code == 200
        with app.app_context():
            assert User.query.count() == 0
            assert PendingRegistration.query.count() == 1

        # New code works.
        resp = client.post(
            '/verify-code?email=alice@example.com',
            data={'code': new_code},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)
        with app.app_context():
            assert User.query.count() == 1
            assert PendingRegistration.query.count() == 0


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
    return kw.get('username', 'alice')


class TestLogin:

    def test_correct_credentials_logs_in(self, app, client, email_log):
        _signup_and_verify(app, client, email_log)
        resp = client.post(
            '/login',
            data={'username': 'alice', 'password': 'CorrectHorse9'},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)
        # Session cookie was issued.
        with client.session_transaction() as sess:
            assert sess.get('_user_id') is not None

    def test_wrong_password_returns_generic_error(self, app, client, email_log):
        _signup_and_verify(app, client, email_log)
        resp = client.post(
            '/login',
            data={'username': 'alice', 'password': 'WrongPw9999'},
        )
        assert resp.status_code == 200
        body = resp.get_data(as_text=True).lower()
        # Generic "invalid username or password" — no leak about which.
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

    def test_unverified_email_redirects_to_verify(self, app, client, email_log):
        # Sign up but don't verify — no User row yet, only a pending record.
        _register(client)
        resp = client.post(
            '/login',
            data={'username': 'alice', 'password': 'CorrectHorse9'},
            follow_redirects=False,
        )
        # Should redirect into the OTP entry page.
        assert resp.status_code in (302, 303)
        assert 'verify-code' in resp.headers['Location']

    def test_lockout_after_five_failed_attempts(self, app, client, email_log):
        _signup_and_verify(app, client, email_log)

        # Five consecutive wrong-password attempts must trip the lockout.
        for _ in range(5):
            client.post('/login', data={'username': 'alice', 'password': 'Bad9999999'})

        # The 6th attempt — even with the *correct* password — is locked.
        resp = client.post(
            '/login',
            data={'username': 'alice', 'password': 'CorrectHorse9'},
        )
        assert resp.status_code == 200
        body = resp.get_data(as_text=True).lower()
        assert 'too many' in body or 'locked' in body or 'try again' in body

        with app.app_context():
            user = User.query.filter_by(username='alice').one()
            assert user.locked_until is not None


# ---------------------------------------------------------------------------
# Token & session tests
# ---------------------------------------------------------------------------

class TestTokenAndSession:

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
        client.post('/login', data={'username': 'alice', 'password': 'CorrectHorse9'})

        with client.session_transaction() as sess:
            assert sess.get('_user_id') is not None

        client.post('/logout')

        with client.session_transaction() as sess:
            assert sess.get('_user_id') is None

    def test_remember_me_sets_persistent_cookie(self, app, client, email_log):
        _signup_and_verify(app, client, email_log)
        resp = client.post(
            '/login',
            data={'username': 'alice', 'password': 'CorrectHorse9', 'remember': 'on'},
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
            data={'username': 'alice', 'password': 'CorrectHorse9'},
            follow_redirects=False,
        )
        cookies = resp.headers.getlist('Set-Cookie')
        assert not any('remember_token' in c for c in cookies)


# ---------------------------------------------------------------------------
# Rate limiting tests
# ---------------------------------------------------------------------------

class TestRateLimits:

    def test_signup_blocked_after_five_per_hour(self, rate_limited_client, email_log):
        # Five attempts succeed; the 6th comes back 429.
        for i in range(5):
            resp = rate_limited_client.post(
                '/register',
                data={
                    'username': f'user{i}',
                    'email': f'user{i}@example.com',
                    'password': 'CorrectHorse9',
                    'confirm_password': 'CorrectHorse9',
                },
            )
            assert resp.status_code in (200, 302, 303), f"attempt {i}: {resp.status_code}"

        resp = rate_limited_client.post(
            '/register',
            data={
                'username': 'user6',
                'email': 'user6@example.com',
                'password': 'CorrectHorse9',
                'confirm_password': 'CorrectHorse9',
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
                'username': 'bob',
                'email': 'bob@example.com',
                'password': 'CorrectHorse9',
                'confirm_password': 'CorrectHorse9',
            },
        )

        # Three resends are allowed.
        for i in range(3):
            resp = rate_limited_client.get('/resend-code?email=bob@example.com')
            assert resp.status_code in (200, 302, 303), f"resend {i}: {resp.status_code}"

        # The 4th is rate-limited.
        resp = rate_limited_client.get('/resend-code?email=bob@example.com')
        assert resp.status_code == 429
