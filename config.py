import os
import secrets
from datetime import timedelta
from pathlib import Path

basedir = Path(__file__).parent


class Config:
    """Base configuration"""
    # Generate a secure SECRET_KEY if not provided via environment variable
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
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
    # If you serve over HTTPS, set this to True (or via env) to harden cookies.
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', '0') in ('1', 'true', 'True')

    # Flask-Login
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', '0') in ('1', 'true', 'True')
    
    # Transaction types (Buy/Sell only — Dividend uses a separate model)
    TRANSACTION_TYPES = ['Buy', 'Sell']
    DIVIDEND_TYPE = 'Dividend'

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

    # Token expiry (seconds)
    EMAIL_VERIFICATION_EXPIRY = 60 * 60 * 24   # 24 hours
    PASSWORD_RESET_EXPIRY     = 60 * 60         # 1 hour
