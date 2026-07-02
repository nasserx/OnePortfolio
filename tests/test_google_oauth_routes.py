"""Google OAuth route tests.

These tests replace the app-scoped OAuth registry with small fakes through
``app.extensions``. They do not contact Google or inspect Authlib internals.
"""

from dataclasses import dataclass, field

import pytest
from authlib.integrations.base_client import OAuthError
from flask import redirect
from sqlalchemy.exc import IntegrityError

from config import Config
from portfolio_app import (
    ONEPORTFOLIO_OAUTH_EXTENSION_KEY,
    create_app,
    db,
    get_oauth,
    limiter,
)
from portfolio_app.models.oauth_identity import OAuthIdentity
from portfolio_app.models.user import User
from portfolio_app.repositories.oauth_identity_repository import OAuthIdentityRepository


class _OAuthRoutesTestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key'
    MAIL_SUPPRESS_SEND = True
    RATELIMIT_ENABLED = False
    SQLALCHEMY_DATABASE_URI = None
    GOOGLE_OAUTH_ENABLED = True
    GOOGLE_CLIENT_ID = 'test-client-id'
    GOOGLE_CLIENT_SECRET = 'test-client-secret'
    GOOGLE_REDIRECT_URI = 'http://localhost/auth/google/callback'


def _config_for(db_path, **overrides):
    db_path.parent.mkdir(parents=True, exist_ok=True)

    class _Config(_OAuthRoutesTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path.resolve().as_posix()}"

    for key, value in overrides.items():
        setattr(_Config, key, value)
    return _Config


@dataclass
class FakeGoogleClient:
    identity: dict | None = field(default_factory=lambda: {
        'sub': 'google-sub-alice',
        'email': 'alice@example.com',
        'email_verified': True,
    })
    token: dict | object | None = None
    oauth_error: Exception | None = None
    redirect_uris: list[str] = field(default_factory=list)
    parse_id_token_called: bool = False

    def authorize_redirect(self, redirect_uri):
        self.redirect_uris.append(redirect_uri)
        return redirect('/fake-google-authorize')

    def authorize_access_token(self):
        if self.oauth_error:
            raise self.oauth_error
        if self.token is not None:
            return self.token
        return {
            'access_token': 'test-only-token',
            'userinfo': self.identity,
        }

    def parse_id_token(self, token):
        self.parse_id_token_called = True
        raise AssertionError('parse_id_token must not be called')


class FakeOAuth:
    def __init__(self, google_client=None):
        self.google_client = google_client

    def create_client(self, name):
        if name != 'google':
            return None
        return self.google_client


@pytest.fixture
def app(tmp_path):
    app = create_app(_config_for(tmp_path / 'oauth-routes.sqlite'))
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
def client(app):
    return app.test_client()


def _install_fake_oauth(app, google_client):
    app.extensions[ONEPORTFOLIO_OAUTH_EXTENSION_KEY] = FakeOAuth(google_client)


def _create_verified_user(app, email='alice@example.com', username='alice'):
    with app.app_context():
        user = User(username=username, email=email.lower(), is_verified=True)
        user.set_password('CorrectHorse9')
        db.session.add(user)
        db.session.commit()
        return user.id


def _create_unverified_user(app, email='alice@example.com', username='alice'):
    with app.app_context():
        user = User(username=username, email=email.lower(), is_verified=False)
        user.set_password('CorrectHorse9')
        db.session.add(user)
        db.session.commit()
        return user.id


def _create_oauth_identity(app, user_id, subject='google-sub-alice', provider='google'):
    with app.app_context():
        identity = OAuthIdentity(
            user_id=user_id,
            provider=provider,
            provider_subject=subject,
        )
        db.session.add(identity)
        db.session.commit()
        return identity.id


def _identity_count(app):
    with app.app_context():
        return OAuthIdentity.query.count()


def _identity_snapshot(app):
    with app.app_context():
        return [
            {
                'user_id': identity.user_id,
                'provider': identity.provider,
                'provider_subject': identity.provider_subject,
            }
            for identity in OAuthIdentity.query.order_by(OAuthIdentity.id).all()
        ]


def _get_user_snapshot(app, user_id):
    with app.app_context():
        user = db.session.get(User, user_id)
        return {
            'count': User.query.count(),
            'username': user.username,
            'email': user.email,
            'password_hash': user.password_hash,
            'is_verified': user.is_verified,
        }


