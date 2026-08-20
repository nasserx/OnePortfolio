"""Schema-34 to passwordless schema-35 cutover contracts."""

import sqlite3

import pytest
from sqlalchemy import text

from config import Config
from portfolio_app import create_app, db
from portfolio_app.migrations import TARGET_SCHEMA_VERSION


def _config(path):
    class MigrationConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        SECRET_KEY = 'migration-test-secret'
        MAIL_SUPPRESS_SEND = True
        RATELIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{path.as_posix()}'
    return MigrationConfig


def _schema34(path, *, pending_expiry=None):
    connection = sqlite3.connect(path)
    connection.executescript('''
        CREATE TABLE "user" (
            id INTEGER NOT NULL PRIMARY KEY,
            username VARCHAR(80) NOT NULL,
            email VARCHAR(120),
            password_hash VARCHAR(255) NOT NULL,
            is_verified BOOLEAN NOT NULL,
            created_at DATETIME,
            last_login DATETIME,
            verification_code VARCHAR(64),
            verification_code_expires_at DATETIME,
            verification_code_failed_attempts INTEGER NOT NULL,
            pending_email VARCHAR(120),
            deletion_code VARCHAR(64),
            deletion_code_expires_at DATETIME,
            deletion_code_failed_attempts INTEGER NOT NULL,
            failed_login_attempts INTEGER NOT NULL,
            locked_until DATETIME,
            password_reset_jti VARCHAR(32),
            auth_generation INTEGER NOT NULL DEFAULT 0
        );
        CREATE UNIQUE INDEX ix_user_username ON "user" (username);
        CREATE UNIQUE INDEX ix_user_email ON "user" (email);
        CREATE TABLE pending_registration (
            id INTEGER NOT NULL PRIMARY KEY,
            token VARCHAR(64) NOT NULL,
            username VARCHAR(80) NOT NULL,
            email VARCHAR(120) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            verification_code VARCHAR(64) NOT NULL,
            verification_code_expires_at DATETIME NOT NULL,
            failed_otp_attempts INTEGER NOT NULL,
            created_at DATETIME NOT NULL,
            expires_at DATETIME NOT NULL
        );
        CREATE UNIQUE INDEX ix_pending_registration_token ON pending_registration (token);
        CREATE UNIQUE INDEX ix_pending_registration_username ON pending_registration (username);
        CREATE UNIQUE INDEX ix_pending_registration_email ON pending_registration (email);
        INSERT INTO "user" VALUES (
            1, 'legacy', 'legacy@example.com', 'preserved-byte-for-byte', 1,
            '2026-01-01', NULL, NULL, NULL, 0, NULL, NULL, NULL, 0,
            4, '2026-01-02', 'preserved-reset-jti', 7
        );
        PRAGMA user_version = 34;
    ''')
    if pending_expiry is not None:
        connection.execute('''
            INSERT INTO pending_registration VALUES (
                1, 'token', 'pending', 'pending@example.com', 'pending-hash',
                ?, '2026-08-20 12:10:00', 0,
                '2026-08-20 12:00:00', ?
            )
        ''', ('a' * 64, pending_expiry))
    connection.commit()
    connection.close()


def test_schema34_cutover_preserves_hash_and_legacy_state_and_revokes_sessions(tmp_path):
    path = tmp_path / 'schema34.sqlite'
    _schema34(path)
    app = create_app(_config(path))
    with app.app_context():
        row = db.session.execute(text('''
            SELECT password_hash, failed_login_attempts, locked_until,
                   password_reset_jti, auth_generation
            FROM "user" WHERE id = 1
        ''')).one()
        assert row == (
            'preserved-byte-for-byte', 4, '2026-01-02',
            'preserved-reset-jti', 8,
        )
        columns = {
            item[1]: item
            for item in db.session.execute(text('PRAGMA table_info("user")'))
        }
        assert columns['password_hash'][3] == 0
        pending_columns = {
            item[1]
            for item in db.session.execute(text(
                'PRAGMA table_info(pending_registration)'
            ))
        }
        assert pending_columns == {
            'id', 'username', 'email', 'created_at', 'expires_at',
        }
        assert db.session.execute(text('PRAGMA user_version')).scalar() == TARGET_SCHEMA_VERSION
        assert db.session.execute(text(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='auth_challenge'"
        )).scalar() == 1


def test_cutover_replay_does_not_advance_generation_twice(tmp_path):
    path = tmp_path / 'replay.sqlite'
    _schema34(path)
    create_app(_config(path))
    restarted = create_app(_config(path))
    with restarted.app_context():
        assert db.session.execute(text(
            'SELECT auth_generation FROM "user" WHERE id=1'
        )).scalar() == 8


def test_expired_pending_registration_is_safely_removed(tmp_path):
    path = tmp_path / 'expired.sqlite'
    _schema34(path, pending_expiry='2000-01-01 00:00:00')
    app = create_app(_config(path))
    with app.app_context():
        assert db.session.execute(text(
            'SELECT COUNT(*) FROM pending_registration'
        )).scalar() == 0


def test_live_pending_registration_refuses_cutover_without_mutation(tmp_path):
    path = tmp_path / 'live.sqlite'
    _schema34(path, pending_expiry='2999-01-01 00:00:00')
    with pytest.raises(RuntimeError, match='live legacy pending registrations'):
        create_app(_config(path))
    connection = sqlite3.connect(path)
    try:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 34
        assert connection.execute(
            'SELECT password_hash FROM "user" WHERE id=1'
        ).fetchone()[0] == 'preserved-byte-for-byte'
        assert connection.execute(
            'SELECT password_hash FROM pending_registration WHERE id=1'
        ).fetchone()[0] == 'pending-hash'
    finally:
        connection.close()


def test_old_schema_live_pending_is_guarded_before_historical_invalidation(tmp_path):
    path = tmp_path / 'schema29-live.sqlite'
    connection = sqlite3.connect(path)
    connection.executescript('''
        CREATE TABLE pending_registration (
            id INTEGER NOT NULL PRIMARY KEY,
            token VARCHAR(64) NOT NULL,
            username VARCHAR(80) NOT NULL,
            email VARCHAR(120) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            verification_code VARCHAR(6) NOT NULL,
            verification_code_expires_at DATETIME NOT NULL,
            failed_otp_attempts INTEGER NOT NULL,
            created_at DATETIME NOT NULL,
            expires_at DATETIME NOT NULL
        );
        INSERT INTO pending_registration VALUES (
            1, 'live-token', 'pending', 'pending@example.com',
            'pending-hash', '123456', '2999-01-01 00:10:00', 0,
            '2026-08-20 12:00:00', '2999-01-02 00:00:00'
        );
        PRAGMA user_version = 29;
    ''')
    connection.commit()
    connection.close()

    with pytest.raises(RuntimeError, match='live legacy pending registrations'):
        create_app(_config(path))

    connection = sqlite3.connect(path)
    try:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 29
        assert connection.execute('''
            SELECT password_hash, verification_code
            FROM pending_registration WHERE id = 1
        ''').fetchone() == ('pending-hash', '123456')
    finally:
        connection.close()
