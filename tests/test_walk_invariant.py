"""Chronological-walk invariant — error-message disambiguation.

The transaction service's ``_assert_walk_non_negative`` raises
``ValidationError`` when a proposed add/edit/delete would drive the
running quantity below zero on the (portfolio, symbol) timeline. The
message is now context-aware:

  * the proposed Sell itself can't fit at its date    → INSUFFICIENT_QUANTITY
  * an existing later Sell becomes uncovered          → LATER_SELL_NEEDS_BUY

This file pins that contract — same scenario the user surfaced where
deleting a Buy with a later Sell used to surface a misleading
"Insufficient quantity." banner.
"""

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from config import Config
from portfolio_app import create_app, db
from portfolio_app.models import Transaction
from portfolio_app.models.user import User
from portfolio_app.calculators import PortfolioCalculator
from portfolio_app.services import ValidationError
from portfolio_app.services.factory import Services
from portfolio_app.utils.messages import MESSAGES


class _TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = (
        f"sqlite:///{(Path(__file__).resolve().parent / 'test_walk.db').as_posix()}"
    )


def _dec(v):
    return Decimal(str(v))


def _seed_user(username='walker'):
    user = User(username=username, email=f'{username}@example.com', is_verified=True)
    user.set_password('test-password')
    db.session.add(user)
    db.session.commit()
    return user.id


@pytest.fixture
def app():
    app = create_app(_TestConfig)
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield app


def _seed_buy_then_sell(svc, portfolio_id, *, buy_qty=10, sell_qty=5):
    """Buy on Jan 1, partial Sell on Jan 5 — the scenario where deleting
    the Buy would leave the Sell uncovered."""
    buy = Transaction(
        portfolio_id=portfolio_id, transaction_type='Buy',
        date=datetime(2026, 1, 1), symbol='AAPL',
        price=100, quantity=buy_qty, fees=0,
    )
    buy.calculate_net_amount()
    sell = Transaction(
        portfolio_id=portfolio_id, transaction_type='Sell',
        date=datetime(2026, 1, 5), symbol='AAPL',
        price=120, quantity=sell_qty, fees=0,
    )
    sell.calculate_net_amount()
    db.session.add_all([buy, sell])
    db.session.commit()
    PortfolioCalculator.recalculate_all_averages_for_symbol(portfolio_id, 'AAPL')
    db.session.commit()
    return buy, sell


def test_delete_buy_with_dependent_sell_uses_later_sell_message(app):
    """Deleting a Buy that a later Sell relies on must surface the
    LATER_SELL_NEEDS_BUY message, not the misleading
    INSUFFICIENT_QUANTITY one."""
    with app.app_context():
        uid = _seed_user()
        svc = Services(user_id=uid)
        p = svc.portfolio_service.create_portfolio('P', user_id=uid)
        svc.portfolio_service.deposit_funds(p.id, _dec(10_000))
        buy, _ = _seed_buy_then_sell(svc, p.id)

        with pytest.raises(ValidationError) as excinfo:
            svc.transaction_service.delete_transaction(buy.id)

        assert str(excinfo.value) == MESSAGES['LATER_SELL_NEEDS_BUY']
        assert MESSAGES['LATER_SELL_NEEDS_BUY'] != MESSAGES['INSUFFICIENT_QUANTITY']


def test_edit_buy_lower_quantity_below_dependent_sell_uses_later_sell_message(app):
    """Editing a Buy down to a quantity that a later Sell can no longer
    consume must use the LATER_SELL_NEEDS_BUY wording (the failure is
    not about the Buy's quantity being 'insufficient' from the user's
    perspective — they chose it freely)."""
    with app.app_context():
        uid = _seed_user()
        svc = Services(user_id=uid)
        p = svc.portfolio_service.create_portfolio('P', user_id=uid)
        svc.portfolio_service.deposit_funds(p.id, _dec(10_000))
        buy, _ = _seed_buy_then_sell(svc, p.id, buy_qty=10, sell_qty=8)

        with pytest.raises(ValidationError) as excinfo:
            svc.transaction_service.update_transaction(
                buy.id, quantity=_dec(5),
            )
        assert str(excinfo.value) == MESSAGES['LATER_SELL_NEEDS_BUY']


def test_edit_buy_symbol_change_orphans_later_sell_uses_later_sell_message(app):
    """Moving a Buy to a different symbol must reject when it would
    leave the old symbol's later Sell uncovered."""
    with app.app_context():
        uid = _seed_user()
        svc = Services(user_id=uid)
        p = svc.portfolio_service.create_portfolio('P', user_id=uid)
        svc.portfolio_service.deposit_funds(p.id, _dec(10_000))
        buy, _ = _seed_buy_then_sell(svc, p.id)

        with pytest.raises(ValidationError) as excinfo:
            svc.transaction_service.update_transaction(buy.id, symbol='MSFT')
        assert str(excinfo.value) == MESSAGES['LATER_SELL_NEEDS_BUY']


