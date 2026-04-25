import sqlite3

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_login import LoginManager
from flask_mail import Mail
from sqlalchemy import event
from sqlalchemy.engine import Engine
from config import Config
from portfolio_app.utils import fmt_decimal, fmt_money

db = SQLAlchemy()
csrf = CSRFProtect()
login_manager = LoginManager()
mail = Mail()


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
            # FK enforcement must be OFF for the duration of the migration.
            # Several legacy tables in deployed databases still carry FK
            # references to renamed parent tables (e.g. ``REFERENCES capital``
            # after capital → fund → portfolio); the orphan-cleanup steps
            # below would also fail mid-flight under enforcement.
            #
            # PRAGMA foreign_keys is silently ignored inside a transaction,
            # and SQLAlchemy autobegins on the first execute(). We bypass
            # SQLAlchemy by going through the raw DBAPI connection so the
            # PRAGMA reaches SQLite while it's still in autocommit mode.
            raw_conn = conn.connection.driver_connection
            raw_conn.execute('PRAGMA foreign_keys=OFF')
            try:
                _apply_migration_steps(conn, sa)
            finally:
                # Re-enable FK enforcement on this pooled connection before
                # it returns to the pool. New connections inherit FK=ON via
                # the engine-level listener.
                raw_conn.execute('PRAGMA foreign_keys=ON')


