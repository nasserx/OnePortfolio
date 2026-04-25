"""Service factory — single source of truth for service instantiation."""

import logging
from typing import Optional
from flask import g
from portfolio_app import db
from portfolio_app.models import Portfolio, PortfolioEvent, Transaction, Symbol, Dividend
from portfolio_app.models.user import User
from portfolio_app.repositories import (
    PortfolioRepository,
    PortfolioEventRepository,
    TransactionRepository,
    SymbolRepository,
    DividendRepository,
)
from portfolio_app.repositories.user_repository import UserRepository
from portfolio_app.services.portfolio_service import PortfolioService
from portfolio_app.services.transaction_service import TransactionService
from portfolio_app.services.overview_service import OverviewService
from portfolio_app.services.auth_service import AuthService

logger = logging.getLogger(__name__)


class Services:
    """Container holding all service and repository instances for a request."""

    __slots__ = (
        'portfolio_repo', 'portfolio_event_repo', 'transaction_repo', 'symbol_repo',
        'dividend_repo', 'user_repo',
        'portfolio_service', 'transaction_service', 'overview_service',
        'auth_service',
    )

    def __init__(self, user_id: Optional[int] = None):
        self.portfolio_repo = PortfolioRepository(Portfolio, db, user_id=user_id)
        self.portfolio_event_repo = PortfolioEventRepository(PortfolioEvent, db, user_id=user_id)
        self.transaction_repo = TransactionRepository(Transaction, db, user_id=user_id)
        self.symbol_repo = SymbolRepository(Symbol, db, user_id=user_id)
        self.dividend_repo = DividendRepository(Dividend, db, user_id=user_id)
        self.user_repo = UserRepository(User, db)

        self.portfolio_service = PortfolioService(self.portfolio_repo, self.portfolio_event_repo)
        self.transaction_service = TransactionService(
            self.transaction_repo, self.symbol_repo, self.portfolio_repo,
            dividend_repo=self.dividend_repo,
        )
        self.overview_service = OverviewService(self.portfolio_repo, user_id=user_id)
        self.auth_service = AuthService(self.user_repo)


def get_services() -> Services:
    """Get service instances, cached per request in Flask's ``g`` object."""
    if not hasattr(g, '_services'):
        from flask_login import current_user
        uid = current_user.id if current_user.is_authenticated else None
        g._services = Services(user_id=uid)
    return g._services
