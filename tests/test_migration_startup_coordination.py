"""RCR-08: one process at a time may bring a SQLite database to target schema.

Startup schema work is two check-then-act operations against the same database:
the incremental migration pass, and ``db.create_all()``.

The migration pass is not one transaction — it commits between steps — so two
workers booting together both pass the ``PRAGMA user_version`` gate and the
loser replays a step that already happened (``duplicate column name``).

``db.create_all()`` is the same shape: its ``checkfirst`` reflection and its
``CREATE TABLE`` statements are not atomic together, so two workers reaching an
empty database both see no tables and both create them (``table user already
exists``). On a fresh install every table comes from ``create_all``, so a lock
covering only the migration pass leaves that whole path unserialized.

``run_startup_schema`` therefore holds one exclusive ``BEGIN IMMEDIATE``
transaction in a sidecar SQLite database across both.

These tests use real SQLite connections, real threads, and real subprocesses —
the lock is never mocked, because the behaviour under test *is* the locking.
"""

from pathlib import Path
import contextlib
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time

from flask import Flask
import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import Engine, make_url

from portfolio_app import db
import portfolio_app.migrations as migrations
from portfolio_app.migrations import (
    STARTUP_SCHEMA_LOCK_SUFFIX,
    STARTUP_SCHEMA_LOCK_TIMEOUT_SECONDS,
    StartupSchemaLockTimeout,
    TARGET_SCHEMA_VERSION,
)

# Registering every model populates ``db.metadata``, which is what
# ``create_all`` builds from and what the pre-check diffs against.
from portfolio_app.models.dividend import Dividend  # noqa: F401
from portfolio_app.models.oauth_identity import OAuthIdentity  # noqa: F401
from portfolio_app.models.pending_registration import PendingRegistration  # noqa: F401
from portfolio_app.models.portfolio import Portfolio  # noqa: F401
from portfolio_app.models.portfolio_event import PortfolioEvent  # noqa: F401
from portfolio_app.models.symbol import Symbol  # noqa: F401
from portfolio_app.models.transaction import Transaction  # noqa: F401
from portfolio_app.models.user import User  # noqa: F401

# The legacy version-33 fixture is a large, exact reproduction of a deployed
# schema. Reusing it keeps the upgrade tests racing a *real* forward migration
# (the Step 34 child-table rebuilds) instead of a no-op pass.
from tests.test_migrations import _create_version_33_no_action_database


REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent

_CREATE_TABLE_RE = re.compile(r'CREATE TABLE\s+(?:IF NOT EXISTS\s+)?"?(\w+)"?',
                              re.IGNORECASE)


def _sqlite_uri(db_path):
    return 'sqlite:///{0}'.format(Path(db_path).resolve().as_posix())


def _bare_app(db_path, **config):
    """A minimal app exposing just what ``run_startup_schema`` needs."""
    app = Flask('startup-schema-{0}'.format(os.urandom(4).hex()))
    app.config['SQLALCHEMY_DATABASE_URI'] = _sqlite_uri(db_path)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config.update(config)
    db.init_app(app)
    return app


def _lock_path_for(db_path):
    return Path(str(Path(db_path).resolve()) + STARTUP_SCHEMA_LOCK_SUFFIX)


def _schema_version(db_path):
    con = sqlite3.connect(str(db_path))
    try:
        return con.execute('PRAGMA user_version').fetchone()[0]
    finally:
        con.close()


def _set_schema_version(db_path, version):
    con = sqlite3.connect(str(db_path))
    try:
        con.execute('PRAGMA user_version = {0:d}'.format(version))
        con.commit()
    finally:
        con.close()


