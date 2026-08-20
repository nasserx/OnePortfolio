from pathlib import Path
import sqlite3

from config import Config
from portfolio_app import create_app, db
from portfolio_app.migrations import TARGET_SCHEMA_VERSION
from portfolio_app.models.oauth_identity import OAuthIdentity
from portfolio_app.models.portfolio import Portfolio
from portfolio_app.models.user import User
import pytest
import sqlalchemy as sa
from sqlalchemy import text


_PORTFOLIO_CHILD_TABLES = (
    'transaction',
    'symbol',
    'dividend',
    'portfolio_event',
)


def _foreign_key_contract(app, table_name):
    with app.app_context():
        return tuple(sorted(
            (row[3], row[2], row[4], row[5].upper(), row[6].upper())
            for row in db.session.execute(
                text(f'PRAGMA foreign_key_list("{table_name}")')
            ).fetchall()
        ))


def _create_version_33_no_action_database(db_path):
    """Create the pre-fix current schema with non-cascading child FKs."""
    con = sqlite3.connect(db_path)
    try:
        con.executescript('''
            PRAGMA foreign_keys = ON;
            CREATE TABLE "user" (
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
            );
            CREATE UNIQUE INDEX ix_user_username ON "user" (username);
            CREATE UNIQUE INDEX ix_user_email ON "user" (email);
            CREATE TABLE pending_registration (
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
            );
            CREATE UNIQUE INDEX ix_pending_registration_token
                ON pending_registration (token);
            CREATE UNIQUE INDEX ix_pending_registration_username
                ON pending_registration (username);
            CREATE UNIQUE INDEX ix_pending_registration_email
                ON pending_registration (email);
            CREATE TABLE portfolio (
                id         INTEGER NOT NULL PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
                name       VARCHAR(50) NOT NULL,
                created_at DATETIME,
                updated_at DATETIME
            );
            CREATE INDEX ix_portfolio_user_id ON portfolio (user_id);
            CREATE TABLE "transaction" (
                id               INTEGER NOT NULL PRIMARY KEY,
                portfolio_id     INTEGER NOT NULL REFERENCES portfolio(id),
                transaction_type VARCHAR(10) NOT NULL,
                symbol           VARCHAR(20),
                price            NUMERIC(20, 10) NOT NULL,
                quantity         NUMERIC(20, 10) NOT NULL,
                fees             NUMERIC(20, 10) NOT NULL DEFAULT 0,
                net_amount       NUMERIC(20, 10) NOT NULL DEFAULT 0,
                average_cost     NUMERIC(20, 10) NOT NULL DEFAULT 0,
                date             DATETIME,
                notes            TEXT,
                CONSTRAINT check_price_positive CHECK (price > 0),
                CONSTRAINT check_quantity_positive CHECK (quantity > 0),
                CONSTRAINT check_fees_non_negative CHECK (fees >= 0),
                CONSTRAINT check_net_amount_non_negative CHECK (net_amount >= 0)
            );
            CREATE TABLE symbol (
                id           INTEGER NOT NULL PRIMARY KEY,
                portfolio_id INTEGER NOT NULL REFERENCES portfolio(id),
                symbol       VARCHAR(20) NOT NULL,
                created_at   DATETIME,
                updated_at   DATETIME,
                CONSTRAINT uq_symbol_portfolio_ticker UNIQUE (portfolio_id, symbol)
            );
            CREATE INDEX ix_symbol_portfolio_ticker ON symbol (portfolio_id, symbol);
            CREATE TABLE dividend (
                id           INTEGER NOT NULL PRIMARY KEY,
                portfolio_id INTEGER NOT NULL REFERENCES portfolio(id),
                symbol       VARCHAR(20) NOT NULL,
                amount       NUMERIC(20, 10) NOT NULL,
                date         DATETIME NOT NULL,
                notes        TEXT,
                created_at   DATETIME NOT NULL,
                CONSTRAINT check_dividend_amount_positive CHECK (amount > 0)
            );
            CREATE TABLE portfolio_event (
                id           INTEGER NOT NULL PRIMARY KEY,
                portfolio_id INTEGER NOT NULL REFERENCES portfolio(id),
                event_type   VARCHAR(20) NOT NULL,
                amount_delta NUMERIC(15, 2) NOT NULL DEFAULT 0,
                date         DATETIME,
                notes        TEXT
            );
            CREATE INDEX ix_portfolio_event_portfolio_date
                ON portfolio_event (portfolio_id, date);
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
            );
            CREATE INDEX ix_oauth_identity_user_id ON oauth_identity (user_id);
            INSERT INTO "user" VALUES (
                41, 'cascade-owner', 'cascade@example.com', 'preserved-hash', 1,
                '2026-01-01 00:00:00', NULL, NULL, NULL, 0, NULL, NULL, NULL,
                0, 0, NULL, NULL, 3
            );
            INSERT INTO portfolio VALUES (
                51, 41, 'Preserved Portfolio',
                '2026-01-02 00:00:00', '2026-01-03 00:00:00'
            );
            INSERT INTO "transaction" VALUES (
                61, 51, 'Buy', 'AAPL', 100, 2, 1, 201, 100.5,
                '2026-01-04 00:00:00', 'preserved transaction'
            );
            INSERT INTO symbol VALUES (
                62, 51, 'AAPL', '2026-01-03 00:00:00', '2026-01-04 00:00:00'
            );
            INSERT INTO dividend VALUES (
                63, 51, 'AAPL', 25, '2026-01-05 00:00:00',
                'preserved income', '2026-01-05 00:00:00'
            );
            INSERT INTO portfolio_event VALUES (
                64, 51, 'Deposit', 1000, '2026-01-02 00:00:00',
                'preserved capital event'
            );
            PRAGMA user_version = 33;
        ''')
        con.commit()
    finally:
        con.close()


