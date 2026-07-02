"""Google sign-in disconnect settings UI tests."""

import re

import pytest

from config import Config
from portfolio_app import create_app, db, limiter
from portfolio_app.models.oauth_identity import OAuthIdentity
from portfolio_app.models.user import User
from portfolio_app.utils.constants import DEMO_USERNAME
from portfolio_app.utils.messages import MESSAGES


PASSWORD = 'CorrectHorse9'


class _GoogleDisconnectUiTestConfig(Config):
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

    class _Config(_GoogleDisconnectUiTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path.resolve().as_posix()}"

    for key, value in overrides.items():
        setattr(_Config, key, value)
    return _Config


@pytest.fixture
def app_factory(tmp_path):
    apps = []

    def _make_app(**overrides):
        app = create_app(_config_for(
            tmp_path / f"google-disconnect-ui-{len(apps)}.sqlite",
            **overrides,
        ))
        with app.app_context():
            db.drop_all()
            db.create_all()
        try:
            limiter.reset()
        except Exception:
            pass
        apps.append(app)
        return app

    yield _make_app

    for app in apps:
        with app.app_context():
            db.session.remove()


def _enabled_oauth_overrides():
    return {
        'GOOGLE_OAUTH_ENABLED': True,
        'GOOGLE_CLIENT_ID': 'test-client-id',
        'GOOGLE_CLIENT_SECRET': 'test-client-secret',
        'GOOGLE_REDIRECT_URI': 'http://localhost/auth/google/callback',
    }


