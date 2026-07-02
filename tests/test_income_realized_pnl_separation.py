from datetime import datetime
from decimal import Decimal

from portfolio_app import db
from portfolio_app.calculators import PortfolioCalculator
from portfolio_app.models.user import User
from portfolio_app.routes.charts import _asset_performance_rows
from portfolio_app.services.factory import Services


def _dec(value):
    return Decimal(str(value))


def _seed_user(username='income_realized_user'):
    user = User(username=username, email=f'{username}@example.com', is_verified=True)
    user.set_password('test-password')
    db.session.add(user)
    db.session.commit()
    return user.id


def _portfolio_with_deposit(uid, *, name='Growth', amount='2000'):
    svc = Services(user_id=uid)
    portfolio = svc.portfolio_service.create_portfolio(name, user_id=uid)
    svc.portfolio_service.deposit_funds(
        portfolio.id, _dec(amount), date=datetime(2024, 1, 1),
    )
    return svc, portfolio


def _add_buy_sell(svc, portfolio_id, *, symbol='AAPL'):
    svc.transaction_service.add_transaction(
        portfolio_id=portfolio_id,
        transaction_type='Buy',
        symbol=symbol,
        price=_dec('100'),
        quantity=_dec('10'),
        fees=_dec('0'),
        date=datetime(2024, 1, 2),
    )
    svc.transaction_service.add_transaction(
        portfolio_id=portfolio_id,
        transaction_type='Sell',
        symbol=symbol,
        price=_dec('120'),
        quantity=_dec('5'),
        fees=_dec('0'),
        date=datetime(2024, 1, 3),
    )


def test_sell_profit_without_income_keeps_income_zero_and_return_uses_trading_profit(app):
    with app.app_context():
        uid = _seed_user()
        svc, portfolio = _portfolio_with_deposit(uid)
        _add_buy_sell(svc, portfolio.id)

        perf = PortfolioCalculator.get_realized_performance_for_portfolio(
            portfolio.id, user_id=uid,
        )
        summary, _ = PortfolioCalculator.get_portfolio_summary(user_id=uid)

        assert perf['realized_pnl'] == _dec('100.0000000000')
        assert perf['total_income'] == _dec('0')
        assert summary[0]['realized_pnl'] == _dec('100.0000000000')
        assert summary[0]['total_income'] == _dec('0')
        assert summary[0]['return_amount'] == _dec('100.0000000000')
        assert summary[0]['return_display'] == '+5.00%'
        assert 'total_realized_pnl' not in summary[0]
        assert 'realized_roi_percent' not in summary[0]


def test_income_after_buy_changes_cash_book_value_and_return_not_realized_pnl_or_positions(app):
    with app.app_context():
        uid = _seed_user('income_after_buy')
        svc, portfolio = _portfolio_with_deposit(uid, amount='1000')
        svc.transaction_service.add_transaction(
            portfolio_id=portfolio.id,
            transaction_type='Buy',
            symbol='MSFT',
            price=_dec('100'),
            quantity=_dec('5'),
            fees=_dec('0'),
            date=datetime(2024, 1, 2),
        )

        before, _ = PortfolioCalculator.get_portfolio_summary(user_id=uid)
        svc.transaction_service.add_dividend(
            portfolio.id, 'MSFT', _dec('50'), datetime(2024, 1, 3),
        )
        after, _ = PortfolioCalculator.get_portfolio_summary(user_id=uid)

        before_item = before[0]
        after_item = after[0]
        assert before_item['realized_pnl'] == after_item['realized_pnl'] == _dec('0')
        assert before_item['positions'] == after_item['positions'] == _dec('500.0000000000')
        assert before_item['total_income'] == _dec('0')
        assert after_item['total_income'] == _dec('50.0000000000')
        assert before_item['cash'] == _dec('500.0000000000')
        assert after_item['cash'] == _dec('550.0000000000')
        assert before_item['book_value'] == _dec('1000.0000000000')
        assert after_item['book_value'] == _dec('1050.0000000000')
        assert before_item['return_amount'] == _dec('0')
        assert after_item['return_amount'] == _dec('50.0000000000')
        assert before_item['return_display'] == '+0.00%'
        assert after_item['return_display'] == '+5.00%'


def test_sell_profit_plus_income_keeps_realized_pnl_strict_and_return_includes_both(app):
    with app.app_context():
        uid = _seed_user('sell_plus_income')
        svc, portfolio = _portfolio_with_deposit(uid)
        _add_buy_sell(svc, portfolio.id)
        svc.transaction_service.add_dividend(
            portfolio.id, 'AAPL', _dec('75'), datetime(2024, 1, 4),
        )

        perf = PortfolioCalculator.get_realized_performance_for_portfolio(
            portfolio.id, user_id=uid,
        )
        summary, _ = PortfolioCalculator.get_portfolio_summary(user_id=uid)

        assert perf['realized_pnl'] == _dec('100.0000000000')
        assert perf['total_income'] == _dec('75.0000000000')
        assert perf['return_amount'] == _dec('175.0000000000')
        assert summary[0]['realized_pnl'] == _dec('100.0000000000')
        assert summary[0]['total_income'] == _dec('75.0000000000')
        assert summary[0]['return_amount'] == _dec('175.0000000000')
        assert summary[0]['return_display'] == '+8.75%'


