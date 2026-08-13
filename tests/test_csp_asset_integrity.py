"""Regression coverage for CSP headers and third-party asset integrity."""

from html.parser import HTMLParser
from pathlib import Path
import re

from portfolio_app import db
from portfolio_app.models.user import User


_TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / 'portfolio_app' / 'templates'
_TOKENS_CSS = (
    Path(__file__).resolve().parents[1]
    / 'portfolio_app'
    / 'static'
    / 'css'
    / 'tokens.css'
)

_ELIGIBLE_ASSETS = {
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js': (
        'sha384-geWF76RCwLtnZ8qwWowPQNguL3RmwHVBC9FhGdlKrxdiJJigb/j/68SIy3Te4Bkz'
    ),
    'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css': (
        'sha384-QuGBSgV5Im3DzL2z+8Ko9/hqNy/N0O7zwvXAtfd1MvPKWa/UbeLV65cfm4BV5Wgq'
    ),
    'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js': (
        'sha384-e6nUZLBkQ86NJ6TVVKAeSaK8jWa3NhkYWZFomE39AvDbQWeie9PlQqM3pmYW5d1g'
    ),
    'https://cdn.jsdelivr.net/npm/flatpickr@4.6.13/dist/flatpickr.min.js': (
        'sha384-5JqMv4L/Xa0hfvtF06qboNdhvuYXUku9ZrhZh3bSk8VXF0A/RuSLHpLsSV9Zqhl6'
    ),
    'https://cdn.jsdelivr.net/npm/flatpickr@4.6.13/dist/flatpickr.min.css': (
        'sha384-RkASv+6KfBMW9eknReJIJ6b3UnjKOKC5bOUaNgIY778NFbQ8MtWq9Lr/khUgqtTt'
    ),
}

_EXPECTED_ASSET_OCCURRENCES = {
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js': 2,
    'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css': 3,
    'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js': 2,
    'https://cdn.jsdelivr.net/npm/flatpickr@4.6.13/dist/flatpickr.min.js': 2,
    'https://cdn.jsdelivr.net/npm/flatpickr@4.6.13/dist/flatpickr.min.css': 2,
}


def _parse_csp(value):
    directives = {}
    for raw_directive in value.split(';'):
        parts = raw_directive.strip().split()
        if parts:
            directives[parts[0]] = set(parts[1:])
    return directives


class _TemplateSecurityParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.resources = []
        self.executable_inline_scripts = []
        self.data_scripts = []
        self.executable_attributes = []
        self.javascript_urls = []

    def handle_starttag(self, tag, attrs):
        attrs_map = {name.lower(): value for name, value in attrs}
        resource_url = None
        if tag == 'script':
            resource_url = attrs_map.get('src')
            if not resource_url:
                script_type = (attrs_map.get('type') or '').strip().lower()
                target = (
                    self.data_scripts
                    if script_type in {'application/json', 'application/ld+json'}
                    else self.executable_inline_scripts
                )
                target.append(attrs_map)
        elif tag == 'link' and 'stylesheet' in (attrs_map.get('rel') or '').lower():
            resource_url = attrs_map.get('href')
        if resource_url and resource_url.startswith('https://'):
            self.resources.append((tag, resource_url, attrs_map))

        for name, value in attrs:
            normalized_name = name.lower()
            if normalized_name.startswith('on'):
                self.executable_attributes.append((tag, normalized_name))
            if normalized_name in {'href', 'src', 'action', 'formaction'}:
                if value and value.lstrip().lower().startswith('javascript:'):
                    self.javascript_urls.append((tag, normalized_name, value))

    handle_startendtag = handle_starttag


def _parse_production_templates():
    parser = _TemplateSecurityParser()
    for template_path in sorted(_TEMPLATE_ROOT.rglob('*.html')):
        parser.feed(template_path.read_text(encoding='utf-8'))
    return parser


def _authenticated_client(app):
    client = app.test_client()
    with app.app_context():
        user = User(
            username='csp_user',
            email='csp-user@example.com',
            is_verified=True,
        )
        user.set_password('correct-password')
        db.session.add(user)
        db.session.commit()
        identity = user.get_id()

    with client.session_transaction() as session:
        session['_user_id'] = identity
        session['_fresh'] = True
    return client


def _response_csp_nonce(response):
    directives = _parse_csp(response.headers['Content-Security-Policy'])
    nonce_sources = [
        source
        for source in directives['script-src']
        if source.startswith("'nonce-")
    ]
    assert len(nonce_sources) == 1
    nonce_source = nonce_sources[0]
    assert nonce_source.endswith("'")
    nonce = nonce_source[len("'nonce-"):-1]
    assert re.fullmatch(r'[A-Za-z0-9_-]{43}', nonce)
    return directives, nonce


