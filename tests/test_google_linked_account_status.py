"""Read-only Google linked-account status tests."""

import pytest

from config import Config
from portfolio_app import create_app, db, limiter
from portfolio_app.models.oauth_identity import OAuthIdentity
from portfolio_app.models.user import User


class _LinkedStatusTestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key'
    MAIL_SUPPRESS_SEND = True
    RATELIMIT_ENABLED = False
    SQLALCHEMY_DATABASE_URI = None
    GOOGLE_OAUTH_ENABLED = False
    GOOGLE_CLIENT_ID = ''
    GOOGLE_CLIENT_SECRET = ''
    GOOGLE_REDIRECT_URI = ''


def _config_for(db_path, **overrides):
    db_path.parent.mkdir(parents=True, exist_ok=True)

    class _Config(_LinkedStatusTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path.resolve().as_posix()}"

    for key, value in overrides.items():
        setattr(_Config, key, value)
    return _Config


@pytest.fixture
def app_factory(tmp_path):
    created = []

    def _make_app(**overrides):
        app = create_app(_config_for(
            tmp_path / f"linked-status-{len(created)}.sqlite",
            **overrides,
        ))
        with app.app_context():
            db.drop_all()
            db.create_all()
        try:
            limiter.reset()
        except Exception:
            pass
        created.append(app)
        return app

    yield _make_app

    for app in created:
        with app.app_context():
            db.session.remove()


def _create_user(app, username='alice', email='alice@example.com', user_id=None):
    with app.app_context():
        user = User(
            id=user_id,
            username=username,
            email=email.lower(),
            is_verified=True,
        )
        user.set_password('CorrectHorse9')
        db.session.add(user)
        db.session.commit()
        return user.id


def _create_google_identity(app, user_id, subject='OpaqueGoogleSubject', identity_id=None):
    with app.app_context():
        identity = OAuthIdentity(
            id=identity_id,
            user_id=user_id,
            provider='google',
            provider_subject=subject,
        )
        db.session.add(identity)
        db.session.commit()
        return identity.id


def _login(client, email='alice@example.com'):
    return client.post(
        '/login',
        data={'username': email, 'password': 'CorrectHorse9'},
        follow_redirects=False,
    )


def _settings_html(app, email='alice@example.com'):
    client = app.test_client()
    _login(client, email=email)
    resp = client.get('/settings?tab=security')
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def _enabled_oauth_overrides():
    return {
        'GOOGLE_OAUTH_ENABLED': True,
        'GOOGLE_CLIENT_ID': 'test-client-id',
        'GOOGLE_CLIENT_SECRET': 'test-client-secret',
        'GOOGLE_REDIRECT_URI': 'http://localhost/auth/google/callback',
    }


def test_settings_requires_authentication(app_factory):
    app = app_factory()
    resp = app.test_client().get('/settings?tab=security')

    assert resp.status_code in (302, 303)
    assert '/login' in resp.headers['Location']


def test_unlinked_user_sees_google_not_connected(app_factory):
    app = app_factory()
    _create_user(app)

    html = _settings_html(app)

    assert 'Connected sign-in methods' in html
    assert 'Google' in html
    assert 'Not connected' in html
    assert 'Connected' not in html.split('Google', 1)[1].split('Not connected', 1)[0]


def test_linked_user_sees_google_connected(app_factory):
    app = app_factory()
    user_id = _create_user(app)
    _create_google_identity(app, user_id)

    html = _settings_html(app)

    assert 'Connected sign-in methods' in html
    assert 'Google' in html
    assert 'Connected' in html
    assert 'Not connected' not in html


def test_status_is_based_only_on_current_user(app_factory):
    app = app_factory()
    _create_user(app, username='alice', email='alice@example.com')
    bob_id = _create_user(app, username='bob', email='bob@example.com')
    _create_google_identity(app, bob_id)

    html = _settings_html(app, email='alice@example.com')

    assert 'Not connected' in html
    assert 'Connected' not in html.split('Google', 1)[1].split('Not connected', 1)[0]


def test_one_user_cannot_see_another_users_link_status(app_factory):
    app = app_factory()
    alice_id = _create_user(app, username='alice', email='alice@example.com')
    bob_id = _create_user(app, username='bob', email='bob@example.com')
    _create_google_identity(app, bob_id, subject='BobOpaqueSubject')

    alice_html = _settings_html(app, email='alice@example.com')
    bob_html = _settings_html(app, email='bob@example.com')

    assert alice_id != bob_id
    assert 'Not connected' in alice_html
    assert 'Connected' in bob_html
    assert 'BobOpaqueSubject' not in alice_html
    assert 'BobOpaqueSubject' not in bob_html


def test_status_remains_accurate_when_google_oauth_disabled(app_factory):
    app = app_factory(GOOGLE_OAUTH_ENABLED=False)
    user_id = _create_user(app)
    _create_google_identity(app, user_id)

    html = _settings_html(app)

    assert 'Connected' in html
    assert 'Not connected' not in html


def test_status_remains_accurate_when_google_oauth_enabled(app_factory):
    app = app_factory(**_enabled_oauth_overrides())
    user_id = _create_user(app)
    _create_google_identity(app, user_id)

    html = _settings_html(app)

    assert 'Connected' in html
    assert 'Not connected' not in html


def test_provider_subject_identity_id_and_user_id_are_not_rendered(app_factory):
    app = app_factory()
    user_id = _create_user(app, user_id=54321)
    identity_id = _create_google_identity(
        app,
        user_id,
        subject='SensitiveProviderSubject',
        identity_id=98765,
    )

    html = _settings_html(app)

    assert 'SensitiveProviderSubject' not in html
    assert str(identity_id) not in html
    assert str(user_id) not in html
    assert 'provider_subject' not in html
    assert 'oauth_identity' not in html
    assert 'user_id' not in html


def test_oauth_configuration_tokens_and_provider_payload_are_not_rendered(app_factory):
    app = app_factory(**_enabled_oauth_overrides())
    user_id = _create_user(app)
    _create_google_identity(app, user_id, subject='ProviderPayloadSubject')

    html = _settings_html(app)

    assert 'test-client-id' not in html
    assert 'test-client-secret' not in html
    assert 'http://localhost/auth/google/callback' not in html
    assert 'access_token' not in html
    assert 'refresh_token' not in html
    assert 'id_token' not in html
    assert 'provider-response' not in html
    assert 'ProviderPayloadSubject' not in html


def test_existing_account_settings_controls_remain_present(app_factory):
    app = app_factory()
    _create_user(app)

    html = _settings_html(app)
    account_html = app.test_client()
    _login(account_html)
    account_page = account_html.get('/settings?tab=account').get_data(as_text=True)

    assert 'Password' in html
    assert 'Change' in html
    assert 'Email Address' in html
    assert 'Update Email' in html
    assert 'Delete Account' in account_page
    assert 'Delete account' in account_page


def test_no_linking_or_unlinking_controls_are_rendered(app_factory):
    app = app_factory()
    user_id = _create_user(app)
    _create_google_identity(app, user_id)

    html = _settings_html(app)

    assert 'Connect Google' not in html
    assert 'Disconnect' not in html
    assert 'Unlink' not in html
    assert 'Relink' not in html
    assert 'Change account' not in html
    assert 'Coming soon' not in html