def _sqlite_uri(path: Path) -> str:
    return f"sqlite:///{path.resolve().as_posix()}"


def _config_for(db_path: Path):
    class _MigrationTestConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        SECRET_KEY = 'test-secret-key'
        MAIL_SUPPRESS_SEND = True
        RATELIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = _sqlite_uri(db_path)

    return _MigrationTestConfig


def _table_names(app):
    with app.app_context():
        return {
            row[0]
            for row in db.session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }


def _pragma_scalar(app, pragma_name):
    with app.app_context():
        return db.session.execute(text(f'PRAGMA {pragma_name}')).scalar()


def _table_column_contract(app, table_name):
    with app.app_context():
        return tuple(
            (row[1], row[2].upper(), row[3], row[4], row[5])
            for row in db.session.execute(
                text(f'PRAGMA table_info("{table_name}")')
            ).fetchall()
        )


def _table_index_contract(app, table_name):
    with app.app_context():
        indexes = db.session.execute(
            text(f'PRAGMA index_list("{table_name}")')
        ).fetchall()
        return sorted(
            (
                index[2],
                tuple(
                    row[2]
                    for row in db.session.execute(
                        text(f'PRAGMA index_info("{index[1]}")')
                    ).fetchall()
                ),
            )
            for index in indexes
        )


def _table_rows(app, table_name):
    with app.app_context():
        return tuple(db.session.execute(
            text(f'SELECT * FROM "{table_name}" ORDER BY id')
        ).fetchall())


def test_fresh_database_startup_creates_schema_and_sets_user_version(tmp_path):
    db_path = tmp_path / 'fresh.sqlite'
    app = create_app(_config_for(db_path))

    assert db_path.exists()
    assert {
        'user',
        'pending_registration',
        'portfolio',
        'portfolio_event',
        'transaction',
        'symbol',
        'dividend',
        'oauth_identity',
        'auth_challenge',
    }.issubset(_table_names(app))
    assert _pragma_scalar(app, 'user_version') == TARGET_SCHEMA_VERSION

    with app.app_context():
        columns = {
            row[1]: row
            for row in db.session.execute(text('PRAGMA table_info("user")')).fetchall()
        }
        auth_generation = columns['auth_generation']
        assert auth_generation[2].upper() == 'INTEGER'
        assert auth_generation[3] == 1
        assert auth_generation[4] == '0'
        assert 'is_admin' not in columns
        assert columns['verification_code'][2].upper() == 'VARCHAR(64)'
        assert columns['deletion_code'][2].upper() == 'VARCHAR(64)'
        pending_columns = {
            row[1]: row
            for row in db.session.execute(
                text('PRAGMA table_info(pending_registration)')
            ).fetchall()
        }
        assert set(pending_columns) == {
            'id', 'username', 'email', 'created_at', 'expires_at',
        }
        assert columns['password_hash'][3] == 0


def test_fresh_schema_uses_database_cascades_for_all_ownership_foreign_keys(tmp_path):
    app = create_app(_config_for(tmp_path / 'fresh-cascades.sqlite'))

    assert TARGET_SCHEMA_VERSION == 35
    assert _foreign_key_contract(app, 'portfolio') == (
        ('user_id', 'user', 'id', 'NO ACTION', 'CASCADE'),
    )
    assert _foreign_key_contract(app, 'oauth_identity') == (
        ('user_id', 'user', 'id', 'NO ACTION', 'CASCADE'),
    )
    for table_name in _PORTFOLIO_CHILD_TABLES:
        assert _foreign_key_contract(app, table_name) == (
            ('portfolio_id', 'portfolio', 'id', 'NO ACTION', 'CASCADE'),
        )


