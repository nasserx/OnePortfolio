from pathlib import Path

import pytest

from config import Config
from portfolio_app import create_app, db


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key'
    MAIL_SUPPRESS_SEND = True
    RATELIMIT_ENABLED = False


def _sqlite_uri(path: Path) -> str:
    return f"sqlite:///{path.resolve().as_posix()}"


@pytest.fixture(scope="session")
def test_db_path(tmp_path_factory):
    return tmp_path_factory.mktemp("oneportfolio-db") / "test.sqlite"


@pytest.fixture(scope="session")
def app(test_db_path):
    class _SessionTestConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = _sqlite_uri(test_db_path)

    app = create_app(_SessionTestConfig)
    with app.app_context():
        db.create_all()
    return app


def _clear_database():
    db.session.rollback()
    db.create_all()
    meta = db.metadata
    for table in reversed(meta.sorted_tables):
        db.session.execute(table.delete())
    db.session.commit()
    db.session.remove()


@pytest.fixture(autouse=True)
def clean_database(app):
    with app.app_context():
        _clear_database()
    yield
    with app.app_context():
        _clear_database()
