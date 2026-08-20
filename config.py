import os
import sys
from datetime import timedelta
from pathlib import Path

basedir = Path(__file__).parent


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

    # Development-only: auto-login as first user, bypasses email OTP auth.
    # Set DEV_AUTO_LOGIN=1 in environment to enable. NEVER use in production.
    DEV_AUTO_LOGIN = os.environ.get('DEV_AUTO_LOGIN', '0') in ('1', 'true', 'True')

    # Security hardening
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    # Secure-by-default in production; explicit false remains available for
    # operators serving an intentional HTTP-only environment (see helper).
    SESSION_COOKIE_SECURE = _default_cookie_secure()
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_REFRESH_EACH_REQUEST = True

    # Cap request body size to blunt cheap DoS via huge multipart/form
    # uploads or oversized JSON. 1 MB is well above any legitimate form
    # in this app (notes are capped at 300 chars, no file uploads).
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024

    # Flask-Limiter storage. The default remains process-local; deployments
    # with multiple authoritative processes must configure a shared backend.
    RATELIMIT_STORAGE_URI = _rate_limit_storage_uri()

    # Flask-Login never issues remember cookies in passwordless runtime. These
    # flags are retained only so pre-cutover cookies can be expired securely.
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

class DevelopmentConfig(Config):
    """Configuration selected only by the local ``python app.py`` entry point."""
    DEBUG = True
