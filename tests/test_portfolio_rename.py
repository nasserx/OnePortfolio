from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock

import pytest

from config import Config
from portfolio_app import create_app, db
from portfolio_app.models.portfolio import Portfolio
from portfolio_app.models.portfolio_event import PortfolioEvent
from portfolio_app.models.transaction import Transaction
from portfolio_app.models.user import User
from tests._auth import authenticate_client
from portfolio_app.services.factory import Services
from portfolio_app.utils.messages import MESSAGES


AJAX_HEADERS = {'X-Requested-With': 'XMLHttpRequest'}


def _seed_user(username):
    user = User(
        username=username,
        email=f'{username}@example.com',
        is_verified=True,
    )
    user.password_hash = 'legacy-test-hash'
    db.session.add(user)
    db.session.commit()
    return user.id


def _login(client, user_id):
    authenticate_client(client, user_id)


def _post_rename(client, portfolio_id, name):
    return client.post(
        f'/portfolios/rename/{portfolio_id}',
        data={'name': name},
        headers=AJAX_HEADERS,
    )


def test_rename_service_commits_once_and_preserves_identity_and_children(app):
    with app.app_context():
        user_id = _seed_user('rename_service')
        services = Services(user_id=user_id)
        portfolio = services.portfolio_service.create_portfolio('Growth', user_id=user_id)
        services.portfolio_service.deposit_funds(
            portfolio.id,
            Decimal('1000'),
            date=datetime(2024, 1, 1),
        )
        transaction = services.transaction_service.add_transaction(
            portfolio_id=portfolio.id,
            transaction_type='Buy',
            symbol='AAPL',
            price=Decimal('100'),
            quantity=Decimal('1'),
            fees=Decimal('0'),
            date=datetime(2024, 1, 2),
        )
        portfolio_id = portfolio.id
        event_ids = [event.id for event in portfolio.events.all()]
        transaction_id = transaction.id

        original_commit = services.portfolio_repo.commit
        services.portfolio_repo.commit = Mock(wraps=original_commit)

        renamed = services.portfolio_service.rename_portfolio(
            portfolio_id,
            '  Long Term  ',
        )

        assert renamed.id == portfolio_id
        assert renamed.name == 'Long Term'
        services.portfolio_repo.commit.assert_called_once_with()

        db.session.expire_all()
        stored = db.session.get(Portfolio, portfolio_id)
        assert stored.name == 'Long Term'
        assert [event.id for event in stored.events.all()] == event_ids
        assert db.session.get(PortfolioEvent, event_ids[0]).portfolio_id == portfolio_id
        assert db.session.get(Transaction, transaction_id).portfolio_id == portfolio_id


def test_rename_route_trims_name_and_returns_existing_ajax_contract(app):
    with app.app_context():
        user_id = _seed_user('rename_route')
        portfolio = Services(user_id=user_id).portfolio_service.create_portfolio(
            'Growth', user_id=user_id,
        )
        portfolio_id = portfolio.id

    client = app.test_client()
    _login(client, user_id)
    response = _post_rename(client, portfolio_id, '  Retirement  ')

    assert response.status_code == 200
    assert response.get_json() == {
        'success': True,
        'message': MESSAGES['PORTFOLIO_RENAMED'],
    }

    with app.app_context():
        assert db.session.get(Portfolio, portfolio_id).name == 'Retirement'


@pytest.mark.parametrize(
    ('name', 'message'),
    [
        ('   ', MESSAGES['FIELD_REQUIRED']),
        ('A' * 21, MESSAGES['NAME_TOO_LONG']),
    ],
)
def test_rename_rejects_invalid_portfolio_names(app, name, message):
    with app.app_context():
        user_id = _seed_user('rename_invalid')
        portfolio = Services(user_id=user_id).portfolio_service.create_portfolio(
            'Growth', user_id=user_id,
        )
        portfolio_id = portfolio.id

    client = app.test_client()
    _login(client, user_id)
    response = _post_rename(client, portfolio_id, name)

    assert response.status_code == 400
    assert response.get_json() == {
        'success': False,
        'errors': {'name': message},
    }

    with app.app_context():
        assert db.session.get(Portfolio, portfolio_id).name == 'Growth'