def _apply_migration_steps(conn, sa):
    inspector = sa.inspect(conn)
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

    # ── Step 9: backfill FundEvent for legacy funds with no event history ─
    # Funds that were created before FundEvent was introduced have a
    # cash_balance but no corresponding event record. We create an
    # Initial event so the history display is accurate. Idempotent:
    # skipped if events already exist for a fund.
    if 'fund' in tables and 'fund_event' in tables:
        legacy_funds = conn.execute(sa.text(
            'SELECT f.id, f.cash_balance, f.created_at '
            'FROM fund f '
            'LEFT JOIN fund_event fe ON fe.fund_id = f.id '
            'WHERE fe.id IS NULL AND f.cash_balance IS NOT NULL AND f.cash_balance != 0'
        )).fetchall()
        for row in legacy_funds:
            conn.execute(sa.text(
                'INSERT INTO fund_event (fund_id, event_type, amount_delta, date) '
                'VALUES (:fund_id, :event_type, :amount, :date)'
            ), {
                'fund_id': row[0],
                'event_type': 'Initial',
                'amount': row[1],
                'date': row[2],
            })
        if legacy_funds:
            conn.commit()

    # ── Step 10: rename asset_class → name in fund table ───────────────
    if 'fund' in tables:
        fund_cols = {c['name'] for c in inspector.get_columns('fund')}
        if 'asset_class' in fund_cols and 'name' not in fund_cols:
            conn.execute(sa.text(
                'ALTER TABLE fund RENAME COLUMN asset_class TO name'
            ))
            conn.commit()

    # ── Step 11: closed_trade table ──────────────────────────────────────
    # Historically created here for the snapshot-based realized-P&L design.
    # Step 23 below now drops the table; we keep this CREATE so older
    # databases progress through the rename steps in order.
    tables = set(inspector.get_table_names())
    if 'closed_trade' not in tables:
        conn.execute(sa.text('''
            CREATE TABLE closed_trade (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id INTEGER NOT NULL UNIQUE
                               REFERENCES "transaction"(id) ON DELETE CASCADE,
                portfolio_id   INTEGER NOT NULL
                               REFERENCES portfolio(id) ON DELETE CASCADE,
                symbol         VARCHAR(20) NOT NULL,
                quantity_sold  NUMERIC(20,10) NOT NULL,
                avg_cost       NUMERIC(20,10) NOT NULL,
                sell_price     NUMERIC(20,10) NOT NULL,
                fees           NUMERIC(20,10) NOT NULL DEFAULT 0,
                cost_basis     NUMERIC(20,10) NOT NULL,
                gross_proceeds NUMERIC(20,10) NOT NULL,
                realized_pnl   NUMERIC(20,10) NOT NULL,
                closed_at      DATE NOT NULL,
                created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at     DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        '''))
        conn.commit()

    # ── Step 12: Rename fund → portfolio ─────────────────────────────────
    tables = set(inspector.get_table_names())
    if 'fund' in tables and 'portfolio' not in tables:
        conn.execute(sa.text('ALTER TABLE fund RENAME TO portfolio'))
        conn.commit()
        tables = set(inspector.get_table_names())

    # ── Step 13: Rename fund_event → portfolio_event ─────────────────────
    if 'fund_event' in tables and 'portfolio_event' not in tables:
        conn.execute(sa.text('ALTER TABLE fund_event RENAME TO portfolio_event'))
        conn.commit()

    # ── Step 14: portfolio_event.fund_id → portfolio_id ──────────────────
    tables = set(inspector.get_table_names())
    if 'portfolio_event' in tables:
        pe_cols = {c['name'] for c in inspector.get_columns('portfolio_event')}
        if 'fund_id' in pe_cols:
            conn.execute(sa.text(
                'ALTER TABLE portfolio_event RENAME COLUMN fund_id TO portfolio_id'
            ))
            conn.commit()

    # ── Step 15: transaction.fund_id → portfolio_id ──────────────────────
    if 'transaction' in tables:
        tx_cols = {c['name'] for c in inspector.get_columns('transaction')}
        if 'fund_id' in tx_cols:
            conn.execute(sa.text(
                'ALTER TABLE "transaction" RENAME COLUMN fund_id TO portfolio_id'
            ))
            conn.commit()

    # ── Step 16: asset.fund_id → portfolio_id ────────────────────────────
    if 'asset' in tables:
        asset_cols = {c['name'] for c in inspector.get_columns('asset')}
        if 'fund_id' in asset_cols:
            conn.execute(sa.text(
                'ALTER TABLE asset RENAME COLUMN fund_id TO portfolio_id'
            ))
            conn.commit()

    # ── Step 17: dividend.fund_id → portfolio_id ─────────────────────────
    if 'dividend' in tables:
        div_cols = {c['name'] for c in inspector.get_columns('dividend')}
        if 'fund_id' in div_cols:
            conn.execute(sa.text(
                'ALTER TABLE dividend RENAME COLUMN fund_id TO portfolio_id'
            ))
            conn.commit()

    # ── Step 18: closed_trade.fund_id → portfolio_id ─────────────────────
    if 'closed_trade' in tables:
        ct_cols = {c['name'] for c in inspector.get_columns('closed_trade')}
        if 'fund_id' in ct_cols:
            conn.execute(sa.text(
                'ALTER TABLE closed_trade RENAME COLUMN fund_id TO portfolio_id'
            ))
            conn.commit()

    # ── Step 19: portfolio.cash_balance → net_deposits ────────────────────
    # Reflects that this field tracks deposits minus withdrawals only —
    # it is NOT the available cash (which also accounts for buy/sell flows).
    tables = set(inspector.get_table_names())
    if 'portfolio' in tables:
        p_cols = {c['name'] for c in inspector.get_columns('portfolio')}
        if 'cash_balance' in p_cols and 'net_deposits' not in p_cols:
            conn.execute(sa.text(
                'ALTER TABLE portfolio RENAME COLUMN cash_balance TO net_deposits'
            ))
            conn.commit()

    # ── Step 20: rename asset → symbol ────────────────────────────────────
    # The "Asset" class/table was a tracked-symbol marker. Renamed for
    # consistency with the domain term used everywhere else in the app.
    # Drop old indexes first so db.create_all() recreates them with the
    # new Symbol table's naming (ix_symbol_portfolio_ticker, etc.).
    tables = set(inspector.get_table_names())
    if 'asset' in tables and 'symbol' not in tables:
        for ix in inspector.get_indexes('asset'):
            conn.execute(sa.text(f'DROP INDEX IF EXISTS "{ix["name"]}"'))
        conn.execute(sa.text('ALTER TABLE asset RENAME TO symbol'))
        conn.commit()

    # ── Step 21: purge orphan closed_trade rows ──────────────────────────
    # Pre-dates SQLite FK enforcement. Rows whose parent transaction or
    # portfolio was deleted under FK-OFF were never cascaded and kept
    # surfacing as ghost realized P&L on the dashboard.
    tables = set(inspector.get_table_names())
    if 'closed_trade' in tables:
        conn.execute(sa.text(
            'DELETE FROM closed_trade '
            'WHERE transaction_id NOT IN (SELECT id FROM "transaction") '
            '   OR portfolio_id   NOT IN (SELECT id FROM portfolio)'
        ))
        conn.commit()

    # ── Step 22: delete orphan portfolios with NULL user_id ──────────────
    # Created before user_id was introduced, invisible to every account
    # (PortfolioRepository filters by user_id). They and all their
    # children — transactions, events, dividends, symbols — are removed.
    if 'portfolio' in tables:
        p_cols = {c['name'] for c in inspector.get_columns('portfolio')}
        if 'user_id' in p_cols:
            orphan_ids = [
                row[0]
                for row in conn.execute(sa.text(
                    'SELECT id FROM portfolio WHERE user_id IS NULL'
                )).fetchall()
            ]
            if orphan_ids:
                placeholders = ','.join(str(int(i)) for i in orphan_ids)
                for child_table, fk_col in (
                    ('"transaction"',     'portfolio_id'),
                    ('portfolio_event',   'portfolio_id'),
                    ('dividend',          'portfolio_id'),
                    ('symbol',            'portfolio_id'),
                ):
                    bare = child_table.strip('"')
                    if bare in tables:
                        conn.execute(sa.text(
                            f'DELETE FROM {child_table} WHERE {fk_col} IN ({placeholders})'
                        ))
                conn.execute(sa.text(
                    f'DELETE FROM portfolio WHERE id IN ({placeholders})'
                ))
                conn.commit()

    # ── Step 23: drop closed_trade table ─────────────────────────────────
    # Realized P&L is now computed dynamically from transactions, so the
    # snapshot table is no longer the source of truth for any read path.
    # Removing it eliminates the entire snapshot-drift bug class.
    # Unconditional DROP ... IF EXISTS — Step 11 above (kept for legacy
    # ordering) creates the table on a fresh install, and inspector results
    # may be cached/stale, so we don't gate on a possibly out-of-date set.
    conn.execute(sa.text('DROP TABLE IF EXISTS closed_trade'))
    conn.commit()

    # ── Step 24: rebuild tables with stale or missing FK constraints ─────
    # Older databases were created when the parent table was named
    # ``capital`` (later ``fund`` then ``portfolio``). SQLite RENAME TABLE
    # does not rewrite FK targets in other tables, so the stored CREATE
    # statements still REFERENCE the obsolete name. With the FK pragma now
    # enforced engine-wide (see _enable_sqlite_foreign_keys), every
    # INSERT/UPDATE/DELETE on those tables would otherwise fail.
    #
    # Each rebuild also adds ``ON DELETE CASCADE`` so deleting a Portfolio
    # (or User) cascades through the entire ownership tree at the database
    # level, not just via SQLAlchemy ORM walks.
    _rebuild_tables_with_fixed_fks(conn, sa, inspector)