def _google_identity(sub='google-sub-alice', email='alice@example.com', verified=True):
    return {
        'sub': sub,
        'email': email,
        'email_verified': verified,
    }


def test_google_login_start_returns_404_when_disabled(tmp_path):
    disabled_app = create_app(_config_for(
        tmp_path / 'disabled.sqlite',
        GOOGLE_OAUTH_ENABLED=False,
    ))

    resp = disabled_app.test_client().get('/auth/google')

    assert resp.status_code == 404


def test_google_login_start_calls_authorize_redirect_when_enabled(app, client):
    fake_google = FakeGoogleClient()
    _install_fake_oauth(app, fake_google)

    resp = client.get('/auth/google')

    assert resp.status_code in (302, 303)
    assert resp.headers['Location'].endswith('/fake-google-authorize')
    assert fake_google.redirect_uris == ['http://localhost/auth/google/callback']


def test_google_login_start_preserves_safe_local_next(app, client):
    fake_google = FakeGoogleClient()
    _install_fake_oauth(app, fake_google)

    client.get('/auth/google?next=/settings')

    with client.session_transaction() as sess:
        assert sess['google_oauth_next'] == '/settings'


def test_google_login_start_discards_external_next(app, client):
    fake_google = FakeGoogleClient()
    _install_fake_oauth(app, fake_google)

    client.get('/auth/google?next=https://evil.example/account')

    with client.session_transaction() as sess:
        assert 'google_oauth_next' not in sess


def test_google_login_start_does_not_expose_credentials_or_tokens(app, client):
    fake_google = FakeGoogleClient()
    _install_fake_oauth(app, fake_google)

    resp = client.get('/auth/google')
    location = resp.headers['Location']

    assert 'test-client-secret' not in location
    assert 'fake-access-token' not in location
    assert 'authorization_code' not in location


def test_google_callback_returns_404_when_disabled(tmp_path):
    disabled_app = create_app(_config_for(
        tmp_path / 'disabled.sqlite',
        GOOGLE_OAUTH_ENABLED=False,
    ))

    resp = disabled_app.test_client().get('/auth/google/callback')

    assert resp.status_code == 404


def test_google_callback_logs_in_existing_verified_user(app, client):
    user_id = _create_verified_user(app)
    fake_google = FakeGoogleClient()
    _install_fake_oauth(app, fake_google)

    resp = client.get('/auth/google/callback')

    assert resp.status_code in (302, 303)
    assert resp.headers['Location'] == '/'
    assert fake_google.parse_id_token_called is False
    with client.session_transaction() as sess:
        assert sess.get('_user_id') == str(user_id)
    assert _identity_snapshot(app) == [{
        'user_id': user_id,
        'provider': 'google',
        'provider_subject': 'google-sub-alice',
    }]


def test_google_callback_existing_provider_subject_logs_in_linked_verified_user(app, client):
    user_id = _create_verified_user(app, email='linked@example.com')
    _create_oauth_identity(app, user_id, subject='stable-google-sub')
    _install_fake_oauth(app, FakeGoogleClient(identity=_google_identity(
        sub='stable-google-sub',
        email='changed-google-email@example.com',
    )))

    resp = client.get('/auth/google/callback')

    assert resp.status_code in (302, 303)
    with client.session_transaction() as sess:
        assert sess.get('_user_id') == str(user_id)


def test_google_callback_linked_login_does_not_require_current_google_email_match(app, client):
    user_id = _create_verified_user(app, email='local@example.com')
    _create_oauth_identity(app, user_id, subject='stable-sub')
    _install_fake_oauth(app, FakeGoogleClient(identity=_google_identity(
        sub='stable-sub',
        email='renamed-google@example.com',
    )))

    client.get('/auth/google/callback')

    with client.session_transaction() as sess:
        assert sess.get('_user_id') == str(user_id)


def test_google_callback_linked_login_does_not_create_another_identity(app, client):
    user_id = _create_verified_user(app)
    _create_oauth_identity(app, user_id, subject='stable-sub')
    _install_fake_oauth(app, FakeGoogleClient(identity=_google_identity(sub='stable-sub')))

    client.get('/auth/google/callback')

    assert _identity_count(app) == 1


