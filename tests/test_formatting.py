from decimal import Decimal

import pytest
from flask import render_template_string

from portfolio_app.utils.formatting import (
    fmt_decimal,
    fmt_money,
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


@pytest.mark.parametrize('value, expected', [
    ('1234.5', '1,234.50'),
    ('1.005', '1.01'),
    ('-1.005', '-1.01'),
    ('0', '0.00'),
])
def test_money_grouping_fixed_decimals_and_half_up_rounding(value, expected):
    assert fmt_money(Decimal(value)) == expected
    assert fmt_display_money(Decimal(value)) == expected


@pytest.mark.parametrize('value, expected', [
    ('1234.5000', '1,234.5'),
    ('0.0000000100', '0.00000001'),
    ('0.0000', '0'),
])
def test_quantity_and_fee_formatting_trim_zeros_without_losing_small_values(value, expected):
    assert fmt_decimal(Decimal(value)) == expected
    assert fmt_display_decimal(Decimal(value)) == expected


@pytest.mark.parametrize('value, expected', [
    ('1234567890', '1.23B'),
    ('-1234567890000', '-1.23T'),
])
def test_compact_billions_and_trillions_preserve_sign(value, expected):
    assert fmt_display_money(Decimal(value)) == expected
    assert fmt_display_decimal(Decimal(value)) == expected
    assert fmt_display_percent(Decimal(value)) == expected + '%'


@pytest.mark.parametrize('value, tone, expected, role', [
    ('1234.5', 'sign', '+1,234.50', 'num--pos'),
    ('-1234.5', 'sign', '-1,234.50', 'num--neg'),
    ('12.5', 'income', '+12.50', 'num--income'),
    ('0', 'sign', '0.00', 'num--flat'),
])
def test_money_macro_preserves_sign_text_and_financial_tone(app, value, tone, expected, role):
    with app.app_context():
        html = render_template_string(
            "{% from 'macros/ui.html' import money %}"
            "{{ money(value, tone=tone, signed=true) }}",
            value=Decimal(value), tone=tone,
        )
    assert f'>{expected}</span>' in html
    assert f'title="{expected}"' in html
    assert role in html


def test_percentage_half_up_and_undefined_dash_contract(app):
    assert fmt_display_percent(Decimal('1.005'), signed=True) == '+1.01%'
    assert fmt_display_percent(Decimal('-1.005'), signed=True) == '-1.01%'
    assert fmt_display_percent(None) == '—'
    with app.app_context():
        # Undefined percentages occur as either None or numeric zero + dash.
        for value, display in ((None, None), (Decimal('0'), '—')):
            html = render_template_string(
                "{% from 'macros/ui.html' import percent %}{{ percent(value, display) }}",
                value=value, display=display,
            )
            assert '>—</span>' in html
            assert 'num--flat' in html
            assert '0.00%' not in html


def test_known_edit_payload_float_formatting_differs_from_decimal_display(app):
    """Characterize the legacy Jinja format filter used for edit payloads.

    This is explicitly a float-boundary test, not a financial float assertion.
    The Decimal formatter retains all ten places while the edit payload loses
    digits. Production templates are intentionally unchanged in this phase.
    """
    value = Decimal('1234567890.1234567890')
    assert fmt_money(value, 10) == '1,234,567,890.1234567890'
    with app.app_context():
        payload = render_template_string('{{ "%.10f"|format(value) }}', value=value)
    assert payload == '1234567890.1234567165'
    assert Decimal(payload) != value
