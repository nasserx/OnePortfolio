"""End-to-end replay of the pre-``portfolio`` schema eras.

The rename chain in Steps 1–20 (``capital`` → ``fund`` → ``portfolio``) had no
end-to-end coverage: every other migration test starts from version 29, 33, or
an empty database, where those steps are no-ops. That gap hid a real defect —
one long-lived SQLAlchemy ``Inspector`` was shared across the whole pass, and
because it memoizes reflection results, a step's precondition was answered with
the schema as it looked *before* the earlier steps' DDL. A ``capital``-era
database failed on every boot forever; a ``fund``-era one needed two.

These tests build genuine legacy databases, boot the application against them,
and assert the whole chain converges in a single startup with the owned rows
intact.
"""

from pathlib import Path
import sqlite3

from config import Config
from portfolio_app import create_app, db
from portfolio_app.migrations import TARGET_SCHEMA_VERSION
import sqlalchemy as sa
from sqlalchemy import text


# The ``user`` table as it stood alongside the capital/fund era: before the
# auth refactor added its columns, and while ``is_admin`` still existed.
_LEGACY_USER_DDL = '''
    CREATE TABLE "user" (
        id            INTEGER NOT NULL PRIMARY KEY,
        username      VARCHAR(80) NOT NULL,
        email         VARCHAR(120),
        password_hash VARCHAR(255) NOT NULL,
        is_admin      BOOLEAN NOT NULL DEFAULT 0,
        is_verified   BOOLEAN NOT NULL DEFAULT 1,
        created_at    DATETIME,
        last_login    DATETIME
    );
    CREATE UNIQUE INDEX ix_user_username ON "user" (username);
    INSERT INTO "user" (id, username, email, password_hash, created_at)
        VALUES (1, 'legacy', 'legacy@example.com', 'hashed', '2023-01-01');
'''


def _create_capital_era_database(db_path, *, owned=True):
    """The oldest shape: ``capital``/``capital_event`` and ``capital_id`` FKs.

    ``owned`` mirrors the two real variants. A database that had already
    gained ``capital.user_id`` carries its rows through the rename chain; one
    that never did leaves them ownerless, and Step 22 purges them by design.
    """
    owner_column = ', user_id INTEGER' if owned else ''
    owner_value = ', 1' if owned else ''
    owner_name = ', user_id' if owned else ''

    con = sqlite3.connect(db_path)
    try:
        con.executescript(_LEGACY_USER_DDL + f'''
            CREATE TABLE capital (
                id         INTEGER NOT NULL PRIMARY KEY,
                category   VARCHAR(50) NOT NULL,
                amount     NUMERIC(15, 2),
                created_at DATETIME,
                updated_at DATETIME
                {owner_column}
            );
            CREATE TABLE capital_event (
                id               INTEGER NOT NULL PRIMARY KEY,
                capital_id       INTEGER NOT NULL REFERENCES capital(id),
                event_type       VARCHAR(20) NOT NULL,
                amount_usd_delta NUMERIC(15, 2) NOT NULL DEFAULT 0,
                date             DATETIME,
                notes            TEXT
            );
            CREATE TABLE "transaction" (
                id               INTEGER NOT NULL PRIMARY KEY,
                capital_id       INTEGER NOT NULL REFERENCES capital(id),
                transaction_type VARCHAR(10) NOT NULL,
                symbol           VARCHAR(20),
                price            NUMERIC(20, 10) NOT NULL,
                quantity         NUMERIC(20, 10) NOT NULL,
                fees             NUMERIC(20, 10) NOT NULL DEFAULT 0,
                total_cost       NUMERIC(20, 10) NOT NULL DEFAULT 0,
                average_cost     NUMERIC(20, 10) NOT NULL DEFAULT 0,
                date             DATETIME,
                notes            TEXT
            );
            CREATE TABLE asset (
                id         INTEGER NOT NULL PRIMARY KEY,
                capital_id INTEGER NOT NULL REFERENCES capital(id),
                symbol     VARCHAR(20) NOT NULL,
                created_at DATETIME,
                updated_at DATETIME
            );
            CREATE INDEX ix_asset_capital_symbol ON asset (capital_id, symbol);
            -- Pre-dates the per-symbol column that Step 8 adds.
            CREATE TABLE dividend (
                id         INTEGER NOT NULL PRIMARY KEY,
                capital_id INTEGER NOT NULL REFERENCES capital(id),
                amount     NUMERIC(20, 10) NOT NULL,
                date       DATETIME NOT NULL,
                notes      TEXT,
                created_at DATETIME NOT NULL
            );

            INSERT INTO capital (id, category, amount, created_at{owner_name})
                VALUES (1, 'Stocks', 5000, '2024-01-01'{owner_value});
            INSERT INTO capital_event
                (id, capital_id, event_type, amount_usd_delta, date, notes)
                VALUES (1, 1, 'Deposit', 5000, '2024-01-01', 'seed capital');
            INSERT INTO "transaction"
                (id, capital_id, transaction_type, symbol, price, quantity,
                 fees, total_cost, average_cost, date, notes)
                VALUES (1, 1, 'Buy', 'AAPL', 100, 10, 0, 1000, 100,
                        '2024-01-02', 'opening buy');
            INSERT INTO asset (id, capital_id, symbol, created_at)
                VALUES (1, 1, 'AAPL', '2024-01-02');
            INSERT INTO dividend (id, capital_id, amount, date, notes, created_at)
                VALUES (1, 1, 75, '2024-01-04', 'unattributed', '2024-01-04');

            PRAGMA user_version = 0;
        ''')
        con.commit()
    finally:
        con.close()