def _table_names(db_path):
    con = sqlite3.connect(str(db_path))
    try:
        return {
            row[0] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        con.close()


def _model_table_names():
    return set(db.metadata.tables)


def _foreign_keys_enabled(db_path):
    """FK enforcement is per-connection; check a brand-new one."""
    app = _bare_app(db_path)
    with app.app_context():
        with db.engine.connect() as conn:
            return conn.exec_driver_sql('PRAGMA foreign_keys').scalar()


@contextlib.contextmanager
def _hold_lock(lock_path):
    """Hold the sidecar lock exactly the way ``run_startup_schema`` does."""
    connection = sqlite3.connect(str(lock_path), isolation_level=None)
    try:
        connection.execute('BEGIN IMMEDIATE')
        yield
    finally:
        connection.close()


@contextlib.contextmanager
def _record_created_tables():
    """Capture every ``CREATE TABLE`` any engine issues, from any thread."""
    created = []

    def _listener(conn, cursor, statement, parameters, context, executemany):
        match = _CREATE_TABLE_RE.match(statement.strip())
        if match:
            created.append(match.group(1))

    event.listen(Engine, 'before_cursor_execute', _listener)
    try:
        yield created
    finally:
        event.remove(Engine, 'before_cursor_execute', _listener)


class _StepRecorder:
    """Counts real migration passes; optionally widens the race window."""

    def __init__(self, hold_seconds=0.0):
        self.calls = 0
        self.hold_seconds = hold_seconds
        self._lock = threading.Lock()
        self._original = migrations._apply_migration_steps

    def install(self, monkeypatch):
        monkeypatch.setattr(migrations, '_apply_migration_steps', self)
        return self

    def __call__(self, conn, sa):
        with self._lock:
            self.calls += 1
        if self.hold_seconds:
            time.sleep(self.hold_seconds)
        return self._original(conn, sa)


def _start_concurrently(db_path, worker_count=2, join_timeout=60):
    """Run ``run_startup_schema`` in N threads released together."""
    apps = [_bare_app(db_path) for _ in range(worker_count)]
    barrier = threading.Barrier(worker_count, timeout=30)
    failures = []

    def _worker(app):
        try:
            barrier.wait()
            migrations.run_startup_schema(app)
        except BaseException as exc:  # noqa: BLE001 - reported as a failure
            failures.append('{0}: {1}'.format(type(exc).__name__, exc))

    threads = [threading.Thread(target=_worker, args=(app,)) for app in apps]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=join_timeout)

    assert not any(thread.is_alive() for thread in threads), 'worker hung'
    return failures


# ---------------------------------------------------------------------------
# Sidecar identity and timeout contract
# ---------------------------------------------------------------------------

def test_lock_path_is_derived_deterministically_from_the_database_path(tmp_path):
    db_path = tmp_path / 'portfolio.db'
    url = make_url(_sqlite_uri(db_path))

    first = migrations._startup_schema_lock_path(url)
    second = migrations._startup_schema_lock_path(url)

    assert first == second
    assert Path(first) == _lock_path_for(db_path)
    assert Path(first).name == 'portfolio.db.schema-lock'
    assert Path(first).parent == tmp_path.resolve()


def test_lock_path_follows_the_engine_database_not_the_config_string(
    tmp_path, monkeypatch
):
    """A relative SQLite URI resolves to instance_path, and the lock must follow.

    Flask-SQLAlchemy rewrites a relative ``sqlite:///`` path to sit under
    ``app.instance_path`` before it builds the engine, so the raw config string
    and the process working directory both point somewhere the database is not.
    Deriving the sidecar from ``db.engine.url`` is what keeps two workers with
    different working directories on one lock file; deriving it from
    ``SQLALCHEMY_DATABASE_URI`` would scatter locks across CWDs and silently
    unserialize startup.
    """
    instance_dir = tmp_path / 'instance'
    elsewhere = tmp_path / 'elsewhere'
    instance_dir.mkdir()
    elsewhere.mkdir()

    # Boot the whole app from a directory that is not the database's.
    monkeypatch.chdir(elsewhere)

    app = Flask('instance-path-{0}'.format(os.urandom(4).hex()),
                instance_path=str(instance_dir))
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///relative.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    with app.app_context():
        engine_database = Path(db.engine.url.database)

    assert engine_database.is_absolute(), 'expected a resolved database path'
    assert engine_database.parent == instance_dir.resolve()

    migrations.run_startup_schema(app)

    lock_path = Path(str(engine_database) + STARTUP_SCHEMA_LOCK_SUFFIX)
    assert lock_path.exists(), 'no sidecar beside the real database file'
    assert lock_path.parent == instance_dir.resolve()
    assert engine_database.exists()
    assert _model_table_names() <= _table_names(engine_database)

    # Where a regression that read the raw config string would have put things.
    assert not (elsewhere / 'relative.db').exists()
    assert list(elsewhere.glob('*' + STARTUP_SCHEMA_LOCK_SUFFIX)) == []


