from dataclasses import dataclass, field

import pytest
from sqlalchemy.exc import SQLAlchemyError

from config import Config
from portfolio_app import ONEPORTFOLIO_OAUTH_EXTENSION_KEY, create_app, db
from portfolio_app.models.oauth_identity import OAuthIdentity
from portfolio_app.models.user import User
from portfolio_app.repositories.oauth_identity_repository import OAuthIdentityRepository
from portfolio_app.utils.messages import MESSAGES


PASSWORD = 'CorrectHorse9'
GOOGLE_SUBJECT = 'SensitiveGoogleSubject-123'


class _GoogleDisconnectTestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key'
    MAIL_SUPPRESS_SEND = True
    RATELIMIT_ENABLED = False
    SQLALCHEMY_DATABASE_URI = None
    GOOGLE_OAUTH_ENABLED = False
    GOOGLE_CLIENT_ID = ''
    GOOGLE_CLIENT_SECRET = ''
    GOOGLE_REDIRECT_URI = 'http://localhost/auth/google/callback'


def _config_for(db_path, **overrides):
    db_path.parent.mkdir(parents=True, exist_ok=True)

    class _Config(_GoogleDisconnectTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path.resolve().as_posix()}"

    for key, value in overrides.items():
        setattr(_Config, key, value)
    return _Config


@pytest.fixture
def app_factory(tmp_path):
    apps = []

    def _make_app(**overrides):
        app = create_app(_config_for(tmp_path / f"disconnect-{len(apps)}.sqlite", **overrides))
        with app.app_context():
            db.drop_all()
            db.create_all()
        apps.append(app)
        return app

    yield _make_app

    for app in apps:
        with app.app_context():
            db.session.remove()


@pytest.fixture
def app(app_factory):
    return app_factory()


@pytest.fixture
def client(app):
    return app.test_client()


@dataclass
class FakeGoogleClient:
    identity: dict = field(default_factory=lambda: {
        'sub': GOOGLE_SUBJECT,
        'email': 'alice@example.com',
        'email_verified': True,
    })

    def authorize_access_token(self):
        return {
            'access_token': 'test-only-token',
            'userinfo': self.identity,
        }


class FakeOAuth:
    def __init__(self, google_client):
        self.google_client = google_client

    def create_client(self, name):
        if name != 'google':
            return None
        return self.google_client


def _install_fake_oauth(app, google_client):
    app.extensions[ONEPORTFOLIO_OAUTH_EXTENSION_KEY] = FakeOAuth(google_client)


def _create_user(app, username='alice', email='alice@example.com', password=PASSWORD, verified=True):
    with app.app_context():
        user = User(username=username, email=email.lower(), is_verified=verified)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user.id


def _create_google_identity(app, user_id, subject=GOOGLE_SUBJECT):
    with app.app_context():
        identity = OAuthIdentity(
            user_id=user_id,
            provider='google',
            provider_subject=subject,
        )
        db.session.add(identity)
        db.session.commit()
        return identity.id


def _login(client, identifier='alice@example.com', password=PASSWORD):
    return client.post(
        '/login',
        data={'username': identifier, 'password': password},
        follow_redirects=False,
    )


def _logout(client):
    return client.post('/logout', follow_redirects=False)


def _identity_for_user(app, user_id):
    with app.app_context():
        return OAuthIdentity.query.filter_by(user_id=user_id, provider='google').first()


def _identity_count(app):
    with app.app_context():
        return OAuthIdentity.query.count()


def _user_snapshot(app, user_id):
    with app.app_context():
        user = db.session.get(User, user_id)
        return {
            'username': user.username,
            'email': user.email,
            'password_hash': user.password_hash,
            'is_verified': user.is_verified,
        }


def _login_session_user_id(client):
    with client.session_transaction() as sess:
        return sess.get('_user_id')


def test_unauthenticated_disconnect_preserves_login_required_behavior(app, client):
    user_id = _create_user(app)
    _create_google_identity(app, user_id)

    response = client.post('/settings/google/disconnect', data={'current_password': PASSWORD})

    assert response.status_code in (302, 303)
    assert '/login' in response.headers['Location']
    assert _identity_for_user(app, user_id) is not None


def test_google_disconnect_get_is_not_allowed(app, client):
    _create_user(app)
    _login(client)

    response = client.get('/settings/google/disconnect')

    assert response.status_code == 405