def test_asset_performance_realized_pnl_excludes_income_and_return_includes_income(app):
    with app.app_context():
        uid = _seed_user('asset_performance_income')
        svc, portfolio = _portfolio_with_deposit(uid)
        _add_buy_sell(svc, portfolio.id)
        svc.transaction_service.add_dividend(
            portfolio.id, 'AAPL', _dec('75'), datetime(2024, 1, 4),
        )

        rows = svc.overview_service.get_symbol_performance()
        row = next(item for item in rows if item['symbol'] == 'AAPL')
        asset_rows = _asset_performance_rows(rows)
        asset_row = next(item for item in asset_rows if item['name'] == 'AAPL')

        assert row['realized_pnl'] == _dec('100.0000000000')
        assert row['total_income'] == _dec('75.0000000000')
        assert row['return_amount'] == _dec('175.0000000000')
        assert row['return_display'] == '+17.50%'
        assert 'total_realized_pnl' not in row
        assert 'dividend_total' not in row
        assert asset_row['realized_pnl'] == 100.0
        assert asset_row['income'] == 75.0
        assert asset_row['return_amount'] == 175.0
        assert asset_row['return_percent'] == 17.5


def test_income_only_symbol_has_zero_realized_pnl_and_no_return_base(app):
    with app.app_context():
        uid = _seed_user('income_only_symbol')
        svc, portfolio = _portfolio_with_deposit(uid)
        svc.transaction_service.add_dividend(
            portfolio.id, 'TRSF', _dec('20'), datetime(2024, 1, 4),
        )

        rows = svc.overview_service.get_symbol_performance()
        row = next(item for item in rows if item['symbol'] == 'TRSF')
        asset_rows = _asset_performance_rows(rows)
        asset_row = next(item for item in asset_rows if item['name'] == 'TRSF')

        assert row['realized_pnl'] == _dec('0')
        assert row['total_income'] == _dec('20.0000000000')
        assert row['return_amount'] == _dec('20.0000000000')
        assert row['return_base'] == _dec('0')
        assert row['return_percent'] == _dec('0')
        assert row['return_display'] == '—'
        assert asset_row['realized_pnl'] == 0.0
        assert asset_row['income'] == 20.0
        assert asset_row['return_amount'] == 20.0
        assert asset_row['return_percent'] is None


def test_updating_and_deleting_income_changes_cash_book_value_return_only(app):
    with app.app_context():
        uid = _seed_user('income_update_delete')
        svc, portfolio = _portfolio_with_deposit(uid, amount='1000')
        svc.transaction_service.add_transaction(
            portfolio_id=portfolio.id,
            transaction_type='Buy',
            symbol='MSFT',
            price=_dec('100'),
            quantity=_dec('5'),
            fees=_dec('0'),
            date=datetime(2024, 1, 2),
        )
        svc.transaction_service.add_dividend(
            portfolio.id, 'MSFT', _dec('100'), datetime(2024, 1, 3),
        )
        dividend = svc.dividend_repo.get_by_portfolio_id(portfolio.id)[0]

        added, _ = PortfolioCalculator.get_portfolio_summary(user_id=uid)
        svc.transaction_service.update_dividend(dividend.id, amount=_dec('150'))
        updated, _ = PortfolioCalculator.get_portfolio_summary(user_id=uid)
        svc.transaction_service.delete_dividend(dividend.id)
        deleted, _ = PortfolioCalculator.get_portfolio_summary(user_id=uid)

        assert [row[0]['realized_pnl'] for row in (added, updated, deleted)] == [
            _dec('0'), _dec('0'), _dec('0'),
        ]
        assert [row[0]['positions'] for row in (added, updated, deleted)] == [
            _dec('500.0000000000'),
            _dec('500.0000000000'),
            _dec('500.0000000000'),
        ]
        assert [row[0]['cash'] for row in (added, updated, deleted)] == [
            _dec('600.0000000000'),
            _dec('650.0000000000'),
            _dec('500.0000000000'),
        ]
        assert [row[0]['book_value'] for row in (added, updated, deleted)] == [
            _dec('1100.0000000000'),
            _dec('1150.0000000000'),
            _dec('1000.0000000000'),
        ]
        assert [row[0]['return_amount'] for row in (added, updated, deleted)] == [
            _dec('100.0000000000'),
            _dec('150.0000000000'),
            _dec('0'),
        ]
        assert [row[0]['return_display'] for row in (added, updated, deleted)] == [
            '+10.00%', '+15.00%', '+0.00%',
        ]
