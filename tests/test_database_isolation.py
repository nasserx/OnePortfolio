from pathlib import Path

from portfolio_app import db
from portfolio_app.models.user import User


def test_pytest_database_path_is_temporary_and_outside_tests(app, test_db_path):
    repo_tests_dir = Path(app.root_path).parent / 'tests'

    assert test_db_path.name == 'test.sqlite'
    assert test_db_path.exists()
    assert not test_db_path.resolve().is_relative_to(repo_tests_dir)


def test_database_starts_empty_before_creating_user(app):
    with app.app_context():
        assert User.query.count() == 0
        user = User(username='isolation_a', email='isolation_a@example.com', is_verified=True)
        user.set_password('test-password')
        db.session.add(user)
        db.session.commit()
        assert User.query.count() == 1


def test_database_is_empty_after_previous_test_created_user(app):
    with app.app_context():
        assert User.query.count() == 0
