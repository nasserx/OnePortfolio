"""Real-Authlib Google OIDC protocol-contract tests.

Only provider HTTP transport is replaced. State, nonce, token exchange,
signature verification, claims validation, and UserInfo construction all run
through the Authlib client registered by the application factory.
"""

import base64
import json
import time
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from requests import Response

from config import Config
from portfolio_app import (
    GOOGLE_OIDC_ACCEPTED_ISSUERS,
    GOOGLE_OIDC_ISSUER,
    create_app,
    db,
)
from portfolio_app.models.oauth_identity import OAuthIdentity
from portfolio_app.models.user import User
from portfolio_app.utils.messages import MESSAGES


CLIENT_ID = 'oidc-contract-client-id'
CLIENT_SECRET = 'oidc-contract-client-secret'
REDIRECT_URI = 'http://localhost/auth/google/callback'
DISCOVERY_URL = f'{GOOGLE_OIDC_ISSUER}/.well-known/openid-configuration'
TOKEN_URL = 'https://oidc-provider.test/token'
JWKS_URL = 'https://oidc-provider.test/jwks'
SUBJECT = 'google-contract-subject'
EMAIL = 'oidc-contract@example.com'
FORGED_SUBJECT = 'forged-token-response-subject'
FORGED_EMAIL = 'forged-token-response@example.com'


class _OidcContractConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'oidc-contract-session-secret'
    MAIL_SUPPRESS_SEND = True
    RATELIMIT_ENABLED = False
    GOOGLE_OAUTH_ENABLED = True
    GOOGLE_CLIENT_ID = CLIENT_ID
    GOOGLE_CLIENT_SECRET = CLIENT_SECRET
    GOOGLE_REDIRECT_URI = REDIRECT_URI


def _base64url(value):
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')