@pytest.mark.parametrize('uri', [
    'sqlite://',
    'sqlite:///:memory:',
    'postgresql://user:pw@localhost/portfolio',
])
def test_lock_is_skipped_without_a_shared_sqlite_file(uri):
    assert migrations._startup_schema_lock_path(make_url(uri)) is None


def test_timeout_is_a_single_internal_constant(tmp_path, monkeypatch):
    """One documented constant — no per-deployment configuration surface.

    Asserted behaviourally rather than by reading the source: rebinding the
    module constant changes how long a contended startup blocks, and config
    keys a regression might reach for are ignored even when present.
    """
    assert STARTUP_SCHEMA_LOCK_TIMEOUT_SECONDS == 30.0

    db_path = tmp_path / 'timeout.db'
    _create_version_33_no_action_database(db_path)
    monkeypatch.setattr(migrations, 'STARTUP_SCHEMA_LOCK_TIMEOUT_SECONDS', 0.5)

    # Plant the settings a configurable implementation would consult. Honouring
    # either one would stretch the wait below to 20s.
    app = _bare_app(
        db_path,
        MIGRATION_LOCK_TIMEOUT=20.0,
        STARTUP_SCHEMA_LOCK_TIMEOUT_SECONDS=20.0,
    )

    started = time.time()
    with _hold_lock(_lock_path_for(db_path)):
        with pytest.raises(StartupSchemaLockTimeout):
            migrations.run_startup_schema(app)
    elapsed = time.time() - started

    assert elapsed < 10, (
        'waited {0:.1f}s on a 0.5s constant — app config overrode it'.format(
            elapsed
        )
    )


# ---------------------------------------------------------------------------
# Fresh empty database — every table comes from create_all
# ---------------------------------------------------------------------------

def test_fresh_database_concurrent_startup_creates_each_table_once(tmp_path):
    """The path a lock around migrations alone would leave unprotected."""
    db_path = tmp_path / 'fresh.db'

    with _record_created_tables() as created:
        failures = _start_concurrently(db_path, worker_count=4)

    assert failures == []

    model_tables = _model_table_names()
    assert model_tables <= _table_names(db_path)

    # Every model table was created exactly once across all four workers —
    # no second worker re-issued a CREATE for a table already present.
    duplicated = sorted(
        name for name in model_tables if created.count(name) != 1
    )
    assert duplicated == [], 'tables created more than once: {0}'.format(
        [(name, created.count(name)) for name in duplicated]
    )

    assert _schema_version(db_path) == TARGET_SCHEMA_VERSION
    assert _foreign_keys_enabled(db_path) == 1


def test_fresh_database_concurrent_startup_is_stable_across_rounds(tmp_path):
    """Repeat the fresh race, because one round is a weak detector.

    Measured against an unguarded ``create_all``, the fresh path crashed in
    only 1 of 6 rounds: SQLite's busy-handler backoff staggers contenders on
    the migration pass, which incidentally spaces out their arrival at
    ``create_all``. Repetition compounds the odds of catching a regression
    here. Deterministic detection lives in the models-ahead tests below, where
    every worker clears a version-only gate at the same instant and the same
    negative control crashed 6 of 6.
    """
    for round_index in range(5):
        db_path = tmp_path / 'fresh-{0}.db'.format(round_index)
        failures = _start_concurrently(db_path, worker_count=3)
        assert failures == [], 'round {0}: {1}'.format(round_index, failures)
        assert _model_table_names() <= _table_names(db_path)
        assert _schema_version(db_path) == TARGET_SCHEMA_VERSION