def test_version_33_no_action_schema_upgrades_to_fresh_fk_parity_and_preserves_data(
    tmp_path,
):
    upgraded_path = tmp_path / 'version-33-no-action.sqlite'
    _create_version_33_no_action_database(upgraded_path)

    upgraded_app = create_app(_config_for(upgraded_path))
    fresh_app = create_app(_config_for(tmp_path / 'fresh-parity.sqlite'))

    assert _pragma_scalar(upgraded_app, 'user_version') == TARGET_SCHEMA_VERSION
    for table_name in ('portfolio', *_PORTFOLIO_CHILD_TABLES):
        assert _foreign_key_contract(upgraded_app, table_name) == (
            _foreign_key_contract(fresh_app, table_name)
        )
        assert _table_index_contract(upgraded_app, table_name) == (
            _table_index_contract(fresh_app, table_name)
        )

    assert _table_rows(upgraded_app, 'portfolio')[0][:3] == (
        51, 41, 'Preserved Portfolio',
    )
    assert _table_rows(upgraded_app, 'transaction')[0][:7] == (
        61, 51, 'Buy', 'AAPL', 100, 2, 1,
    )
    assert _table_rows(upgraded_app, 'symbol')[0][:3] == (62, 51, 'AAPL')
    assert _table_rows(upgraded_app, 'dividend')[0][:5] == (
        63, 51, 'AAPL', 25, '2026-01-05 00:00:00',
    )
    assert _table_rows(upgraded_app, 'portfolio_event')[0][:5] == (
        64, 51, 'Deposit', 1000, '2026-01-02 00:00:00',
    )
    with upgraded_app.app_context():
        assert db.session.execute(text('PRAGMA foreign_key_check')).fetchall() == []


def test_upgraded_schema_cascades_raw_portfolio_delete_to_every_owned_table(tmp_path):
    upgraded_path = tmp_path / 'version-33-cascade-behavior.sqlite'
    _create_version_33_no_action_database(upgraded_path)
    app = create_app(_config_for(upgraded_path))

    with app.app_context():
        db.session.execute(text('DELETE FROM portfolio WHERE id = 51'))
        db.session.commit()

        assert db.session.execute(text('SELECT COUNT(*) FROM "user"')).scalar() == 1
        for table_name in _PORTFOLIO_CHILD_TABLES:
            assert db.session.execute(
                text(f'SELECT COUNT(*) FROM "{table_name}"')
            ).scalar() == 0
        assert db.session.execute(text('PRAGMA foreign_key_check')).fetchall() == []


def test_cascade_repair_replay_is_idempotent_and_preserves_current_data(tmp_path):
    upgraded_path = tmp_path / 'cascade-replay.sqlite'
    _create_version_33_no_action_database(upgraded_path)
    first_app = create_app(_config_for(upgraded_path))

    tables = ('user', 'portfolio', *_PORTFOLIO_CHILD_TABLES)
    rows_before = {table: _table_rows(first_app, table) for table in tables}
    with first_app.app_context():
        db.session.execute(text('PRAGMA user_version = 33'))
        db.session.commit()
        db.session.remove()

    replayed_app = create_app(_config_for(upgraded_path))

    assert _pragma_scalar(replayed_app, 'user_version') == TARGET_SCHEMA_VERSION
    assert {
        table: _table_rows(replayed_app, table) for table in tables
    } == rows_before
    for table_name in _PORTFOLIO_CHILD_TABLES:
        assert _foreign_key_contract(replayed_app, table_name) == (
            ('portfolio_id', 'portfolio', 'id', 'NO ACTION', 'CASCADE'),
        )
    with replayed_app.app_context():
        assert db.session.execute(text('PRAGMA foreign_key_check')).fetchall() == []


def test_warm_startup_is_idempotent_and_preserves_existing_data(tmp_path):
    db_path = tmp_path / 'warm.sqlite'
    first_app = create_app(_config_for(db_path))

    with first_app.app_context():
        user = User(username='warm', email='warm@example.com', is_verified=True)
        user.password_hash = 'legacy-test-hash'
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        db.session.remove()

    second_app = create_app(_config_for(db_path))

    with second_app.app_context():
        assert db.session.get(User, user_id).email == 'warm@example.com'
        portfolio = Portfolio(user_id=user_id, name='Warm Portfolio')
        db.session.add(portfolio)
        db.session.commit()
        assert Portfolio.query.filter_by(user_id=user_id).count() == 1
        assert db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='oauth_identity'")
        ).scalar() == 'oauth_identity'
        assert db.session.execute(text('PRAGMA user_version')).scalar() == TARGET_SCHEMA_VERSION


