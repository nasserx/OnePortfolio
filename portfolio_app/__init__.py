from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_login import LoginManager
from flask_mail import Mail
from config import Config
from portfolio_app.utils import fmt_decimal, fmt_money

db = SQLAlchemy()
csrf = CSRFProtect()
login_manager = LoginManager()
mail = Mail()


def _run_migrations(app):
    """Apply incremental schema changes that SQLAlchemy create_all() cannot handle.

    All steps are idempotent — safe to run on both fresh installs and existing
    databases. Each step checks the current state before acting, so re-running
    after a partial migration is safe.

    Requires SQLite 3.25+ for RENAME COLUMN support (released 2018).
    """
    import sqlalchemy as sa
    with app.app_context():
        with db.engine.connect() as conn:
            inspector = sa.inspect(db.engine)
            tables = set(inspector.get_table_names())

            # ── Step 1: Rename legacy tables ─────────────────────────────────
            if 'capital' in tables and 'fund' not in tables:
                conn.execute(sa.text('ALTER TABLE capital RENAME TO fund'))
                conn.commit()
                tables = set(inspector.get_table_names())

            if 'capital_event' in tables and 'fund_event' not in tables:
                conn.execute(sa.text('ALTER TABLE capital_event RENAME TO fund_event'))
                conn.commit()

            # ── Step 2: fund table — add missing column, then rename legacy ones ──
            if 'fund' in tables:
                fund_cols = {c['name'] for c in inspector.get_columns('fund')}

                if 'user_id' not in fund_cols:
                    conn.execute(sa.text(
                        'ALTER TABLE fund ADD COLUMN user_id INTEGER REFERENCES "user"(id)'
                    ))
                    conn.commit()
                    fund_cols.add('user_id')

                if 'category' in fund_cols:
                    conn.execute(sa.text(
                        'ALTER TABLE fund RENAME COLUMN category TO asset_class'
                    ))
                    conn.commit()

                if 'amount' in fund_cols:
                    conn.execute(sa.text(
                        'ALTER TABLE fund RENAME COLUMN amount TO cash_balance'
                    ))
                    conn.commit()

            # ── Step 3: fund_event table — rename legacy columns ─────────────
            if 'fund_event' in tables:
                fe_cols = {c['name'] for c in inspector.get_columns('fund_event')}

                if 'capital_id' in fe_cols:
                    conn.execute(sa.text(
                        'ALTER TABLE fund_event RENAME COLUMN capital_id TO fund_id'
                    ))
                    conn.commit()

                if 'amount_usd_delta' in fe_cols:
                    conn.execute(sa.text(
                        'ALTER TABLE fund_event RENAME COLUMN amount_usd_delta TO amount_delta'
                    ))
                    conn.commit()

                # Drop indexes so db.create_all() can recreate them cleanly
                existing_indexes = {ix['name'] for ix in inspector.get_indexes('fund_event')}
                for ix_name in existing_indexes:
                    conn.execute(sa.text(f'DROP INDEX IF EXISTS "{ix_name}"'))
                conn.commit()

            # ── Step 4: transaction table — rename legacy columns ─────────────
            if 'transaction' in tables:
                tx_cols = {c['name'] for c in inspector.get_columns('transaction')}

                if 'capital_id' in tx_cols:
                    conn.execute(sa.text(
                        'ALTER TABLE "transaction" RENAME COLUMN capital_id TO fund_id'
                    ))
                    conn.commit()

                if 'total_cost' in tx_cols:
                    conn.execute(sa.text(
                        'ALTER TABLE "transaction" RENAME COLUMN total_cost TO net_amount'
                    ))
                    conn.commit()

            # ── Step 5: asset table — rename legacy FK column ─────────────────
            if 'asset' in tables:
                asset_cols = {c['name'] for c in inspector.get_columns('asset')}
                if 'capital_id' in asset_cols:
                    conn.execute(sa.text(
                        'ALTER TABLE asset RENAME COLUMN capital_id TO fund_id'
                    ))
                    conn.commit()

            # ── Step 6: dividend table — rename legacy FK column ──────────────
            if 'dividend' in tables:
                div_cols = {c['name'] for c in inspector.get_columns('dividend')}
                if 'capital_id' in div_cols:
                    conn.execute(sa.text(
                        'ALTER TABLE dividend RENAME COLUMN capital_id TO fund_id'
                    ))
                    conn.commit()

            # ── Step 7: user table — add columns introduced in earlier releases ─
            if 'user' in tables:
                user_cols = {c['name'] for c in inspector.get_columns('user')}

                if 'email' not in user_cols:
                    conn.execute(sa.text(
                        'ALTER TABLE "user" ADD COLUMN email VARCHAR(120)'
                    ))
                    conn.commit()

                if 'is_verified' not in user_cols:
                    conn.execute(sa.text(
                        'ALTER TABLE "user" ADD COLUMN is_verified BOOLEAN NOT NULL DEFAULT 0'
                    ))
                    # Mark existing users as verified so their accounts stay accessible
                    conn.execute(sa.text('UPDATE "user" SET is_verified = 1'))
                    conn.commit()

                user_cols = {c['name'] for c in inspector.get_columns('user')}

                if 'verification_code' not in user_cols:
                    conn.execute(sa.text(
                        'ALTER TABLE "user" ADD COLUMN verification_code VARCHAR(6)'
                    ))
                    conn.commit()

                if 'verification_code_expires_at' not in user_cols:
                    conn.execute(sa.text(
                        'ALTER TABLE "user" ADD COLUMN verification_code_expires_at DATETIME'
                    ))
                    conn.commit()

                user_cols = {c['name'] for c in inspector.get_columns('user')}

                if 'pending_email' not in user_cols:
                    conn.execute(sa.text(
                        'ALTER TABLE "user" ADD COLUMN pending_email VARCHAR(120)'
                    ))
                    conn.commit()

                if 'deletion_code' not in user_cols:
                    conn.execute(sa.text(
                        'ALTER TABLE "user" ADD COLUMN deletion_code VARCHAR(6)'
                    ))
                    conn.commit()

                if 'deletion_code_expires_at' not in user_cols:
                    conn.execute(sa.text(
                        'ALTER TABLE "user" ADD COLUMN deletion_code_expires_at DATETIME'
                    ))
                    conn.commit()

            # ── Step 8: dividend table — add per-symbol tracking column ────────
            if 'dividend' in tables:
                div_cols = {c['name'] for c in inspector.get_columns('dividend')}
                if 'symbol' not in div_cols:
                    conn.execute(sa.text(
                        'ALTER TABLE dividend ADD COLUMN symbol VARCHAR(20)'
                    ))
                    conn.commit()