def test_models_ahead_of_schema_version_still_serialize(tmp_path):
    """Version current but tables missing: the pre-check must still lock.

    This is the path with no accidental stagger — every worker would sail
    through a version-only gate straight into a concurrent create_all.
    """
    db_path = tmp_path / 'models-ahead.db'
    sqlite3.connect(str(db_path)).close()
    _set_schema_version(db_path, TARGET_SCHEMA_VERSION)

    app = _bare_app(db_path)
    assert migrations._startup_schema_pending(app) is True

    failures = _start_concurrently(db_path, worker_count=4)

    assert failures == []
    assert _model_table_names() <= _table_names(db_path)


# ---------------------------------------------------------------------------
# Upgraded database — real v33 → v34 forward migration
# ---------------------------------------------------------------------------

def test_two_concurrent_threads_run_migration_work_once(tmp_path, monkeypatch):
    db_path = tmp_path / 'threaded.db'
    _create_version_33_no_action_database(db_path)

    recorder = _StepRecorder(hold_seconds=0.75).install(monkeypatch)

    failures = _start_concurrently(db_path)

    assert failures == []
    # The loser queued on the lock, then found the version already bumped.
    assert recorder.calls == 1
    assert _schema_version(db_path) == TARGET_SCHEMA_VERSION
    assert _foreign_keys_enabled(db_path) == 1


def test_concurrent_migration_preserves_seeded_rows(tmp_path, monkeypatch):
    """The Step 34 rebuild copies real rows; racing must not lose them."""
    db_path = tmp_path / 'preserve.db'
    _create_version_33_no_action_database(db_path)

    _StepRecorder(hold_seconds=0.5).install(monkeypatch)

    assert _start_concurrently(db_path) == []

    app = _bare_app(db_path)
    with app.app_context():
        rows = db.session.execute(text('SELECT id, name FROM portfolio')).fetchall()
        assert [(row[0], row[1]) for row in rows] == [(51, 'Preserved Portfolio')]
        assert db.session.execute(
            text('SELECT COUNT(*) FROM "transaction"')
        ).scalar() == 1
        assert db.session.execute(
            text('SELECT COUNT(*) FROM dividend')
        ).scalar() == 1
        assert db.session.execute(
            text('SELECT COUNT(*) FROM portfolio_event')
        ).scalar() == 1


# ---------------------------------------------------------------------------
# Real concurrency: separate worker processes booting the full factory
# ---------------------------------------------------------------------------

_WORKER_SCRIPT = r'''
import os
import sys
import time

REPO_ROOT = {repo}
DATABASE_URI = {uri}
LOG_PATH = {log}
READY_DIR = {ready_dir}
GO_PATH = {go}
HOLD_SECONDS = {hold}
TAG = sys.argv[1]

sys.path.insert(0, REPO_ROOT)

from config import Config
import portfolio_app.migrations as migrations
from portfolio_app import create_app

_original_apply = migrations._apply_migration_steps


def _instrumented(conn, sa):
    with open(LOG_PATH, 'a') as handle:
        handle.write(TAG + '\n')
        handle.flush()
    time.sleep(HOLD_SECONDS)
    return _original_apply(conn, sa)


migrations._apply_migration_steps = _instrumented


class _WorkerConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key'
    MAIL_SUPPRESS_SEND = True
    RATELIMIT_ENABLED = False
    SQLALCHEMY_DATABASE_URI = DATABASE_URI


with open(os.path.join(READY_DIR, 'ready-' + TAG), 'w') as handle:
    handle.write(TAG)

deadline = time.time() + 60
while not os.path.exists(GO_PATH):
    if time.time() > deadline:
        raise SystemExit('rendezvous timed out')
    time.sleep(0.01)

create_app(_WorkerConfig)
'''


