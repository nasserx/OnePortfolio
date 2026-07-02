"""Google OAuth login UI tests."""

from urllib.parse import parse_qs, urlparse

import pytest

from config import Config
from portfolio_app import create_app, db, limiter
from portfolio_app.models.user import User


class _OAuthUiTestConfig(Config):
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

    class _Config(_OAuthUiTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path.resolve().as_posix()}"

    for key, value in overrides.items():
        setattr(_Config, key, value)
    return _Config


@pytest.fixture
def app_factory(tmp_path):
    created = []

    def _make_app(**overrides):
        app = create_app(_config_for(
            tmp_path / f"oauth-ui-{len(created)}.sqlite",
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


def _enabled_oauth_app(app_factory):
    return app_factory(
        GOOGLE_OAUTH_ENABLED=True,
        GOOGLE_CLIENT_ID='test-client-id',
        GOOGLE_CLIENT_SECRET='test-client-secret',
        GOOGLE_REDIRECT_URI='http://localhost/auth/google/callback',
    )


def _google_href(html):
    marker = 'href="'
    label_index = html.index('Continue with Google')
    href_start = html.rfind(marker, 0, label_index) + len(marker)
    href_end = html.index('"', href_start)
    return html[href_start:href_end]


def test_google_control_absent_when_oauth_disabled(app_factory):
    app = app_factory(GOOGLE_OAUTH_ENABLED=False)
    resp = app.test_client().get('/login')
    html = resp.get_data(as_text=True)

    assert 'Continue with Google' not in html
    assert 'btn-google' not in html


def test_google_separator_absent_when_oauth_unavailable(app_factory):
    app = app_factory(GOOGLE_OAUTH_ENABLED=False)
    html = app.test_client().get('/login').get_data(as_text=True)

    assert 'auth-divider' not in html
    assert '>or<' not in html


def test_google_control_appears_when_oauth_enabled_and_registered(app_factory):
    app = _enabled_oauth_app(app_factory)
    html = app.test_client().get('/login').get_data(as_text=True)

    assert 'Continue with Google' in html
    assert 'btn-google' in html


def test_google_control_links_to_google_signin_route(app_factory):
    app = _enabled_oauth_app(app_factory)
    html = app.test_client().get('/login').get_data(as_text=True)

    assert urlparse(_google_href(html)).path == '/auth/google'


def test_google_control_visible_label_is_continue_with_google(app_factory):
    app = _enabled_oauth_app(app_factory)
    html = app.test_client().get('/login').get_data(as_text=True)
    label_index = html.index('Continue with Google')
    anchor_start = html.rfind('<a ', 0, label_index)
    anchor_end = html.index('</a>', label_index)
    anchor_text = ' '.join(html[anchor_start:anchor_end].split())

    assert 'Continue with Google' in anchor_text
    assert 'Sign up with Google' not in html
    assert 'Create account with Google' not in html


def test_google_signin_url_includes_safe_local_next(app_factory):
    app = _enabled_oauth_app(app_factory)
    html = app.test_client().get('/login?next=/settings').get_data(as_text=True)
    parsed = urlparse(_google_href(html))

    assert parsed.path == '/auth/google'
    assert parse_qs(parsed.query) == {'next': ['/settings']}


def test_google_signin_url_excludes_external_next(app_factory):
    app = _enabled_oauth_app(app_factory)
    html = app.test_client().get(
        '/login?next=https://evil.example/account'
    ).get_data(as_text=True)

    assert parse_qs(urlparse(_google_href(html)).query) == {}
    assert 'evil.example' not in html


def test_google_signin_url_excludes_protocol_relative_next(app_factory):
    app = _enabled_oauth_app(app_factory)
    html = app.test_client().get('/login?next=//evil.example/path').get_data(as_text=True)

    assert parse_qs(urlparse(_google_href(html)).query) == {}
    assert 'evil.example' not in html


def test_google_signin_url_excludes_backslash_prefixed_next(app_factory):
    app = _enabled_oauth_app(app_factory)
    html = app.test_client().get('/login?next=%2F%5Cevil.example').get_data(as_text=True)

    assert parse_qs(urlparse(_google_href(html)).query) == {}
    assert 'evil.example' not in html


def test_password_login_form_remains_present_and_functional(app_factory):
    app = _enabled_oauth_app(app_factory)
    with app.app_context():
        user = User(username='alice', email='alice@example.com', is_verified=True)
        user.set_password('CorrectHorse9')
        db.session.add(user)
        db.session.commit()
        user_id = str(user.id)

    client = app.test_client()
    html = client.get('/login').get_data(as_text=True)
    assert 'name="username"' in html
    assert 'name="password"' in html
    assert 'Sign in' in html

    resp = client.post(
        '/login',
        data={'username': 'alice@example.com', 'password': 'CorrectHorse9'},
    )
    assert resp.status_code in (302, 303)
    with client.session_transaction() as sess:
        assert sess.get('_user_id') == user_id


def test_google_oauth_secrets_tokens_and_provider_data_not_rendered(app_factory):
    app = _enabled_oauth_app(app_factory)
    html = app.test_client().get('/login?next=/settings').get_data(as_text=True)

    assert 'test-client-id' not in html
    assert 'test-client-secret' not in html
    assert 'http://localhost/auth/google/callback' not in html
    assert 'access_token' not in html
    assert 'refresh_token' not in html
    assert 'id_token' not in html
    assert 'provider-response' not in html