def test_sqlite_foreign_keys_are_on_after_startup(tmp_path):
    app = create_app(_config_for(tmp_path / 'foreign_keys.sqlite'))

    assert _pragma_scalar(app, 'foreign_keys') == 1


def test_failed_migration_rolls_back_restores_foreign_keys_and_can_retry(
    tmp_path,
    monkeypatch,
):
    import portfolio_app.migrations as migrations

    app = create_app(_config_for(tmp_path / 'failed-migration-retry.sqlite'))
    with app.app_context():
        user = User(
            username='migration-original',
            email='migration-original@example.com',
            is_verified=True,
        )
        user.password_hash = 'legacy-test-hash'
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        db.session.execute(text('PRAGMA user_version = 33'))
        db.session.commit()
        db.session.remove()

    original_apply_migration_steps = migrations._apply_migration_steps

    def _write_then_fail(conn, sa_module):
        conn.execute(
            sa_module.text(
                'UPDATE "user" SET username = :username WHERE id = :user_id'
            ),
            {'username': 'migration-should-rollback', 'user_id': user_id},
        )
        raise RuntimeError('injected migration failure')

    monkeypatch.setattr(
        migrations,
        '_apply_migration_steps',
        _write_then_fail,
    )

    with pytest.raises(RuntimeError, match='injected migration failure'):
        migrations.run_startup_schema(app)

    with app.app_context():
        with db.engine.connect() as conn:
            assert conn.exec_driver_sql('PRAGMA user_version').scalar() == 33
            assert conn.exec_driver_sql('PRAGMA foreign_keys').scalar() == 1
            assert conn.execute(
                text('SELECT username FROM "user" WHERE id = :user_id'),
                {'user_id': user_id},
            ).scalar_one() == 'migration-original'

    monkeypatch.setattr(
        migrations,
        '_apply_migration_steps',
        original_apply_migration_steps,
    )
    migrations.run_startup_schema(app)

    with app.app_context():
        with db.engine.connect() as conn:
            assert conn.exec_driver_sql(
                'PRAGMA user_version'
            ).scalar() == TARGET_SCHEMA_VERSION
            assert conn.exec_driver_sql('PRAGMA foreign_keys').scalar() == 1
            assert conn.execute(
                text('SELECT username FROM "user" WHERE id = :user_id'),
                {'user_id': user_id},
            ).scalar_one() == 'migration-original'


def test_application_factory_runs_migrations_before_create_all(tmp_path, monkeypatch):
    """Ordering holds inside the startup schema lock that now spans both."""
    import portfolio_app.migrations as migrations

    order = []
    original_migration_pass = migrations._run_migration_pass
    original_create_all = db.create_all

    def _recording_migration_pass(app):
        order.append('migrations')
        return original_migration_pass(app)

    def _recording_create_all(*args, **kwargs):
        order.append('create_all')
        return original_create_all(*args, **kwargs)

    monkeypatch.setattr(migrations, '_run_migration_pass', _recording_migration_pass)
    monkeypatch.setattr(db, 'create_all', _recording_create_all)

    db_path = tmp_path / 'ordering.sqlite'
    create_app(_config_for(db_path))

    assert order == ['migrations', 'create_all']
    repo_tests_dir = Path(__file__).resolve().parent
    assert repo_tests_dir.resolve() not in db_path.resolve().parents


def _index_columns(app, table_name):
    with app.app_context():
        indexes = db.session.execute(text(f'PRAGMA index_list({table_name})')).fetchall()
        result = {}
        for index in indexes:
            index_name = index[1]
            is_unique = index[2] == 1
            columns = tuple(
                row[2]
                for row in db.session.execute(
                    text(f'PRAGMA index_info("{index_name}")')
                ).fetchall()
            )
            result[index_name] = {'unique': is_unique, 'columns': columns}
        return result


def test_oauth_identity_migration_creates_required_unique_constraints(tmp_path):
    app = create_app(_config_for(tmp_path / 'oauth-identity.sqlite'))

    indexes = _index_columns(app, 'oauth_identity')

    assert any(
        index['unique'] and index['columns'] == ('provider', 'provider_subject')
        for index in indexes.values()
    )
    assert any(
        index['unique'] and index['columns'] == ('user_id', 'provider')
        for index in indexes.values()
    )


