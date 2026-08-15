import os
import ipaddress
import re
import sys
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

basedir = Path(__file__).parent
_LOCAL_APP_BASE_URL = 'http://127.0.0.1:5000'
_DNS_LABEL_RE = re.compile(r'\A[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z')


def _is_valid_url_hostname(hostname: str) -> bool:
    """Accept IP literals and syntactically valid IDNA/DNS hostnames."""
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        # A dotted numeric value is intended to be an IPv4 address; do not
        # reinterpret an invalid one as a DNS name.
        if re.fullmatch(r'[0-9.]+', hostname):
            return False

    dns_name = hostname[:-1] if hostname.endswith('.') else hostname
    try:
        ascii_name = dns_name.encode('idna').decode('ascii').lower()
    except UnicodeError:
        return False

    if not ascii_name or len(ascii_name) > 253:
        return False
    return all(
        _DNS_LABEL_RE.fullmatch(label) is not None
        for label in ascii_name.split('.')
    )


def normalize_app_base_url(value, *, allow_insecure=False) -> str:
    """Return the canonical public URL used to build emailed links.

    Production requires an explicit HTTPS URL. Tests and debug deployments may
    omit it for a deterministic local fallback or explicitly use HTTP. Request
    host data is deliberately not involved in this configuration contract.
    """
    if value is None:
        candidate = ''
    elif isinstance(value, str):
        candidate = value.strip()
    else:
        raise RuntimeError('APP_BASE_URL must be a text URL.')

    if not candidate:
        if allow_insecure:
            return _LOCAL_APP_BASE_URL
        raise RuntimeError(
            'APP_BASE_URL must be configured as an absolute HTTPS URL.'
        )

    if any(character.isspace() for character in candidate):
        raise RuntimeError(
            'APP_BASE_URL must be an absolute HTTP(S) URL without whitespace.'
        )

    try:
        parsed = urlsplit(candidate)
        hostname = parsed.hostname
        parsed.port  # Validate malformed/non-numeric port declarations.
    except ValueError as exc:
        raise RuntimeError('APP_BASE_URL is malformed.') from exc

    scheme = parsed.scheme.lower()
    if scheme not in ('http', 'https') or not parsed.netloc or not hostname:
        raise RuntimeError('APP_BASE_URL must be an absolute HTTP(S) URL.')
    if parsed.netloc.endswith(':'):
        raise RuntimeError('APP_BASE_URL contains an empty port.')
    if not _is_valid_url_hostname(hostname):
        raise RuntimeError('APP_BASE_URL contains an invalid hostname.')
    if parsed.username is not None or parsed.password is not None:
        raise RuntimeError('APP_BASE_URL must not contain credentials.')
    if parsed.query or parsed.fragment:
        raise RuntimeError('APP_BASE_URL must not contain a query or fragment.')
    if parsed.path not in ('', '/'):
        raise RuntimeError('APP_BASE_URL must be an origin without a path.')
    if scheme != 'https' and not allow_insecure:
        raise RuntimeError('APP_BASE_URL must use HTTPS outside debug/test mode.')

    return urlunsplit((
        scheme,
        parsed.netloc,
        '',
        '',
        '',
    ))


def _require_secret_key() -> str:
    key = os.environ.get('SECRET_KEY')
    if key:
        return key
    # Allow the insecure default ONLY when explicitly running in dev/test.
    # The previous FLASK_ENV='production' trigger is unreliable because
    # Flask 2.3+ removed FLASK_ENV, so production deployments that forgot
    # to set SECRET_KEY were silently falling through to the published
    # hard-coded dev key.
    if (
        os.environ.get('FLASK_DEBUG') in ('1', 'true', 'True')
        or 'pytest' in sys.modules
    ):
        return 'dev-only-insecure-key-do-not-use-in-production'
    raise RuntimeError(
        'SECRET_KEY environment variable must be set. '
        'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
    )


def _default_cookie_secure() -> bool:
    """Resolve the Secure cookie flag from an explicit or automatic setting.

    The historical default was '0' (off), which meant a production deploy
    that forgot to set SESSION_COOKIE_SECURE would ship its session cookie
    over plain HTTP. We only default to '0' in dev/test (FLASK_DEBUG=1 or
    pytest); everything else is treated as production and defaults to
    Secure=True. Blank values retain that automatic behavior. Nonblank values
    must be an explicit true or false spelling so configuration mistakes fail
    at startup instead of silently disabling Secure cookies.
    """
    explicit = os.environ.get('SESSION_COOKIE_SECURE')
    if explicit is not None:
        normalized = explicit.strip().lower()
        if normalized in ('1', 'true'):
            return True
        if normalized in ('0', 'false'):
            return False
        if normalized:
            raise RuntimeError(
                'SESSION_COOKIE_SECURE must be unset, blank, or one of: '
                '1, true, 0, false.'
            )
    in_dev = (
        os.environ.get('FLASK_DEBUG') in ('1', 'true', 'True')
        or 'pytest' in sys.modules
    )
    return not in_dev


def _rate_limit_storage_uri() -> str:
    """Return the configured limiter storage URI or the local default."""
    configured = os.environ.get('RATELIMIT_STORAGE_URI', '').strip()
    return configured or 'memory://'


class Config:
    """Base configuration"""
    SECRET_KEY = _require_secret_key()
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        f'sqlite:///{basedir / "portfolio.db"}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Debug mode - disabled by default for production
    DEBUG = False

    # Development-only: auto-login as first user, bypasses email/password auth.
    # Set DEV_AUTO_LOGIN=1 in environment to enable. NEVER use in production.
    DEV_AUTO_LOGIN = os.environ.get('DEV_AUTO_LOGIN', '0') in ('1', 'true', 'True')

    # Security hardening
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    # Secure-by-default in production; explicit false remains available for
    # operators serving an intentional HTTP-only environment (see helper).
    SESSION_COOKIE_SECURE = _default_cookie_secure()

    # Cap request body size to blunt cheap DoS via huge multipart/form
    # uploads or oversized JSON. 1 MB is well above any legitimate form
    # in this app (notes are capped at 300 chars, no file uploads).
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024

    # Flask-Limiter storage. The default remains process-local; deployments
    # with multiple authoritative processes must configure a shared backend.
    RATELIMIT_STORAGE_URI = _rate_limit_storage_uri()

    # Flask-Login
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = _default_cookie_secure()
    
    # Transaction types (Buy/Sell only — Dividend uses a separate model)
    TRANSACTION_TYPES = ['Buy', 'Sell']

    # Flask-Mail — Gmail SMTP configuration
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_USERNAME = os.environ.get('EMAIL_USER')
    MAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = ('OnePortfolio', os.environ.get('EMAIL_USER', ''))

    # Raw public URL; create_app validates and normalizes it before use.
    APP_BASE_URL = os.environ.get('APP_BASE_URL', '')

    # Google OAuth foundation configuration. Disabled by default; sign-in
    # routes and callback handling are not implemented yet.
    GOOGLE_OAUTH_ENABLED = os.getenv("GOOGLE_OAUTH_ENABLED", "0") == "1"
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "")

    # Token expiry (seconds). Email-verification uses a 6-digit OTP whose
    # 10-minute lifetime is enforced in AuthService — no Config knob needed.
    PASSWORD_RESET_EXPIRY     = 60 * 60         # 1 hour


class DevelopmentConfig(Config):
    """Configuration selected only by the local ``python app.py`` entry point."""
    DEBUG = True
