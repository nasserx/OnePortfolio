import sqlite3
import re
import secrets

from flask import Flask, current_app, g
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_login import LoginManager
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from authlib.integrations.flask_client import OAuth
from sqlalchemy import event
from sqlalchemy.engine import Engine
from config import Config
from portfolio_app.utils import (
    fmt_decimal,
    fmt_display_decimal,
    fmt_display_money,
    fmt_display_percent,
    fmt_money,
)
from portfolio_app.utils.redirects import safe_local_redirect

db = SQLAlchemy()
csrf = CSRFProtect()
login_manager = LoginManager()
mail = Mail()
ONEPORTFOLIO_OAUTH_EXTENSION_KEY = 'oneportfolio_oauth'
GOOGLE_OIDC_ISSUER = 'https://accounts.google.com'
GOOGLE_OIDC_ACCEPTED_ISSUERS = (
    GOOGLE_OIDC_ISSUER,
    'accounts.google.com',
)
_AUTH_IDENTITY_RE = re.compile(r'\Av1:([1-9][0-9]*):(0|[1-9][0-9]*)\Z')
_LEGACY_AUTH_IDENTITY_RE = re.compile(r'\A[1-9][0-9]*\Z')
# ``RATELIMIT_STORAGE_URI`` is owned by application configuration and consumed
# by ``init_app``. No constructor value should override that deployment choice.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
)


def get_oauth():
    """Return the app-scoped Authlib OAuth registry."""
    return current_app.extensions[ONEPORTFOLIO_OAUTH_EXTENSION_KEY]


def _register_google_oauth_client(app, oauth_client):
    """Register Google OpenID Connect only when explicitly enabled."""
    if not app.config.get('GOOGLE_OAUTH_ENABLED'):
        return

    missing = [
        name for name in (
            'GOOGLE_CLIENT_ID',
            'GOOGLE_CLIENT_SECRET',
            'GOOGLE_REDIRECT_URI',
        )
        if not app.config.get(name)
    ]
    if missing:
        raise RuntimeError(
            'Google OAuth is enabled but required configuration is missing: '
            + ', '.join(missing)
        )

    oauth_client.register(
        name='google',
        client_id=app.config['GOOGLE_CLIENT_ID'],
        client_secret=app.config['GOOGLE_CLIENT_SECRET'],
        server_metadata_url=(
            f'{GOOGLE_OIDC_ISSUER}/.well-known/openid-configuration'
        ),
        client_kwargs={'scope': 'openid email profile'},
        redirect_uri=app.config['GOOGLE_REDIRECT_URI'],
    )


def _dev_auto_login_allowed(app) -> bool:
    return bool(app.testing or app.debug)


def _validate_dev_auto_login_config(app) -> None:
    if app.config.get('DEV_AUTO_LOGIN') and not _dev_auto_login_allowed(app):
        raise RuntimeError(
            'DEV_AUTO_LOGIN can only be enabled when TESTING=True, '
            'or DEBUG=True.'
        )


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    # SQLite ships with foreign-key enforcement disabled. Without this pragma
    # every ``ON DELETE CASCADE`` and ``passive_deletes=True`` is silently a
    # no-op, leaving orphan rows on every parent delete (notably ClosedTrade
    # rows from deleted Sells, which then resurrected as ghost realized P&L).
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()




