#!/usr/bin/env python3
"""
Comprehensive test suite for the OnePortfolio application.

Tests cover:
  - Transaction calculations (average cost, realized P&L)
  - Fund events: Total Funds = deposits only (withdrawals excluded)
  - Cash balance calculation (deposits - withdrawals - buys + sells)
  - Category summary (Overview cards): correct amounts and ROI
  - Portfolio dashboard totals
  - Application routes (HTTP 200 checks)
"""

from portfolio_app import create_app, db
from portfolio_app.models import Fund, Transaction, FundEvent
from portfolio_app.calculators import PortfolioCalculator
from portfolio_app.services.factory import Services
from datetime import datetime
from decimal import Decimal
from config import Config
from pathlib import Path

ZERO = Decimal('0')


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = (
        f"sqlite:///{(Path(__file__).resolve().parent / 'test_portfolio.db').as_posix()}"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dec(v) -> Decimal:
    return Decimal(str(v))


def _assert(label: str, expected, actual, tol=_dec('0.01')):
    ok = abs(_dec(str(expected)) - _dec(str(actual))) < tol
    status = 'PASS' if ok else 'FAIL'
    print(f"  {status}  {label}")
    print(f"         expected={expected}  actual={actual}")
    if not ok:
        raise AssertionError(f"{label}: expected {expected}, got {actual}")


# ---------------------------------------------------------------------------
# Test 1 – Transaction calculations (unchanged logic)
# ---------------------------------------------------------------------------

def test_transaction_calculations(app):
    """Verify average cost and realized P&L for buy/sell transactions."""
    with app.app_context():
        db.drop_all()
        db.create_all()

        svc = Services()

        # --- Commodities: XAU (2 buys, no sell) ---
        comm = svc.fund_service.create_fund('Commodities', _dec(25000))
        t1 = Transaction(fund_id=comm.id, transaction_type='Buy',
                         date=datetime(2026, 1, 10), symbol='XAU',
                         price=2000, quantity=1.5, fees=50)
        t1.calculate_net_amount()
        t2 = Transaction(fund_id=comm.id, transaction_type='Buy',
                         date=datetime(2026, 1, 15), symbol='XAU',
                         price=2050, quantity=1.0, fees=30)
        t2.calculate_net_amount()

        # --- Stocks: AAPL (2 buys) + MSFT (1 buy) ---
        stocks = svc.fund_service.create_fund('Stocks', _dec(40000))
        t3 = Transaction(fund_id=stocks.id, transaction_type='Buy',
                         date=datetime(2026, 1, 8), symbol='AAPL',
                         price=100, quantity=50, fees=25)
        t3.calculate_net_amount()
        t4 = Transaction(fund_id=stocks.id, transaction_type='Buy',
                         date=datetime(2026, 1, 12), symbol='AAPL',
                         price=105, quantity=30, fees=15)
        t4.calculate_net_amount()
        t5 = Transaction(fund_id=stocks.id, transaction_type='Buy',
                         date=datetime(2026, 1, 9), symbol='MSFT',
                         price=200, quantity=10, fees=10)
        t5.calculate_net_amount()

        # --- ETFs: ETHA (buy, partial sell, buy again) ---
        etfs = svc.fund_service.create_fund('ETFs', _dec(200))
        e1 = Transaction(fund_id=etfs.id, transaction_type='Buy',
                         date=datetime(2026, 1, 1), symbol='ETHA',
                         price=10, quantity=10, fees=0)
        e1.calculate_net_amount()
        e2 = Transaction(fund_id=etfs.id, transaction_type='Sell',
                         date=datetime(2026, 1, 2), symbol='ETHA',
                         price=12, quantity=5, fees=1)
        e2.calculate_net_amount()
        e3 = Transaction(fund_id=etfs.id, transaction_type='Buy',
                         date=datetime(2026, 1, 3), symbol='ETHA',
                         price=10, quantity=5, fees=0)
        e3.calculate_net_amount()

        db.session.add_all([t1, t2, t3, t4, t5, e1, e2, e3])
        db.session.commit()

        PortfolioCalculator.recalculate_all_averages_for_symbol(comm.id, 'XAU')
        PortfolioCalculator.recalculate_all_averages_for_symbol(stocks.id, 'AAPL')
        PortfolioCalculator.recalculate_all_averages_for_symbol(stocks.id, 'MSFT')
        PortfolioCalculator.recalculate_all_averages_for_symbol(etfs.id, 'ETHA')
        db.session.commit()

        print("\n" + "=" * 60)
        print("TEST 1 – TRANSACTION CALCULATIONS")
        print("=" * 60)

        # XAU average cost
        xau = PortfolioCalculator.get_symbol_transactions_summary(comm.id, 'XAU')
        expected_xau_avg = (1.5 * 2000 + 50 + 1.0 * 2050 + 30) / (1.5 + 1.0)
        _assert('XAU average cost', round(expected_xau_avg, 4), xau['average_cost'])

        # AAPL average cost
        aapl = PortfolioCalculator.get_symbol_transactions_summary(stocks.id, 'AAPL')
        expected_aapl_avg = (50 * 100 + 25 + 30 * 105 + 15) / (50 + 30)
        _assert('AAPL average cost', round(expected_aapl_avg, 4), aapl['average_cost'])

        # MSFT must not mix with AAPL
        msft = PortfolioCalculator.get_symbol_transactions_summary(stocks.id, 'MSFT')
        _assert('MSFT average cost (isolated)', (10 * 200 + 10) / 10, msft['average_cost'])

        # ETHA: buy 10@10, sell 5@12 (-1 fee), buy 5@10
        etha = PortfolioCalculator.get_symbol_transactions_summary(etfs.id, 'ETHA')
        _assert('ETHA realized P&L', 9.0, etha['realized_pnl'])   # (12-10)*5 - 1 fee
        # Buy 10@10 → sell 5 (remaining cost=50) → buy 5@10 → total=100/10 = 10.0
        _assert('ETHA average cost', 10.0, etha['average_cost'])

        print("  All transaction calculation checks passed.")


# ---------------------------------------------------------------------------
# Test 2 – Fund events: Total Funds = deposits only
# ---------------------------------------------------------------------------

def test_fund_events(app):
    """
    Verify that get_total_funds_for_fund() returns the sum of Initial +
    Deposit events only, and that withdrawals do NOT inflate Total Funds.
    """
    with app.app_context():
        db.drop_all()
        db.create_all()

        svc = Services()

        print("\n" + "=" * 60)
        print("TEST 2 – FUND EVENTS (Total Funds = deposits only)")
        print("=" * 60)

        # ── Scenario A: deposits only, no withdrawals ──
        #   Initial=10,000  Deposit=5,000  → Total Funds=15,000
        fund_a = svc.fund_service.create_fund('Stocks', _dec(10_000))
        svc.fund_service.deposit_funds(fund_a.id, _dec(5_000))

        tf_a = PortfolioCalculator.get_total_funds_for_fund(fund_a.id)
        cash_a = PortfolioCalculator.get_cash_balance_for_fund(fund_a.id)

        print("\n  Scenario A – deposits only")
        _assert('Total Funds (deposits only)', 15_000, tf_a)
        _assert('Cash (no transactions)', 15_000, cash_a)
        _assert('fund.cash_balance equals cash when no transactions',
                cash_a, _dec(str(fund_a.cash_balance)))

        # ── Scenario B: deposits + withdrawals, no transactions ──
        #   Initial=10,000  Deposit=1,000  Withdraw=4,999  Withdraw=5,999
        #   Total Funds = 10,000+1,000 = 11,000
        #   fund.cash_balance = 10,000+1,000-4,999-5,999 = 2
        #   Cash = fund.cash_balance = 2 (no buys/sells)
        fund_b = svc.fund_service.create_fund('ETFs', _dec(10_000))
        svc.fund_service.deposit_funds(fund_b.id, _dec(1_000))
        svc.fund_service.withdraw_funds(fund_b.id, _dec(4_999))
        svc.fund_service.withdraw_funds(fund_b.id, _dec(5_999))
        db.session.refresh(fund_b)

        tf_b = PortfolioCalculator.get_total_funds_for_fund(fund_b.id)
        cash_b = PortfolioCalculator.get_cash_balance_for_fund(fund_b.id)

        print("\n  Scenario B – deposits + withdrawals, no transactions")
        _assert('Total Funds (deposits only, ignores withdrawals)', 11_000, tf_b)
        _assert('fund.cash_balance (net after withdrawals)', 2, _dec(str(fund_b.cash_balance)))
        _assert('Cash = fund.cash_balance when no transactions', 2, cash_b)

        # ── Scenario C: deposits + withdrawals + transactions ──
        #   Initial=10,000  Withdraw=4,999  Deposit=1,000  Withdraw=5,999
        #   fund.cash_balance = 2
        #   Buy  5000 AAPL @ $1 fees=1 → outflow=5,001
        #   Sell 2500 AAPL @ $2 fees=1 → inflow=4,999
        #   Cash = 2 - 5,001 + 4,999 = 0
        #   current_invested = cost basis of 2500 remaining = 5,001 * (2500/5000) = 2,500.50
        #   realized_pnl = (2*2500 - 1) - (5001 * 2500/5000) = 4,999 - 2,500.50 = 2,498.50
        #   Total Funds = 10,000 + 1,000 = 11,000
        #   Total Value = cash + invested = 0 + 2,500.50 = 2,500.50
        #   ROI base = 11,000  →  ROI = 2,498.50 / 11,000 = ~22.71%
        fund_c = svc.fund_service.create_fund('Crypto', _dec(10_000))
        svc.fund_service.withdraw_funds(fund_c.id, _dec(4_999))
        svc.fund_service.deposit_funds(fund_c.id, _dec(1_000))
        svc.fund_service.withdraw_funds(fund_c.id, _dec(5_999))
        db.session.refresh(fund_c)

        buy = Transaction(fund_id=fund_c.id, transaction_type='Buy',
                          date=datetime(2026, 1, 1), symbol='AAPL',
                          price=1, quantity=5000, fees=1)
        buy.calculate_net_amount()
        sell = Transaction(fund_id=fund_c.id, transaction_type='Sell',
                           date=datetime(2026, 1, 2), symbol='AAPL',
                           price=2, quantity=2500, fees=1)
        sell.calculate_net_amount()
        db.session.add_all([buy, sell])
        db.session.commit()
        PortfolioCalculator.recalculate_all_averages_for_symbol(fund_c.id, 'AAPL')
        db.session.commit()

        tf_c = PortfolioCalculator.get_total_funds_for_fund(fund_c.id)
        cash_c = PortfolioCalculator.get_cash_balance_for_fund(fund_c.id)
        tx_c = PortfolioCalculator.get_category_transactions_summary(fund_c.id)
        realized_c = PortfolioCalculator.get_realized_performance_for_fund(fund_c.id)

        print("\n  Scenario C – deposits + withdrawals + transactions")
        _assert('Total Funds (deposits only)', 11_000, tf_c)
        _assert('fund.cash_balance (net)', 2, _dec(str(fund_c.cash_balance)))
        _assert('Cash (after buys/sells)', 0, cash_c)
        _assert('Invested (cost basis of 2500 remaining)', _dec('2500.50'), tx_c['current_invested'])
        _assert('Realized P&L', _dec('2498.50'), realized_c['realized_pnl'])

        # ── Scenario D: legacy fund with no FundEvents (fallback to fund.cash_balance) ──
        #   Simulates old database where fund.cash_balance=8,000 but no events exist.
        #   get_total_funds_for_fund() must return 8,000 (not 0).
        legacy_fund = Fund(asset_class='Commodities', cash_balance=_dec(8_000))
        db.session.add(legacy_fund)
        db.session.commit()

        tf_legacy = PortfolioCalculator.get_total_funds_for_fund(legacy_fund.id)
        cash_legacy = PortfolioCalculator.get_cash_balance_for_fund(legacy_fund.id)

        print("\n  Scenario D – legacy fund (no FundEvents, fallback to fund.cash_balance)")
        _assert('Total Funds fallback = fund.cash_balance', 8_000, tf_legacy)
        _assert('Cash fallback = fund.cash_balance (no transactions)', 8_000, cash_legacy)

        print("  All fund event checks passed.")


# ---------------------------------------------------------------------------
# Test 3 – Category summary (Overview cards)
# ---------------------------------------------------------------------------

def test_category_summary(app):
    """
    Verify get_category_summary() uses deposits-only Total Funds
    and computes correct Total Value and ROI.
    """
    with app.app_context():
        db.drop_all()
        db.create_all()

        svc = Services()

        # Fund: Initial=10,000  Withdraw=4,999  Deposit=1,000  Withdraw=5,999
        # Buy 5000 AAPL @ $1 fees=1 | Sell 2500 AAPL @ $2 fees=1
        fund = svc.fund_service.create_fund('Stocks', _dec(10_000))
        svc.fund_service.withdraw_funds(fund.id, _dec(4_999))
        svc.fund_service.deposit_funds(fund.id, _dec(1_000))
        svc.fund_service.withdraw_funds(fund.id, _dec(5_999))

        buy = Transaction(fund_id=fund.id, transaction_type='Buy',
                          date=datetime(2026, 1, 1), symbol='AAPL',
                          price=1, quantity=5000, fees=1)
        buy.calculate_net_amount()
        sell = Transaction(fund_id=fund.id, transaction_type='Sell',
                           date=datetime(2026, 1, 2), symbol='AAPL',
                           price=2, quantity=2500, fees=1)
        sell.calculate_net_amount()
        db.session.add_all([buy, sell])
        db.session.commit()
        PortfolioCalculator.recalculate_all_averages_for_symbol(fund.id, 'AAPL')
        db.session.commit()

        summary, portfolio_value = PortfolioCalculator.get_category_summary()
        assert len(summary) == 1
        cat = summary[0]

        print("\n" + "=" * 60)
        print("TEST 3 – CATEGORY SUMMARY (Overview cards)")
        print("=" * 60)

        _assert('Allocated Funds (deposits only)', 11_000, cat['amount'])
        _assert('Cash', 0, cat['cash'])
        _assert('Invested', _dec('2500.50'), cat['current_invested'])
        _assert('Total Value = cash + invested', _dec('2500.50'), cat['total_value'])
        _assert('Realized P&L', _dec('2498.50'), cat['realized_pnl'])

        # ROI = 2498.50 / 11000 * 100
        expected_roi = _dec('2498.50') / _dec('11000') * 100
        _assert('Realized ROI % (base=deposits)', round(expected_roi, 2), cat['realized_roi_percent'])

        print("  All category summary checks passed.")


# ---------------------------------------------------------------------------
# Test 4 – Portfolio dashboard totals
# ---------------------------------------------------------------------------

def test_dashboard_totals(app):
    """
    Verify get_portfolio_dashboard_totals() sums Total Funds from deposits
    only across all categories.
    """
    with app.app_context():
        db.drop_all()
        db.create_all()

        svc = Services()

        # Fund A: Initial=20,000  Withdraw=5,000 → total_funds=20,000  fund.cash_balance=15,000
        fa = svc.fund_service.create_fund('Stocks', _dec(20_000))
        svc.fund_service.withdraw_funds(fa.id, _dec(5_000))

        # Fund B: Initial=10,000  Deposit=2,000 → total_funds=12,000  fund.cash_balance=12,000
        fb = svc.fund_service.create_fund('ETFs', _dec(10_000))
        svc.fund_service.deposit_funds(fb.id, _dec(2_000))

        totals = PortfolioCalculator.get_portfolio_dashboard_totals()

        print("\n" + "=" * 60)
        print("TEST 4 – PORTFOLIO DASHBOARD TOTALS")
        print("=" * 60)

        # Total Allocated = 20,000 + 12,000 = 32,000 (deposits only)
        _assert('Total Allocated (sum of deposits)', 32_000, totals['total_allocated'])

        # Cash: fund_a.cash_balance=15,000 + fund_b.cash_balance=12,000 = 27,000 (no transactions)
        _assert('Total Cash (no transactions)', 27_000, totals['total_cash'])

        # Total Value = cash + invested = 27,000 + 0 = 27,000
        _assert('Total Value', 27_000, totals['total_value'])

        print("  All dashboard totals checks passed.")


# ---------------------------------------------------------------------------
# Test 5 – Application routes (HTTP)
# ---------------------------------------------------------------------------

def test_routes(app):
    """Verify key pages return HTTP 200."""
    with app.app_context():
        db.drop_all()
        db.create_all()
        from portfolio_app.models.user import User
        user = User(username='testuser', is_verified=True)
        user.set_password('testpassword123')
        db.session.add(user)
        db.session.commit()

    client = app.test_client()
    client.post('/login', data={'username': 'testuser', 'password': 'testpassword123'})

    print("\n" + "=" * 60)
    print("TEST 5 – APPLICATION ROUTES")
    print("=" * 60)

    routes = [
        ('GET', '/',               'Dashboard'),
        ('GET', '/transactions/',  'Transactions'),
        ('GET', '/funds/',         'Funds'),
    ]
    for method, path, label in routes:
        r = client.get(path)
        status = 'PASS' if r.status_code == 200 else 'FAIL'
        print(f"  {status}  {method} {path} -> {r.status_code}  ({label})")
        assert r.status_code == 200, f"{label} route returned {r.status_code}"

    print("  All route checks passed.")


# ---------------------------------------------------------------------------
# Test 6 – Dividend feature
# ---------------------------------------------------------------------------

def test_dividends(app):
    """
    Verify dividend income is correctly:
      - Stored and retrieved per fund
      - Added to realized P&L
      - Added to cash balance
      - Protected by ownership checks (update/delete reject wrong fund)
    """
    with app.app_context():
        db.drop_all()
        db.create_all()

        from portfolio_app.models import Dividend
        from portfolio_app.models.user import User
        from portfolio_app.services.factory import Services

        # Create two users with separate funds
        u1 = User(username='alice', is_verified=True); u1.set_password('pw')
        u2 = User(username='bob',   is_verified=True); u2.set_password('pw')
        db.session.add_all([u1, u2]); db.session.commit()

        svc1 = Services(user_id=u1.id)
        svc2 = Services(user_id=u2.id)

        fund1 = svc1.fund_service.create_fund('Stocks', _dec(10_000), user_id=u1.id)
        fund2 = svc2.fund_service.create_fund('ETFs',   _dec(5_000),  user_id=u2.id)

        print("\n" + "=" * 60)
        print("TEST 6 – DIVIDEND FEATURE")
        print("=" * 60)

        # ── 6a: add dividends and verify total ──
        print("\n  6a – dividend total calculation")
        svc1.transaction_service.add_dividend(fund1.id, 'AAPL', _dec('100'), datetime(2026, 1, 10))
        svc1.transaction_service.add_dividend(fund1.id, 'AAPL', _dec('50'),  datetime(2026, 1, 20))

        total = PortfolioCalculator.get_dividend_total_for_fund(fund1.id)
        _assert('Dividend total for fund1', _dec('150'), total)

        # ── 6b: dividends added to cash balance ──
        print("\n  6b – dividends reflected in cash")
        cash = PortfolioCalculator.get_cash_balance_for_fund(fund1.id)
        # fund.cash_balance = 10,000; no buy/sell; dividends = 150 → cash = 10,150
        _assert('Cash includes dividend income', _dec('10150'), cash)

        # ── 6c: dividends added to realized P&L ──
        print("\n  6c – dividends reflected in realized P&L")
        perf = PortfolioCalculator.get_realized_performance_for_fund(fund1.id)
        _assert('Realized P&L includes dividends', _dec('150'), perf['realized_pnl'])

        # ── 6d: fund2 has zero dividends (no cross-contamination) ──
        print("\n  6d – no cross-fund contamination")
        total2 = PortfolioCalculator.get_dividend_total_for_fund(fund2.id)
        _assert('Dividend total for fund2 (none added)', _dec('0'), total2)

        # ── 6e: update dividend ──
        print("\n  6e – update dividend")
        divs = svc1.dividend_repo.get_by_fund_id(fund1.id)
        d = divs[0]
        svc1.transaction_service.update_dividend(d.id, amount=_dec('200'))
        new_total = PortfolioCalculator.get_dividend_total_for_fund(fund1.id)
        # get_by_fund_id returns newest first → divs[0] is the 50 dividend → updated to 200
        # other (100) stays → total = 100 + 200 = 300
        _assert('Total after update', _dec('300'), new_total)

        # ── 6f: ownership check – user2 cannot delete user1's dividend ──
        print("\n  6f – ownership check (cross-user delete rejected)")
        import pytest
        try:
            svc2.transaction_service.delete_dividend(d.id)
            raise AssertionError('Should have raised ValueError for wrong owner')
        except ValueError:
            print("  PASS  cross-user delete correctly rejected")

        # ── 6g: delete dividend ──
        print("\n  6g – delete dividend")
        svc1.transaction_service.delete_dividend(d.id)
        final_total = PortfolioCalculator.get_dividend_total_for_fund(fund1.id)
        # divs[0] (the 200 one) deleted → only the original 100 remains
        _assert('Total after delete (one removed)', _dec('100'), final_total)

        print("\n  All dividend checks passed.")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("  OnePortfolio – FULL TEST SUITE")
    print("=" * 60)

    app = create_app(TestConfig)
    passed = 0
    failed = 0

    tests = [
        ('Transaction Calculations',  test_transaction_calculations),
        ('Fund Events Logic',          test_fund_events),
        ('Category Summary',           test_category_summary),
        ('Dashboard Totals',           test_dashboard_totals),
        ('Application Routes',         test_routes),
        ('Dividend Feature',           test_dividends),
    ]

    for name, fn in tests:
        try:
            fn(app)
            passed += 1
        except Exception as exc:
            failed += 1
            print(f"\n  FAIL {name}: {exc}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    total = passed + failed
    print(f"  Results: {passed}/{total} tests passed")
    if failed:
        print(f"  ({failed} FAILED)")
    print("=" * 60 + "\n")
