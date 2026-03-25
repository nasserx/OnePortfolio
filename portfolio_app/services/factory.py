"""Service factory — single source of truth for service instantiation."""

import logging
from typing import Optional
from flask import g
from portfolio_app import db
from portfolio_app.models import Fund, FundEvent, Transaction, Asset, Dividend
from portfolio_app.models.user import User
from portfolio_app.repositories import (
    FundRepository,
    FundEventRepository,
    TransactionRepository,
    AssetRepository,
    DividendRepository,
)
from portfolio_app.repositories.user_repository import UserRepository
from portfolio_app.services.fund_service import FundService
from portfolio_app.services.transaction_service import TransactionService
from portfolio_app.services.portfolio_service import PortfolioService
from portfolio_app.services.auth_service import AuthService

logger = logging.getLogger(__name__)


class Services:
    """Container holding all service and repository instances for a request."""

    __slots__ = (
        'fund_repo', 'event_repo', 'transaction_repo', 'asset_repo',
        'dividend_repo', 'user_repo',
        'fund_service', 'transaction_service', 'portfolio_service',
        'auth_service',
    )

    def __init__(self, user_id: Optional[int] = None):
        self.fund_repo = FundRepository(Fund, db, user_id=user_id)
        self.event_repo = FundEventRepository(FundEvent, db)
        self.transaction_repo = TransactionRepository(Transaction, db)
        self.asset_repo = AssetRepository(Asset, db)
        self.dividend_repo = DividendRepository(Dividend, db)
        self.user_repo = UserRepository(User, db)

        self.fund_service = FundService(self.fund_repo, self.event_repo)
        self.transaction_service = TransactionService(
            self.transaction_repo, self.asset_repo, self.fund_repo,
            dividend_repo=self.dividend_repo,
        )
        self.portfolio_service = PortfolioService(self.fund_repo, user_id=user_id)
        self.auth_service = AuthService(self.user_repo)


def get_services() -> Services:
    """Get service instances, cached per request in Flask's ``g`` object."""
    if not hasattr(g, '_services'):
        from flask_login import current_user
        uid = current_user.id if current_user.is_authenticated else None
        g._services = Services(user_id=uid)
    return g._services