def test_google_callback_linked_login_does_not_modify_local_user_fields(app, client):
    user_id = _create_verified_user(app, email='local@example.com')
    _create_oauth_identity(app, user_id, subject='stable-sub')
    before = _get_user_snapshot(app, user_id)
    _install_fake_oauth(app, FakeGoogleClient(identity=_google_identity(
        sub='stable-sub',
        email='changed@example.com',
    )))

    client.get('/auth/google/callback')

    assert _get_user_snapshot(app, user_id) == before


def test_google_callback_linked_identity_to_unverified_user_is_rejected(app, client):
    user_id = _create_unverified_user(app)
    _create_oauth_identity(app, user_id, subject='stable-sub')
    _install_fake_oauth(app, FakeGoogleClient(identity=_google_identity(sub='stable-sub')))

    resp = client.get('/auth/google/callback', follow_redirects=True)

    assert 'Google sign-in could not be completed.' in resp.get_data(as_text=True)
    with client.session_transaction() as sess:
        assert '_user_id' not in sess


def test_google_callback_matches_email_case_insensitively(app, client):
    user_id = _create_verified_user(app, email='alice@example.com')
    _install_fake_oauth(app, FakeGoogleClient(identity={
        'sub': 'google-sub-alice',
        'email': 'ALICE@EXAMPLE.COM',
        'email_verified': True,
    }))

    client.get('/auth/google/callback')

    with client.session_transaction() as sess:
        assert sess.get('_user_id') == str(user_id)


def test_google_callback_uses_userinfo_from_access_token(app, client):
    user_id = _create_verified_user(app, email='token-user@example.com')
    fake_google = FakeGoogleClient(
        identity=_google_identity(email='ignored@example.com'),
        token={
            'access_token': 'test-only-token',
            'userinfo': {
                'sub': 'token-user-sub',
                'email': 'TOKEN-USER@EXAMPLE.COM',
                'email_verified': True,
            },
        },
    )
    _install_fake_oauth(app, fake_google)

    client.get('/auth/google/callback')

    assert fake_google.parse_id_token_called is False
    with client.session_transaction() as sess:
        assert sess.get('_user_id') == str(user_id)


def test_google_callback_redirects_to_default_authenticated_destination(app, client):
    _create_verified_user(app)
    _install_fake_oauth(app, FakeGoogleClient())

    resp = client.get('/auth/google/callback')

    assert resp.headers['Location'] == '/'


def test_google_callback_redirects_to_preserved_safe_local_next(app, client):
    _create_verified_user(app)
    _install_fake_oauth(app, FakeGoogleClient())
    with client.session_transaction() as sess:
        sess['google_oauth_next'] = '/settings'

    resp = client.get('/auth/google/callback')

    assert resp.headers['Location'].endswith('/settings')


def test_google_callback_refuses_external_or_protocol_relative_next(app, client):
    _create_verified_user(app)
    _install_fake_oauth(app, FakeGoogleClient())
    with client.session_transaction() as sess:
        sess['google_oauth_next'] = '//evil.example/path'

    resp = client.get('/auth/google/callback')

    assert resp.headers['Location'] == '/'


def test_google_callback_refuses_missing_email(app, client):
    _create_verified_user(app)
    _install_fake_oauth(app, FakeGoogleClient(identity={
        'sub': 'missing-email-sub',
        'email_verified': True,
    }))

    resp = client.get('/auth/google/callback', follow_redirects=True)

    assert resp.status_code == 200
    assert 'Google sign-in could not be completed.' in resp.get_data(as_text=True)


def test_google_callback_refuses_missing_sub(app, client):
    _create_verified_user(app)
    _install_fake_oauth(app, FakeGoogleClient(identity={
        'email': 'alice@example.com',
        'email_verified': True,
    }))

    resp = client.get('/auth/google/callback', follow_redirects=True)

    assert 'Google sign-in could not be completed.' in resp.get_data(as_text=True)
    assert _identity_count(app) == 0


def test_google_callback_refuses_empty_sub(app, client):
    _create_verified_user(app)
    _install_fake_oauth(app, FakeGoogleClient(identity=_google_identity(sub='')))

    resp = client.get('/auth/google/callback', follow_redirects=True)

    assert 'Google sign-in could not be completed.' in resp.get_data(as_text=True)
    assert _identity_count(app) == 0


def test_google_callback_refuses_missing_userinfo(app, client):
    _create_verified_user(app)
    _install_fake_oauth(app, FakeGoogleClient(token={'access_token': 'test-only-token'}))

    resp = client.get('/auth/google/callback', follow_redirects=True)

    assert 'Google sign-in could not be completed.' in resp.get_data(as_text=True)