def _boot_workers(tmp_path, db_path, tags, hold_seconds):
    """Boot the real factory in one process per tag, released together."""
    log_path = tmp_path / 'applied.log'
    go_path = tmp_path / 'go'
    ready_paths = [tmp_path / ('ready-' + tag) for tag in tags]

    script = tmp_path / 'boot_worker.py'
    script.write_text(
        _WORKER_SCRIPT.format(
            repo=repr(str(REPO_ROOT)),
            uri=repr(_sqlite_uri(db_path)),
            log=repr(str(log_path)),
            ready_dir=repr(str(tmp_path)),
            go=repr(str(go_path)),
            hold=repr(hold_seconds),
        ),
        encoding='utf-8',
    )

    # A child process is not running under pytest, so it takes the production
    # configuration path: SECRET_KEY must be supplied the way a deployment
    # supplies it (see config._require_secret_key).
    worker_env = dict(os.environ)
    worker_env['SECRET_KEY'] = 'startup-schema-worker-key'
    worker_env.pop('DATABASE_URL', None)

    processes = [
        subprocess.Popen(
            [sys.executable, '-B', str(script), tag],
            cwd=str(REPO_ROOT),
            env=worker_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        for tag in tags
    ]

    try:
        # Rendezvous: release the workers only once each has imported the
        # application and is one call away from startup schema work.
        deadline = time.time() + 120
        while not all(path.exists() for path in ready_paths):
            if time.time() > deadline:
                raise AssertionError('workers never signalled readiness')
            for process in processes:
                if process.poll() not in (None, 0):
                    raise AssertionError(
                        'worker exited early: ' + process.communicate()[1]
                    )
            time.sleep(0.02)

        go_path.write_text('go')
        results = [process.communicate(timeout=180) for process in processes]
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()

    for (stdout, stderr), process in zip(results, processes):
        assert process.returncode == 0, 'worker failed ({0}):\n{1}\n{2}'.format(
            process.returncode, stdout, stderr
        )

    applied = []
    if log_path.exists():
        applied = [
            line for line in log_path.read_text(encoding='utf-8').splitlines()
            if line
        ]
    return applied


def test_two_concurrent_worker_processes_run_migration_work_once(tmp_path):
    """Two real processes boot the real factory against one v33 database."""
    db_path = tmp_path / 'workers.db'
    _create_version_33_no_action_database(db_path)
    tags = ('worker-a', 'worker-b')

    applied = _boot_workers(tmp_path, db_path, tags, hold_seconds=1.0)

    assert len(applied) == 1, 'migration steps ran {0}x: {1}'.format(
        len(applied), applied
    )
    assert applied[0] in tags
    assert _schema_version(db_path) == TARGET_SCHEMA_VERSION
    assert _foreign_keys_enabled(db_path) == 1


def test_concurrent_worker_processes_start_on_a_fresh_database(tmp_path):
    """Four real processes, empty database: every table comes from create_all."""
    db_path = tmp_path / 'fresh-workers.db'
    tags = ('worker-a', 'worker-b', 'worker-c', 'worker-d')

    _boot_workers(tmp_path, db_path, tags, hold_seconds=0.0)

    assert _model_table_names() <= _table_names(db_path)
    assert _schema_version(db_path) == TARGET_SCHEMA_VERSION
    assert _foreign_keys_enabled(db_path) == 1


def test_concurrent_worker_processes_with_models_ahead_of_version(tmp_path):
    """Empty database already stamped at target: the unstaggered crash path.

    Every worker passes a version-only gate instantly and lands in create_all
    at the same moment, with none of the lock backoff that masks the race in
    the other process tests.
    """
    db_path = tmp_path / 'ahead-workers.db'
    sqlite3.connect(str(db_path)).close()
    _set_schema_version(db_path, TARGET_SCHEMA_VERSION)
    tags = ('worker-a', 'worker-b', 'worker-c', 'worker-d')

    applied = _boot_workers(tmp_path, db_path, tags, hold_seconds=0.0)

    assert applied == []  # version already current: no migration steps
    assert _model_table_names() <= _table_names(db_path)


# ---------------------------------------------------------------------------
# Release semantics
# ---------------------------------------------------------------------------

def test_lock_is_released_after_failed_migration_and_retry_succeeds(
    tmp_path, monkeypatch
):
    db_path = tmp_path / 'failed.db'
    _create_version_33_no_action_database(db_path)
    lock_path = _lock_path_for(db_path)

    def _explode(conn, sa_module):
        raise RuntimeError('injected migration failure')

    monkeypatch.setattr(migrations, '_apply_migration_steps', _explode)

    with pytest.raises(RuntimeError, match='injected migration failure'):
        migrations.run_startup_schema(_bare_app(db_path))

    assert _schema_version(db_path) == 33
    assert _foreign_keys_enabled(db_path) == 1

    # The lock must be free even though the migration raised inside it.
    free_connection = sqlite3.connect(
        str(lock_path), timeout=0.2, isolation_level=None
    )
    try:
        free_connection.execute('BEGIN IMMEDIATE')
        free_connection.execute('ROLLBACK')
    finally:
        free_connection.close()

    monkeypatch.undo()
    migrations.run_startup_schema(_bare_app(db_path))

    assert _schema_version(db_path) == TARGET_SCHEMA_VERSION
    assert _foreign_keys_enabled(db_path) == 1


def test_lock_is_released_after_failed_table_creation(tmp_path, monkeypatch):
    """create_all is inside the critical section, so it must release too."""
    db_path = tmp_path / 'failed-create.db'
    lock_path = _lock_path_for(db_path)

    original_create_all = db.create_all

    def _explode(*args, **kwargs):
        raise RuntimeError('injected create_all failure')

    monkeypatch.setattr(db, 'create_all', _explode)

    with pytest.raises(RuntimeError, match='injected create_all failure'):
        migrations.run_startup_schema(_bare_app(db_path))

    monkeypatch.setattr(db, 'create_all', original_create_all)

    free_connection = sqlite3.connect(
        str(lock_path), timeout=0.2, isolation_level=None
    )
    try:
        free_connection.execute('BEGIN IMMEDIATE')
        free_connection.execute('ROLLBACK')
    finally:
        free_connection.close()

    migrations.run_startup_schema(_bare_app(db_path))
    assert _model_table_names() <= _table_names(db_path)


def test_lock_is_released_when_the_holding_connection_tears_down(tmp_path):
    """A killed worker leaves no stale lock: SQLite drops it on close."""
    lock_path = _lock_path_for(tmp_path / 'teardown.db')

    abandoned = sqlite3.connect(str(lock_path), isolation_level=None)
    abandoned.execute('BEGIN IMMEDIATE')

    contender = sqlite3.connect(str(lock_path), timeout=0.2, isolation_level=None)
    try:
        with pytest.raises(sqlite3.OperationalError):
            contender.execute('BEGIN IMMEDIATE')

        abandoned.close()  # stands in for the holding process dying

        contender.execute('BEGIN IMMEDIATE')
        contender.execute('ROLLBACK')
    finally:
        contender.close()


# ---------------------------------------------------------------------------
# Gate behaviour
# ---------------------------------------------------------------------------

def test_complete_schema_returns_without_waiting_for_the_lock(
    tmp_path, monkeypatch
):
    db_path = tmp_path / 'current.db'
    _create_version_33_no_action_database(db_path)
    migrations.run_startup_schema(_bare_app(db_path))
    assert _schema_version(db_path) == TARGET_SCHEMA_VERSION

    recorder = _StepRecorder().install(monkeypatch)
    assert migrations._startup_schema_pending(_bare_app(db_path)) is False

    # Someone else holds the lock, but a complete schema never needs it.
    started = time.time()
    with _record_created_tables() as created:
        with _hold_lock(_lock_path_for(db_path)):
            migrations.run_startup_schema(_bare_app(db_path))
    elapsed = time.time() - started

    assert recorder.calls == 0
    assert created == []
    assert elapsed < 5, 'warm boot waited on a lock it did not need'


def test_stale_schema_with_held_lock_fails_closed(tmp_path, monkeypatch):
    db_path = tmp_path / 'contended.db'
    _create_version_33_no_action_database(db_path)
    recorder = _StepRecorder().install(monkeypatch)
    monkeypatch.setattr(migrations, 'STARTUP_SCHEMA_LOCK_TIMEOUT_SECONDS', 0.3)

    with _hold_lock(_lock_path_for(db_path)):
        with pytest.raises(StartupSchemaLockTimeout) as excinfo:
            migrations.run_startup_schema(_bare_app(db_path))

    message = str(excinfo.value)
    assert 'schema version 33' in message
    assert str(TARGET_SCHEMA_VERSION) in message
    assert STARTUP_SCHEMA_LOCK_SUFFIX in message

    assert recorder.calls == 0
    assert _schema_version(db_path) == 33


def test_missing_tables_with_held_lock_fail_closed(tmp_path, monkeypatch):
    """Fail-closed covers the create_all half of the contract too."""
    db_path = tmp_path / 'contended-tables.db'
    sqlite3.connect(str(db_path)).close()
    _set_schema_version(db_path, TARGET_SCHEMA_VERSION)
    monkeypatch.setattr(migrations, 'STARTUP_SCHEMA_LOCK_TIMEOUT_SECONDS', 0.3)

    with _record_created_tables() as created:
        with _hold_lock(_lock_path_for(db_path)):
            with pytest.raises(StartupSchemaLockTimeout) as excinfo:
                migrations.run_startup_schema(_bare_app(db_path))

    assert 'missing tables' in str(excinfo.value)
    assert created == []
    assert _table_names(db_path) == set()


def test_acquisition_timeout_proceeds_when_another_worker_finished(
    tmp_path, monkeypatch
):
    """Waiting out the holder is success when the holder did the work."""
    db_path = tmp_path / 'handoff.db'
    _create_version_33_no_action_database(db_path)
    migrations.run_startup_schema(_bare_app(db_path))   # complete schema
    _set_schema_version(db_path, 33)                    # ...then look stale

    recorder = _StepRecorder().install(monkeypatch)
    monkeypatch.setattr(migrations, 'STARTUP_SCHEMA_LOCK_TIMEOUT_SECONDS', 1.0)

    def _finish_startup_elsewhere():
        time.sleep(0.2)
        _set_schema_version(db_path, TARGET_SCHEMA_VERSION)

    with _hold_lock(_lock_path_for(db_path)):
        finisher = threading.Thread(target=_finish_startup_elsewhere)
        finisher.start()
        try:
            migrations.run_startup_schema(_bare_app(db_path))
        finally:
            finisher.join(timeout=30)

    assert recorder.calls == 0
    assert _schema_version(db_path) == TARGET_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Artifact hygiene
# ---------------------------------------------------------------------------

def test_lock_artifacts_stay_beside_the_database_and_out_of_the_repo(tmp_path):
    db_path = tmp_path / 'artifacts.db'
    _create_version_33_no_action_database(db_path)

    migrations.run_startup_schema(_bare_app(db_path))

    lock_path = _lock_path_for(db_path)
    assert lock_path.parent == tmp_path.resolve()
    assert TESTS_DIR not in lock_path.resolve().parents
    assert REPO_ROOT not in lock_path.resolve().parents
    assert list(TESTS_DIR.glob('*' + STARTUP_SCHEMA_LOCK_SUFFIX)) == []
