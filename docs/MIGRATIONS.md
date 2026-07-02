# Migrations

OnePortfolio uses an in-app SQLite migration system in `portfolio_app/migrations.py`.

## Schema Version

`TARGET_SCHEMA_VERSION` in `portfolio_app/migrations.py` defines the current expected SQLite schema version.

Startup migration state is stored in SQLite through:

`PRAGMA user_version`

When `user_version` is already at or above `TARGET_SCHEMA_VERSION`, migration work short-circuits.

## Startup Flow

`create_app()` imports and calls `run_migrations(app)` before creating missing tables. The migration runner:

1. Opens the configured SQLAlchemy engine.
2. Checks `PRAGMA user_version`.
3. Applies idempotent migration steps when needed.
4. Writes `TARGET_SCHEMA_VERSION` after successful migration.

## Idempotency

Every migration step must be safe to run against partially upgraded databases. Steps should inspect tables, columns, indexes, and constraints before changing them.

Do not assume a table or column exists just because a previous step created it. Local databases may be old, partially migrated, or manually edited.

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

## Required Validation

Run:

```bash
python -m pytest -v
python -m compileall portfolio_app
git diff --check
```

For schema work, also test with a copy of an existing SQLite database before production deployment.