def _assert_security_header_contract(response):
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['X-Frame-Options'] == 'DENY'
    assert response.headers['Referrer-Policy'] == 'strict-origin-when-cross-origin'
    assert response.headers['Permissions-Policy'] == 'geolocation=(), microphone=(), camera=()'

    directives, nonce = _response_csp_nonce(response)
    assert directives['default-src'] == {"'self'"}
    assert directives['script-src'] == {
        "'self'",
        f"'nonce-{nonce}'",
        'https://cdn.jsdelivr.net',
    }
    assert directives['script-src-attr'] == {"'none'"}
    assert directives['style-src'] == {
        "'self'",
        "'unsafe-inline'",
        'https://cdn.jsdelivr.net',
        'https://fonts.googleapis.com',
    }
    assert directives['font-src'] == {
        "'self'",
        'https://fonts.gstatic.com',
        'https://cdn.jsdelivr.net',
    }
    assert directives['img-src'] == {"'self'", 'data:'}
    assert directives['object-src'] == {"'none'"}
    assert directives['connect-src'] == {"'self'"}
    assert directives['frame-ancestors'] == {"'none'"}
    assert directives['base-uri'] == {"'self'"}
    assert directives['form-action'] == {"'self'"}
    assert "'unsafe-eval'" not in directives['script-src']
    assert "'unsafe-inline'" not in directives['script-src']
    assert 'data:' not in directives['script-src']
    assert 'blob:' not in directives['script-src']
    return nonce


def test_representative_flask_responses_receive_security_headers(app):
    guest_client = app.test_client()
    authenticated_client = _authenticated_client(app)
    responses = {
        'guest HTML': guest_client.get('/'),
        'authenticated HTML': authenticated_client.get('/'),
        'JSON': guest_client.get('/health'),
        'application error': guest_client.get('/route-that-does-not-exist'),
        'Flask static': guest_client.get('/static/css/base.css'),
    }

    assert responses['guest HTML'].status_code == 200
    assert responses['authenticated HTML'].status_code == 200
    assert responses['JSON'].is_json
    assert responses['application error'].status_code == 404
    assert responses['Flask static'].status_code == 200
    nonces = [_assert_security_header_contract(response) for response in responses.values()]
    assert len(set(nonces)) == len(responses)


def test_rendered_executable_scripts_share_their_response_nonce(app):
    guest_client = app.test_client()
    authenticated_client = _authenticated_client(app)
    responses = {
        'landing shell': guest_client.get('/'),
        'authentication shell': guest_client.get('/login'),
        'primary application shell': authenticated_client.get('/'),
        'dynamic assets page': authenticated_client.get('/transactions/'),
    }

    expected_executable_counts = {
        'landing shell': 1,
        'authentication shell': 2,
        'primary application shell': 2,
        'dynamic assets page': 2,
    }
    for name, response in responses.items():
        assert response.status_code == 200
        nonce = _assert_security_header_contract(response)
        parser = _TemplateSecurityParser()
        parser.feed(response.get_data(as_text=True))
        assert len(parser.executable_inline_scripts) == expected_executable_counts[name]
        assert {
            attrs.get('nonce') for attrs in parser.executable_inline_scripts
        } == {nonce}
        assert all('nonce' not in attrs for attrs in parser.data_scripts)


def test_csp_nonce_is_request_scoped_and_not_stored_in_session(app):
    client = app.test_client()
    first_nonce = _assert_security_header_contract(client.get('/login'))
    second_nonce = _assert_security_header_contract(client.get('/login'))

    assert first_nonce != second_nonce
    with client.session_transaction() as session:
        assert 'csp_nonce' not in session
        assert first_nonce not in session.values()
        assert second_nonce not in session.values()


def test_every_eligible_production_asset_has_exact_sri_and_cors_mode():
    parser = _parse_production_templates()
    occurrences = {url: 0 for url in _ELIGIBLE_ASSETS}
    directly_loaded_jsdelivr_assets = {
        url
        for _tag, url, _attrs in parser.resources
        if url.startswith('https://cdn.jsdelivr.net/')
    }

    assert directly_loaded_jsdelivr_assets == set(_ELIGIBLE_ASSETS)

    for _tag, url, attrs in parser.resources:
        if url not in _ELIGIBLE_ASSETS:
            continue
        occurrences[url] += 1
        assert attrs.get('integrity') == _ELIGIBLE_ASSETS[url]
        assert attrs['integrity'].startswith('sha384-')
        assert attrs.get('crossorigin') == 'anonymous'

    assert occurrences == _EXPECTED_ASSET_OCCURRENCES


def test_google_fonts_and_bootstrap_css_keep_their_explicit_exceptions():
    parser = _parse_production_templates()
    google_stylesheets = [
        attrs
        for tag, url, attrs in parser.resources
        if tag == 'link' and url.startswith('https://fonts.googleapis.com/')
    ]
    assert len(google_stylesheets) == 3
    assert all('integrity' not in attrs for attrs in google_stylesheets)

    tokens_css = _TOKENS_CSS.read_text(encoding='utf-8')
    assert (
        '@import url("https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/'
        'dist/css/bootstrap.min.css") layer(vendor);'
    ) in tokens_css


def test_production_templates_have_no_inline_handlers_or_javascript_urls():
    parser = _parse_production_templates()
    assert parser.executable_attributes == []
    assert parser.javascript_urls == []


def test_every_production_inline_script_has_the_correct_nonce_contract():
    parser = _parse_production_templates()

    assert len(parser.executable_inline_scripts) == 11
    assert {
        attrs.get('nonce') for attrs in parser.executable_inline_scripts
    } == {'{{ csp_nonce }}'}
    assert len(parser.data_scripts) == 2
    assert all(attrs.get('type') == 'application/json' for attrs in parser.data_scripts)
    assert all('nonce' not in attrs for attrs in parser.data_scripts)