def _integer_bytes(value):
    return value.to_bytes((value.bit_length() + 7) // 8, 'big')


def _json_segment(value):
    return _base64url(
        json.dumps(value, separators=(',', ':'), sort_keys=True).encode('utf-8')
    )


class _DeterministicGoogleProvider:
    def __init__(self):
        self.signing_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        self.other_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        self.signing_kid = 'contract-signing-key'
        self.nonce = None
        self.claim_overrides = {}
        self.omit_nonce = False
        self.omit_id_token = False
        self.forged_userinfo = False
        self.token_calls = 0
        self.jwks_calls = 0
        self.jwt_key = self.signing_key
        self.jwt_kid = self.signing_kid

    def _jwk(self):
        numbers = self.signing_key.public_key().public_numbers()
        return {
            'kty': 'RSA',
            'use': 'sig',
            'alg': 'RS256',
            'kid': self.signing_kid,
            'n': _base64url(_integer_bytes(numbers.n)),
            'e': _base64url(_integer_bytes(numbers.e)),
        }

    def _claims(self):
        now = int(time.time())
        claims = {
            'iss': GOOGLE_OIDC_ISSUER,
            'sub': SUBJECT,
            'aud': CLIENT_ID,
            'exp': now + 600,
            'iat': now,
            'nonce': self.nonce,
            'email': EMAIL,
            'email_verified': True,
        }
        if self.omit_nonce:
            claims.pop('nonce')
        claims.update(self.claim_overrides)
        return claims

    def _id_token(self):
        encoded_header = _json_segment({'alg': 'RS256', 'kid': self.jwt_kid})
        encoded_claims = _json_segment(self._claims())
        signing_input = f'{encoded_header}.{encoded_claims}'.encode('ascii')
        signature = self.jwt_key.sign(
            signing_input,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return f'{encoded_header}.{encoded_claims}.{_base64url(signature)}'

    @staticmethod
    def _response(url, payload):
        response = Response()
        response.status_code = 200
        response.url = url
        response.headers['Content-Type'] = 'application/json'
        response._content = json.dumps(payload).encode('utf-8')
        return response

    def request(self, method, url, **_kwargs):
        if method.upper() == 'GET' and url == DISCOVERY_URL:
            return self._response(url, {
                'issuer': GOOGLE_OIDC_ISSUER,
                'authorization_endpoint': 'https://oidc-provider.test/authorize',
                'token_endpoint': TOKEN_URL,
                'jwks_uri': JWKS_URL,
                'id_token_signing_alg_values_supported': ['RS256'],
            })
        if method.upper() == 'GET' and url == JWKS_URL:
            self.jwks_calls += 1
            return self._response(url, {'keys': [self._jwk()]})
        if method.upper() == 'POST' and url == TOKEN_URL:
            self.token_calls += 1
            token = {
                'access_token': 'transport-only-access-token',
                'token_type': 'Bearer',
                'expires_in': 3600,
            }
            if not self.omit_id_token:
                token['id_token'] = self._id_token()
            if self.forged_userinfo:
                token['userinfo'] = {
                    'sub': FORGED_SUBJECT,
                    'email': FORGED_EMAIL,
                    'email_verified': True,
                }
            return self._response(url, token)
        raise AssertionError(f'Unexpected provider request: {method} {url}')


@pytest.fixture
def oidc_app(tmp_path):
    class _Config(_OidcContractConfig):
        SQLALCHEMY_DATABASE_URI = (
            f"sqlite:///{(tmp_path / 'oidc-contract.sqlite').resolve().as_posix()}"
        )

    app = create_app(_Config)
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()


@pytest.fixture
def provider(monkeypatch):
    deterministic_provider = _DeterministicGoogleProvider()

    def _transport_request(_session, method, url, **kwargs):
        return deterministic_provider.request(method, url, **kwargs)

    monkeypatch.setattr(
        'requests.sessions.Session.request',
        _transport_request,
    )
    return deterministic_provider


def _create_verified_user(app):
    with app.app_context():
        user = User(username='oidc_contract', email=EMAIL, is_verified=True)
        user.set_password('ContractPassword9')
        db.session.add(user)
        db.session.commit()
        return user.id


def _begin_authorization(client, provider):
    response = client.get('/auth/google')
    assert response.status_code in (302, 303)
    query = parse_qs(urlparse(response.headers['Location']).query)
    assert query['state'][0]
    assert query['nonce'][0]
    provider.nonce = query['nonce'][0]
    return query['state'][0]


def _assert_account_processing_unreachable(monkeypatch):
    reached = {'value': False}

    def _fail_if_reached():
        reached['value'] = True
        raise AssertionError('application identity processing was reached')

    monkeypatch.setattr(
        'portfolio_app.routes.auth.get_services',
        _fail_if_reached,
    )
    return reached


def _assert_generic_google_failure(client, response):
    assert response.status_code in (302, 303)
    assert urlparse(response.headers['Location']).path == '/login'
    with client.session_transaction() as session:
        assert session.get('_flashes') == [
            ('warning', MESSAGES['GOOGLE_SIGNIN_FAILED'])
        ]


def _complete_rejected_callback(client, state, reached):
    response = client.get(
        f'/auth/google/callback?code=provider-code&state={state}'
    )
    assert reached['value'] is False
    _assert_generic_google_failure(client, response)
    return response


def test_valid_signed_oidc_callback_links_and_logs_in_user(oidc_app, provider):
    assert GOOGLE_OIDC_ISSUER == 'https://accounts.google.com'
    assert GOOGLE_OIDC_ACCEPTED_ISSUERS == (
        'https://accounts.google.com',
        'accounts.google.com',
    )
    user_id = _create_verified_user(oidc_app)
    client = oidc_app.test_client()
    state = _begin_authorization(client, provider)

    response = client.get(
        f'/auth/google/callback?code=provider-code&state={state}'
    )

    assert response.status_code in (302, 303)
    assert response.headers['Location'] == '/'
    assert provider.token_calls == 1
    assert provider.jwks_calls == 1
    with client.session_transaction() as session:
        assert session.get('_user_id') == f'v1:{user_id}:0'
    with oidc_app.app_context():
        identity = OAuthIdentity.query.one()
        assert identity.user_id == user_id
        assert identity.provider == 'google'
        assert identity.provider_subject == SUBJECT


def test_legacy_google_issuer_is_accepted_by_authlib(oidc_app, provider):
    user_id = _create_verified_user(oidc_app)
    client = oidc_app.test_client()
    state = _begin_authorization(client, provider)
    provider.claim_overrides['iss'] = 'accounts.google.com'

    response = client.get(
        f'/auth/google/callback?code=provider-code&state={state}'
    )

    assert response.status_code in (302, 303)
    assert response.headers['Location'] == '/'
    with client.session_transaction() as session:
        assert session.get('_user_id') == f'v1:{user_id}:0'
    with oidc_app.app_context():
        identity = OAuthIdentity.query.one()
        assert identity.user_id == user_id
        assert identity.provider_subject == SUBJECT


def test_validated_id_token_userinfo_overrides_forged_token_userinfo(
    oidc_app, provider
):
    user_id = _create_verified_user(oidc_app)
    client = oidc_app.test_client()
    state = _begin_authorization(client, provider)
    provider.forged_userinfo = True

    response = client.get(
        f'/auth/google/callback?code=provider-code&state={state}'
    )

    assert response.status_code in (302, 303)
    assert response.headers['Location'] == '/'
    with client.session_transaction() as session:
        assert session.get('_user_id') == f'v1:{user_id}:0'
    with oidc_app.app_context():
        identity = OAuthIdentity.query.one()
        assert identity.user_id == user_id
        assert identity.provider_subject == SUBJECT
        assert OAuthIdentity.query.filter_by(
            provider='google',
            provider_subject=FORGED_SUBJECT,
        ).one_or_none() is None
        assert User.query.filter_by(email=FORGED_EMAIL).one_or_none() is None


def test_wrong_state_is_rejected_before_token_endpoint(oidc_app, provider, monkeypatch):
    client = oidc_app.test_client()
    _begin_authorization(client, provider)
    reached = _assert_account_processing_unreachable(monkeypatch)

    response = client.get('/auth/google/callback?code=provider-code&state=wrong')

    _assert_generic_google_failure(client, response)
    assert provider.token_calls == 0
    assert reached['value'] is False


def test_state_from_another_session_is_rejected_before_token_endpoint(
    oidc_app, provider, monkeypatch
):
    first_client = oidc_app.test_client()
    second_client = oidc_app.test_client()
    state = _begin_authorization(first_client, provider)
    reached = _assert_account_processing_unreachable(monkeypatch)

    response = second_client.get(
        f'/auth/google/callback?code=provider-code&state={state}'
    )

    _assert_generic_google_failure(second_client, response)
    assert provider.token_calls == 0
    assert reached['value'] is False


@pytest.mark.parametrize('omit_nonce', [False, True], ids=['wrong', 'missing'])
def test_invalid_nonce_is_rejected_by_authlib(
    oidc_app, provider, monkeypatch, omit_nonce
):
    client = oidc_app.test_client()
    state = _begin_authorization(client, provider)
    if omit_nonce:
        provider.omit_nonce = True
    else:
        provider.claim_overrides['nonce'] = 'wrong-nonce'
    reached = _assert_account_processing_unreachable(monkeypatch)

    _complete_rejected_callback(client, state, reached)


def test_invalid_signature_is_rejected_by_authlib(oidc_app, provider, monkeypatch):
    client = oidc_app.test_client()
    state = _begin_authorization(client, provider)
    provider.jwt_key = provider.other_key
    reached = _assert_account_processing_unreachable(monkeypatch)

    _complete_rejected_callback(client, state, reached)


def test_unknown_signing_key_is_rejected_by_authlib(oidc_app, provider, monkeypatch):
    client = oidc_app.test_client()
    state = _begin_authorization(client, provider)
    provider.jwt_key = provider.other_key
    provider.jwt_kid = 'unknown-signing-key'
    reached = _assert_account_processing_unreachable(monkeypatch)

    _complete_rejected_callback(client, state, reached)

    assert provider.jwks_calls == 2


def test_wrong_issuer_is_rejected_by_authlib(oidc_app, provider, monkeypatch):
    client = oidc_app.test_client()
    state = _begin_authorization(client, provider)
    provider.claim_overrides['iss'] = 'https://wrong-issuer.test'
    reached = _assert_account_processing_unreachable(monkeypatch)

    _complete_rejected_callback(client, state, reached)


def test_wrong_audience_with_matching_azp_is_rejected_by_authlib(
    oidc_app, provider, monkeypatch
):
    client = oidc_app.test_client()
    state = _begin_authorization(client, provider)
    provider.claim_overrides.update({
        'aud': 'different-client-id',
        'azp': CLIENT_ID,
    })
    reached = _assert_account_processing_unreachable(monkeypatch)

    _complete_rejected_callback(client, state, reached)


def test_expired_id_token_is_rejected_by_authlib(oidc_app, provider, monkeypatch):
    client = oidc_app.test_client()
    state = _begin_authorization(client, provider)
    provider.claim_overrides['exp'] = int(time.time()) - 600
    reached = _assert_account_processing_unreachable(monkeypatch)

    _complete_rejected_callback(client, state, reached)


def test_userinfo_without_id_token_cannot_reach_identity_processing(
    oidc_app, provider, monkeypatch
):
    client = oidc_app.test_client()
    state = _begin_authorization(client, provider)
    provider.omit_id_token = True
    provider.forged_userinfo = True
    reached = _assert_account_processing_unreachable(monkeypatch)

    response = client.get(
        f'/auth/google/callback?code=provider-code&state={state}'
    )

    _assert_generic_google_failure(client, response)
    assert reached['value'] is False
    with oidc_app.app_context():
        assert OAuthIdentity.query.count() == 0


def test_post_authlib_application_type_error_is_not_normalized(
    oidc_app, provider, monkeypatch
):
    client = oidc_app.test_client()
    state = _begin_authorization(client, provider)

    def _raise_post_authlib_type_error():
        raise TypeError('post-authlib application sentinel')

    monkeypatch.setattr(
        'portfolio_app.routes.auth.get_services',
        _raise_post_authlib_type_error,
    )

    with pytest.raises(TypeError, match='^post-authlib application sentinel$'):
        client.get(f'/auth/google/callback?code=provider-code&state={state}')

    assert provider.token_calls == 1
    assert provider.jwks_calls == 1
