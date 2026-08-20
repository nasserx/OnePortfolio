import contextlib
import os
import sqlite3

from portfolio_app import db


# Bumped whenever a new migration step is added below. Stored in the SQLite
# header (PRAGMA user_version) after a successful migration so subsequent
# boots can short-circuit the whole inspection pass.
TARGET_SCHEMA_VERSION = 35

# Sidecar file that carries the startup schema lock, derived from the
# application database path (``portfolio.db`` → ``portfolio.db.schema-lock``).
STARTUP_SCHEMA_LOCK_SUFFIX = '.schema-lock'

# Bounded wait for that lock. Long enough for a losing worker to sit through a
# realistic migration (the table rebuilds in Step 24/34 copy every row) instead
# of failing a deploy that is merely slow, short enough that a wedged lock
# cannot hang a worker boot indefinitely. Deliberately a single internal
# constant: the value only has to bracket this application's own startup work,
# and a deployment-tunable knob would be one more way to misconfigure a boot.
STARTUP_SCHEMA_LOCK_TIMEOUT_SECONDS = 30.0


class StartupSchemaLockTimeout(RuntimeError):
    """The startup schema lock could not be acquired within the timeout."""


def run_startup_schema(app):
    """Bring the database to the target schema under one exclusive lock.

    Startup schema work is two operations that must not be split: the
    incremental migration pass, and ``db.create_all()`` for tables introduced
    by the models. Both are check-then-act against the same database.

    The migration pass is *not* one transaction — it commits between steps so
    each can re-inspect the schema — so two workers booting together (a
    deploy, a worker reload) can both read the same pre-migration state and
    both act on it. The loser replays a step that already happened and dies on
    ``duplicate column name``, leaving a half-migrated database.

    ``db.create_all()`` has exactly the same shape: its ``checkfirst``
    reflection and its ``CREATE TABLE`` statements are not atomic together, so
    two workers reaching an empty database both see no tables and both create
    them — the loser dies on ``table user already exists``. On a fresh install
    the migration pass has almost nothing to do and *every* table comes from
    ``create_all``, so a lock covering only migrations leaves the entire
    fresh-install path unserialized.

    Hence one lock across both. It cannot live in the application database —
    holding a write transaction there would block the very writes it guards —
    so it lives in a sidecar SQLite database next to it. That reuses the
    locking primitive the deployment already depends on, needs no new
    dependency, and releases automatically when the holding connection closes
    or its process dies.

    Ordering is a double-checked gate. The unlocked pre-check is two cheap
    queries (schema version, table names) and takes no lock when there is
    nothing to do — cheaper than the unconditional ``create_all`` reflection
    it replaces. Under the lock, the migration pass re-reads the version and
    ``create_all`` re-reflects, so a worker that waited out another's startup
    does no work.

    Requires SQLite 3.25+ for RENAME COLUMN support (released 2018).
    """
    with app.app_context():
        lock_path = _startup_schema_lock_path(db.engine.url)

    # Non-SQLite or in-memory databases have no shared file to coordinate on;
    # an in-memory database is private to the process that opened it.
    if lock_path is None:
        _apply_startup_schema(app)
        return

    if not _startup_schema_pending(app):
        return

    timeout_seconds = STARTUP_SCHEMA_LOCK_TIMEOUT_SECONDS
    try:
        with _startup_schema_lock(lock_path, timeout_seconds):
            _apply_startup_schema(app)
    except StartupSchemaLockTimeout as exc:
        # The holder may simply have finished the work we were waiting for.
        if not _startup_schema_pending(app):
            return
        raise StartupSchemaLockTimeout(
            f'Timed out after {timeout_seconds:g}s waiting for the SQLite '
            f'startup schema lock at {lock_path}. The database is still at '
            f'schema version {_current_schema_version(app)} (target '
            f'{TARGET_SCHEMA_VERSION}) or missing tables '
            f'{sorted(_missing_table_names(app))}, so this process refuses to '
            f'migrate concurrently. If another process is starting up, retry '
            f'once it finishes; if none is, a previous startup was '
            f'interrupted — inspect the database before restarting.'
        ) from exc


def _apply_startup_schema(app):
    """The guarded critical section: migrate, then create missing tables."""
    _run_migration_pass(app)
    with app.app_context():
        db.create_all()


def _startup_schema_lock_path(url):
    """Return the sidecar lock path for a file-backed SQLite URL, else None."""
    if url.drivername.split('+')[0] != 'sqlite':
        return None
    database = url.database
    if not database or database == ':memory:':
        return None
    return os.path.abspath(database) + STARTUP_SCHEMA_LOCK_SUFFIX