def test_google_callback_refuses_non_mapping_token(app, client):
    _create_verified_user(app)
    _install_fake_oauth(app, FakeGoogleClient(token='not-a-token-mapping'))

    resp = client.get('/auth/google/callback', follow_redirects=True)

    assert 'Google sign-in could not be completed.' in resp.get_data(as_text=True)


def test_google_callback_refuses_non_mapping_userinfo(app, client):
    _create_verified_user(app)
    _install_fake_oauth(app, FakeGoogleClient(token={
        'access_token': 'test-only-token',
        'userinfo': 'not-userinfo',
    }))

    resp = client.get('/auth/google/callback', follow_redirects=True)

    assert 'Google sign-in could not be completed.' in resp.get_data(as_text=True)


def test_google_callback_refuses_email_verified_false(app, client):
    _create_verified_user(app)
    _install_fake_oauth(app, FakeGoogleClient(identity={
        'sub': 'unverified-email-sub',
        'email': 'alice@example.com',
        'email_verified': False,
    }))

    resp = client.get('/auth/google/callback', follow_redirects=True)

    assert 'Google sign-in could not be completed.' in resp.get_data(as_text=True)


def test_google_callback_refuses_missing_email_verified(app, client):
    _create_verified_user(app)
    _install_fake_oauth(app, FakeGoogleClient(identity={
        'sub': 'missing-email-verified-sub',
        'email': 'alice@example.com',
    }))

    resp = client.get('/auth/google/callback', follow_redirects=True)

    assert 'Google sign-in could not be completed.' in resp.get_data(as_text=True)


def test_google_callback_does_not_create_user_when_no_match(app, client):
    _install_fake_oauth(app, FakeGoogleClient(identity={
        'sub': 'missing-account-sub',
        'email': 'missing@example.com',
        'email_verified': True,
    }))

    resp = client.get('/auth/google/callback', follow_redirects=True)

    with app.app_context():
        assert User.query.count() == 0
        assert OAuthIdentity.query.count() == 0
    assert 'No existing account matches that Google email.' in resp.get_data(as_text=True)


def test_google_callback_first_link_creates_google_identity_for_verified_email(app, client):
    user_id = _create_verified_user(app, email='alice@example.com')
    _install_fake_oauth(app, FakeGoogleClient(identity=_google_identity(
        sub='NewSub-CaseSensitive',
        email='ALICE@EXAMPLE.COM',
    )))

    resp = client.get('/auth/google/callback')

    assert resp.status_code in (302, 303)
    assert _identity_snapshot(app) == [{
        'user_id': user_id,
        'provider': 'google',
        'provider_subject': 'NewSub-CaseSensitive',
    }]
    with client.session_transaction() as sess:
        assert sess.get('_user_id') == str(user_id)


def test_google_callback_created_identity_stores_subject_unchanged(app, client):
    user_id = _create_verified_user(app)
    _install_fake_oauth(app, FakeGoogleClient(identity=_google_identity(
        sub=' Subject With Case And Spaces ',
    )))

    client.get('/auth/google/callback')

    assert _identity_snapshot(app) == [{
        'user_id': user_id,
        'provider': 'google',
        'provider_subject': ' Subject With Case And Spaces ',
    }]


def test_google_callback_subject_is_opaque_and_case_sensitive(app, client):
    linked_user_id = _create_verified_user(app, email='linked@example.com', username='linked')
    new_user_id = _create_verified_user(app, email='alice@example.com', username='alice')
    _create_oauth_identity(app, linked_user_id, subject='CaseSensitiveSub')
    _install_fake_oauth(app, FakeGoogleClient(identity=_google_identity(
        sub='casesensitivesub',
        email='alice@example.com',
    )))

    client.get('/auth/google/callback')

    with client.session_transaction() as sess:
        assert sess.get('_user_id') == str(new_user_id)
    assert sorted(row['provider_subject'] for row in _identity_snapshot(app)) == [
        'CaseSensitiveSub',
        'casesensitivesub',
    ]


