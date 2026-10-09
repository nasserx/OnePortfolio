"""Bind authenticated financial responses to one account and SQL snapshot."""

from functools import wraps

from flask import current_app
from flask_login import current_user, logout_user

from portfolio_app import db
from portfolio_app.models import User
from portfolio_app.repositories.read_snapshot import read_snapshot


def authenticated_report(view):
    @wraps(view)
    def guarded(*args, **kwargs):
        if not current_user.is_authenticated:
            return view(*args, **kwargs)  # Existing landing/login-required behavior.
        uid, identity = current_user.id, current_user.get_id()
        with read_snapshot():
            # Pin the account check and every subsequent report query to the
            # same database state, including history accessed during rendering.
            account = db.session.get(User, uid)
            if account is None or not account.is_verified or account.get_id() != identity:
                logout_user()
                return current_app.login_manager.unauthorized()
            return view(*args, **kwargs)
    return guarded


def register_financial_reads(app):
    for endpoint in (
        'dashboard.index', 'dashboard.api_portfolio_summary', 'dashboard.api_holdings',
        'transactions.transaction_list', 'portfolios.portfolios_list',
        'portfolios.portfolios_withdrawal_max',
    ):
        app.view_functions[endpoint] = authenticated_report(app.view_functions[endpoint])
