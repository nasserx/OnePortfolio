# Migrations

OnePortfolio uses an in-app SQLite migration system in `portfolio_app/migrations.py`.

## Schema Version

`TARGET_SCHEMA_VERSION` in `portfolio_app/migrations.py` defines the current expected SQLite schema version.

Startup migration state is stored in SQLite through:

`PRAGMA user_version`

When `user_version` is already at or above `TARGET_SCHEMA_VERSION`, the migration pass short-circuits.

Startup as a whole short-circuits under a stricter condition: the version must be current **and** every model table must already exist. The version is written at the end of the migration pass, before `db.create_all()` runs, so a current version on its own does not mean the schema is complete. See [Startup Coordination](#startup-coordination).

## Startup Flow

`create_app()` calls `run_startup_schema(app)`, the single entry point that brings the database to the target schema:

1. Opens the configured SQLAlchemy engine.
2. Pre-checks whether any work is pending — `PRAGMA user_version` below target, or model tables missing from the database. Returns immediately when neither is true, without taking a lock.
3. Acquires the startup schema lock (see below).
4. Runs the migration pass, which re-checks `PRAGMA user_version` under the lock and writes `TARGET_SCHEMA_VERSION` on success.
5. Runs `db.create_all()` for tables introduced by the models.
6. Releases the lock.

## Startup Coordination

Exactly one process at a time may bring a given SQLite database to the target schema. The lock spans **both** the migration pass and `db.create_all()`.

Both halves are check-then-act against the same database:

- **Migration steps** are individually idempotent, but the pass is not a single transaction — it commits between steps, and each step re-inspects the schema live (see [Idempotency](#idempotency)) so it sees the DDL the steps before it committed. Two workers starting together read the same pre-migration state, both act on it, and the loser replays a step that already happened (`duplicate column name`) or exhausts SQLite's busy timeout (`database is locked`), leaving a half-migrated database at the old version.
- **`db.create_all()`** has the same shape. Its `checkfirst` reflection and its `CREATE TABLE` statements are not atomic together, so two workers reaching an empty database both observe no tables and both create them; the loser dies on `table user already exists`.

The second half matters most on a fresh install, where the migration pass has almost nothing to do and *every* table comes from `create_all`. A lock covering only migrations would leave that entire path unserialized. It also matters when the models are ahead of the schema version: those workers pass a version-only gate instantly and land in `create_all` together, with none of the incidental stagger that lock contention would otherwise introduce. That is why the pre-check tests for missing tables as well as for the version.

`PRAGMA user_version` does not prevent any of this on its own. It is written only after the migration pass succeeds, so concurrent starters both pass the gate, and it says nothing about table presence. It does short-circuit workers that start *after* a complete startup.

The lock is an exclusive `BEGIN IMMEDIATE` transaction held for the whole critical section in a sidecar SQLite database beside the application database:

`portfolio.db` → `portfolio.db.schema-lock`

The lock cannot live in the application database itself: SQLite allows one writer per file, so holding a write transaction there would block the very writes it guards. The sidecar reuses the locking primitive the deployment already relies on, adds no dependency, and works identically on Windows and Linux.

Release is automatic on success, on failure, and on connection teardown — including an interrupted process. The sidecar carries no schema state; `PRAGMA user_version` and the tables themselves remain the source of truth, and deleting the sidecar while no startup is running is harmless.

A process that cannot acquire the lock within `STARTUP_SCHEMA_LOCK_TIMEOUT_SECONDS` (30) re-runs the pre-check. If the schema is complete it proceeds normally; otherwise it raises `StartupSchemaLockTimeout` and fails closed rather than starting up concurrently. The timeout is a single internal constant in `portfolio_app/migrations.py`, deliberately not a deployment setting: it only has to bracket this application's own startup work, and a tunable knob would be one more way to misconfigure a boot.

Non-SQLite and in-memory databases skip locking: an in-memory database is private to the process that opened it, and there is no shared file to coordinate on.

## Idempotency

Every migration step must be safe to run against partially upgraded databases. Steps should inspect tables, columns, indexes, and constraints before changing them.

Do not assume a table or column exists just because a previous step created it. Local databases may be old, partially migrated, or manually edited.

Reflection must be read fresh at every check. A SQLAlchemy `Inspector` memoizes each result for its own lifetime, so one instance shared across the pass answers later steps with the schema as it looked before the first `ALTER` — which is how the `capital → fund → portfolio` rename chain silently stopped halfway. The pass therefore inspects through `_LiveInspector`, which reflects the database again on every call. Keep using it, and refresh any local `tables` set you carry across a rename.

## Foreign Keys

SQLite foreign-key enforcement is enabled engine-wide through a connection listener. During migration, the runner temporarily disables foreign-key checks where table rebuilds require it, then re-enables them after migration.

Do not leave foreign keys disabled after a migration.

## Table Rebuilds

SQLite cannot alter every table property in place. The project uses a table-rebuild approach for changes such as stale foreign-key constraints, cascade behavior, or dropped legacy columns.

A rebuild should:

1. Create a replacement table with the desired schema.
2. Copy only valid columns.
3. Recreate needed indexes.
4. Drop or replace the old table.
5. Preserve data where valid.

## Adding a Migration Safely

When adding a migration:

- Increase `TARGET_SCHEMA_VERSION`.
- Add a narrowly scoped, idempotent step.
- Inspect schema state before each alteration.
- Preserve user data.
- For OAuth identity storage, keep provider subjects separate from tokens or secrets; never add token persistence casually.
- Consider old databases and partially migrated databases.
- Keep foreign-key behavior explicit.
- Add or update tests that cover startup against representative schema states.
- Back up real databases before deploying.

Never casually modify old completed migration behavior. If historical behavior must be corrected, add a new forward migration that handles databases already past the old step.

Schema version 33 replaces recoverable six-digit registration, email-change,
and account-deletion OTP storage with keyed digests. Upgrade invalidates staged
registrations and clears outstanding email-change and deletion verification
state; affected users must restart those short-lived workflows after deployment.

Schema version 34 aligns fresh and upgraded ownership constraints. Deleting a
portfolio cascades at the database boundary to its transactions, symbols,
dividends, and capital-event history; the forward migration rebuilds only child
tables whose existing foreign key still uses non-cascading delete behavior.

Schema version 35 performs the reversible passwordless-auth cutover. It makes
`User.password_hash` nullable without rewriting existing hash values, advances
every user's `auth_generation` once, and rebuilds `pending_registration`
without password or embedded OTP state. Startup refuses the cutover when a live
legacy pending registration exists; operators must resolve that short-lived
state before redeployment rather than silently losing it. Expired pending rows
are removed. `db.create_all()` then creates the dedicated `auth_challenge`
table. Legacy password reset/lockout columns and OAuth identity rows are
preserved but have no production runtime caller, providing a bounded rollback
window before a later separately approved destructive cleanup.

## Required Validation

Run:

```bash
python -m pytest -v
python -m compileall portfolio_app
git diff --check
```

For schema work, also test with a copy of an existing SQLite database before production deployment.