def _create_fund_era_database(db_path):
    """The middle shape: ``fund``/``fund_event`` and ``fund_id`` FKs."""
    con = sqlite3.connect(db_path)
    try:
        con.executescript(_LEGACY_USER_DDL + '''
            CREATE TABLE fund (
                id           INTEGER NOT NULL PRIMARY KEY,
                asset_class  VARCHAR(50) NOT NULL,
                cash_balance NUMERIC(15, 2),
                created_at   DATETIME,
                updated_at   DATETIME,
                user_id      INTEGER REFERENCES "user"(id)
            );
            CREATE TABLE fund_event (
                id           INTEGER NOT NULL PRIMARY KEY,
                fund_id      INTEGER NOT NULL REFERENCES fund(id),
                event_type   VARCHAR(20) NOT NULL,
                amount_delta NUMERIC(15, 2) NOT NULL DEFAULT 0,
                date         DATETIME,
                notes        TEXT
            );
            CREATE TABLE "transaction" (
                id               INTEGER NOT NULL PRIMARY KEY,
                fund_id          INTEGER NOT NULL REFERENCES fund(id),
                transaction_type VARCHAR(10) NOT NULL,
                symbol           VARCHAR(20),
                price            NUMERIC(20, 10) NOT NULL,
                quantity         NUMERIC(20, 10) NOT NULL,
                fees             NUMERIC(20, 10) NOT NULL DEFAULT 0,
                net_amount       NUMERIC(20, 10) NOT NULL DEFAULT 0,
                average_cost     NUMERIC(20, 10) NOT NULL DEFAULT 0,
                date             DATETIME,
                notes            TEXT
            );
            CREATE TABLE asset (
                id         INTEGER NOT NULL PRIMARY KEY,
                fund_id    INTEGER NOT NULL REFERENCES fund(id),
                symbol     VARCHAR(20) NOT NULL,
                created_at DATETIME,
                updated_at DATETIME
            );
            CREATE INDEX ix_asset_fund_symbol ON asset (fund_id, symbol);
            CREATE TABLE dividend (
                id         INTEGER NOT NULL PRIMARY KEY,
                fund_id    INTEGER NOT NULL REFERENCES fund(id),
                symbol     VARCHAR(20),
                amount     NUMERIC(20, 10) NOT NULL,
                date       DATETIME NOT NULL,
                notes      TEXT,
                created_at DATETIME NOT NULL
            );

            INSERT INTO fund
                (id, asset_class, cash_balance, created_at, user_id)
                VALUES (1, 'Stocks', 5000, '2024-01-01', 1);
            INSERT INTO fund_event
                (id, fund_id, event_type, amount_delta, date, notes)
                VALUES (1, 1, 'Deposit', 5000, '2024-01-01', 'seed capital');
            INSERT INTO "transaction"
                (id, fund_id, transaction_type, symbol, price, quantity,
                 fees, net_amount, average_cost, date, notes)
                VALUES (1, 1, 'Buy', 'AAPL', 100, 10, 0, 1000, 100,
                        '2024-01-02', 'opening buy');
            INSERT INTO asset (id, fund_id, symbol, created_at)
                VALUES (1, 1, 'AAPL', '2024-01-02');
            INSERT INTO dividend
                (id, fund_id, symbol, amount, date, notes, created_at)
                VALUES (1, 1, 'AAPL', 75, '2024-01-04', 'q1', '2024-01-04');

            PRAGMA user_version = 0;
        ''')
        con.commit()
    finally:
        con.close()