def _rebuild_tables_with_fixed_fks(conn, sa, inspector):
    """Rebuild legacy tables whose FK targets reference renamed parents.

    Idempotent: each table is inspected first; if its current CREATE
    statement already references the correct parent, the rebuild is
    skipped. Caller must have FK enforcement disabled.
    """
    tables = set(inspector.get_table_names())

    # Each entry: (table_name, expected_fk_text_in_current_schema_if_correct,
    #              CREATE statement for replacement, columns to copy,
    #              list of CREATE INDEX statements to apply afterwards)
    rebuilds = [
        (
            'transaction',
            'REFERENCES portfolio',
            '''
            CREATE TABLE _new_transaction (
                id               INTEGER NOT NULL PRIMARY KEY,
                portfolio_id     INTEGER NOT NULL REFERENCES portfolio(id) ON DELETE CASCADE,
                transaction_type VARCHAR(10) NOT NULL,
                symbol           VARCHAR(20),
                price            NUMERIC(20, 10) NOT NULL,
                quantity         NUMERIC(20, 10) NOT NULL,
                fees             NUMERIC(20, 10) NOT NULL DEFAULT 0,
                net_amount       NUMERIC(20, 10) NOT NULL DEFAULT 0,
                average_cost     NUMERIC(20, 10) NOT NULL DEFAULT 0,
                date             DATETIME,
                notes            TEXT,
                CONSTRAINT check_price_positive          CHECK (price > 0),
                CONSTRAINT check_quantity_positive       CHECK (quantity > 0),
                CONSTRAINT check_fees_non_negative       CHECK (fees >= 0),
                CONSTRAINT check_net_amount_non_negative CHECK (net_amount >= 0)
            )
            ''',
            ['id', 'portfolio_id', 'transaction_type', 'symbol', 'price',
             'quantity', 'fees', 'net_amount', 'average_cost', 'date', 'notes'],
            [],
        ),
        (
            'symbol',
            'REFERENCES portfolio',
            '''
            CREATE TABLE _new_symbol (
                id           INTEGER NOT NULL PRIMARY KEY,
                portfolio_id INTEGER NOT NULL REFERENCES portfolio(id) ON DELETE CASCADE,
                symbol       VARCHAR(20) NOT NULL,
                created_at   DATETIME,
                updated_at   DATETIME,
                CONSTRAINT uq_symbol_portfolio_ticker UNIQUE (portfolio_id, symbol)
            )
            ''',
            ['id', 'portfolio_id', 'symbol', 'created_at', 'updated_at'],
            ['CREATE INDEX ix_symbol_portfolio_ticker ON symbol (portfolio_id, symbol)'],
        ),
        (
            'dividend',
            'REFERENCES portfolio',
            '''
            CREATE TABLE _new_dividend (
                id           INTEGER NOT NULL PRIMARY KEY,
                portfolio_id INTEGER NOT NULL REFERENCES portfolio(id) ON DELETE CASCADE,
                symbol       VARCHAR(20),
                amount       NUMERIC(20, 10) NOT NULL,
                date         DATETIME NOT NULL,
                notes        TEXT,
                created_at   DATETIME NOT NULL,
                CONSTRAINT check_dividend_amount_positive CHECK (amount > 0)
            )
            ''',
            ['id', 'portfolio_id', 'symbol', 'amount', 'date', 'notes', 'created_at'],
            [],
        ),
        (
            'portfolio_event',
            'ON DELETE CASCADE',
            '''
            CREATE TABLE _new_portfolio_event (
                id           INTEGER NOT NULL PRIMARY KEY,
                portfolio_id INTEGER NOT NULL REFERENCES portfolio(id) ON DELETE CASCADE,
                event_type   VARCHAR(20) NOT NULL,
                amount_delta NUMERIC(15, 2) NOT NULL DEFAULT 0,
                date         DATETIME,
                notes        TEXT
            )
            ''',
            ['id', 'portfolio_id', 'event_type', 'amount_delta', 'date', 'notes'],
            ['CREATE INDEX ix_portfolio_event_portfolio_date ON portfolio_event (portfolio_id, date)'],
        ),
        (
            'portfolio',
            'ON DELETE CASCADE',
            '''
            CREATE TABLE _new_portfolio (
                id           INTEGER NOT NULL PRIMARY KEY,
                user_id      INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
                name         VARCHAR(50) NOT NULL,
                net_deposits NUMERIC(15, 2) NOT NULL DEFAULT 0,
                created_at   DATETIME,
                updated_at   DATETIME
            )
            ''',
            ['id', 'user_id', 'name', 'net_deposits', 'created_at', 'updated_at'],
            ['CREATE INDEX ix_portfolio_user_id ON portfolio (user_id)'],
        ),
    ]

    for table, ok_marker, create_sql, columns, indexes in rebuilds:
        if table not in tables:
            continue
        existing_sql = conn.execute(sa.text(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=:n"
        ), {'n': table}).scalar() or ''
        if ok_marker in existing_sql:
            continue  # already correct — skip

        # Drop a leftover temp table from a previous interrupted run
        conn.execute(sa.text(f'DROP TABLE IF EXISTS _new_{table}'))
        conn.execute(sa.text(create_sql))

        cols_csv = ', '.join(columns)
        conn.execute(sa.text(
            f'INSERT INTO _new_{table} ({cols_csv}) '
            f'SELECT {cols_csv} FROM "{table}"'
        ))

        # Drop indexes pointing at the soon-to-be-dropped original table.
        # Skip auto-indexes (sqlite_autoindex_*); SQLite manages those.
        for ix in inspector.get_indexes(table):
            ix_name = ix['name']
            if ix_name and not ix_name.startswith('sqlite_autoindex_'):
                conn.execute(sa.text(f'DROP INDEX IF EXISTS "{ix_name}"'))

        conn.execute(sa.text(f'DROP TABLE "{table}"'))
        conn.execute(sa.text(f'ALTER TABLE _new_{table} RENAME TO "{table}"'))
        for ix_sql in indexes:
            conn.execute(sa.text(ix_sql))
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
        return db.session.get(User, int(user_id))

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

        ref = request.referrer
        if ref:
            return redirect(ref)
        return redirect(url_for("dashboard.index"))

    # Template filters
    app.jinja_env.filters['fmt_decimal'] = fmt_decimal
    app.jinja_env.filters['fmt_money'] = fmt_money

    # Expose the MESSAGES dictionary to all templates
    from portfolio_app.utils.messages import MESSAGES

    @app.context_processor
    def inject_template_globals():
        return {'MESSAGES': MESSAGES}

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

    # Register blueprints
    from portfolio_app.routes import register_blueprints
    register_blueprints(app)

    # Apply incremental schema migrations first (renames, column drops/adds),
    # then create_all() for any new tables/columns introduced in this release.
    _run_migrations(app)
    with app.app_context():
        db.create_all()

    return app