def test_oauth_identity_migration_is_idempotent_and_preserves_existing_users(tmp_path):
    db_path = tmp_path / 'oauth-identity-idempotent.sqlite'
    first_app = create_app(_config_for(db_path))

    with first_app.app_context():
        user = User(username='linked', email='linked@example.com', is_verified=True)
        user.password_hash = 'legacy-test-hash'
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        db.session.add(OAuthIdentity(
            user_id=user_id,
            provider='google',
            provider_subject='opaque-sub',
        ))
        db.session.commit()
        db.session.remove()

    second_app = create_app(_config_for(db_path))

    with second_app.app_context():
        assert db.session.get(User, user_id).email == 'linked@example.com'
        assert OAuthIdentity.query.filter_by(
            user_id=user_id,
            provider='google',
            provider_subject='opaque-sub',
        ).count() == 1
        assert db.session.execute(text('PRAGMA user_version')).scalar() == TARGET_SCHEMA_VERSION


def test_migration_repairs_version_29_pending_registration_missing_otp_counter(tmp_path):
    db_path = tmp_path / 'missing-pending-registration-otp-counter.sqlite'
    import sqlite3

    con = sqlite3.connect(db_path)
    try:
        con.executescript('''
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
            );
            INSERT INTO pending_registration (
                token,
                username,
                email,
                password_hash,
                verification_code,
                verification_code_expires_at,
                created_at,
                expires_at
            ) VALUES (
                'token',
                'pending',
                'pending@example.com',
                'hash',
                '123456',
                '2026-01-01 00:10:00',
                '2026-01-01 00:00:00',
                '2026-01-02 00:00:00'
            );
            PRAGMA user_version = 29;
        ''')
        con.commit()
    finally:
        con.close()

    app = create_app(_config_for(db_path))

    with app.app_context():
        columns = {
            row[1]: row
            for row in db.session.execute(
                text('PRAGMA table_info(pending_registration)')
            ).fetchall()
        }
        assert set(columns) == {
            'id', 'username', 'email', 'created_at', 'expires_at',
        }
        assert db.session.execute(text(
            'SELECT COUNT(*) FROM pending_registration'
        )).scalar() == 0
        assert db.session.execute(text('PRAGMA user_version')).scalar() == TARGET_SCHEMA_VERSION


def test_migration_adds_auth_generation_and_preserves_existing_user(tmp_path):
    db_path = tmp_path / 'auth-generation-upgrade.sqlite'
    import sqlite3

    con = sqlite3.connect(db_path)
    try:
        con.executescript('''
            CREATE TABLE "user" (
                id                                INTEGER PRIMARY KEY AUTOINCREMENT,
                username                          VARCHAR(80) NOT NULL UNIQUE,
                email                             VARCHAR(120) UNIQUE,
                password_hash                     VARCHAR(255) NOT NULL,
                is_admin                          BOOLEAN NOT NULL DEFAULT 0,
                is_verified                       BOOLEAN NOT NULL DEFAULT 0,
                created_at                        DATETIME,
                last_login                        DATETIME,
                verification_code                 VARCHAR(6),
                verification_code_expires_at      DATETIME,
                verification_code_failed_attempts INTEGER NOT NULL DEFAULT 0,
                pending_email                     VARCHAR(120),
                deletion_code                     VARCHAR(6),
                deletion_code_expires_at          DATETIME,
                deletion_code_failed_attempts     INTEGER NOT NULL DEFAULT 0,
                failed_login_attempts              INTEGER NOT NULL DEFAULT 0,
                locked_until                       DATETIME,
                password_reset_jti                 VARCHAR(32)
            );
            INSERT INTO "user" (
                username, email, password_hash, is_verified
            ) VALUES (
                'existing', 'existing@example.com', 'preserved-hash', 1
            );
            PRAGMA user_version = 30;
        ''')
        con.commit()
    finally:
        con.close()

    app = create_app(_config_for(db_path))

    with app.app_context():
        columns = {
            row[1]: row
            for row in db.session.execute(text('PRAGMA table_info("user")')).fetchall()
        }
        auth_generation = columns['auth_generation']
        assert auth_generation[2].upper() == 'INTEGER'
        assert auth_generation[3] == 1
        assert auth_generation[4] == '0'
        assert 'is_admin' not in columns

        user = User.query.filter_by(email='existing@example.com').one()
        assert user.password_hash == 'preserved-hash'
        assert user.auth_generation == 1
        user.auth_generation = 3
        db.session.commit()

    restarted_app = create_app(_config_for(db_path))
    with restarted_app.app_context():
        user = User.query.filter_by(email='existing@example.com').one()
        assert user.auth_generation == 3
        assert db.session.execute(text('PRAGMA user_version')).scalar() == TARGET_SCHEMA_VERSION