def _sqlite_uri(path: Path) -> str:
    return f"sqlite:///{path.resolve().as_posix()}"


def _config_for(db_path: Path):
    class _LegacyReplayConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        SECRET_KEY = 'test-secret-key'
        MAIL_SUPPRESS_SEND = True
        RATELIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = _sqlite_uri(db_path)

    return _LegacyReplayConfig


def _scalar(app, statement):
    with app.app_context():
        return db.session.execute(text(statement)).scalar()


def _rows(app, statement):
    with app.app_context():
        return [tuple(row) for row in db.session.execute(text(statement))]


def _table_names(app):
    return {
        row[0]
        for row in _rows(app, "SELECT name FROM sqlite_master WHERE type='table'")
    }


def _foreign_key_contract(app, table_name):
    return tuple(sorted(
        (row[3], row[2], row[6].upper())
        for row in _rows(app, f'PRAGMA foreign_key_list("{table_name}")')
    ))


def _assert_database_is_sound(app):
    assert _rows(app, 'PRAGMA foreign_key_check') == []
    assert _scalar(app, 'PRAGMA integrity_check') == 'ok'


# ---------------------------------------------------------------------------
# capital era
# ---------------------------------------------------------------------------

def test_capital_era_database_reaches_target_version_in_one_boot(tmp_path):
    db_path = tmp_path / 'capital-era.sqlite'
    _create_capital_era_database(db_path)

    app = create_app(_config_for(db_path))

    assert _scalar(app, 'PRAGMA user_version') == TARGET_SCHEMA_VERSION
    names = _table_names(app)
    assert {'portfolio', 'portfolio_event', 'transaction', 'symbol',
            'dividend', 'user'}.issubset(names)
    # Every legacy name is gone, including the closed_trade snapshot table
    # that Step 11 creates on the way through and Step 23 drops.
    assert names.isdisjoint(
        {'capital', 'capital_event', 'fund', 'fund_event', 'asset',
         'closed_trade'}
    )
    _assert_database_is_sound(app)


def test_capital_era_replay_carries_every_owned_row_through_the_renames(tmp_path):
    db_path = tmp_path / 'capital-era-rows.sqlite'
    _create_capital_era_database(db_path)

    app = create_app(_config_for(db_path))

    assert _rows(app, 'SELECT id, username, email FROM "user"') == [
        (1, 'legacy', 'legacy@example.com'),
    ]
    # capital.category → asset_class → name; capital.id kept.
    assert _rows(app, 'SELECT id, user_id, name FROM portfolio') == [
        (1, 1, 'Stocks'),
    ]
    # capital_event.amount_usd_delta → amount_delta, capital_id → portfolio_id.
    assert _rows(
        app,
        'SELECT id, portfolio_id, event_type, amount_delta, notes '
        'FROM portfolio_event',
    ) == [(1, 1, 'Deposit', 5000, 'seed capital')]
    # transaction.total_cost → net_amount, capital_id → portfolio_id.
    assert _rows(
        app,
        'SELECT id, portfolio_id, transaction_type, symbol, price, quantity, '
        'net_amount, average_cost, notes FROM "transaction"',
    ) == [(1, 1, 'Buy', 'AAPL', 100, 10, 1000, 100, 'opening buy')]
    # asset → symbol, capital_id → portfolio_id.
    assert _rows(app, 'SELECT id, portfolio_id, symbol FROM symbol') == [
        (1, 1, 'AAPL'),
    ]
    # The one deliberate deletion: this era's dividends carry no symbol, and
    # Step 25 purges them so Step 24 can rebuild the table with symbol NOT
    # NULL. Asserted so the intent stays explicit rather than incidental.
    assert _rows(app, 'SELECT COUNT(*) FROM dividend') == [(0,)]