def test_add_sell_exceeding_holdings_keeps_insufficient_quantity_message(app):
    """A Sell whose quantity exceeds current holdings is genuinely
    'insufficient quantity' — that wording must remain unchanged so
    client-side validators still match it."""
    with app.app_context():
        uid = _seed_user()
        svc = Services(user_id=uid)
        p = svc.portfolio_service.create_portfolio('P', user_id=uid)
        svc.portfolio_service.deposit_funds(p.id, _dec(10_000))
        # 10 held; try to sell 15.
        buy = Transaction(
            portfolio_id=p.id, transaction_type='Buy',
            date=datetime(2026, 1, 1), symbol='AAPL',
            price=100, quantity=10, fees=0,
        )
        buy.calculate_net_amount()
        db.session.add(buy)
        db.session.commit()

        with pytest.raises(ValidationError) as excinfo:
            svc.transaction_service.add_transaction(
                portfolio_id=p.id, transaction_type='Sell',
                symbol='AAPL', price=_dec(120), quantity=_dec(15),
                fees=_dec(0),
            )
        assert str(excinfo.value) == MESSAGES['INSUFFICIENT_QUANTITY']


def test_edit_sell_backdated_before_buy_uses_insufficient_quantity_message(app):
    """A Sell backdated to before its covering Buy can't fit at its
    new date — that's the user's own Sell row failing, so the
    INSUFFICIENT_QUANTITY message is the right one."""
    with app.app_context():
        uid = _seed_user()
        svc = Services(user_id=uid)
        p = svc.portfolio_service.create_portfolio('P', user_id=uid)
        svc.portfolio_service.deposit_funds(p.id, _dec(10_000))
        _, sell = _seed_buy_then_sell(svc, p.id)

        with pytest.raises(ValidationError) as excinfo:
            # Backdate the Sell to before the Buy.
            svc.transaction_service.update_transaction(
                sell.id, date=datetime(2025, 12, 31),
            )
        assert str(excinfo.value) == MESSAGES['INSUFFICIENT_QUANTITY']


# ---------------------------------------------------------------------------
# Cash-clawback wording (CASH_ALREADY_SPENT vs INSUFFICIENT_AMOUNT)
# ---------------------------------------------------------------------------
#
# These pin the message wording so the user no longer sees the misleading
# "Insufficient amount." when they're trying to *remove* an inflow that
# has already been spent on a later transaction.

def test_delete_deposit_after_buy_uses_cash_already_spent(app):
    """Deleting a Deposit that's already been spent on a Buy must
    surface CASH_ALREADY_SPENT — "Insufficient amount." reads as if
    the user's input is wrong, but they're not entering a value here."""
    with app.app_context():
        uid = _seed_user()
        svc = Services(user_id=uid)
        p = svc.portfolio_service.create_portfolio('P', user_id=uid)
        svc.portfolio_service.deposit_funds(p.id, _dec(1_000))
        # Spend the deposit on a Buy.
        svc.transaction_service.add_transaction(
            portfolio_id=p.id, transaction_type='Buy',
            symbol='AAPL', price=_dec(100), quantity=_dec(10), fees=_dec(0),
        )
        # Find the deposit event and try to delete it.
        events = svc.portfolio_event_repo.get_by_portfolio_id(p.id)
        deposit = next(e for e in events if e.event_type == 'Deposit')

        with pytest.raises(ValueError) as excinfo:
            svc.portfolio_service.delete_portfolio_event(deposit.id)
        assert str(excinfo.value) == MESSAGES['CASH_ALREADY_SPENT']


def test_lower_deposit_below_spent_uses_cash_already_spent(app):
    """Lowering a Deposit below what's been spent on later Buys must
    use CASH_ALREADY_SPENT (not INSUFFICIENT_AMOUNT)."""
    with app.app_context():
        uid = _seed_user()
        svc = Services(user_id=uid)
        p = svc.portfolio_service.create_portfolio('P', user_id=uid)
        svc.portfolio_service.deposit_funds(p.id, _dec(1_000))
        svc.transaction_service.add_transaction(
            portfolio_id=p.id, transaction_type='Buy',
            symbol='AAPL', price=_dec(100), quantity=_dec(10), fees=_dec(0),
        )
        events = svc.portfolio_event_repo.get_by_portfolio_id(p.id)
        deposit = next(e for e in events if e.event_type == 'Deposit')

        with pytest.raises(ValueError) as excinfo:
            svc.portfolio_service.update_portfolio_event(
                deposit.id, amount_delta=_dec(500),
            )
        assert str(excinfo.value) == MESSAGES['CASH_ALREADY_SPENT']


