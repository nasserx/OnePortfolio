"""RCR-09: the obsolete ``init_db.py`` schema path stays retired.

``init_db.py`` called ``create_app()`` — which already brings the database to
target under the startup schema lock — and then re-ran an unlocked
``db.create_all()`` plus a private one-step copy of the migration system. That
copy still targeted the ``capital`` table, renamed to ``fund`` and then
``portfolio`` by migration steps, so the script raised
``NoSuchTableError: capital`` on every run against a current database. It was
retired rather than repaired: deploying and starting the application *is* the
initialization.

The authoritative path itself is already covered elsewhere —
``test_application_factory_runs_migrations_before_create_all`` in
tests/test_migrations.py, and the whole of
tests/test_migration_startup_coordination.py. These two checks add only what
those cannot see: that the retired competitor has not come back.
"""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_the_obsolete_init_db_script_is_gone():
    assert not (REPO_ROOT / 'init_db.py').exists()


def test_no_supported_documentation_references_it():
    docs = sorted(REPO_ROOT.glob('*.md')) + sorted((REPO_ROOT / 'docs').glob('*.md'))
    stale = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in docs
        if 'init_db' in path.read_text(encoding='utf-8')
    ]

    assert stale == [], 'docs still point at the retired script: {0}'.format(stale)