def test_capital_era_without_an_owner_purges_orphans_and_still_converges(tmp_path):
    """Step 22's documented purge, on a database that never had user_id."""
    db_path = tmp_path / 'capital-era-ownerless.sqlite'
    _create_capital_era_database(db_path, owned=False)

    app = create_app(_config_for(db_path))

    assert _scalar(app, 'PRAGMA user_version') == TARGET_SCHEMA_VERSION
    assert _rows(app, 'SELECT id, username FROM "user"') == [(1, 'legacy')]
    for table_name in ('portfolio', 'portfolio_event', 'transaction',
                       'symbol', 'dividend'):
        assert _rows(app, f'SELECT COUNT(*) FROM "{table_name}"') == [(0,)], (
            f'{table_name} still holds rows from an ownerless portfolio'
        )
    _assert_database_is_sound(app)


def test_capital_era_second_boot_changes_nothing(tmp_path):
    db_path = tmp_path / 'capital-era-replay.sqlite'
    _create_capital_era_database(db_path)

    first = create_app(_config_for(db_path))
    after_first = {
        table: _rows(first, f'SELECT * FROM "{table}" ORDER BY id')
        for table in ('user', 'portfolio', 'portfolio_event', 'transaction',
                      'symbol')
    }
    schema_after_first = _rows(
        first, "SELECT type, name, sql FROM sqlite_master ORDER BY type, name")

    second = create_app(_config_for(db_path))

    assert _scalar(second, 'PRAGMA user_version') == TARGET_SCHEMA_VERSION
    for table, expected in after_first.items():
        assert _rows(
            second, f'SELECT * FROM "{table}" ORDER BY id') == expected, table
    assert _rows(
        second, "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
    ) == schema_after_first
    _assert_database_is_sound(second)


# ---------------------------------------------------------------------------
# fund era
# ---------------------------------------------------------------------------

def test_fund_era_database_reaches_target_version_in_one_boot(tmp_path):
    db_path = tmp_path / 'fund-era.sqlite'
    _create_fund_era_database(db_path)

    app = create_app(_config_for(db_path))

    assert _scalar(app, 'PRAGMA user_version') == TARGET_SCHEMA_VERSION
    names = _table_names(app)
    assert {'portfolio', 'portfolio_event', 'transaction', 'symbol',
            'dividend'}.issubset(names)
    assert names.isdisjoint(
        {'capital', 'capital_event', 'fund', 'fund_event', 'asset',
         'closed_trade'}
    )
    _assert_database_is_sound(app)


def test_fund_era_replay_carries_every_owned_row_through_the_renames(tmp_path):
    db_path = tmp_path / 'fund-era-rows.sqlite'
    _create_fund_era_database(db_path)

    app = create_app(_config_for(db_path))

    assert _rows(app, 'SELECT id, user_id, name FROM portfolio') == [
        (1, 1, 'Stocks'),
    ]
    assert _rows(
        app,
        'SELECT id, portfolio_id, event_type, amount_delta, notes '
        'FROM portfolio_event',
    ) == [(1, 1, 'Deposit', 5000, 'seed capital')]
    assert _rows(
        app,
        'SELECT id, portfolio_id, transaction_type, symbol, price, quantity, '
        'net_amount, average_cost, notes FROM "transaction"',
    ) == [(1, 1, 'Buy', 'AAPL', 100, 10, 1000, 100, 'opening buy')]
    assert _rows(app, 'SELECT id, portfolio_id, symbol FROM symbol') == [
        (1, 1, 'AAPL'),
    ]
    # This era already had the per-symbol column, so the income row survives.
    assert _rows(
        app, 'SELECT id, portfolio_id, symbol, amount, notes FROM dividend'
    ) == [(1, 1, 'AAPL', 75, 'q1')]