def test_migration_removes_legacy_admin_column_and_preserves_user_graph(tmp_path):
    import sqlite3

    upgraded_path = tmp_path / 'legacy-admin-upgrade.sqlite'
    con = sqlite3.connect(upgraded_path)
    try:
        con.executescript('''
            PRAGMA foreign_keys = ON;
            CREATE TABLE "user" (
                id                                INTEGER NOT NULL PRIMARY KEY,
                username                          VARCHAR(80) NOT NULL UNIQUE,
                email                             VARCHAR(120) UNIQUE,
                password_hash                     VARCHAR(255) NOT NULL,
                is_admin                          BOOLEAN NOT NULL DEFAULT 0,
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
            );
            CREATE INDEX ix_user_username ON "user" (username);
            CREATE INDEX ix_user_email ON "user" (email);
            CREATE TABLE portfolio (
                id         INTEGER NOT NULL PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
                name       VARCHAR(50) NOT NULL,
                created_at DATETIME,
                updated_at DATETIME
            );
            CREATE INDEX ix_portfolio_user_id ON portfolio (user_id);
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
            );
            CREATE INDEX ix_oauth_identity_user_id ON oauth_identity (user_id);
            INSERT INTO "user" VALUES (
                41, 'legacy-true', 'true@example.com', 'hash-true', 1, 1,
                '2026-01-01 01:02:03', '2026-02-01 02:03:04', '123456',
                '2026-03-01 03:04:05', 2, 'new-true@example.com', '654321',
                '2026-04-01 04:05:06', 3, 4, '2026-05-01 05:06:07',
                'jti-true', 7
            );
            INSERT INTO "user" VALUES (
                84, 'legacy-false', 'false@example.com', 'hash-false', 0, 0,
                '2025-01-01 01:02:03', NULL, NULL, NULL, 0, NULL, NULL,
                NULL, 0, 0, NULL, NULL, 0
            );
            INSERT INTO portfolio VALUES (
                501, 41, 'Preserved Portfolio',
                '2026-06-01 06:07:08', '2026-07-01 07:08:09'
            );
            INSERT INTO oauth_identity VALUES (
                601, 84, 'google', 'preserved-subject',
                '2026-08-01 08:09:10', '2026-08-02 09:10:11'
            );
            PRAGMA user_version = 31;
        ''')
        con.commit()
    finally:
        con.close()

    upgraded_app = create_app(_config_for(upgraded_path))

    with upgraded_app.app_context():
        columns = {
            row[1]
            for row in db.session.execute(text('PRAGMA table_info("user")'))
        }
        assert 'is_admin' not in columns
        assert db.session.execute(text('''
            SELECT id, username, email, password_hash, is_verified, created_at,
                   last_login, verification_code, verification_code_expires_at,
                   verification_code_failed_attempts, pending_email,
                   deletion_code, deletion_code_expires_at,
                   deletion_code_failed_attempts, failed_login_attempts,
                   locked_until, password_reset_jti, auth_generation
            FROM "user" ORDER BY id
        ''')).fetchall() == [
            (
                41, 'legacy-true', 'true@example.com', 'hash-true', 1,
                '2026-01-01 01:02:03', '2026-02-01 02:03:04', None,
                None, 0, None, None,
                None, 0, 4, '2026-05-01 05:06:07',
                'jti-true', 8,
            ),
            (
                84, 'legacy-false', 'false@example.com', 'hash-false', 0,
                '2025-01-01 01:02:03', None, None, None, 0, None, None,
                None, 0, 0, None, None, 1,
            ),
        ]
        assert db.session.execute(text(
            'SELECT id, user_id, name FROM portfolio'
        )).one() == (501, 41, 'Preserved Portfolio')
        assert db.session.execute(text('''
            SELECT id, user_id, provider, provider_subject FROM oauth_identity
        ''')).one() == (601, 84, 'google', 'preserved-subject')
        for child_table in ('portfolio', 'oauth_identity'):
            assert any(
                row[2] == 'user' and row[3] == 'user_id' and row[4] == 'id'
                for row in db.session.execute(
                    text(f'PRAGMA foreign_key_list("{child_table}")')
                ).fetchall()
            )
        assert db.session.execute(text('PRAGMA foreign_key_check')).fetchall() == []
        assert db.session.execute(text('PRAGMA foreign_keys')).scalar() == 1
        assert db.session.execute(text('PRAGMA user_version')).scalar() == TARGET_SCHEMA_VERSION

    fresh_app = create_app(_config_for(tmp_path / 'fresh-equivalent.sqlite'))
    assert _table_column_contract(upgraded_app, 'user') == _table_column_contract(
        fresh_app,
        'user',
    )
    assert _table_index_contract(upgraded_app, 'user') == _table_index_contract(
        fresh_app,
        'user',
    )


