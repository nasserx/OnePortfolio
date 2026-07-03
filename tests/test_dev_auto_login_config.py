import pytest

from config import Config
from portfolio_app import create_app, db


class _StartupConfig(Config):
    SECRET_KEY = 'test-secret-key'
    WTF_CSRF_ENABLED = False
    MAIL_SUPPRESS_SEND = True
    RATELIMIT_ENABLED = False
    GOOGLE_OAUTH_ENABLED = False
    GOOGLE_CLIENT_ID = ''
    GOOGLE_CLIENT_SECRET = ''
    GOOGLE_REDIRECT_URI = ''
    TESTING = False
    DEBUG = False
    DEV_AUTO_LOGIN = False


def _config_for(db_path, **overrides):
    db_path.parent.mkdir(parents=True, exist_ok=True)

    class _Config(_StartupConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path.resolve().as_posix()}"

    for key, value in overrides.items():
        setattr(_Config, key, value)
    return _Config


def test_dev_auto_login_allowed_in_testing_config(tmp_path):
    app = create_app(_config_for(
        tmp_path / 'testing.sqlite',
        TESTING=True,
        DEV_AUTO_LOGIN=True,
    ))

    assert app.config['DEV_AUTO_LOGIN'] is True

    with app.app_context():
        db.session.remove()


def test_dev_auto_login_allowed_in_debug_config(tmp_path):
    app = create_app(_config_for(
        tmp_path / 'debug.sqlite',
        DEBUG=True,
        DEV_AUTO_LOGIN=True,
    ))

    assert app.config['DEV_AUTO_LOGIN'] is True

    with app.app_context():
        db.session.remove()


def test_dev_auto_login_fails_closed_in_production_like_config(tmp_path):
    with pytest.raises(RuntimeError, match='DEV_AUTO_LOGIN can only be enabled'):
        create_app(_config_for(
            tmp_path / 'blocked.sqlite',
            TESTING=False,
            DEBUG=False,
            DEV_AUTO_LOGIN=True,
        ))


def test_production_like_startup_allows_dev_auto_login_disabled_and_oauth_disabled(tmp_path):
    app = create_app(_config_for(
        tmp_path / 'production-like.sqlite',
        TESTING=False,
        DEBUG=False,
        DEV_AUTO_LOGIN=False,
        GOOGLE_OAUTH_ENABLED=False,
        GOOGLE_CLIENT_ID='',
        GOOGLE_CLIENT_SECRET='',
        GOOGLE_REDIRECT_URI='',
    ))

    assert app.config['DEV_AUTO_LOGIN'] is False
    assert app.config['GOOGLE_OAUTH_ENABLED'] is False

    with app.app_context():
        db.session.remove()