def create_app(config_class=Config):
    """Application factory pattern."""
    app = Flask(__name__)
    app.config.from_object(config_class)
    _validate_dev_auto_login_config(app)

    # ------------------------------------------------------------------
    # Development-only: auto-login as first user, bypasses authentication.
    # Activate by setting the environment variable: DEV_AUTO_LOGIN=1
    # NEVER enable this in production.
    # ------------------------------------------------------------------
    if app.config.get('DEV_AUTO_LOGIN'):
        from flask_login import login_user
        from flask import request as _request

        @app.before_request
        def _auto_login():
            from flask_login import current_user
            if not current_user.is_authenticated and not _request.path.startswith('/static'):
                from portfolio_app.models.user import User
                user = User.query.first()
                if user:
                    login_user(user, remember=False)

    # Initialize extensions
    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    oauth = OAuth()
    oauth.init_app(app)
    app.extensions[ONEPORTFOLIO_OAUTH_EXTENSION_KEY] = oauth
    _register_google_oauth_client(app, oauth)
    # Rate limiting is on by default; the test config flips
    # ``RATELIMIT_ENABLED`` off so the bulk of the suite can run without
    # bumping into per-IP limits, and re-enables it just for the
    # rate-limit-specific tests.
    limiter.init_app(app)

    # Flask-Login configuration
    login_manager.login_view = 'auth.login'
    login_manager.login_message = ''

    @login_manager.user_loader
    def load_user(identity: str):
        from portfolio_app.models.user import User

        # Current identities explicitly bind the database id to the user's
        # authentication generation. Pre-release id-only identities represent
        # generation zero, preserving a controlled upgrade path; malformed
        # values fail closed as anonymous without raising on normal requests.
        if not isinstance(identity, str):
            return None
        match = _AUTH_IDENTITY_RE.fullmatch(identity)
        if match:
            user_id = int(match.group(1))
            generation = int(match.group(2))
        elif _LEGACY_AUTH_IDENTITY_RE.fullmatch(identity):
            user_id = int(identity)
            generation = 0
        else:
            return None

        user = db.session.get(User, user_id)
        if (
            user is None
            or user.auth_generation != generation
            or not user.is_verified
        ):
            return None
        return user

    @app.errorhandler(CSRFError)
    def _handle_csrf_error(e: CSRFError):
        from flask import flash, redirect, request, url_for, jsonify
        from portfolio_app.utils.messages import MESSAGES

        # Return JSON for AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'success': False, 'error': MESSAGES['SESSION_EXPIRED']}), 400

        try:
            flash(MESSAGES['CSRF_CHECK_FAILED'], "warning")
        except Exception:
            pass

        # Reuse the same strict local-path contract as auth ``next`` values.
        # Malformed URLs fail closed to the deterministic internal fallback.
        try:
            safe_referrer = safe_local_redirect(request.referrer)
        except ValueError:
            safe_referrer = None
        return redirect(safe_referrer or url_for("dashboard.index"))

    # Template filters
    app.jinja_env.filters['fmt_decimal'] = fmt_decimal
    app.jinja_env.filters['fmt_display_decimal'] = fmt_display_decimal
    app.jinja_env.filters['fmt_display_money'] = fmt_display_money
    app.jinja_env.filters['fmt_display_percent'] = fmt_display_percent
    app.jinja_env.filters['fmt_money'] = fmt_money

    # Expose the MESSAGES dictionary to all templates
    from portfolio_app.utils.messages import MESSAGES

    # Static-asset cache buster. Bumped by hand when CSS/JS ships, so every
    # template can use `v=ASSET_VERSION` instead of carrying its own literal.
    ASSET_VERSION = '20260810-6'

    def _get_csp_nonce():
        """Return the single cryptographically random nonce for this request."""
        if not hasattr(g, 'csp_nonce'):
            g.csp_nonce = secrets.token_urlsafe(32)
        return g.csp_nonce

    @app.context_processor
    def inject_template_globals():
        return {
            'MESSAGES': MESSAGES,
            'ASSET_VERSION': ASSET_VERSION,
            'csp_nonce': _get_csp_nonce(),
        }

    # Health check route
    @app.route('/health')
    def health():
        return {'status': 'healthy'}, 200

    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return {'error': 'Not Found', 'message': MESSAGES['NOT_FOUND']}, 404

    @app.errorhandler(500)
    def internal_error(error):
        return {'error': 'Internal Server Error', 'message': MESSAGES['INTERNAL_SERVER_ERROR']}, 500

    @app.errorhandler(429)
    def _ratelimit_handler(error):
        from flask import request, jsonify, render_template, flash, redirect, url_for
        # The error_message set on the @limiter.limit decorator surfaces here.
        message = getattr(error, 'description', None) or MESSAGES['RATE_LIMIT_SIGNUP']
        wants_json = (
            request.form.get('_modal') == '1'
            or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or request.is_json
            or request.accept_mimetypes.best == 'application/json'
        )
        if wants_json:
            return jsonify({'ok': False, 'errors': {'__all__': message}}), 429

        # Route-aware re-render: the user landed here from a specific form,
        # so put the rate-limit message inline on that form instead of
        # serving a bare standalone page. Falls back to a wrapped page for
        # any other rate-limited endpoint.
        endpoint = request.endpoint or ''

        if endpoint == 'auth.verify_code':
            email = request.args.get('email', '') or request.form.get('email', '')
            return render_template(
                'auth/verify_code.html',
                email=email,
                form_errors={'__all__': message},
            ), 429

        if endpoint == 'auth.login':
            return render_template(
                'auth/login.html',
                form_errors={'__all__': message},
                form_values=request.form,
            ), 429

        if endpoint == 'auth.register':
            return render_template(
                'auth/register.html',
                form_errors={'__all__': message},
                form_values=request.form,
            ), 429

        if endpoint == 'auth.resend_code':
            # Flash + bounce the user back to the verify-code screen after a
            # rate-limited resend form submission.
            flash(message, 'warning')
            email = request.args.get('email', '')
            if email:
                return redirect(url_for('auth.verify_code', email=email))
            return redirect(url_for('auth.login'))

        if endpoint == 'auth.delete_account_verify':
            flash(message, 'warning')
            return redirect(url_for('auth.settings', tab='account', deletion_sent='1'))

        # Generic fallback — keep the message inside a real page so the
        # user still sees navigation, branding, and a way out.
        return render_template('errors/rate_limit.html', message=message), 429

    # ── Security headers ────────────────────────────────────────────────
    # Defence-in-depth: HSTS (only when serving over HTTPS), clickjacking
    # protection, MIME sniffing protection, locked-down referrer/permission
    # policy, and a CSP scoped to the origins this app actually loads from
    # (Bootstrap + bootstrap-icons via jsdelivr, Inter via Google Fonts).
    # Executable inline <script> blocks use one request-scoped nonce; inline
    # HTML event-handler attributes remain prohibited by ``script-src-attr
    # 'none'``. ``style-src 'unsafe-inline'`` separately permits inline styles.
    _CSP_TEMPLATE = (
        "default-src 'self'; "
        "object-src 'none'; "
        "script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net; "
        "script-src-attr 'none'; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )

    @app.after_request
    def _security_headers(resp):
        resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
        resp.headers.setdefault('X-Frame-Options', 'DENY')
        resp.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        resp.headers.setdefault(
            'Permissions-Policy',
            'geolocation=(), microphone=(), camera=()',
        )
        # HSTS is only meaningful — and only safe — when the app is served
        # exclusively over HTTPS. Gate on the same flag that locks the
        # session cookie to HTTPS so we never advertise HSTS over plain HTTP.
        if app.config.get('SESSION_COOKIE_SECURE'):
            resp.headers.setdefault(
                'Strict-Transport-Security',
                'max-age=31536000; includeSubDomains',
            )
        resp.headers.setdefault(
            'Content-Security-Policy',
            _CSP_TEMPLATE.format(nonce=_get_csp_nonce()),
        )
        return resp

    # Register blueprints
    from portfolio_app.routes import register_blueprints
    register_blueprints(app)

    # Apply incremental schema migrations first (renames, column drops/adds),
    # then create_all() for any new tables/columns introduced in this release.
    from portfolio_app.migrations import run_migrations
    run_migrations(app)
    with app.app_context():
        db.create_all()

    return app