def _current_schema_version(app):
    with app.app_context():
        with db.engine.connect() as conn:
            return conn.exec_driver_sql('PRAGMA user_version').scalar()


def _missing_table_names(app):
    """Model tables absent from the database — exactly what create_all builds.

    ``create_all(checkfirst=True)`` skips any table that already exists, so an
    empty result means it would issue no DDL at all.
    """
    with app.app_context():
        with db.engine.connect() as conn:
            existing = {
                row[0] for row in conn.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        return set(db.metadata.tables) - existing


def _startup_schema_pending(app):
    """True when either the migration pass or create_all still has work."""
    if _current_schema_version(app) < TARGET_SCHEMA_VERSION:
        return True
    return bool(_missing_table_names(app))


def _is_lock_contention(exc):
    message = str(exc).lower()
    return 'locked' in message or 'busy' in message


@contextlib.contextmanager
def _startup_schema_lock(lock_path, timeout_seconds):
    """Hold an exclusive transaction in the sidecar database for the caller.

    ``BEGIN IMMEDIATE`` takes SQLite's RESERVED lock straight away rather than
    on first write, so contention surfaces here instead of midway through the
    critical section. The lock is on the sidecar file only — the application
    database stays writable for the work running inside this block.
    """
    connection = sqlite3.connect(
        lock_path,
        timeout=timeout_seconds,
        isolation_level=None,  # explicit BEGIN; no implicit transaction
    )
    try:
        connection.execute(f'PRAGMA busy_timeout = {int(timeout_seconds * 1000)}')
        try:
            connection.execute('BEGIN IMMEDIATE')
        except sqlite3.OperationalError as exc:
            if not _is_lock_contention(exc):
                raise
            raise StartupSchemaLockTimeout(
                f'Could not acquire the SQLite startup schema lock at '
                f'{lock_path} within {timeout_seconds:g}s.'
            ) from exc

        try:
            yield
        finally:
            # Release on success and on failure alike. Closing the connection
            # below releases it too, so a killed process leaves no stale lock.
            try:
                connection.execute('ROLLBACK')
            except sqlite3.Error:
                pass
    finally:
        connection.close()


def _run_migration_pass(app):
    """Apply incremental schema changes that SQLAlchemy create_all() cannot handle.

    All steps are idempotent — safe to run on both fresh installs and existing
    databases. Each step checks the current state before acting, so re-running
    after a partial migration is safe.

    Warm starts short-circuit via ``PRAGMA user_version``: once a successful
    migration writes ``TARGET_SCHEMA_VERSION`` into the SQLite header, every
    subsequent boot exits this function in one query. Under the startup schema
    lock held by :func:`run_startup_schema`, that same gate is the inner half
    of the double check — a worker that queued behind another worker's startup
    finds the target version already written and does no work.
    """
    import sqlalchemy as sa
    with app.app_context():
        with db.engine.connect() as conn:
            raw_conn = conn.connection.driver_connection

            current_version = raw_conn.execute('PRAGMA user_version').fetchone()[0]
            if current_version >= TARGET_SCHEMA_VERSION:
                return

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
            raw_conn.execute('PRAGMA foreign_keys=OFF')
            try:
                _apply_migration_steps(conn, sa)
                # End any residual migration transaction before changing the
                # connection-level FK pragma. Individual historical steps may
                # commit earlier, but inspection-only work can autobegin again.
                conn.commit()
            finally:
                # A failed step can leave DDL/DML pending. SQLite ignores the
                # FK pragma inside that transaction, so rollback must happen
                # first; the original exception then propagates unchanged.
                if conn.in_transaction():
                    conn.rollback()

                # Re-enable FK enforcement on this pooled connection before
                # it returns to the pool. New connections inherit FK=ON via
                # the engine-level listener.
                raw_conn.execute('PRAGMA foreign_keys=ON')

            # Mark this DB as up-to-date so future boots skip everything above.
            raw_conn.execute(f'PRAGMA user_version = {TARGET_SCHEMA_VERSION}')


class _LiveInspector:
    """Schema reflection that is re-read from the database on every call.

    SQLAlchemy memoizes every reflection result in ``Inspector.info_cache``
    for the lifetime of the inspector object. A single inspector shared
    across the pass therefore keeps reporting the schema as it looked
    before the first ``ALTER``: once Step 4 renames
    ``transaction.capital_id`` to ``fund_id``, Step 15 asking that same
    inspector for the table's columns is still answered ``capital_id``, so
    the ``fund_id → portfolio_id`` rename never fires and the Step 24
    rebuild dies on ``no such column: portfolio_id``. A ``capital``-era
    database could not converge to the target version at all, and a
    ``fund``-era one needed a second boot to finish.

    Each call here builds a new inspector, so a step's precondition always
    sees the DDL that the steps before it committed. Steps keep asking the
    same three questions in the same way — only the answers stop being
    stale.
    """

    def __init__(self, conn, sa):
        self._conn = conn
        self._sa = sa

    def _inspect(self):
        return self._sa.inspect(self._conn)

    def get_table_names(self):
        return self._inspect().get_table_names()

    def get_columns(self, table_name):
        return self._inspect().get_columns(table_name)

    def get_indexes(self, table_name):
        return self._inspect().get_indexes(table_name)


def _apply_migration_steps(conn, sa):
    inspector = _LiveInspector(conn, sa)
    tables = set(inspector.get_table_names())

    # The historical OTP-hardening step deliberately emptied recoverable
    # registrations. At the passwordless cutover boundary, reject a live
    # legacy row before *any* older migration step can discard it.
    _guard_live_legacy_pending_registrations(conn, sa, tables)

    # ── Step 1: Rename legacy tables ─────────────────────────────────
    if 'capital' in tables and 'fund' not in tables:
        conn.execute(sa.text('ALTER TABLE capital RENAME TO fund'))
        conn.commit()
        tables = set(inspector.get_table_names())

    if 'capital_event' in tables and 'fund_event' not in tables:
        conn.execute(sa.text('ALTER TABLE capital_event RENAME TO fund_event'))
        conn.commit()
        # Steps 2 and 3 below gate on this same local set, so it has to see
        # the renamed table — without this refresh Step 3 skips the
        # ``capital_id → fund_id`` rename on a capital-era database.
        tables = set(inspector.get_table_names())

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
    # Both parent tables must exist to be orphaned against. On a fresh
    # install Step 11 has just created an empty ``closed_trade`` while
    # ``transaction`` and ``portfolio`` are still waiting on create_all,
    # and there is nothing to purge anyway.
    tables = set(inspector.get_table_names())
    if {'closed_trade', 'transaction', 'portfolio'} <= tables:
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

    # ── Step 25: purge dividends without an attributed symbol ────────────
    # Pre-dates the form requiring symbol; any legacy null/empty rows were
    # silently dropped from totals by a defensive filter in the calculator.
    # Step 24 below rebuilds dividend with ``symbol NOT NULL``, so these
    # rows must be removed first or the rebuild's INSERT...SELECT fails.
    # (Numbered 25 to keep migration ordering intuitive — runs before 24.)
    if 'dividend' in tables:
        conn.execute(sa.text(
            "DELETE FROM dividend WHERE symbol IS NULL OR symbol = ''"
        ))
        conn.commit()

    # ── Step 26: auth refactor — pending_registration table + lockout cols ─
    # Sign-ups now stage in pending_registration until the OTP is confirmed,
    # so the `user` table no longer holds unverified rows squatting on a
    # username/email. The lockout columns drive the brute-force protection
    # in AuthService.authenticate (5 fails → 30-min cooldown).
    tables = set(inspector.get_table_names())
    if 'pending_registration' not in tables:
        conn.execute(sa.text('''
            CREATE TABLE pending_registration (
                id                            INTEGER PRIMARY KEY AUTOINCREMENT,
                token                         VARCHAR(64)  NOT NULL UNIQUE,
                username                      VARCHAR(80)  NOT NULL UNIQUE,
                email                         VARCHAR(120) NOT NULL UNIQUE,
                password_hash                 VARCHAR(255) NOT NULL,
                verification_code             VARCHAR(6)   NOT NULL,
                verification_code_expires_at  DATETIME     NOT NULL,
                created_at                    DATETIME     NOT NULL,
                expires_at                    DATETIME     NOT NULL
            )
        '''))
        conn.execute(sa.text(
            'CREATE INDEX ix_pending_registration_token ON pending_registration (token)'
        ))
        conn.execute(sa.text(
            'CREATE INDEX ix_pending_registration_email ON pending_registration (email)'
        ))
        conn.execute(sa.text(
            'CREATE INDEX ix_pending_registration_username ON pending_registration (username)'
        ))
        conn.commit()

    if 'user' in tables:
        user_cols = {c['name'] for c in inspector.get_columns('user')}
        if 'failed_login_attempts' not in user_cols:
            conn.execute(sa.text(
                'ALTER TABLE "user" ADD COLUMN failed_login_attempts INTEGER NOT NULL DEFAULT 0'
            ))
            conn.commit()
        if 'locked_until' not in user_cols:
            conn.execute(sa.text(
                'ALTER TABLE "user" ADD COLUMN locked_until DATETIME'
            ))
            conn.commit()

    # ── Step 27: per-OTP failure counters (Fix #3 — brute-force defence) ──
    # Adds the columns that AuthService increments on each bad code and
    # clears on success. After MAX_OTP_ATTEMPTS failures the code itself is
    # wiped so the user must request a fresh one via /resend-code, closing
    # the brute-force window even within the OTP's 10-minute validity.
    if 'pending_registration' in tables:
        pr_cols = {c['name'] for c in inspector.get_columns('pending_registration')}
        if 'failed_otp_attempts' not in pr_cols:
            conn.execute(sa.text(
                'ALTER TABLE pending_registration '
                'ADD COLUMN failed_otp_attempts INTEGER NOT NULL DEFAULT 0'
            ))
            conn.commit()

    if 'user' in tables:
        user_cols = {c['name'] for c in inspector.get_columns('user')}
        if 'verification_code_failed_attempts' not in user_cols:
            conn.execute(sa.text(
                'ALTER TABLE "user" '
                'ADD COLUMN verification_code_failed_attempts INTEGER NOT NULL DEFAULT 0'
            ))
            conn.commit()
        if 'deletion_code_failed_attempts' not in user_cols:
            conn.execute(sa.text(
                'ALTER TABLE "user" '
                'ADD COLUMN deletion_code_failed_attempts INTEGER NOT NULL DEFAULT 0'
            ))
            conn.commit()

    # ── Step 28: single-use password-reset tokens (Fix MED-A6) ────────────
    # Adds the column AuthService writes to when issuing a reset link and
    # clears on success. itsdangerous tokens are time-signed but stateless;
    # without this column, a leaked link could be replayed within the
    # 1-hour validity window. The DB is now the single source of truth
    # for "is this token still live".
    if 'user' in tables:
        user_cols = {c['name'] for c in inspector.get_columns('user')}
        if 'password_reset_jti' not in user_cols:
            conn.execute(sa.text(
                'ALTER TABLE "user" ADD COLUMN password_reset_jti VARCHAR(32)'
            ))
            conn.commit()

    # ── Step 29: OAuth identity links ───────────────────────────────────
    # Stores stable provider subject identifiers linked to local users.
    # Tokens, authorization codes, provider payloads, and client secrets are
    # intentionally not persisted.
    tables = set(inspector.get_table_names())
    if 'oauth_identity' not in tables:
        conn.execute(sa.text('''
            CREATE TABLE oauth_identity (
                id               INTEGER NOT NULL PRIMARY KEY,
                user_id          INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
                provider         VARCHAR(50) NOT NULL,
                provider_subject VARCHAR(255) NOT NULL,
                created_at       DATETIME NOT NULL,
                updated_at       DATETIME NOT NULL,
                CONSTRAINT uq_oauth_identity_provider_subject
                    UNIQUE (provider, provider_subject),
                CONSTRAINT uq_oauth_identity_user_provider
                    UNIQUE (user_id, provider)
            )
        '''))
        conn.execute(sa.text(
            'CREATE INDEX ix_oauth_identity_user_id ON oauth_identity (user_id)'
        ))
        conn.commit()

    # ── Step 30: repair pending_registration OTP counter drift ──────────
    # Some local databases reached schema version 29 while still missing
    # this column, so startup short-circuited before Step 27 could repair
    # the table. Keep this forward migration narrowly scoped and idempotent.
    tables = set(inspector.get_table_names())
    if 'pending_registration' in tables:
        pr_cols = {
            row[1]
            for row in conn.execute(
                sa.text('PRAGMA table_info(pending_registration)')
            ).fetchall()
        }
        if 'failed_otp_attempts' not in pr_cols:
            conn.execute(sa.text(
                'ALTER TABLE pending_registration '
                'ADD COLUMN failed_otp_attempts INTEGER NOT NULL DEFAULT 0'
            ))
            conn.commit()

    # ── Step 31: per-user authentication generation ───────────────────
    # Flask-Login identities carry this value. Incrementing it in the same
    # transaction as a password change/reset makes older session and remember
    # cookies fail server-side without introducing session persistence.
    if 'user' in tables:
        user_cols = {c['name'] for c in inspector.get_columns('user')}
        if 'auth_generation' not in user_cols:
            conn.execute(sa.text(
                'ALTER TABLE "user" '
                'ADD COLUMN auth_generation INTEGER NOT NULL DEFAULT 0'
            ))
            conn.commit()

    # ── Step 32: remove the obsolete application-admin flag ───────────
    # The application no longer has a privileged cross-user role. Rebuild
    # the table because the supported SQLite baseline predates DROP COLUMN.
    # Child tables are left intact while the migration runner has foreign-key
    # enforcement disabled; their user_id values continue to reference the
    # preserved primary keys after the replacement table is renamed.
    _rebuild_user_without_admin(conn, sa)

    # ── Step 33: keyed-digest storage for numeric OTP credentials ───────
    # Legacy six-digit plaintext values are deliberately invalidated rather
    # than supported through a dual verification path. Rebuild both owning
    # tables so upgraded declarations match fresh model-created schemas.
    _harden_otp_storage(conn, sa)

    # ── Step 24: rebuild tables with stale FK constraints / dropped cols ─
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
    #
    # The ``portfolio`` rebuild also drops the legacy ``net_deposits``
    # denormalized column — net deposits are now derived on read from the
    # PortfolioEvent log, so the column is no longer a source of truth.
    _rebuild_tables(conn, sa, inspector)

    # ── Step 34: fresh/upgraded portfolio-cascade parity ────────────────
    # Version-33 databases created directly from the models could have the
    # correct parent target but NO ACTION delete behavior. The historical
    # Step 24 marker deliberately remains unchanged; this forward pass uses
    # exact PRAGMA metadata and repairs only FK actions that are not CASCADE.
    _rebuild_tables(
        conn,
        sa,
        inspector,
        require_portfolio_cascades=True,
    )

    # ── Step 35: passwordless-auth cutover ─────────────────────────────
    # The user rebuild both makes legacy hashes nullable/inert and acts as
    # the idempotent marker for the one-time authentication-generation bump.
    # Pending registrations are safe to reshape only when no live staged
    # signup would be discarded; expired rows carry no usable credential.
    _cut_over_passwordless_auth(conn, sa)


def _cut_over_passwordless_auth(conn, sa):
    """Make password state inert and reshape empty staged registrations."""
    tables = {
        row[0]
        for row in conn.execute(sa.text(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )).fetchall()
    }

    if 'pending_registration' in tables:
        pending_columns = {
            row[1]
            for row in conn.execute(
                sa.text('PRAGMA table_info(pending_registration)')
            ).fetchall()
        }
        legacy_pending = 'password_hash' in pending_columns
        if legacy_pending:
            _guard_live_legacy_pending_registrations(conn, sa, tables)
            conn.execute(sa.text('DELETE FROM pending_registration'))
            conn.execute(sa.text('DROP TABLE IF EXISTS _new_pending_registration'))
            conn.execute(sa.text('''
                CREATE TABLE _new_pending_registration (
                    id         INTEGER NOT NULL PRIMARY KEY,
                    username   VARCHAR(80) NOT NULL,
                    email      VARCHAR(120) NOT NULL,
                    created_at DATETIME NOT NULL,
                    expires_at DATETIME NOT NULL
                )
            '''))
            for index_name in (
                'ix_pending_registration_token',
                'ix_pending_registration_username',
                'ix_pending_registration_email',
            ):
                conn.execute(sa.text(f'DROP INDEX IF EXISTS "{index_name}"'))
            conn.execute(sa.text('DROP TABLE pending_registration'))
            conn.execute(sa.text(
                'ALTER TABLE _new_pending_registration RENAME TO pending_registration'
            ))
            conn.execute(sa.text(
                'CREATE UNIQUE INDEX ix_pending_registration_username '
                'ON pending_registration (username)'
            ))
            conn.execute(sa.text(
                'CREATE UNIQUE INDEX ix_pending_registration_email '
                'ON pending_registration (email)'
            ))
            conn.commit()

    if 'user' not in tables:
        return
    password_column = next(
        row for row in conn.execute(sa.text('PRAGMA table_info("user")')).fetchall()
        if row[1] == 'password_hash'
    )
    if password_column[3] == 0:
        return

    conn.execute(sa.text('DROP TABLE IF EXISTS _new_user'))
    conn.execute(sa.text('''
        CREATE TABLE _new_user (
            id                                INTEGER NOT NULL PRIMARY KEY,
            username                          VARCHAR(80) NOT NULL,
            email                             VARCHAR(120),
            password_hash                     VARCHAR(255),
            is_verified                       BOOLEAN NOT NULL,
            created_at                        DATETIME,
            last_login                        DATETIME,
            verification_code                 VARCHAR(64),
            verification_code_expires_at      DATETIME,
            verification_code_failed_attempts INTEGER NOT NULL,
            pending_email                     VARCHAR(120),
            deletion_code                     VARCHAR(64),
            deletion_code_expires_at          DATETIME,
            deletion_code_failed_attempts     INTEGER NOT NULL,
            failed_login_attempts              INTEGER NOT NULL,
            locked_until                       DATETIME,
            password_reset_jti                 VARCHAR(32),
            auth_generation                   INTEGER NOT NULL DEFAULT 0
        )
    '''))
    conn.execute(sa.text('''
        INSERT INTO _new_user (
            id, username, email, password_hash, is_verified, created_at,
            last_login, verification_code, verification_code_expires_at,
            verification_code_failed_attempts, pending_email, deletion_code,
            deletion_code_expires_at, deletion_code_failed_attempts,
            failed_login_attempts, locked_until, password_reset_jti,
            auth_generation
        )
        SELECT
            id, username, email, password_hash, is_verified, created_at,
            last_login, verification_code, verification_code_expires_at,
            verification_code_failed_attempts, pending_email, deletion_code,
            deletion_code_expires_at, deletion_code_failed_attempts,
            failed_login_attempts, locked_until, password_reset_jti,
            auth_generation + 1
        FROM "user"
    '''))
    for index_name in ('ix_user_username', 'ix_user_email'):
        conn.execute(sa.text(f'DROP INDEX IF EXISTS "{index_name}"'))
    conn.execute(sa.text('DROP TABLE "user"'))
    conn.execute(sa.text('ALTER TABLE _new_user RENAME TO "user"'))
    conn.execute(sa.text(
        'CREATE UNIQUE INDEX ix_user_username ON "user" (username)'
    ))
    conn.execute(sa.text(
        'CREATE UNIQUE INDEX ix_user_email ON "user" (email)'
    ))
    conn.commit()


def _guard_live_legacy_pending_registrations(conn, sa, tables=None):
    """Fail before migration can discard an active password-era signup."""
    if tables is None:
        tables = {
            row[0]
            for row in conn.execute(sa.text(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )).fetchall()
        }
    if 'pending_registration' not in tables:
        return
    columns = {
        row[1]
        for row in conn.execute(
            sa.text('PRAGMA table_info(pending_registration)')
        ).fetchall()
    }
    if 'password_hash' not in columns or 'expires_at' not in columns:
        return
    live_count = conn.execute(sa.text('''
        SELECT COUNT(*)
        FROM pending_registration
        WHERE datetime(expires_at) >= CURRENT_TIMESTAMP
    ''')).scalar()
    if live_count:
        raise RuntimeError(
            'Passwordless cutover refused: live legacy pending '
            'registrations must finish or expire before deployment.'
        )


def _rebuild_user_without_admin(conn, sa):
    """Drop the legacy user.is_admin column while preserving user identity."""
    user_cols = {
        row[1]
        for row in conn.execute(sa.text('PRAGMA table_info("user")')).fetchall()
    }
    if 'is_admin' not in user_cols:
        return

    columns = [
        'id',
        'username',
        'email',
        'password_hash',
        'is_verified',
        'created_at',
        'last_login',
        'verification_code',
        'verification_code_expires_at',
        'verification_code_failed_attempts',
        'pending_email',
        'deletion_code',
        'deletion_code_expires_at',
        'deletion_code_failed_attempts',
        'failed_login_attempts',
        'locked_until',
        'password_reset_jti',
        'auth_generation',
    ]
    columns_csv = ', '.join(columns)

    conn.execute(sa.text('DROP TABLE IF EXISTS _new_user'))
    conn.execute(sa.text('''
        CREATE TABLE _new_user (
            id                                INTEGER NOT NULL PRIMARY KEY,
            username                          VARCHAR(80) NOT NULL,
            email                             VARCHAR(120),
            password_hash                     VARCHAR(255) NOT NULL,
            is_verified                       BOOLEAN NOT NULL,
            created_at                        DATETIME,
            last_login                        DATETIME,
            verification_code                 VARCHAR(6),
            verification_code_expires_at      DATETIME,
            verification_code_failed_attempts INTEGER NOT NULL,
            pending_email                     VARCHAR(120),
            deletion_code                     VARCHAR(6),
            deletion_code_expires_at          DATETIME,
            deletion_code_failed_attempts     INTEGER NOT NULL,
            failed_login_attempts              INTEGER NOT NULL,
            locked_until                       DATETIME,
            password_reset_jti                 VARCHAR(32),
            auth_generation                   INTEGER NOT NULL DEFAULT 0
        )
    '''))
    conn.execute(sa.text(
        f'INSERT INTO _new_user ({columns_csv}) '
        f'SELECT {columns_csv} FROM "user"'
    ))

    for index_name in ('ix_user_username', 'ix_user_email'):
        conn.execute(sa.text(f'DROP INDEX IF EXISTS "{index_name}"'))
    conn.execute(sa.text('DROP TABLE "user"'))
    conn.execute(sa.text('ALTER TABLE _new_user RENAME TO "user"'))
    conn.execute(sa.text(
        'CREATE UNIQUE INDEX ix_user_username ON "user" (username)'
    ))
    conn.execute(sa.text(
        'CREATE UNIQUE INDEX ix_user_email ON "user" (email)'
    ))
    conn.commit()


def _harden_otp_storage(conn, sa):
    """Widen legacy OTP fields and invalidate their pre-HMAC workflows."""
    tables = {
        row[0]
        for row in conn.execute(
            sa.text("SELECT name FROM sqlite_master WHERE type='table'")
        ).fetchall()
    }

    if 'user' in tables:
        user_columns = {
            row[1]: row
            for row in conn.execute(sa.text('PRAGMA table_info("user")')).fetchall()
        }
        digest_columns_are_current = all(
            user_columns[name][2].upper() == 'VARCHAR(64)'
            for name in ('verification_code', 'deletion_code')
        )
        if not digest_columns_are_current:
            _rebuild_user_with_digest_otp_columns(conn, sa)

    if 'pending_registration' in tables:
        pending_columns = {
            row[1]: row
            for row in conn.execute(
                sa.text('PRAGMA table_info(pending_registration)')
            ).fetchall()
        }
        # Schema 35 intentionally removes registration OTP columns. A lowered
        # user_version or interrupted replay must not make this historical
        # hardening step assume the legacy columns still exist.
        if (
            'verification_code' in pending_columns
            and pending_columns['verification_code'][2].upper() != 'VARCHAR(64)'
        ):
            _rebuild_empty_pending_registration_with_digest_otp(conn, sa)


def _rebuild_user_with_digest_otp_columns(conn, sa):
    """Rebuild User with 64-character OTP digests and preserved identity."""
    conn.execute(sa.text('DROP TABLE IF EXISTS _new_user'))
    conn.execute(sa.text('''
        CREATE TABLE _new_user (
            id                                INTEGER NOT NULL PRIMARY KEY,
            username                          VARCHAR(80) NOT NULL,
            email                             VARCHAR(120),
            password_hash                     VARCHAR(255) NOT NULL,
            is_verified                       BOOLEAN NOT NULL,
            created_at                        DATETIME,
            last_login                        DATETIME,
            verification_code                 VARCHAR(64),
            verification_code_expires_at      DATETIME,
            verification_code_failed_attempts INTEGER NOT NULL,
            pending_email                     VARCHAR(120),
            deletion_code                     VARCHAR(64),
            deletion_code_expires_at          DATETIME,
            deletion_code_failed_attempts     INTEGER NOT NULL,
            failed_login_attempts              INTEGER NOT NULL,
            locked_until                       DATETIME,
            password_reset_jti                 VARCHAR(32),
            auth_generation                   INTEGER NOT NULL DEFAULT 0
        )
    '''))
    conn.execute(sa.text('''
        INSERT INTO _new_user (
            id, username, email, password_hash, is_verified, created_at,
            last_login, verification_code, verification_code_expires_at,
            verification_code_failed_attempts, pending_email, deletion_code,
            deletion_code_expires_at, deletion_code_failed_attempts,
            failed_login_attempts, locked_until, password_reset_jti,
            auth_generation
        )
        SELECT
            id, username, email, password_hash, is_verified, created_at,
            last_login, NULL, NULL, 0, NULL, NULL, NULL, 0,
            failed_login_attempts, locked_until, password_reset_jti,
            auth_generation
        FROM "user"
    '''))
    for index_name in ('ix_user_username', 'ix_user_email'):
        conn.execute(sa.text(f'DROP INDEX IF EXISTS "{index_name}"'))
    conn.execute(sa.text('DROP TABLE "user"'))
    conn.execute(sa.text('ALTER TABLE _new_user RENAME TO "user"'))
    conn.execute(sa.text(
        'CREATE UNIQUE INDEX ix_user_username ON "user" (username)'
    ))
    conn.execute(sa.text(
        'CREATE UNIQUE INDEX ix_user_email ON "user" (email)'
    ))
    conn.commit()


def _rebuild_empty_pending_registration_with_digest_otp(conn, sa):
    """Replace PendingRegistration while invalidating every legacy row."""
    conn.execute(sa.text('DROP TABLE IF EXISTS _new_pending_registration'))
    conn.execute(sa.text('''
        CREATE TABLE _new_pending_registration (
            id                           INTEGER NOT NULL PRIMARY KEY,
            token                        VARCHAR(64) NOT NULL,
            username                     VARCHAR(80) NOT NULL,
            email                        VARCHAR(120) NOT NULL,
            password_hash                VARCHAR(255) NOT NULL,
            verification_code            VARCHAR(64) NOT NULL,
            verification_code_expires_at DATETIME NOT NULL,
            failed_otp_attempts           INTEGER NOT NULL,
            created_at                   DATETIME NOT NULL,
            expires_at                   DATETIME NOT NULL
        )
    '''))
    for index_name in (
        'ix_pending_registration_token',
        'ix_pending_registration_username',
        'ix_pending_registration_email',
    ):
        conn.execute(sa.text(f'DROP INDEX IF EXISTS "{index_name}"'))
    conn.execute(sa.text('DROP TABLE pending_registration'))
    conn.execute(sa.text(
        'ALTER TABLE _new_pending_registration RENAME TO pending_registration'
    ))
    conn.execute(sa.text(
        'CREATE UNIQUE INDEX ix_pending_registration_token '
        'ON pending_registration (token)'
    ))
    conn.execute(sa.text(
        'CREATE UNIQUE INDEX ix_pending_registration_username '
        'ON pending_registration (username)'
    ))
    conn.execute(sa.text(
        'CREATE UNIQUE INDEX ix_pending_registration_email '
        'ON pending_registration (email)'
    ))
    conn.commit()


def _rebuild_tables(conn, sa, inspector, *, require_portfolio_cascades=False):
    """Rebuild legacy tables whose CREATE statements need a fresh schema.

    Idempotent: each table is inspected; if the existing schema already
    matches the desired shape (FKs correct AND no dropped columns still
    present), the rebuild is skipped. Caller must have FK enforcement
    disabled.
    """
    tables = set(inspector.get_table_names())

    # Each entry: (table_name,
    #              must_have_marker      — substring expected in correct CREATE,
    #              must_not_have_marker  — substring whose presence forces rebuild
    #                                      (e.g., dropped column name); None to ignore,
    #              CREATE statement for replacement,
    #              columns to copy,
    #              list of CREATE INDEX statements to apply afterwards).
    rebuilds = [
        (
            'transaction',
            'REFERENCES portfolio',
            None,
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
            None,
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
            None,
            '''
            CREATE TABLE _new_dividend (
                id           INTEGER NOT NULL PRIMARY KEY,
                portfolio_id INTEGER NOT NULL REFERENCES portfolio(id) ON DELETE CASCADE,
                symbol       VARCHAR(20) NOT NULL,
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
            None,
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
            'net_deposits',  # presence in the existing CREATE forces a rebuild
            '''
            CREATE TABLE _new_portfolio (
                id         INTEGER NOT NULL PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
                name       VARCHAR(50) NOT NULL,
                created_at DATETIME,
                updated_at DATETIME
            )
            ''',
            ['id', 'user_id', 'name', 'created_at', 'updated_at'],
            ['CREATE INDEX ix_portfolio_user_id ON portfolio (user_id)'],
        ),
    ]

    for table, must_have, must_not_have, create_sql, columns, indexes in rebuilds:
        if table not in tables:
            continue
        existing_sql = conn.execute(sa.text(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=:n"
        ), {'n': table}).scalar() or ''

        already_correct = (
            must_have in existing_sql
            and (must_not_have is None or must_not_have not in existing_sql)
        )
        if already_correct and require_portfolio_cascades:
            parent_table = 'user' if table == 'portfolio' else 'portfolio'
            fk_column = 'user_id' if table == 'portfolio' else 'portfolio_id'
            fk_rows = conn.execute(
                sa.text(f'PRAGMA foreign_key_list("{table}")')
            ).fetchall()
            already_correct = any(
                row[2] == parent_table
                and row[3] == fk_column
                and row[4] == 'id'
                and str(row[6]).upper() == 'CASCADE'
                for row in fk_rows
            )
        # dividend.symbol must be NOT NULL — substring matching whitespace
        # in the CREATE statement is too brittle, so consult PRAGMA directly.
        # PRAGMA table_info row layout: (cid, name, type, notnull, dflt, pk).
        if already_correct and table == 'dividend':
            for r in conn.execute(sa.text(f'PRAGMA table_info("{table}")')).fetchall():
                if r[1] == 'symbol' and r[3] == 0:
                    already_correct = False
                    break
        if already_correct:
            continue

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