def test_rename_rejects_case_insensitive_duplicate(app):
    with app.app_context():
        user_id = _seed_user('rename_duplicate')
        services = Services(user_id=user_id)
        portfolio = services.portfolio_service.create_portfolio('Growth', user_id=user_id)
        services.portfolio_service.create_portfolio('Income', user_id=user_id)
        portfolio_id = portfolio.id

    client = app.test_client()
    _login(client, user_id)
    response = _post_rename(client, portfolio_id, '  iNcOmE  ')

    assert response.status_code == 400
    assert response.get_json()['errors']['name'] == MESSAGES['PORTFOLIO_NAME_TAKEN']


def test_rename_to_same_normalized_name_is_a_no_op(app):
    with app.app_context():
        user_id = _seed_user('rename_noop')
        services = Services(user_id=user_id)
        portfolio = services.portfolio_service.create_portfolio('Growth', user_id=user_id)
        services.portfolio_repo.commit = Mock()

        unchanged = services.portfolio_service.rename_portfolio(
            portfolio.id,
            '  gRoWtH  ',
        )

        assert unchanged is portfolio
        assert unchanged.name == 'Growth'
        services.portfolio_repo.commit.assert_not_called()


def test_rename_cannot_access_another_users_portfolio(app):
    with app.app_context():
        owner_id = _seed_user('rename_owner')
        other_id = _seed_user('rename_other')
        portfolio = Services(user_id=owner_id).portfolio_service.create_portfolio(
            'Private', user_id=owner_id,
        )
        portfolio_id = portfolio.id

    client = app.test_client()
    _login(client, other_id)
    response = _post_rename(client, portfolio_id, 'Stolen')

    assert response.status_code == 400
    assert response.get_json() == {
        'success': False,
        'errors': {'__all__': MESSAGES['PORTFOLIO_NOT_FOUND']},
    }

    with app.app_context():
        assert db.session.get(Portfolio, portfolio_id).name == 'Private'


def test_portfolios_page_renders_rename_action_and_modal_contract(app):
    with app.app_context():
        user_id = _seed_user('rename_render')
        portfolio = Services(user_id=user_id).portfolio_service.create_portfolio(
            'Growth', user_id=user_id,
        )
        portfolio_id = portfolio.id

    client = app.test_client()
    _login(client, user_id)
    response = client.get('/portfolios/')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'id="renamePortfolioModal"' in html
    assert 'aria-labelledby="renamePortfolioModalTitle"' in html
    assert 'id="renamePortfolioForm"' in html
    assert 'name="csrf_token"' in html
    assert 'id="rename_portfolio_name" name="name"' in html
    assert 'maxlength="20"' in html
    assert 'class="dropdown-item js-rename-portfolio-btn"' in html
    assert f'data-portfolio-id="{portfolio_id}"' in html
    assert 'data-name="Growth"' in html
    assert '<span>Rename</span>' in html


def test_rename_ajax_requires_csrf_token(tmp_path):
    class CsrfConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = True
        SECRET_KEY = 'rename-csrf-secret'
        MAIL_SUPPRESS_SEND = True
        RATELIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'rename-csrf.db').as_posix()}"

    csrf_app = create_app(CsrfConfig)
    with csrf_app.app_context():
        db.create_all()
        user_id = _seed_user('rename_csrf')
        portfolio = Services(user_id=user_id).portfolio_service.create_portfolio(
            'Growth', user_id=user_id,
        )
        portfolio_id = portfolio.id

    client = csrf_app.test_client()
    _login(client, user_id)
    response = _post_rename(client, portfolio_id, 'Retirement')

    assert response.status_code == 400
    assert response.get_json() == {
        'success': False,
        'error': MESSAGES['SESSION_EXPIRED'],
    }

    with csrf_app.app_context():
        assert db.session.get(Portfolio, portfolio_id).name == 'Growth'