def test_google_callback_logs_in_only_after_identity_persisted(app, client, monkeypatch):
    _create_verified_user(app)
    _install_fake_oauth(app, FakeGoogleClient())

    def _fail_commit(self):
        raise RuntimeError('database failure')

    login_calls = []
    monkeypatch.setattr(OAuthIdentityRepository, 'commit', _fail_commit)
    monkeypatch.setattr(
        'portfolio_app.routes.auth.login_user',
        lambda user, remember=False: login_calls.append((user.id, remember)),
    )

    with pytest.raises(RuntimeError, match='database failure'):
        client.get('/auth/google/callback')

    assert login_calls == []


def test_google_callback_unverified_local_account_is_not_linked(app, client):
    _create_unverified_user(app)
    _install_fake_oauth(app, FakeGoogleClient())

    resp = client.get('/auth/google/callback', follow_redirects=True)

    assert 'No existing account matches that Google email.' in resp.get_data(as_text=True)
    assert _identity_count(app) == 0


def test_google_callback_user_linked_to_different_google_subject_is_rejected(app, client):
    user_id = _create_verified_user(app)
    _create_oauth_identity(app, user_id, subject='existing-sub')
    _install_fake_oauth(app, FakeGoogleClient(identity=_google_identity(sub='new-sub')))

    resp = client.get('/auth/google/callback', follow_redirects=True)

    assert 'Google sign-in could not be completed.' in resp.get_data(as_text=True)
    assert _identity_snapshot(app) == [{
        'user_id': user_id,
        'provider': 'google',
        'provider_subject': 'existing-sub',
    }]


def test_google_callback_never_replaces_existing_identity(app, client):
    user_id = _create_verified_user(app)
    _create_oauth_identity(app, user_id, subject='existing-sub')
    _install_fake_oauth(app, FakeGoogleClient(identity=_google_identity(sub='replacement-sub')))

    client.get('/auth/google/callback')

    assert _identity_snapshot(app) == [{
        'user_id': user_id,
        'provider': 'google',
        'provider_subject': 'existing-sub',
    }]


def test_google_callback_provider_subject_conflict_rolls_back_safely(app, client, monkeypatch):
    matched_user_id = _create_verified_user(app, email='alice@example.com', username='alice')
    other_user_id = _create_verified_user(app, email='other@example.com', username='other')
    _install_fake_oauth(app, FakeGoogleClient(identity=_google_identity(sub='conflict-sub')))

    def _conflict_commit(self):
        self.db.session.rollback()
        self.db.session.add(OAuthIdentity(
            user_id=other_user_id,
            provider='google',
            provider_subject='conflict-sub',
        ))
        self.db.session.commit()
        raise IntegrityError('race', {}, Exception('unique'))

    monkeypatch.setattr(OAuthIdentityRepository, 'commit', _conflict_commit)

    resp = client.get('/auth/google/callback', follow_redirects=True)

    assert 'Google sign-in could not be completed.' in resp.get_data(as_text=True)
    assert _identity_snapshot(app) == [{
        'user_id': other_user_id,
        'provider': 'google',
        'provider_subject': 'conflict-sub',
    }]
    with app.app_context():
        assert db.session.get(User, matched_user_id).email == 'alice@example.com'


def test_google_callback_user_provider_conflict_rolls_back_safely(app, client, monkeypatch):
    user_id = _create_verified_user(app)
    _install_fake_oauth(app, FakeGoogleClient(identity=_google_identity(sub='incoming-sub')))

    def _conflict_commit(self):
        self.db.session.rollback()
        self.db.session.add(OAuthIdentity(
            user_id=user_id,
            provider='google',
            provider_subject='different-race-sub',
        ))
        self.db.session.commit()
        raise IntegrityError('race', {}, Exception('unique'))

    monkeypatch.setattr(OAuthIdentityRepository, 'commit', _conflict_commit)

    resp = client.get('/auth/google/callback', follow_redirects=True)

    assert 'Google sign-in could not be completed.' in resp.get_data(as_text=True)
    assert _identity_snapshot(app) == [{
        'user_id': user_id,
        'provider': 'google',
        'provider_subject': 'different-race-sub',
    }]


def test_google_callback_race_resolving_same_user_and_subject_logs_in(app, client, monkeypatch):
    user_id = _create_verified_user(app)
    _install_fake_oauth(app, FakeGoogleClient(identity=_google_identity(sub='same-race-sub')))

    def _conflict_commit(self):
        self.db.session.rollback()
        self.db.session.add(OAuthIdentity(
            user_id=user_id,
            provider='google',
            provider_subject='same-race-sub',
        ))
        self.db.session.commit()
        raise IntegrityError('race', {}, Exception('unique'))

    monkeypatch.setattr(OAuthIdentityRepository, 'commit', _conflict_commit)

    resp = client.get('/auth/google/callback')

    assert resp.status_code in (302, 303)
    with client.session_transaction() as sess:
        assert sess.get('_user_id') == str(user_id)
    assert _identity_snapshot(app) == [{
        'user_id': user_id,
        'provider': 'google',
        'provider_subject': 'same-race-sub',
    }]


