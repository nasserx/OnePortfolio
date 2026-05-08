import pytest
from pathlib import Path
from config import Config
from portfolio_app import create_app


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = (
        f"sqlite:///{(Path(__file__).resolve().parent / 'test_portfolio.db').as_posix()}"
    )


@pytest.fixture(scope="session")
def app():
    return create_app(TestConfig)
