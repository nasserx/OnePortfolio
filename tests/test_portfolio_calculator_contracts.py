from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from portfolio_app import db
from portfolio_app.calculators import PortfolioCalculator
from portfolio_app.models import Dividend, Portfolio, PortfolioEvent, Transaction
from portfolio_app.models.user import User
from portfolio_app.routes.charts import _allocation_rows


ZERO = Decimal('0')


def _dec(value):
    return Decimal(str(value))


def _tx(transaction_type, price, quantity, fees='0', date=None):
    return SimpleNamespace(
        transaction_type=transaction_type,
        price=_dec(price),
        quantity=_dec(quantity),
        fees=_dec(fees),
        date=date or datetime(2024, 1, 1),
    )


def _seed_user(username):
    user = User(username=username, email=f'{username}@example.com', is_verified=True)
    user.set_password('test-password')
    db.session.add(user)
    db.session.commit()
    return user


def _portfolio(user, name):
    portfolio = Portfolio(user_id=user.id, name=name)
    db.session.add(portfolio)
    db.session.commit()
    return portfolio


def _event(portfolio, event_type, amount, date):
    row = PortfolioEvent(
        portfolio_id=portfolio.id,
        event_type=event_type,
        amount_delta=_dec(amount),
        date=date,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _transaction(portfolio, transaction_type, symbol, price, quantity, fees, date):
    row = Transaction(
        portfolio_id=portfolio.id,
        transaction_type=transaction_type,
        symbol=symbol,
        price=_dec(price),
        quantity=_dec(quantity),
        fees=_dec(fees),
        date=date,
    )
    row.calculate_net_amount()
    db.session.add(row)
    db.session.commit()
    return row


def _income(portfolio, symbol, amount, date):
    row = Dividend(
        portfolio_id=portfolio.id,
        symbol=symbol,
        amount=_dec(amount),
        date=date,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _assert_decimal(value, expected):
    assert isinstance(value, Decimal)
    assert value == _dec(expected)


def test_average_cost_single_buy_contract_from_list():
    summary = PortfolioCalculator.get_symbol_transactions_summary_from_list([
        _tx('Buy', '10', '3', '0.75'),
    ])

    _assert_decimal(summary['total_buy_cost'], '30.75')
    _assert_decimal(summary['total_buy_fees'], '0.75')
    _assert_decimal(summary['cost_basis'], '30.75')
    _assert_decimal(summary['average_cost'], '10.25')
    _assert_decimal(summary['total_quantity_held'], '3')
    _assert_decimal(summary['realized_pnl'], '0')


def test_average_cost_multiple_buys_contract_from_list():
    summary = PortfolioCalculator.get_symbol_transactions_summary_from_list([
        _tx('Buy', '10', '2', '1'),
        _tx('Buy', '12', '3', '1.5'),
    ])

    _assert_decimal(summary['total_buy_cost'], '58.5')
    _assert_decimal(summary['total_buy_quantity'], '5')
    _assert_decimal(summary['cost_basis'], '58.5')
    _assert_decimal(summary['average_cost'], '11.7')


def test_average_cost_partial_sell_contract_from_list():
    summary = PortfolioCalculator.get_symbol_transactions_summary_from_list([
        _tx('Buy', '10', '2', '1'),
        _tx('Buy', '12', '3', '1.5'),
        _tx('Sell', '15', '2', '1'),
    ])

    _assert_decimal(summary['realized_pnl'], '5.6')
    _assert_decimal(summary['realized_cost_basis'], '23.4')
    _assert_decimal(summary['realized_proceeds'], '29')
    _assert_decimal(summary['total_sell_cost'], '29')
    _assert_decimal(summary['total_sell_fees'], '1')
    _assert_decimal(summary['total_quantity_held'], '3')
    _assert_decimal(summary['cost_basis'], '35.1')
    _assert_decimal(summary['average_cost'], '11.7')


def test_average_cost_full_liquidation_contract_from_list():
    summary = PortfolioCalculator.get_symbol_transactions_summary_from_list([
        _tx('Buy', '25', '4', '4'),
        _tx('Sell', '30', '4', '2'),
    ])

    _assert_decimal(summary['total_quantity_held'], '0')
    _assert_decimal(summary['cost_basis'], '0')
    _assert_decimal(summary['average_cost'], '0')
    _assert_decimal(summary['realized_cost_basis'], '104')
    _assert_decimal(summary['realized_proceeds'], '118')
    _assert_decimal(summary['realized_pnl'], '14')


def test_average_cost_multiple_buy_sell_sequence_contract_from_list():
    summary = PortfolioCalculator.get_symbol_transactions_summary_from_list([
        _tx('Buy', '10', '10'),
        _tx('Sell', '12', '4', '1'),
        _tx('Buy', '13', '4', '2'),
        _tx('Sell', '11', '5', '0.5'),
    ])

    _assert_decimal(summary['total_quantity_held'], '5')
    _assert_decimal(summary['cost_basis'], '57')
    _assert_decimal(summary['average_cost'], '11.4')
    _assert_decimal(summary['realized_cost_basis'], '97')
    _assert_decimal(summary['realized_proceeds'], '101.5')
    _assert_decimal(summary['realized_pnl'], '4.5')


def test_database_summary_uses_calendar_date_buy_first_and_id_ordering(app):
    with app.app_context():
        user = _seed_user('ordering_user')
        portfolio = _portfolio(user, 'Ordering')

        first_same_day_buy = _transaction(
            portfolio, 'Buy', 'ORDER', '20', '1', '0', datetime(2024, 1, 2, 15, 0),
        )
        same_day_sell = _transaction(
            portfolio, 'Sell', 'ORDER', '30', '2', '0', datetime(2024, 1, 2, 9, 0),
        )
        second_same_day_buy = _transaction(
            portfolio, 'Buy', 'ORDER', '40', '1', '0', datetime(2024, 1, 2, 18, 0),
        )
        earlier_buy = _transaction(
            portfolio, 'Buy', 'ORDER', '10', '1', '0', datetime(2024, 1, 1, 23, 0),
        )

        assert first_same_day_buy.id < same_day_sell.id < second_same_day_buy.id < earlier_buy.id

        summary = PortfolioCalculator.get_symbol_transactions_summary(
            portfolio.id, 'ORDER', user_id=user.id,
        )

        expected_average = _dec('70') / _dec('3')
        expected_remaining_cost = _dec('70') - (expected_average * _dec('2'))
        _assert_decimal(summary['total_buy_cost'], '70.0000000000')
        _assert_decimal(summary['total_buy_quantity'], '3.0000000000')
        assert summary['realized_cost_basis'] == expected_average * _dec('2')
        assert summary['realized_pnl'] == _dec('60') - (expected_average * _dec('2'))
        assert summary['total_quantity_held'] == _dec('1.0000000000')
        assert summary['cost_basis'] == expected_remaining_cost
        assert summary['average_cost'] == expected_remaining_cost


def test_portfolio_capital_cash_positions_book_value_and_return_contracts(app):
    with app.app_context():
        user = _seed_user('capital_cash_user')
        portfolio = _portfolio(user, 'Capital Cash')
        _event(portfolio, 'Initial', '1000', datetime(2024, 1, 1))
        _event(portfolio, 'Deposit', '500', datetime(2024, 1, 2))
        _event(portfolio, 'Withdrawal', '-200', datetime(2024, 1, 3))
        _transaction(portfolio, 'Buy', 'AAPL', '50', '10', '5', datetime(2024, 1, 4))
        _transaction(portfolio, 'Sell', 'AAPL', '60', '4', '2', datetime(2024, 1, 5))

        before_income, _ = PortfolioCalculator.get_portfolio_summary(user_id=user.id)
        _income(portfolio, 'AAPL', '25', datetime(2024, 1, 6))
        after_income, _ = PortfolioCalculator.get_portfolio_summary(user_id=user.id)

        _assert_decimal(PortfolioCalculator.get_total_capital_for_portfolio(portfolio.id, user_id=user.id), '1300.00')
        _assert_decimal(PortfolioCalculator.get_total_deposits_for_portfolio(portfolio.id, user_id=user.id), '1500.00')

        before = before_income[0]
        after = after_income[0]
        _assert_decimal(before['cash'], '1033.0000000000')
        _assert_decimal(after['cash'], '1058.0000000000')
        _assert_decimal(before['positions'], '303.0000000000')
        _assert_decimal(after['positions'], '303.0000000000')
        _assert_decimal(before['book_value'], '1336.0000000000')
        _assert_decimal(after['book_value'], '1361.0000000000')
        _assert_decimal(before['realized_pnl'], '36.0000000000')
        _assert_decimal(after['realized_pnl'], '36.0000000000')
        _assert_decimal(after['total_income'], '25.0000000000')
        _assert_decimal(after['return_amount'], '61.0000000000')
        assert after['return_percent'] == _dec('61.0000000000') / _dec('1500.00') * _dec('100')
        assert after['return_display'] == '+4.07%'


def test_asset_return_income_and_zero_denominator_contracts(app):
    with app.app_context():
        user = _seed_user('asset_return_user')
        portfolio = _portfolio(user, 'Asset Return')
        _event(portfolio, 'Deposit', '1500', datetime(2024, 1, 1))
        _transaction(portfolio, 'Buy', 'AAPL', '50', '10', '5', datetime(2024, 1, 2))
        _transaction(portfolio, 'Sell', 'AAPL', '60', '4', '2', datetime(2024, 1, 3))
        _income(portfolio, 'AAPL', '25', datetime(2024, 1, 4))
        _income(portfolio, 'TRSF', '12.34', datetime(2024, 1, 5))

        rows = PortfolioCalculator.get_user_symbol_performance(user.id)
        by_symbol = {row['symbol']: row for row in rows}

        aapl = by_symbol['AAPL']
        _assert_decimal(aapl['realized_pnl'], '36.0000000000')
        _assert_decimal(aapl['total_income'], '25.0000000000')
        _assert_decimal(aapl['return_amount'], '61.0000000000')
        _assert_decimal(aapl['total_buy_cost'], '505.0000000000')
        assert aapl['return_percent'] == _dec('61.0000000000') / _dec('505.0000000000') * _dec('100')
        assert aapl['return_display'] == '+12.08%'

        trsf = by_symbol['TRSF']
        _assert_decimal(trsf['realized_pnl'], '0')
        _assert_decimal(trsf['total_income'], '12.3400000000')
        _assert_decimal(trsf['return_amount'], '12.3400000000')
        _assert_decimal(trsf['return_base'], '0')
        _assert_decimal(trsf['return_percent'], '0')
        assert trsf['return_display'] == '—'


def test_negative_realized_pnl_and_return_display_contract(app):
    with app.app_context():
        user = _seed_user('negative_return_user')
        portfolio = _portfolio(user, 'Negative')
        _event(portfolio, 'Deposit', '1000', datetime(2024, 1, 1))
        _transaction(portfolio, 'Buy', 'LOSS', '10', '10', '0', datetime(2024, 1, 2))
        _transaction(portfolio, 'Sell', 'LOSS', '8', '5', '1', datetime(2024, 1, 3))

        summary, _ = PortfolioCalculator.get_portfolio_summary(user_id=user.id)
        asset_row = PortfolioCalculator.get_user_symbol_performance(user.id)[0]

        _assert_decimal(summary[0]['realized_pnl'], '-11.0000000000')
        _assert_decimal(summary[0]['return_amount'], '-11.0000000000')
        assert summary[0]['return_percent'] == _dec('-1.100000000000')
        assert summary[0]['return_display'] == '-1.10%'
        _assert_decimal(asset_row['realized_pnl'], '-11.0000000000')
        assert asset_row['return_percent'] == _dec('-11.000000000000')
        assert asset_row['return_display'] == '-11.00%'


def test_multi_portfolio_aggregation_allocation_and_distinct_symbol_rows(app):
    with app.app_context():
        user = _seed_user('aggregate_user')
        first = _portfolio(user, 'First')
        second = _portfolio(user, 'Second')

        _event(first, 'Deposit', '1000', datetime(2024, 1, 1))
        _transaction(first, 'Buy', 'AAPL', '100', '5', '0', datetime(2024, 1, 2))
        _transaction(first, 'Sell', 'AAPL', '120', '2', '0', datetime(2024, 1, 3))
        _income(first, 'AAPL', '10', datetime(2024, 1, 4))

        _event(second, 'Deposit', '2000', datetime(2024, 1, 1))
        _transaction(second, 'Buy', 'AAPL', '50', '10', '0', datetime(2024, 1, 2))
        _transaction(second, 'Buy', 'MSFT', '200', '2', '0', datetime(2024, 1, 2))
        _transaction(second, 'Sell', 'MSFT', '180', '1', '0', datetime(2024, 1, 3))
        _income(second, 'TRSF', '30', datetime(2024, 1, 4))

        summary, total_book_value = PortfolioCalculator.get_portfolio_summary(user_id=user.id)
        by_name = {row['name']: row for row in summary}
        dashboard = PortfolioCalculator.get_portfolio_dashboard_totals(user_id=user.id)
        symbol_rows = PortfolioCalculator.get_user_symbol_performance(user.id)

        _assert_decimal(by_name['First']['realized_pnl'], '40.0000000000')
        _assert_decimal(by_name['First']['total_income'], '10.0000000000')
        _assert_decimal(by_name['First']['cash'], '750.0000000000')
        _assert_decimal(by_name['First']['positions'], '300.0000000000')
        _assert_decimal(by_name['First']['book_value'], '1050.0000000000')

        _assert_decimal(by_name['Second']['realized_pnl'], '-20.0000000000')
        _assert_decimal(by_name['Second']['total_income'], '30.0000000000')
        _assert_decimal(by_name['Second']['cash'], '1310.0000000000')
        _assert_decimal(by_name['Second']['positions'], '700.0000000000')
        _assert_decimal(by_name['Second']['book_value'], '2010.0000000000')

        _assert_decimal(total_book_value, '3060.0000000000')
        _assert_decimal(dashboard['total_contributed'], '3000.00')
        _assert_decimal(dashboard['total_capital'], '3000.00')
        _assert_decimal(dashboard['total_cash'], '2060.0000000000')
        _assert_decimal(dashboard['total_positions'], '1000.0000000000')
        _assert_decimal(dashboard['realized_pnl'], '20.0000000000')
        _assert_decimal(dashboard['total_income'], '40.0000000000')
        _assert_decimal(dashboard['return_amount'], '60.0000000000')
        _assert_decimal(dashboard['total_value'], '3060.0000000000')

        assert by_name['First']['allocation'] == _dec('1050.0000000000') / _dec('3060.0000000000') * _dec('100')
        assert by_name['Second']['allocation'] == _dec('2010.0000000000') / _dec('3060.0000000000') * _dec('100')
        allocation_rows = {row['name']: row for row in _allocation_rows(summary)}
        assert allocation_rows['First']['book_value'] == 1050.0
        assert allocation_rows['Second']['book_value'] == 2010.0

        aapl_rows = [row for row in symbol_rows if row['symbol'] == 'AAPL']
        assert sorted(row['portfolio_name'] for row in aapl_rows) == ['First', 'Second']
        trsf = next(row for row in symbol_rows if row['symbol'] == 'TRSF')
        _assert_decimal(trsf['realized_pnl'], '0')
        _assert_decimal(trsf['total_income'], '30.0000000000')
        assert trsf['return_display'] == '—'


def test_user_scoped_calculator_calls_exclude_other_user_data(app):
    with app.app_context():
        owner = _seed_user('owner_user')
        other = _seed_user('other_user')
        owner_portfolio = _portfolio(owner, 'Owner')
        other_portfolio = _portfolio(other, 'Other')

        _event(owner_portfolio, 'Deposit', '1000', datetime(2024, 1, 1))
        _transaction(owner_portfolio, 'Buy', 'OWN', '100', '2', '0', datetime(2024, 1, 2))
        _income(owner_portfolio, 'OWN', '5', datetime(2024, 1, 3))

        _event(other_portfolio, 'Deposit', '9999', datetime(2024, 1, 1))
        _transaction(other_portfolio, 'Buy', 'EVIL', '333', '3', '0', datetime(2024, 1, 2))
        _transaction(other_portfolio, 'Sell', 'EVIL', '444', '1', '0', datetime(2024, 1, 3))
        _income(other_portfolio, 'EVIL', '777', datetime(2024, 1, 4))

        owner_summary, _ = PortfolioCalculator.get_portfolio_summary(user_id=owner.id)
        owner_dashboard = PortfolioCalculator.get_portfolio_dashboard_totals(user_id=owner.id)
        owner_symbols = PortfolioCalculator.get_user_symbol_performance(owner.id)

        assert [row['name'] for row in owner_summary] == ['Owner']
        assert [row['symbol'] for row in owner_symbols] == ['OWN']
        _assert_decimal(owner_dashboard['total_contributed'], '1000.00')
        _assert_decimal(owner_dashboard['total_cash'], '805.0000000000')
        _assert_decimal(owner_dashboard['total_income'], '5.0000000000')

        _assert_decimal(
            PortfolioCalculator.get_total_capital_for_portfolio(other_portfolio.id, user_id=owner.id),
            '0',
        )
        _assert_decimal(
            PortfolioCalculator.get_available_cash_for_portfolio(other_portfolio.id, user_id=owner.id),
            '0',
        )
        blocked_summary = PortfolioCalculator.get_symbol_transactions_summary(
            other_portfolio.id, 'EVIL', user_id=owner.id,
        )
        _assert_decimal(blocked_summary['total_buy_cost'], '0')
        _assert_decimal(blocked_summary['realized_pnl'], '0')


def test_decimal_precision_contract_avoids_float_rounding(app):
    summary = PortfolioCalculator.get_symbol_transactions_summary_from_list([
        _tx('Buy', '0.10', '0.10', '0.01'),
        _tx('Buy', '0.30', '0.10', '0.01'),
        _tx('Sell', '0.50', '0.10', '0.002'),
    ])

    for key in (
        'total_buy_cost',
        'total_buy_fees',
        'total_buy_quantity',
        'total_sell_cost',
        'total_sell_fees',
        'total_sell_quantity',
        'total_quantity_held',
        'average_cost',
        'realized_pnl',
        'realized_cost_basis',
        'realized_proceeds',
        'cost_basis',
    ):
        assert isinstance(summary[key], Decimal)

    _assert_decimal(summary['total_buy_cost'], '0.0600')
    _assert_decimal(summary['total_buy_fees'], '0.02')
    _assert_decimal(summary['total_buy_quantity'], '0.20')
    _assert_decimal(summary['total_sell_cost'], '0.048')
    _assert_decimal(summary['realized_cost_basis'], '0.0300')
    _assert_decimal(summary['realized_pnl'], '0.0180')
    _assert_decimal(summary['cost_basis'], '0.0300')
    _assert_decimal(summary['average_cost'], '0.3000')