def test_fund_era_second_boot_changes_nothing(tmp_path):
    db_path = tmp_path / 'fund-era-replay.sqlite'
    _create_fund_era_database(db_path)

    first = create_app(_config_for(db_path))
    after_first = {
        table: _rows(first, f'SELECT * FROM "{table}" ORDER BY id')
        for table in ('user', 'portfolio', 'portfolio_event', 'transaction',
                      'symbol', 'dividend')
    }
    schema_after_first = _rows(
        first, "SELECT type, name, sql FROM sqlite_master ORDER BY type, name")

    second = create_app(_config_for(db_path))

    assert _scalar(second, 'PRAGMA user_version') == TARGET_SCHEMA_VERSION
    for table, expected in after_first.items():
        assert _rows(
            second, f'SELECT * FROM "{table}" ORDER BY id') == expected, table
    assert _rows(
        second, "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
    ) == schema_after_first
    _assert_database_is_sound(second)


# ---------------------------------------------------------------------------
# parity with a fresh install, and the reflection contract itself
# ---------------------------------------------------------------------------

def test_every_era_lands_on_the_fresh_installs_cascade_contract(tmp_path):
    capital_path = tmp_path / 'parity-capital.sqlite'
    fund_path = tmp_path / 'parity-fund.sqlite'
    _create_capital_era_database(capital_path)
    _create_fund_era_database(fund_path)

    fresh = create_app(_config_for(tmp_path / 'parity-fresh.sqlite'))
    upgraded = [
        create_app(_config_for(capital_path)),
        create_app(_config_for(fund_path)),
    ]

    for table_name in ('portfolio', 'portfolio_event', 'transaction',
                       'symbol', 'dividend'):
        expected = _foreign_key_contract(fresh, table_name)
        assert expected, f'{table_name} declares no foreign key on a fresh install'
        for app in upgraded:
            assert _foreign_key_contract(app, table_name) == expected, table_name


def test_reflection_used_by_the_migration_pass_never_goes_stale(tmp_path):
    """The contract the rename chain depends on, asserted directly.

    A plain ``sa.inspect(conn)`` memoizes; the pass must not, or a step's
    precondition silently describes the schema as it was before the DDL that
    earlier steps already committed.
    """
    # Imported here rather than at module scope so the replay tests above
    # still collect and run against a build that predates this contract.
    from portfolio_app.migrations import _LiveInspector

    db_path = tmp_path / 'reflection.sqlite'
    engine = sa.create_engine(_sqlite_uri(db_path))
    with engine.connect() as conn:
        conn.exec_driver_sql('CREATE TABLE legacy (id INTEGER, capital_id INTEGER)')
        conn.commit()

        cached = sa.inspect(conn)
        live = _LiveInspector(conn, sa)

        # Prime both the way the pass does: an early step reads the table
        # before a later step renames anything.
        assert 'legacy' in cached.get_table_names()
        assert [c['name'] for c in cached.get_columns('legacy')] == ['id', 'capital_id']
        assert 'legacy' in live.get_table_names()
        assert [c['name'] for c in live.get_columns('legacy')] == ['id', 'capital_id']

        conn.exec_driver_sql('ALTER TABLE legacy RENAME COLUMN capital_id TO fund_id')
        conn.commit()

        # What the old shared-inspector pass saw, and why later steps whose
        # preconditions depended on this rename silently stopped firing.
        assert [c['name'] for c in cached.get_columns('legacy')] == ['id', 'capital_id']
        assert [c['name'] for c in live.get_columns('legacy')] == ['id', 'fund_id']

        conn.exec_driver_sql('ALTER TABLE legacy RENAME TO renamed')
        conn.commit()

        assert cached.get_table_names() == ['legacy']
        assert live.get_table_names() == ['renamed']
    engine.dispose()