def test_delete_dividend_after_spent_uses_cash_already_spent(app):
    """Deleting a Dividend whose cash was already spent on a later Buy
    must use CASH_ALREADY_SPENT."""
    with app.app_context():
        uid = _seed_user()
        svc = Services(user_id=uid)
        p = svc.portfolio_service.create_portfolio('P', user_id=uid)
        svc.portfolio_service.deposit_funds(p.id, _dec(1_000))
        # First Buy uses the deposit, leaving cash = 0.
        svc.transaction_service.add_transaction(
            portfolio_id=p.id, transaction_type='Buy',
            symbol='AAPL', price=_dec(100), quantity=_dec(10), fees=_dec(0),
        )
        # Dividend brings cash to 50.
        div = svc.transaction_service.add_dividend(
            portfolio_id=p.id, symbol='AAPL',
            amount=_dec(50), date=datetime(2026, 2, 1),
        )
        # Spend the 50 on another Buy → cash = 0, dividend already consumed.
        svc.transaction_service.add_transaction(
            portfolio_id=p.id, transaction_type='Buy',
            symbol='AAPL', price=_dec(50), quantity=_dec(1), fees=_dec(0),
        )

        with pytest.raises(ValueError) as excinfo:
            svc.transaction_service.delete_dividend(div.id)
        assert str(excinfo.value) == MESSAGES['CASH_ALREADY_SPENT']


def test_withdraw_more_than_available_keeps_insufficient_amount(app):
    """Genuine over-withdrawal (the user is asking for more than the
    portfolio has) keeps the INSUFFICIENT_AMOUNT wording — that's the
    one case where 'Insufficient amount.' is accurate."""
    with app.app_context():
        uid = _seed_user()
        svc = Services(user_id=uid)
        p = svc.portfolio_service.create_portfolio('P', user_id=uid)
        svc.portfolio_service.deposit_funds(p.id, _dec(100))

        with pytest.raises(ValueError) as excinfo:
            svc.portfolio_service.withdraw_funds(p.id, _dec(500))
        assert str(excinfo.value) == MESSAGES['INSUFFICIENT_AMOUNT']


# ---------------------------------------------------------------------------
# AJAX responses — the route must return JSON so the modal can show the
# error inline. Previously these routes always did flash+redirect, which
# the central ModalAjaxHandler couldn't display in the dialog.
# ---------------------------------------------------------------------------

def test_delete_event_route_returns_json_for_ajax_clawback(app):
    """The Confirm Remove dialog needs CASH_ALREADY_SPENT to come back
    as JSON `errors.__all__` so the modal banner can render it. Pin
    that contract so we don't silently regress to flash+redirect."""
    with app.app_context():
        uid = _seed_user('ajaxer')
        svc = Services(user_id=uid)
        p = svc.portfolio_service.create_portfolio('P', user_id=uid)
        svc.portfolio_service.deposit_funds(p.id, _dec(1_000))
        svc.transaction_service.add_transaction(
            portfolio_id=p.id, transaction_type='Buy',
            symbol='AAPL', price=_dec(100), quantity=_dec(10), fees=_dec(0),
        )
        events = svc.portfolio_event_repo.get_by_portfolio_id(p.id)
        deposit_id = next(e.id for e in events if e.event_type == 'Deposit')

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)
        sess['_fresh'] = True

    resp = client.post(
        f'/portfolios/events/delete/{deposit_id}',
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )

    assert resp.status_code == 400
    assert resp.is_json
    body = resp.get_json()
    assert body['success'] is False
    assert body['errors']['__all__'] == MESSAGES['CASH_ALREADY_SPENT']


def test_delete_event_route_keeps_redirect_for_non_ajax(app):
    """Non-AJAX (curl, JS-disabled) clients still get the legacy
    flash+redirect flow — we didn't break the fallback."""
    with app.app_context():
        uid = _seed_user('non_ajaxer')
        svc = Services(user_id=uid)
        p = svc.portfolio_service.create_portfolio('P', user_id=uid)
        svc.portfolio_service.deposit_funds(p.id, _dec(1_000))
        svc.transaction_service.add_transaction(
            portfolio_id=p.id, transaction_type='Buy',
            symbol='AAPL', price=_dec(100), quantity=_dec(10), fees=_dec(0),
        )
        events = svc.portfolio_event_repo.get_by_portfolio_id(p.id)
        deposit_id = next(e.id for e in events if e.event_type == 'Deposit')

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)
        sess['_fresh'] = True

    resp = client.post(f'/portfolios/events/delete/{deposit_id}')
    # Plain POST → redirect, message in flash queue (handled by
    # AlertManager on the next page render).
    assert resp.status_code in (302, 303)
