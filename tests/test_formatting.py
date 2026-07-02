from decimal import Decimal

from portfolio_app.utils.formatting import (
    fmt_display_decimal,
    fmt_display_money,
    fmt_display_percent,
)


def test_display_money_only_abbreviates_millions():
    assert fmt_display_money(Decimal('999.99')) == '999.99'
    assert fmt_display_money(Decimal('1800.00')) == '1,800.00'
    assert fmt_display_money(Decimal('83050.00')) == '83,050.00'
    assert fmt_display_money(Decimal('999999.99')) == '999,999.99'
    assert fmt_display_money(Decimal('1000000.00')) == '1.00M'
    assert fmt_display_money(Decimal('1430000.00')) == '1.43M'


def test_display_money_preserves_existing_external_signs():
    assert f"+{fmt_display_money(Decimal('1800.00'))}" == '+1,800.00'
    assert fmt_display_money(Decimal('-1800.00')) == '-1,800.00'
    assert f"+{fmt_display_money(Decimal('1430000.00'))}" == '+1.43M'
    assert fmt_display_money(Decimal('-1430000.00')) == '-1.43M'


def test_display_decimal_never_uses_thousands_abbreviation():
    assert fmt_display_decimal(Decimal('999.99')) == '999.99'
    assert fmt_display_decimal(Decimal('1800.00')) == '1,800'
    assert fmt_display_decimal(Decimal('83050.00')) == '83,050'
    assert fmt_display_decimal(Decimal('999999.99')) == '999,999.99'
    assert fmt_display_decimal(Decimal('1000000.00')) == '1.00M'


def test_display_percent_never_uses_thousands_abbreviation():
    assert fmt_display_percent(Decimal('1800.00'), signed=True) == '+1,800.00%'
    assert fmt_display_percent(Decimal('50035.00'), signed=True) == '+50,035.00%'
    assert fmt_display_percent(Decimal('-1800.00'), signed=True) == '-1,800.00%'
    assert fmt_display_percent(Decimal('0'), signed=True) == '0.00%'
    assert fmt_display_percent(Decimal('1000000.00'), signed=True) == '+1.00M%'
