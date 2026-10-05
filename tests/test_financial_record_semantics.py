"""Presentation contracts for financial record types and terminology."""

from pathlib import Path

from flask import render_template_string


ROOT = Path(__file__).resolve().parents[1]
ASSETS = (ROOT / 'portfolio_app' / 'templates' / 'assets.html').read_text(
    encoding='utf-8'
)
PORTFOLIOS = (ROOT / 'portfolio_app' / 'templates' / 'portfolios.html').read_text(
    encoding='utf-8'
)
COMPONENTS = (
    ROOT / 'portfolio_app' / 'static' / 'css' / 'components.css'
).read_text(encoding='utf-8')
MAIN = (ROOT / 'portfolio_app' / 'static' / 'js' / 'main.js').read_text(
    encoding='utf-8'
)


def _render_type(app, value):
    with app.app_context():
        return render_template_string(
            "{% from 'macros/ui.html' import record_type %}"
            "{{ record_type(value) }}",
            value=value,
        )


def test_shared_record_type_mapping_assigns_financial_roles(app):
    expected = {
        'Buy': 'positive',
        'Deposit': 'positive',
        'Sell': 'negative',
        'Withdrawal': 'negative',
        'Dividends': 'income',
        'Initial': 'neutral',
    }
    for label, role in expected.items():
        html = _render_type(app, label)
        assert f'class="record-type record-type--{role}"' in html
        assert f'>{label}</span>' in html


def test_both_financial_tables_use_the_shared_mapping():
    assert '{{ record_type(transaction.transaction_type) }}' in ASSETS
    assert "{{ record_type('Dividends') }}" in ASSETS
    assert '{{ record_type(event.event_type) }}' in PORTFOLIOS
    for obsolete in ('tx-type-label', 'badge-dividend'):
        assert obsolete not in ASSETS
        assert obsolete not in PORTFOLIOS


def test_record_type_css_uses_only_approved_foreground_roles():
    expected = {
        '.record-type--positive': '--financial-positive',
        '.record-type--negative': '--financial-negative',
        '.record-type--income': '--financial-income',
        '.record-type--neutral': '--financial-flat',
    }
    for selector, token in expected.items():
        rule = COMPONENTS.split(f'{selector} {{', 1)[1].split('}', 1)[0]
        assert f'color: var({token});' in rule
        for forbidden in (
            'background', 'border', '--chart-', '--portfolio-chart-',
            '--destructive',
        ):
            assert forbidden not in rule


def test_financial_table_and_calculated_summary_terminology():
    assert '>Total Amount</th>' in ASSETS
    assert '>Total</th>' not in ASSETS
    assert "metric('Purchase Cost')" in ASSETS
    assert 'Total Buy Cost' not in ASSETS
    assert "const label = isSell ? 'Total Received:' : 'Purchase Cost:';" in MAIN


def test_transaction_calculation_and_formatting_contract_is_unchanged():
    assert 'const gross = price * quantity;' in MAIN
    assert 'const total = isSell ? (gross - fees) : (gross + fees);' in MAIN
    assert 'const formatted = Utils.formatMoney(total);' in MAIN
    assert (
        '<div id="total_cost_preview" class="tx-preview" '
        'aria-live="polite"></div>'
    ) in ASSETS
    assert (
        '<div id="edit_total_cost_preview" class="tx-preview" '
        'aria-live="polite"></div>'
    ) in ASSETS


def test_touched_multiword_labels_are_title_case():
    for label in ('Total Amount', 'Purchase Cost', 'Total Received'):
        assert label in ASSETS + MAIN
