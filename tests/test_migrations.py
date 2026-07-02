from pathlib import Path

from config import Config
from portfolio_app import create_app, db
from portfolio_app.migrations import TARGET_SCHEMA_VERSION
from portfolio_app.models.portfolio import Portfolio
from portfolio_app.models.user import User
from sqlalchemy import text


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
    }.issubset(_table_names(app))
    assert _pragma_scalar(app, 'user_version') == TARGET_SCHEMA_VERSION


def test_warm_startup_is_idempotent_and_preserves_existing_data(tmp_path):
    db_path = tmp_path / 'warm.sqlite'
    first_app = create_app(_config_for(db_path))

    with first_app.app_context():
        user = User(username='warm', email='warm@example.com', is_verified=True)
        user.set_password('test-password')
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
        assert db.session.execute(text('PRAGMA user_version')).scalar() == TARGET_SCHEMA_VERSION


def test_sqlite_foreign_keys_are_on_after_startup(tmp_path):
    app = create_app(_config_for(tmp_path / 'foreign_keys.sqlite'))

    assert _pragma_scalar(app, 'foreign_keys') == 1


def test_application_factory_runs_migrations_before_create_all(tmp_path, monkeypatch):
    import portfolio_app.migrations as migrations

    order = []
    original_run_migrations = migrations.run_migrations
    original_create_all = db.create_all

    def _recording_run_migrations(app):
        order.append('migrations')
        return original_run_migrations(app)

    def _recording_create_all(*args, **kwargs):
        order.append('create_all')
        return original_create_all(*args, **kwargs)

    monkeypatch.setattr(migrations, 'run_migrations', _recording_run_migrations)
    monkeypatch.setattr(db, 'create_all', _recording_create_all)

    db_path = tmp_path / 'ordering.sqlite'
    create_app(_config_for(db_path))

    assert order == ['migrations', 'create_all']
    repo_tests_dir = Path(__file__).resolve().parent
    assert not db_path.resolve().is_relative_to(repo_tests_dir)