def _create_user(app, username='alice', email='alice@example.com', password=PASSWORD):
    with app.app_context():
        user = User(username=username, email=email.lower(), is_verified=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user.id


def _create_google_identity(app, user_id, subject='SensitiveGoogleSubject', identity_id=None):
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


def _login(client, email='alice@example.com', password=PASSWORD):
    return client.post(
        '/login',
        data={'username': email, 'password': password},
        follow_redirects=False,
    )


def _settings_response(app, email='alice@example.com'):
    client = app.test_client()
    _login(client, email=email)
    response = client.get('/settings?tab=security')
    assert response.status_code == 200
    return response, client


def _settings_html(app, email='alice@example.com'):
    response, _client = _settings_response(app, email=email)
    return response.get_data(as_text=True)


def _login_session(client, user_id):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True


def _google_disconnect_form(html):
    match = re.search(
        r'<form[^>]+action="/settings/google/disconnect"[^>]*>.*?</form>',
        html,
        flags=re.DOTALL,
    )
    return match.group(0) if match else ''


def _csrf_from_google_disconnect_form(html):
    form = _google_disconnect_form(html)
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', form)
    assert match is not None
    return match.group(1)


def _identity_count(app):
    with app.app_context():
        return OAuthIdentity.query.count()


def _identity_for_user(app, user_id):
    with app.app_context():
        return OAuthIdentity.query.filter_by(user_id=user_id, provider='google').first()


def test_unauthenticated_settings_access_preserves_login_required_behavior(app_factory):
    app = app_factory()

    response = app.test_client().get('/settings?tab=security')

    assert response.status_code in (302, 303)
    assert '/login' in response.headers['Location']


def test_unlinked_user_sees_not_connected_and_no_disconnect_form(app_factory):
    app = app_factory()
    _create_user(app)

    html = _settings_html(app)

    assert 'Not connected' in html
    assert _google_disconnect_form(html) == ''
    assert 'name="current_password"' not in html
    assert 'Disconnect Google' not in html
    assert 'Disconnecting Google sign-in does not delete this account.' not in html


def test_linked_user_sees_connected_and_disconnect_form(app_factory):
    app = app_factory()
    user_id = _create_user(app)
    _create_google_identity(app, user_id)

    html = _settings_html(app)

    form = _google_disconnect_form(html)
    assert 'Connected' in html
    assert form
    assert 'Disconnect Google' in form


def test_disconnect_form_targets_backend_route_with_post_method(app_factory):
    app = app_factory()
    user_id = _create_user(app)
    _create_google_identity(app, user_id)

    form = _google_disconnect_form(_settings_html(app))

    assert 'action="/settings/google/disconnect"' in form
    assert 'method="post"' in form


def test_csrf_field_is_rendered_under_csrf_enabled_configuration(app_factory):
    app = app_factory(WTF_CSRF_ENABLED=True)
    user_id = _create_user(app)
    _create_google_identity(app, user_id)
    client = app.test_client()
    _login_session(client, user_id)

    html = client.get('/settings?tab=security').get_data(as_text=True)

    form = _google_disconnect_form(html)
    assert 'name="csrf_token"' in form
    assert _csrf_from_google_disconnect_form(html)


def test_current_password_input_has_password_type_autocomplete_and_label(app_factory):
    app = app_factory()
    user_id = _create_user(app)
    _create_google_identity(app, user_id)

    form = _google_disconnect_form(_settings_html(app))

    assert '<label for="google-disconnect-current-password" class="form-label">Current password</label>' in form
    assert 'type="password"' in form
    assert 'name="current_password"' in form
    assert 'autocomplete="current-password"' in form


def test_disconnect_submit_exists_only_for_linked_users(app_factory):
    linked_app = app_factory()
    linked_user_id = _create_user(linked_app)
    _create_google_identity(linked_app, linked_user_id)
    unlinked_app = app_factory()
    _create_user(unlinked_app)

    assert 'Disconnect Google' in _google_disconnect_form(_settings_html(linked_app))
    assert 'Disconnect Google' not in _settings_html(unlinked_app)


def test_disconnect_form_does_not_render_oauth_identifiers_or_provider_fields(app_factory):
    app = app_factory()
    user_id = _create_user(app)
    identity_id = _create_google_identity(app, user_id, identity_id=98765)

    form = _google_disconnect_form(_settings_html(app))

    assert f'name="user_id" value="{user_id}"' not in form
    assert f'name="identity_id" value="{identity_id}"' not in form
    assert f'value="{user_id}"' not in form
    assert f'value="{identity_id}"' not in form
    assert 'SensitiveGoogleSubject' not in form
    assert 'provider_subject' not in form
    assert 'name="provider"' not in form
    assert 'name="user_id"' not in form
    assert 'identity_id' not in form


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


@pytest.mark.parametrize('enabled', [False, True])
def test_disconnect_ui_remains_visible_for_linked_user_regardless_of_feature_flag(app_factory, enabled):
    overrides = _enabled_oauth_overrides() if enabled else {'GOOGLE_OAUTH_ENABLED': False}
    app = app_factory(**overrides)
    user_id = _create_user(app)
    _create_google_identity(app, user_id)

    html = _settings_html(app)

    assert 'Connected' in html
    assert _google_disconnect_form(html)
    assert 'Disconnect Google' in html


def test_existing_account_settings_controls_remain_present(app_factory):
    app = app_factory()
    user_id = _create_user(app)
    _create_google_identity(app, user_id)

    html = _settings_html(app)

    assert 'Password' in html
    assert 'Change' in html
    assert 'Email Address' in html
    assert 'Update Email' in html
    assert 'Connected sign-in methods' in html


def test_demo_account_shows_disabled_disconnect_action_without_password_form(app_factory):
    app = app_factory()
    user_id = _create_user(app, username=DEMO_USERNAME, email='demo@example.com')
    _create_google_identity(app, user_id)

    html = _settings_html(app, email='demo@example.com')

    assert 'Connected' in html
    assert 'Disabled for the demo account.' in html
    assert '<button class="btn btn-outline-secondary btn-sm" disabled>Disconnect Google</button>' in html
    assert _google_disconnect_form(html) == ''
    assert 'name="current_password"' not in html


def test_password_values_are_not_rendered_back_into_settings_page(app_factory):
    app = app_factory()
    user_id = _create_user(app)
    _create_google_identity(app, user_id)
    response, client = _settings_response(app)
    assert response.status_code == 200

    response = client.post(
        '/settings/google/disconnect',
        data={'current_password': 'wrong-password-value'},
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)

    assert 'wrong-password-value' not in html
    assert 'value="wrong-password-value"' not in html


def test_submitting_rendered_form_with_correct_password_removes_link_and_keeps_user_authenticated(app_factory):
    app = app_factory(WTF_CSRF_ENABLED=True)
    user_id = _create_user(app)
    _create_google_identity(app, user_id)
    client = app.test_client()
    _login_session(client, user_id)
    html = client.get('/settings?tab=security').get_data(as_text=True)
    csrf_token = _csrf_from_google_disconnect_form(html)

    response = client.post(
        '/settings/google/disconnect',
        data={'csrf_token': csrf_token, 'current_password': PASSWORD},
        follow_redirects=True,
    )

    assert MESSAGES['GOOGLE_DISCONNECT_SUCCESS'] in response.get_data(as_text=True)
    assert _identity_for_user(app, user_id) is None
    with client.session_transaction() as sess:
        assert sess.get('_user_id') == str(user_id)


def test_submitting_wrong_password_leaves_link_and_returns_to_settings(app_factory):
    app = app_factory()
    user_id = _create_user(app)
    _create_google_identity(app, user_id)
    response, client = _settings_response(app)
    assert response.status_code == 200

    response = client.post(
        '/settings/google/disconnect',
        data={'current_password': 'wrong-password'},
        follow_redirects=True,
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert MESSAGES['CURRENT_PASSWORD_INCORRECT'] in html
    assert 'Connected sign-in methods' in html
    assert _identity_for_user(app, user_id) is not None


def test_success_and_failure_messages_render_through_existing_flash_system(app_factory):
    app = app_factory()
    user_id = _create_user(app)
    _create_google_identity(app, user_id)
    response, client = _settings_response(app)
    assert response.status_code == 200

    failure = client.post(
        '/settings/google/disconnect',
        data={'current_password': 'wrong-password'},
        follow_redirects=True,
    )
    success = client.post(
        '/settings/google/disconnect',
        data={'current_password': PASSWORD},
        follow_redirects=True,
    )

    assert MESSAGES['CURRENT_PASSWORD_INCORRECT'] in failure.get_data(as_text=True)
    assert MESSAGES['GOOGLE_DISCONNECT_SUCCESS'] in success.get_data(as_text=True)
    assert _identity_count(app) == 0