def test_google_callback_race_rejects_another_user_or_subject(app, client, monkeypatch):
    matched_user_id = _create_verified_user(app, email='alice@example.com', username='alice')
    other_user_id = _create_verified_user(app, email='other@example.com', username='other')
    _install_fake_oauth(app, FakeGoogleClient(identity=_google_identity(sub='incoming-sub')))

    def _conflict_commit(self):
        self.db.session.rollback()
        self.db.session.add(OAuthIdentity(
            user_id=other_user_id,
            provider='google',
            provider_subject='incoming-sub',
        ))
        self.db.session.commit()
        raise IntegrityError('race', {}, Exception('unique'))

    monkeypatch.setattr(OAuthIdentityRepository, 'commit', _conflict_commit)

    resp = client.get('/auth/google/callback', follow_redirects=True)

    assert 'Google sign-in could not be completed.' in resp.get_data(as_text=True)
    with client.session_transaction() as sess:
        assert '_user_id' not in sess
    with app.app_context():
        assert db.session.get(User, matched_user_id) is not None


def test_google_callback_database_session_remains_usable_after_integrity_rollback(app, client, monkeypatch):
    other_user_id = _create_verified_user(app, email='other@example.com', username='other')
    _create_verified_user(app, email='alice@example.com', username='alice')
    _install_fake_oauth(app, FakeGoogleClient(identity=_google_identity(sub='conflict-sub')))

    def _conflict_commit(self):
        self.db.session.rollback()
        self.db.session.add(OAuthIdentity(
            user_id=other_user_id,
            provider='google',
            provider_subject='conflict-sub',
        ))
        self.db.session.commit()
        raise IntegrityError('race', {}, Exception('unique'))

    monkeypatch.setattr(OAuthIdentityRepository, 'commit', _conflict_commit)

    client.get('/auth/google/callback')

    with app.app_context():
        assert User.query.count() == 2
        assert OAuthIdentity.query.count() == 1


def test_google_callback_does_not_change_existing_user_password_or_identity(app, client):
    user_id = _create_verified_user(app)
    before = _get_user_snapshot(app, user_id)
    _install_fake_oauth(app, FakeGoogleClient())

    client.get('/auth/google/callback')

    after = _get_user_snapshot(app, user_id)
    assert after == before


def test_google_callback_handles_oauth_denial_with_generic_redirect(app, client):
    _create_verified_user(app)
    _install_fake_oauth(app, FakeGoogleClient(
        oauth_error=OAuthError(error='access_denied'),
    ))

    resp = client.get('/auth/google/callback', follow_redirects=True)

    assert resp.status_code == 200
    assert 'Google sign-in could not be completed.' in resp.get_data(as_text=True)


def test_google_callback_removes_preserved_next_after_success(app, client):
    _create_verified_user(app)
    _install_fake_oauth(app, FakeGoogleClient())
    with client.session_transaction() as sess:
        sess['google_oauth_next'] = '/settings'

    client.get('/auth/google/callback')

    with client.session_transaction() as sess:
        assert 'google_oauth_next' not in sess


def test_google_callback_removes_preserved_next_after_expected_oauth_failure(app, client):
    _install_fake_oauth(app, FakeGoogleClient(
        oauth_error=OAuthError(error='access_denied'),
    ))
    with client.session_transaction() as sess:
        sess['google_oauth_next'] = '/settings'

    client.get('/auth/google/callback')

    with client.session_transaction() as sess:
        assert 'google_oauth_next' not in sess


def test_google_callback_oauth_failure_log_excludes_sensitive_values(app, client, caplog):
    _install_fake_oauth(app, FakeGoogleClient(
        oauth_error=OAuthError(error='authorization-code test-only-token test-client-secret provider-response'),
    ))
    with client.session_transaction() as sess:
        sess['google_oauth_next'] = '/authorization-code'

    with caplog.at_level('INFO', logger='portfolio_app.routes.auth'):
        client.get('/auth/google/callback')

    log_text = caplog.text
    assert 'OAuthError' in log_text
    assert 'authorization-code' not in log_text
    assert 'test-only-token' not in log_text
    assert 'test-client-secret' not in log_text
    assert 'provider-response' not in log_text