def test_migration_hardens_otp_columns_and_invalidates_legacy_state(tmp_path):
    import sqlite3

    assert TARGET_SCHEMA_VERSION == 35
    upgraded_path = tmp_path / 'legacy-otp-upgrade.sqlite'
    con = sqlite3.connect(upgraded_path)
    try:
        con.executescript('''
            PRAGMA foreign_keys = ON;
            CREATE TABLE "user" (
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
            );
            CREATE UNIQUE INDEX ix_user_username ON "user" (username);
            CREATE UNIQUE INDEX ix_user_email ON "user" (email);
            CREATE TABLE pending_registration (
                id                           INTEGER NOT NULL PRIMARY KEY,
                token                        VARCHAR(64) NOT NULL,
                username                     VARCHAR(80) NOT NULL,
                email                        VARCHAR(120) NOT NULL,
                password_hash                VARCHAR(255) NOT NULL,
                verification_code            VARCHAR(6) NOT NULL,
                verification_code_expires_at DATETIME NOT NULL,
                failed_otp_attempts           INTEGER NOT NULL,
                created_at                   DATETIME NOT NULL,
                expires_at                   DATETIME NOT NULL
            );
            CREATE UNIQUE INDEX ix_pending_registration_token
                ON pending_registration (token);
            CREATE UNIQUE INDEX ix_pending_registration_username
                ON pending_registration (username);
            CREATE UNIQUE INDEX ix_pending_registration_email
                ON pending_registration (email);
            CREATE TABLE portfolio (
                id         INTEGER NOT NULL PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
                name       VARCHAR(50) NOT NULL,
                created_at DATETIME,
                updated_at DATETIME
            );
            CREATE INDEX ix_portfolio_user_id ON portfolio (user_id);
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
            );
            CREATE INDEX ix_oauth_identity_user_id ON oauth_identity (user_id);
            INSERT INTO "user" VALUES (
                41, 'otp-user', 'otp@example.com', 'preserved-hash', 1,
                '2026-01-01 01:02:03', '2026-02-01 02:03:04', '123456',
                '2026-03-01 03:04:05', 2, 'new@example.com', '654321',
                '2026-04-01 04:05:06', 3, 4, '2026-05-01 05:06:07',
                'preserved-reset-jti', 7
            );
            INSERT INTO "user" VALUES (
                84, 'ordinary-user', 'ordinary@example.com', 'ordinary-hash', 0,
                '2025-01-01 01:02:03', NULL, NULL, NULL, 0, NULL, NULL,
                NULL, 0, 0, NULL, NULL, 0
            );
            INSERT INTO pending_registration VALUES (
                91, 'registration-token', 'pending-user', 'pending@example.com',
                'pending-hash', '112233', '2026-08-01 00:10:00', 2,
                '2026-08-01 00:00:00', '2026-08-02 00:00:00'
            );
            INSERT INTO portfolio VALUES (
                501, 41, 'Preserved Portfolio',
                '2026-06-01 06:07:08', '2026-07-01 07:08:09'
            );
            INSERT INTO oauth_identity VALUES (
                601, 84, 'google', 'preserved-subject',
                '2026-08-01 08:09:10', '2026-08-02 09:10:11'
            );
            PRAGMA user_version = 32;
        ''')
        con.commit()
    finally:
        con.close()

    upgraded_app = create_app(_config_for(upgraded_path))

    with upgraded_app.app_context():
        assert db.session.execute(text('PRAGMA user_version')).scalar() == TARGET_SCHEMA_VERSION
        assert db.session.execute(text(
            'SELECT COUNT(*) FROM pending_registration'
        )).scalar() == 0
        assert db.session.execute(text('''
            SELECT id, username, email, password_hash, is_verified, created_at,
                   last_login, verification_code, verification_code_expires_at,
                   verification_code_failed_attempts, pending_email,
                   deletion_code, deletion_code_expires_at,
                   deletion_code_failed_attempts, failed_login_attempts,
                   locked_until, password_reset_jti, auth_generation
            FROM "user" ORDER BY id
        ''')).fetchall() == [
            (
                41, 'otp-user', 'otp@example.com', 'preserved-hash', 1,
                '2026-01-01 01:02:03', '2026-02-01 02:03:04', None,
                None, 0, None, None, None, 0, 4,
                '2026-05-01 05:06:07', 'preserved-reset-jti', 8,
            ),
            (
                84, 'ordinary-user', 'ordinary@example.com', 'ordinary-hash', 0,
                '2025-01-01 01:02:03', None, None, None, 0, None, None,
                None, 0, 0, None, None, 1,
            ),
        ]
        assert db.session.execute(text(
            'SELECT id, user_id, name FROM portfolio'
        )).one() == (501, 41, 'Preserved Portfolio')
        assert db.session.execute(text('''
            SELECT id, user_id, provider, provider_subject FROM oauth_identity
        ''')).one() == (601, 84, 'google', 'preserved-subject')
        for child_table in ('portfolio', 'oauth_identity'):
            assert any(
                row[2] == 'user' and row[3] == 'user_id' and row[4] == 'id'
                for row in db.session.execute(
                    text(f'PRAGMA foreign_key_list("{child_table}")')
                ).fetchall()
            )
        assert db.session.execute(text('PRAGMA foreign_key_check')).fetchall() == []
        assert db.session.execute(text('PRAGMA foreign_keys')).scalar() == 1

    fresh_app = create_app(_config_for(tmp_path / 'otp-fresh-equivalent.sqlite'))
    for table_name in ('user', 'pending_registration'):
        assert _table_column_contract(upgraded_app, table_name) == (
            _table_column_contract(fresh_app, table_name)
        )
        assert _table_index_contract(upgraded_app, table_name) == (
            _table_index_contract(fresh_app, table_name)
        )

    restarted_app = create_app(_config_for(upgraded_path))
    with restarted_app.app_context():
        assert db.session.execute(text('PRAGMA user_version')).scalar() == TARGET_SCHEMA_VERSION
        assert db.session.execute(text(
            'SELECT password_hash FROM "user" WHERE id = 41'
        )).scalar() == 'preserved-hash'


