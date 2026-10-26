"""Upgrade safety uses disposable databases, never the working portfolio.db."""

import sqlite3

import pytest

from portfolio_app import create_app, db
from tests.test_migrations import _config_for, _create_version_33_no_action_database
from tests.test_migration_legacy_replay import (
    _create_capital_era_database, _attribute_capital_dividend,
)


def dump(path):
    with sqlite3.connect(path) as connection:
        return tuple(connection.iterdump()), connection.execute('PRAGMA user_version').fetchone()[0]


def close_app(app):
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def test_oldest_schema_without_symbol_column_is_preserved_before_any_rename(tmp_path):
    path = tmp_path / 'capital.sqlite'
    _create_capital_era_database(path)
    before = dump(path)
    with pytest.raises(RuntimeError, match='unattributed dividend'):
        create_app(_config_for(path))
    assert dump(path) == before


@pytest.mark.parametrize('version', [33, 40])
@pytest.mark.parametrize('symbol', [None, '', '   '])
def test_unattributed_dividend_blocks_upgrade_without_changing_any_records(tmp_path, version, symbol):
    path = tmp_path / 'unattributed.sqlite'
    _create_version_33_no_action_database(path)
    if version == 40:
        close_app(create_app(_config_for(path)))
    with sqlite3.connect(path) as connection:
        # Model an older nullable-symbol schema, including an already-upgraded
        # installation with surviving imported legacy records.
        connection.executescript('''
            ALTER TABLE dividend RENAME TO old_dividend;
            CREATE TABLE dividend AS SELECT * FROM old_dividend;
            DROP TABLE old_dividend;
        ''')
        connection.execute('UPDATE dividend SET symbol=? WHERE id=63', (symbol,))
        connection.execute(f'PRAGMA user_version={version}')
    before = dump(path)
    for _ in range(2):
        with pytest.raises(RuntimeError, match='unattributed dividend') as error:
            create_app(_config_for(path))
        assert '63' in str(error.value)
        assert dump(path) == before


@pytest.mark.parametrize('missing_history', [False, True])
def test_schema40_forward_upgrade_preserves_survivors_and_never_invents_history(tmp_path, missing_history):
    path = tmp_path / 'schema40.sqlite'
    _create_version_33_no_action_database(path)
    close_app(create_app(_config_for(path)))
    with sqlite3.connect(path) as connection:
        if missing_history:
            # Previously executed destructive migration: no facts remain to
            # reconstruct. The new revision must not fabricate a replacement.
            connection.execute('DELETE FROM dividend')
        connection.execute('PRAGMA user_version=40')
    before, _ = dump(path)
    for _ in range(2):
        close_app(create_app(_config_for(path)))
        after, version = dump(path)
        assert after == before
        assert version == 41


def test_corrected_legacy_attribution_can_retry_upgrade(tmp_path):
    path = tmp_path / 'corrected.sqlite'
    _create_version_33_no_action_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE dividend SET symbol='' WHERE id=63")
    with pytest.raises(RuntimeError, match='unattributed dividend'):
        create_app(_config_for(path))
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE dividend SET symbol='AAPL' WHERE id=63")
    close_app(create_app(_config_for(path)))
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT id,portfolio_id,symbol,amount,notes FROM dividend').fetchall() == [
            (63, 51, 'AAPL', '25', 'preserved income'),
        ]
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 41
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []


def test_symbol_repair_still_blocks_until_legacy_owner_is_explicitly_repaired(tmp_path):
    path = tmp_path / 'owner-repair.sqlite'
    _create_capital_era_database(path, owned=False)
    before = dump(path)
    with pytest.raises(RuntimeError, match='unattributed dividend'):
        create_app(_config_for(path))
    assert dump(path) == before

    _attribute_capital_dividend(path)
    before = dump(path)
    for _ in range(2):
        with pytest.raises(RuntimeError, match='unresolved ownership'):
            create_app(_config_for(path))
        assert dump(path) == before

    # Explicit, evidence-based operator repair; startup must never do this.
    with sqlite3.connect(path) as connection:
        connection.execute('ALTER TABLE capital ADD COLUMN user_id INTEGER')
        connection.execute('UPDATE capital SET user_id=1 WHERE id=1')
    close_app(create_app(_config_for(path)))
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT id,user_id FROM portfolio').fetchall() == [(1, 1)]
        assert connection.execute('SELECT id,portfolio_id,symbol,amount,notes FROM dividend').fetchall() == [
            (1, 1, 'AAPL', '75', 'unattributed'),
        ]
        assert connection.execute('SELECT id,amount_delta FROM portfolio_event').fetchall() == [(1, '5000')]
        assert connection.execute('SELECT id,price,quantity,fees FROM "transaction"').fetchall() == [(1, '100', '10', '0')]
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
    after = dump(path)
    close_app(create_app(_config_for(path)))
    assert dump(path) == after


@pytest.mark.parametrize('owner', [None, 999])
def test_schema40_unresolved_owner_blocks_without_changes_then_retries(tmp_path, owner):
    path = tmp_path / 'owner40.sqlite'
    _create_version_33_no_action_database(path)
    close_app(create_app(_config_for(path)))
    with sqlite3.connect(path) as connection:
        if owner is None:
            # Imported legacy tables can retain nullable ownership on schema 40.
            connection.executescript('''
                CREATE TABLE nullable_portfolio AS SELECT * FROM portfolio;
                DROP TABLE portfolio;
                ALTER TABLE nullable_portfolio RENAME TO portfolio;
                CREATE UNIQUE INDEX ix_nullable_portfolio_id ON portfolio(id);
            ''')
        connection.execute('UPDATE portfolio SET user_id=? WHERE id=51', (owner,))
        connection.execute('PRAGMA user_version=40')
    before = dump(path)
    with pytest.raises(RuntimeError, match='unresolved ownership'):
        create_app(_config_for(path))
    assert dump(path) == before
    with sqlite3.connect(path) as connection:
        owner_id = connection.execute('SELECT id FROM user').fetchone()[0]
        connection.execute('UPDATE portfolio SET user_id=? WHERE id=51', (owner_id,))
    close_app(create_app(_config_for(path)))
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT id,amount FROM dividend').fetchall() == [(63, '25')]
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 41


def test_ownership_preflight_allows_retry_during_legacy_parent_rename(tmp_path):
    path = tmp_path / 'partial-rename.sqlite'
    _create_capital_era_database(path)
    _attribute_capital_dividend(path)
    with sqlite3.connect(path) as connection:
        # Step 1 committed; child column renames have not run yet.
        connection.execute('ALTER TABLE capital RENAME TO fund')
    close_app(create_app(_config_for(path)))
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT id,user_id FROM portfolio').fetchall() == [(1, 1)]
        assert connection.execute('SELECT id,amount FROM dividend').fetchall() == [(1, '75')]
