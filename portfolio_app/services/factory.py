"""Service factory — single source of truth for service instantiation."""

from typing import Optional
from flask import g
from portfolio_app import db
from portfolio_app.models import (
    AuthChallenge,
    Portfolio,
    PortfolioEvent,
    Transaction,
    Symbol,
    Dividend,
    PortfolioTransfer,
)
from portfolio_app.models.user import User
from portfolio_app.repositories import (
    PortfolioRepository,
    PortfolioEventRepository,
    TransactionRepository,
    SymbolRepository,
    DividendRepository,
    AuthChallengeRepository,
)
from portfolio_app.repositories.user_repository import UserRepository
from portfolio_app.repositories.pending_registration_repository import (
    PendingRegistrationRepository,
)
from portfolio_app.models.pending_registration import PendingRegistration
from portfolio_app.services.portfolio_service import PortfolioService
from portfolio_app.services.transaction_service import TransactionService
from portfolio_app.services.overview_service import OverviewService
from portfolio_app.services.auth_service import AuthService
from portfolio_app.services.transfer_service import TransferService
from portfolio_app.repositories.portfolio_transfer_repository import PortfolioTransferRepository
from portfolio_app.repositories.financial_audit_repository import FinancialAuditRepository


class Services:
    """Container holding all service and repository instances for a request."""

    __slots__ = (
        'portfolio_repo', 'portfolio_event_repo', 'transaction_repo', 'symbol_repo',
        'dividend_repo', 'user_repo', 'pending_registration_repo',
        'auth_challenge_repo',
        'portfolio_service', 'transaction_service', 'overview_service',
        'auth_service',
        'transfer_repo', 'transfer_service',
        'audit_repo',
    )

    def __init__(self, user_id: Optional[int] = None):
        self.portfolio_repo = PortfolioRepository(Portfolio, db, user_id=user_id)
        self.audit_repo = FinancialAuditRepository(user_id)
        self.portfolio_event_repo = PortfolioEventRepository(PortfolioEvent, db, user_id=user_id)
        self.transaction_repo = TransactionRepository(Transaction, db, user_id=user_id)
        self.symbol_repo = SymbolRepository(Symbol, db, user_id=user_id)
        self.dividend_repo = DividendRepository(Dividend, db, user_id=user_id)
        self.transfer_repo = PortfolioTransferRepository(PortfolioTransfer, db, user_id=user_id)
        self.transfer_service = TransferService(self.portfolio_repo, self.transfer_repo)
        self.user_repo = UserRepository(User, db)
        self.pending_registration_repo = PendingRegistrationRepository(PendingRegistration, db)
        self.auth_challenge_repo = AuthChallengeRepository(AuthChallenge, db)

        self.portfolio_service = PortfolioService(self.portfolio_repo, self.portfolio_event_repo)
        self.transaction_service = TransactionService(
            self.transaction_repo, self.symbol_repo, self.portfolio_repo,
            dividend_repo=self.dividend_repo,
        )
        self.overview_service = OverviewService(user_id=user_id)
        self.auth_service = AuthService(
            self.user_repo,
            self.pending_registration_repo,
            self.auth_challenge_repo,
        )


def get_services() -> Services:
    """Get service instances, cached per request in Flask's ``g`` object."""
    if not hasattr(g, '_services'):
        from flask_login import current_user
        uid = current_user.id if current_user.is_authenticated else None
        g._services = Services(user_id=uid)
    return g._services