def test_otp_hardening_replay_preserves_current_workflow_state(tmp_path):
    import portfolio_app.migrations as migrations

    app = create_app(_config_for(tmp_path / 'otp-hardening-replay.sqlite'))

    with app.app_context():
        db.session.execute(text('''
            INSERT INTO "user" (
                id, username, email, password_hash, is_verified, created_at,
                verification_code, verification_code_expires_at,
                verification_code_failed_attempts, pending_email,
                deletion_code, deletion_code_expires_at,
                deletion_code_failed_attempts, failed_login_attempts,
                auth_generation
            ) VALUES (
                701, 'current-otp-user', 'current@example.com',
                'preserved-password-hash', 1, '2026-08-13 10:00:00',
                :verification_digest, '2026-08-13 10:10:00', 2,
                'pending@example.com', :deletion_digest,
                '2026-08-13 10:10:00', 3, 0, 4
            )
        '''), {
            'verification_digest': 'a' * 64,
            'deletion_digest': 'b' * 64,
        })
        db.session.execute(text('''
            INSERT INTO pending_registration (
                id, username, email, created_at, expires_at
            ) VALUES (
                702, 'current-pending-user',
                'registration@example.com',
                '2026-08-13 10:00:00', '2026-08-14 10:00:00'
            )
        '''))
        db.session.commit()

        user_state_before = db.session.execute(text('''
            SELECT pending_email, verification_code,
                   verification_code_expires_at,
                   verification_code_failed_attempts, deletion_code,
                   deletion_code_expires_at, deletion_code_failed_attempts
            FROM "user" WHERE id = 701
        ''')).one()
        pending_state_before = db.session.execute(text('''
            SELECT username, email, created_at, expires_at
            FROM pending_registration WHERE id = 702
        ''')).one()
        user_columns_before = _table_column_contract(app, 'user')
        user_indexes_before = _table_index_contract(app, 'user')
        pending_columns_before = _table_column_contract(
            app,
            'pending_registration',
        )
        pending_indexes_before = _table_index_contract(
            app,
            'pending_registration',
        )
        db.session.remove()

        with db.engine.connect() as conn:
            migrations._harden_otp_storage(conn, sa)

        assert db.session.execute(text('''
            SELECT pending_email, verification_code,
                   verification_code_expires_at,
                   verification_code_failed_attempts, deletion_code,
                   deletion_code_expires_at, deletion_code_failed_attempts
            FROM "user" WHERE id = 701
        ''')).one() == user_state_before
        assert db.session.execute(text('''
            SELECT username, email, created_at, expires_at
            FROM pending_registration WHERE id = 702
        ''')).one() == pending_state_before
        assert _table_column_contract(app, 'user') == user_columns_before
        assert _table_index_contract(app, 'user') == user_indexes_before
        assert _table_column_contract(
            app,
            'pending_registration',
        ) == pending_columns_before
        assert _table_index_contract(
            app,
            'pending_registration',
        ) == pending_indexes_before
        assert db.session.execute(text('PRAGMA foreign_key_check')).fetchall() == []
        assert db.session.execute(text('PRAGMA foreign_keys')).scalar() == 1