def test_google_disconnect_requires_csrf_with_normal_csrf_enabled_config(app_factory):
    app = app_factory(WTF_CSRF_ENABLED=True)
    client = app.test_client()
    user_id = _create_user(app)
    _create_google_identity(app, user_id)
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True

    response = client.post(
        '/settings/google/disconnect',
        data={'current_password': PASSWORD},
        follow_redirects=False,
    )

    assert response.status_code in (302, 303)
    assert _identity_for_user(app, user_id) is not None


def test_wrong_current_password_does_not_remove_identity(app, client):
    user_id = _create_user(app)
    _create_google_identity(app, user_id)
    _login(client)

    response = client.post(
        '/settings/google/disconnect',
        data={'current_password': 'wrong-password'},
        follow_redirects=True,
    )

    assert MESSAGES['CURRENT_PASSWORD_INCORRECT'].encode() in response.data
    assert _identity_for_user(app, user_id) is not None


def test_missing_password_does_not_remove_identity(app, client):
    user_id = _create_user(app)
    _create_google_identity(app, user_id)
    _login(client)

    response = client.post('/settings/google/disconnect', data={}, follow_redirects=True)

    assert MESSAGES['CURRENT_PASSWORD_REQUIRED'].encode() in response.data
    assert _identity_for_user(app, user_id) is not None


def test_correct_password_removes_current_users_google_identity(app, client):
    user_id = _create_user(app)
    _create_google_identity(app, user_id)
    _login(client)

    response = client.post(
        '/settings/google/disconnect',
        data={'current_password': PASSWORD},
        follow_redirects=True,
    )

    assert MESSAGES['GOOGLE_DISCONNECT_SUCCESS'].encode() in response.data
    assert _identity_for_user(app, user_id) is None


def test_successful_disconnect_commits_before_reporting_success(app, client, monkeypatch):
    from portfolio_app.routes import auth as auth_routes

    events = []
    user_id = _create_user(app)
    _create_google_identity(app, user_id)
    _login(client)
    original_commit = OAuthIdentityRepository.commit

    def _record_commit(self):
        events.append('commit')
        return original_commit(self)

    def _record_flash(message, category='message'):
        events.append(f'flash:{message}')

    monkeypatch.setattr(OAuthIdentityRepository, 'commit', _record_commit)
    monkeypatch.setattr(auth_routes, 'flash', _record_flash)

    response = client.post(
        '/settings/google/disconnect',
        data={'current_password': PASSWORD},
        follow_redirects=False,
    )

    assert response.status_code in (302, 303)
    assert events == ['commit', f"flash:{MESSAGES['GOOGLE_DISCONNECT_SUCCESS']}"]
    assert _identity_for_user(app, user_id) is None


def test_successful_disconnect_keeps_user_authenticated(app, client):
    user_id = _create_user(app)
    _create_google_identity(app, user_id)
    _login(client)

    client.post('/settings/google/disconnect', data={'current_password': PASSWORD})

    assert _login_session_user_id(client) == str(user_id)


def test_successful_disconnect_does_not_modify_user_fields_or_password_hash(app, client):
    user_id = _create_user(app)
    _create_google_identity(app, user_id)
    before = _user_snapshot(app, user_id)
    _login(client)

    client.post('/settings/google/disconnect', data={'current_password': PASSWORD})

    assert _user_snapshot(app, user_id) == before


def test_current_user_cannot_remove_another_users_identity_or_trust_browser_identifiers(app, client):
    alice_id = _create_user(app, username='alice', email='alice@example.com')
    bob_id = _create_user(app, username='bob', email='bob@example.com')
    bob_identity_id = _create_google_identity(app, bob_id)
    _login(client, 'alice@example.com')

    response = client.post(
        '/settings/google/disconnect',
        data={
            'current_password': PASSWORD,
            'user_id': str(bob_id),
            'identity_id': str(bob_identity_id),
            'provider': 'google',
            'provider_subject': GOOGLE_SUBJECT,
        },
        follow_redirects=True,
    )

    assert MESSAGES['GOOGLE_DISCONNECT_NOT_CONNECTED'].encode() in response.data
    assert _identity_for_user(app, alice_id) is None
    assert _identity_for_user(app, bob_id) is not None


