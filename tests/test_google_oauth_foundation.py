"""Google OAuth extension foundation tests.

These tests cover app startup and client registration only. They intentionally
do not exercise a Google login route or callback flow.
"""

import pytest

from config import Config
from portfolio_app import (
    ONEPORTFOLIO_OAUTH_EXTENSION_KEY,
    create_app,
    db,
    get_oauth,
)


class _OAuthTestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key'
    MAIL_SUPPRESS_SEND = True
    RATELIMIT_ENABLED = False
    GOOGLE_OAUTH_ENABLED = False
    GOOGLE_CLIENT_ID = ''
    GOOGLE_CLIENT_SECRET = ''
    GOOGLE_REDIRECT_URI = ''


def _config_for(db_path, **overrides):
    db_path.parent.mkdir(parents=True, exist_ok=True)

    class _Config(_OAuthTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path.resolve().as_posix()}"

    for key, value in overrides.items():
        setattr(_Config, key, value)
    return _Config


def _create_test_app(tmp_path, **overrides):
    app = create_app(_config_for(tmp_path / 'oauth.sqlite', **overrides))
    with app.app_context():
        db.create_all()
    return app


def test_app_creation_succeeds_when_google_oauth_disabled(tmp_path):
    app = _create_test_app(tmp_path)

    assert app.config['GOOGLE_OAUTH_ENABLED'] is False


def test_disabled_google_oauth_does_not_require_credentials(tmp_path):
    app = _create_test_app(
        tmp_path,
        GOOGLE_CLIENT_ID='',
        GOOGLE_CLIENT_SECRET='',
        GOOGLE_REDIRECT_URI='',
    )

    assert app.config['GOOGLE_CLIENT_ID'] == ''
    assert app.config['GOOGLE_CLIENT_SECRET'] == ''
    assert app.config['GOOGLE_REDIRECT_URI'] == ''


def test_oauth_extension_is_initialized_with_application(tmp_path):
    app = _create_test_app(tmp_path)

    with app.app_context():
        oauth = get_oauth()

    assert app.extensions[ONEPORTFOLIO_OAUTH_EXTENSION_KEY] is oauth
    assert oauth.app is app


def test_google_client_is_not_registered_when_feature_flag_is_false(tmp_path):
    app = _create_test_app(tmp_path, GOOGLE_OAUTH_ENABLED=False)

    with app.app_context():
        assert get_oauth().create_client('google') is None


def test_enabled_google_oauth_missing_client_id_fails_clearly(tmp_path):
    with pytest.raises(RuntimeError, match='GOOGLE_CLIENT_ID'):
        _create_test_app(
            tmp_path,
            GOOGLE_OAUTH_ENABLED=True,
            GOOGLE_CLIENT_ID='',
            GOOGLE_CLIENT_SECRET='test-client-secret',
            GOOGLE_REDIRECT_URI='http://localhost/auth/google/callback',
        )


def test_enabled_google_oauth_missing_client_secret_fails_clearly(tmp_path):
    with pytest.raises(RuntimeError, match='GOOGLE_CLIENT_SECRET'):
        _create_test_app(
            tmp_path,
            GOOGLE_OAUTH_ENABLED=True,
            GOOGLE_CLIENT_ID='test-client-id',
            GOOGLE_CLIENT_SECRET='',
            GOOGLE_REDIRECT_URI='http://localhost/auth/google/callback',
        )


def test_enabled_google_oauth_complete_config_registers_google_client(tmp_path):
    app = _create_test_app(
        tmp_path,
        GOOGLE_OAUTH_ENABLED=True,
        GOOGLE_CLIENT_ID='test-client-id',
        GOOGLE_CLIENT_SECRET='test-client-secret',
        GOOGLE_REDIRECT_URI='http://localhost/auth/google/callback',
    )

    with app.app_context():
        google = get_oauth().create_client('google')

    assert google is not None
    assert google.name == 'google'
    assert google.client_id == 'test-client-id'
    assert google.client_kwargs['scope'] == 'openid email profile'
    assert google.authorize_url is None
    assert google.access_token_url is None


def test_enabled_then_disabled_apps_do_not_share_google_registration(tmp_path):
    enabled_app = _create_test_app(
        tmp_path / 'enabled',
        GOOGLE_OAUTH_ENABLED=True,
        GOOGLE_CLIENT_ID='test-client-id',
        GOOGLE_CLIENT_SECRET='test-client-secret',
        GOOGLE_REDIRECT_URI='http://localhost/auth/google/callback',
    )
    disabled_app = _create_test_app(tmp_path / 'disabled', GOOGLE_OAUTH_ENABLED=False)

    with enabled_app.app_context():
        enabled_oauth = get_oauth()
        assert enabled_oauth.create_client('google') is not None

    with disabled_app.app_context():
        disabled_oauth = get_oauth()
        assert disabled_oauth.create_client('google') is None

    assert enabled_oauth is not disabled_oauth


def test_disabled_then_enabled_apps_do_not_share_google_registration(tmp_path):
    disabled_app = _create_test_app(tmp_path / 'disabled', GOOGLE_OAUTH_ENABLED=False)
    enabled_app = _create_test_app(
        tmp_path / 'enabled',
        GOOGLE_OAUTH_ENABLED=True,
        GOOGLE_CLIENT_ID='test-client-id',
        GOOGLE_CLIENT_SECRET='test-client-secret',
        GOOGLE_REDIRECT_URI='http://localhost/auth/google/callback',
    )

    with disabled_app.app_context():
        disabled_oauth = get_oauth()
        assert disabled_oauth.create_client('google') is None

    with enabled_app.app_context():
        enabled_oauth = get_oauth()
        assert enabled_oauth.create_client('google') is not None

    assert disabled_oauth is not enabled_oauth


def test_oauth_foundation_tests_use_project_owned_public_interface(tmp_path):
    app = _create_test_app(tmp_path, GOOGLE_OAUTH_ENABLED=False)

    with app.app_context():
        oauth = get_oauth()

    assert app.extensions[ONEPORTFOLIO_OAUTH_EXTENSION_KEY] is oauth


def test_google_oauth_registration_performs_no_network_request(tmp_path, monkeypatch):
    def _fail_network(*args, **kwargs):
        raise AssertionError('network request was attempted during app startup')

    monkeypatch.setattr('requests.sessions.Session.request', _fail_network)

    _create_test_app(
        tmp_path,
        GOOGLE_OAUTH_ENABLED=True,
        GOOGLE_CLIENT_ID='test-client-id',
        GOOGLE_CLIENT_SECRET='test-client-secret',
        GOOGLE_REDIRECT_URI='http://localhost/auth/google/callback',
    )