def test_google_callback_unexpected_non_oauth_error_propagates(app, client):
    _install_fake_oauth(app, FakeGoogleClient(
        oauth_error=RuntimeError('programming failure'),
    ))

    with pytest.raises(RuntimeError, match='programming failure'):
        client.get('/auth/google/callback')


def test_google_callback_does_not_persist_token_data(app, client):
    _create_verified_user(app)
    _install_fake_oauth(app, FakeGoogleClient(token={
        'access_token': 'fake-access-token',
        'refresh_token': 'fake-refresh-token',
        'id_token': 'fake-id-token',
        'userinfo': {
            'sub': 'no-token-persistence-sub',
            'email': 'alice@example.com',
            'email_verified': True,
        },
    }))

    client.get('/auth/google/callback')

    with client.session_transaction() as sess:
        serialized_values = ' '.join(str(value) for value in sess.values())
        assert 'fake-access-token' not in serialized_values
        assert 'fake-refresh-token' not in serialized_values
        assert 'fake-id-token' not in serialized_values


def test_google_callback_does_not_store_userinfo_payload_or_provider_email(app, client):
    _create_verified_user(app)
    _install_fake_oauth(app, FakeGoogleClient(token={
        'access_token': 'fake-access-token',
        'userinfo': {
            'sub': 'payload-sub',
            'email': 'alice@example.com',
            'email_verified': True,
            'name': 'Provider Name',
            'picture': 'https://provider.example/avatar.png',
            'provider_response': 'provider-response',
        },
    }))

    client.get('/auth/google/callback')

    with app.app_context():
        identity = OAuthIdentity.query.one()
        assert identity.provider == 'google'
        assert identity.provider_subject == 'payload-sub'
        assert not hasattr(identity, 'provider_email')
        assert not hasattr(identity, 'name')
        assert not hasattr(identity, 'picture')


def test_google_callback_sensitive_values_not_in_logs_or_response(app, client, caplog):
    _create_verified_user(app)
    _install_fake_oauth(app, FakeGoogleClient(token={
        'access_token': 'sensitive-access-token',
        'userinfo': {
            'sub': 'SensitiveSubjectValue',
            'email': 'missing@example.com',
            'email_verified': True,
            'provider_response': 'sensitive-provider-response',
        },
    }))

    with caplog.at_level('INFO', logger='portfolio_app.routes.auth'):
        resp = client.get(
            '/auth/google/callback?code=sensitive-authorization-code',
            follow_redirects=True,
        )

    combined = caplog.text + resp.get_data(as_text=True)
    assert 'SensitiveSubjectValue' not in combined
    assert 'sensitive-access-token' not in combined
    assert 'sensitive-authorization-code' not in combined
    assert 'test-client-secret' not in combined
    assert 'sensitive-provider-response' not in combined


def test_google_oauth_routes_use_app_scoped_oauth_instances(tmp_path):
    enabled_app = create_app(_config_for(tmp_path / 'enabled.sqlite'))
    disabled_app = create_app(_config_for(
        tmp_path / 'disabled.sqlite',
        GOOGLE_OAUTH_ENABLED=False,
    ))
    enabled_fake = FakeOAuth(FakeGoogleClient())
    disabled_fake = FakeOAuth(None)
    enabled_app.extensions[ONEPORTFOLIO_OAUTH_EXTENSION_KEY] = enabled_fake
    disabled_app.extensions[ONEPORTFOLIO_OAUTH_EXTENSION_KEY] = disabled_fake

    with enabled_app.app_context():
        assert get_oauth().create_client('google') is enabled_fake.google_client
    with disabled_app.app_context():
        assert get_oauth().create_client('google') is None


def test_google_oauth_routes_perform_no_real_network_request(app, client, monkeypatch):
    def _fail_network(*args, **kwargs):
        raise AssertionError('network request was attempted')

    monkeypatch.setattr('requests.sessions.Session.request', _fail_network)
    _create_verified_user(app)
    _install_fake_oauth(app, FakeGoogleClient())

    resp = client.get('/auth/google/callback')

    assert resp.status_code in (302, 303)