def test_browser_supplied_provider_cannot_remove_non_google_identity(app, client):
    user_id = _create_user(app)
    with app.app_context():
        identity = OAuthIdentity(
            user_id=user_id,
            provider='github',
            provider_subject='github-subject',
        )
        db.session.add(identity)
        db.session.commit()
    _login(client)

    response = client.post(
        '/settings/google/disconnect',
        data={
            'current_password': PASSWORD,
            'provider': 'github',
            'provider_subject': 'github-subject',
        },
        follow_redirects=True,
    )

    assert MESSAGES['GOOGLE_DISCONNECT_NOT_CONNECTED'].encode() in response.data
    with app.app_context():
        identity = OAuthIdentity.query.filter_by(user_id=user_id, provider='github').one()
        assert identity.provider_subject == 'github-subject'


def test_no_existing_google_link_is_handled_safely(app, client):
    _create_user(app)
    _login(client)

    response = client.post(
        '/settings/google/disconnect',
        data={'current_password': PASSWORD},
        follow_redirects=True,
    )

    assert MESSAGES['GOOGLE_DISCONNECT_NOT_CONNECTED'].encode() in response.data
    assert _identity_count(app) == 0


def test_disconnect_works_when_google_oauth_enabled_or_disabled(app_factory):
    for enabled in (False, True):
        app = app_factory(
            GOOGLE_OAUTH_ENABLED=enabled,
            GOOGLE_CLIENT_ID='test-client-id' if enabled else '',
            GOOGLE_CLIENT_SECRET='test-client-secret' if enabled else '',
        )
        client = app.test_client()
        user_id = _create_user(app, username=f'user{enabled}', email=f'user{enabled}@example.com')
        _create_google_identity(app, user_id, subject=f'subject-{enabled}')
        _login(client, f'user{enabled}@example.com')

        response = client.post(
            '/settings/google/disconnect',
            data={'current_password': PASSWORD},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert _identity_for_user(app, user_id) is None


def test_database_failure_rolls_back_keeps_link_and_session_usable(app, client, monkeypatch, caplog):
    user_id = _create_user(app)
    _create_google_identity(app, user_id)
    _login(client)

    def _fail_commit(self):
        raise SQLAlchemyError(f'contains {GOOGLE_SUBJECT} {PASSWORD} test-only-token client-secret')

    monkeypatch.setattr(OAuthIdentityRepository, 'commit', _fail_commit)

    with caplog.at_level('WARNING', logger='portfolio_app.routes.auth'):
        response = client.post(
            '/settings/google/disconnect',
            data={'current_password': PASSWORD},
            follow_redirects=True,
        )

    log_text = caplog.text
    response_text = response.get_data(as_text=True)
    assert MESSAGES['GOOGLE_DISCONNECT_FAILED'] in response_text
    assert _identity_for_user(app, user_id) is not None
    with app.app_context():
        assert User.query.count() == 1
    for sensitive in (GOOGLE_SUBJECT, PASSWORD, 'test-only-token', 'client-secret'):
        assert sensitive not in log_text
        assert sensitive not in response_text


def test_unexpected_non_database_error_propagates(app, client, monkeypatch):
    user_id = _create_user(app)
    _create_google_identity(app, user_id)
    _login(client)

    def _fail_delete(self, identity):
        raise RuntimeError('programming failure')

    monkeypatch.setattr(OAuthIdentityRepository, 'delete', _fail_delete)

    with pytest.raises(RuntimeError, match='programming failure'):
        client.post('/settings/google/disconnect', data={'current_password': PASSWORD})


def test_existing_password_login_still_works_after_disconnect(app, client):
    user_id = _create_user(app)
    _create_google_identity(app, user_id)
    _login(client)

    client.post('/settings/google/disconnect', data={'current_password': PASSWORD})
    _logout(client)
    _login(client)

    assert _login_session_user_id(client) == str(user_id)


def test_later_google_callback_can_recreate_link_after_disconnect(app_factory):
    app = app_factory(
        GOOGLE_OAUTH_ENABLED=True,
        GOOGLE_CLIENT_ID='test-client-id',
        GOOGLE_CLIENT_SECRET='test-client-secret',
    )
    client = app.test_client()
    user_id = _create_user(app)
    _create_google_identity(app, user_id)
    _login(client)
    client.post('/settings/google/disconnect', data={'current_password': PASSWORD})
    assert _identity_for_user(app, user_id) is None
    _logout(client)
    _install_fake_oauth(app, FakeGoogleClient())

    response = client.get('/auth/google/callback')

    assert response.status_code in (302, 303)
    assert _identity_for_user(app, user_id).provider_subject == GOOGLE_SUBJECT
    assert _login_session_user_id(client) == str(user_id)
