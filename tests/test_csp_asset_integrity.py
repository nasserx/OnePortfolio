"""Regression coverage for CSP headers and third-party asset integrity."""

from html.parser import HTMLParser
from pathlib import Path

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
        self.executable_attributes = []
        self.javascript_urls = []

    def handle_starttag(self, tag, attrs):
        attrs_map = {name.lower(): value for name, value in attrs}
        resource_url = None
        if tag == 'script':
            resource_url = attrs_map.get('src')
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


def _assert_security_header_contract(response):
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['X-Frame-Options'] == 'DENY'
    assert response.headers['Referrer-Policy'] == 'strict-origin-when-cross-origin'
    assert response.headers['Permissions-Policy'] == 'geolocation=(), microphone=(), camera=()'

    directives = _parse_csp(response.headers['Content-Security-Policy'])
    assert directives['default-src'] == {"'self'"}
    assert directives['script-src'] == {
        "'self'",
        "'unsafe-inline'",
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
    assert 'data:' not in directives['script-src']
    assert 'blob:' not in directives['script-src']


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
    for response in responses.values():
        _assert_security_header_contract(response)


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