def create_app(config_class=Config):
    """Application factory pattern."""
    app = Flask(__name__)
    app.config.from_object(config_class)

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

    # Flask-Login configuration
    login_manager.login_view = 'auth.login'
    login_manager.login_message = ''

    @login_manager.user_loader
    def load_user(user_id: str):
        from portfolio_app.models.user import User
        return User.query.get(int(user_id))

    @app.errorhandler(CSRFError)
    def _handle_csrf_error(e: CSRFError):
        from flask import flash, redirect, request, url_for, jsonify

        # Return JSON for AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'success': False, 'error': 'Session expired. Please refresh the page.'}), 400

        try:
            flash("Security check failed (CSRF token missing/invalid). Refresh the page then try again.", "warning")
        except Exception:
            pass

        ref = request.referrer
        if ref:
            return redirect(ref)
        return redirect(url_for("dashboard.index"))

    # Template filters
    app.jinja_env.filters['fmt_decimal'] = fmt_decimal
    app.jinja_env.filters['fmt_money'] = fmt_money

    # Inject asset class icons and message classes into all templates
    from portfolio_app.utils.messages import (
        ErrorMessages, SuccessMessages, ConfirmMessages,
        ValidationMessages, AuthMessages, AdminMessages,
    )

    @app.context_processor
    def inject_template_globals():
        return {
            'asset_class_icons': app.config.get('ASSET_CLASS_ICONS', {}),
            'asset_class_icon_default': app.config.get('ASSET_CLASS_ICON_DEFAULT', ('bi-folder', 'text-secondary')),
            'Msg': {
                'error': ErrorMessages,
                'success': SuccessMessages,
                'confirm': ConfirmMessages,
                'validation': ValidationMessages,
                'auth': AuthMessages,
                'admin': AdminMessages,
            },
        }

    # Health check route
    @app.route('/health')
    def health():
        return {'status': 'healthy'}, 200

    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return {'error': 'Not Found', 'message': 'The requested resource was not found'}, 404

    @app.errorhandler(500)
    def internal_error(error):
        return {'error': 'Internal Server Error', 'message': 'An unexpected error occurred'}, 500

    # Register blueprints
    from portfolio_app.routes import register_blueprints
    register_blueprints(app)

    # Apply incremental schema migrations first (renames, column drops/adds),
    # then create_all() for any new tables/columns introduced in this release.
    _run_migrations(app)
    with app.app_context():
        db.create_all()

    return app
