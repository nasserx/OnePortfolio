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
    """Default the Secure cookie flag ON in production-like environments.

    The historical default was '0' (off), which meant a production deploy
    that forgot to set SESSION_COOKIE_SECURE would ship its session cookie
    over plain HTTP. We only default to '0' in dev/test (FLASK_DEBUG=1 or
    pytest); everything else is treated as production and defaults to
    Secure=True. The env variable still wins when explicitly set.
    """
    explicit = os.environ.get('SESSION_COOKIE_SECURE')
    if explicit is not None:
        return explicit in ('1', 'true', 'True')
    in_dev = (
        os.environ.get('FLASK_DEBUG') in ('1', 'true', 'True')
        or 'pytest' in sys.modules
    )
    return not in_dev


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
    # Secure-by-default in production; opt-out only in dev/test (see helper).
    SESSION_COOKIE_SECURE = _default_cookie_secure()

    # Cap request body size to blunt cheap DoS via huge multipart/form
    # uploads or oversized JSON. 1 MB is well above any legitimate form
    # in this app (notes are capped at 300 chars, no file uploads).
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024

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

    # Public base URL used in email links (no trailing slash)
    APP_BASE_URL = os.environ.get('APP_BASE_URL', '')

    # Google OAuth placeholder configuration. Disabled by default; this release
    # only prepares the UI/config surface and does not implement OAuth.
    GOOGLE_OAUTH_ENABLED = os.getenv("GOOGLE_OAUTH_ENABLED", "0") == "1"
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "")

    # Token expiry (seconds). Email-verification uses a 6-digit OTP whose
    # 10-minute lifetime is enforced in AuthService — no Config knob needed.
    PASSWORD_RESET_EXPIRY     = 60 * 60         # 1 hour
