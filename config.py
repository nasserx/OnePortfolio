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
    
    # Asset categories
    ASSET_CATEGORIES = [
        'Stocks',
        'ETFs',
        'Commodities',
        'Crypto'
    ]

    # Icon mapping per category: (bootstrap-icon-class, text-color-class)
    # To add a new category icon, add an entry here matching the category name exactly.
    ASSET_CATEGORY_ICONS = {
        'Stocks':      ('bi-graph-up',           'text-success'),
        'ETFs':        ('bi-bar-chart-line',      'text-info'),
        'Commodities': ('bi-box-seam',            'text-warning'),
        'Crypto':      ('bi-currency-bitcoin',    'text-danger'),
    }
    ASSET_CATEGORY_ICON_DEFAULT = ('bi-folder',  'text-secondary')

    # Transaction types
    TRANSACTION_TYPES = ['Buy', 'Sell']

    # Flask-Mail — Outlook SMTP configuration
    MAIL_SERVER = 'smtp.office365.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_USERNAME = os.environ.get('EMAIL_USER', 'oneportfolio.no.reply@outlook.com')
    MAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = ('OnePortfolio', os.environ.get('EMAIL_USER', 'oneportfolio.no.reply@outlook.com'))

    # Public base URL used in email links (no trailing slash)
    APP_BASE_URL = os.environ.get('APP_BASE_URL', 'https://oneportfolio.pythonanywhere.com')

    # Token expiry (seconds)
    EMAIL_VERIFICATION_EXPIRY = 60 * 60 * 24   # 24 hours
    PASSWORD_RESET_EXPIRY     = 60 * 60         # 1 hour
