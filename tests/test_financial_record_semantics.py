"""Presentation contracts for financial record types and terminology."""

from pathlib import Path
import re

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
PREVIEWS = (ROOT / 'portfolio_app' / 'static' / 'js' / 'transaction_previews.js').read_text(
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
    for label in ('Net Proceeds:', 'Purchase Cost:'):
        assert label in PREVIEWS
    assert 'Total Received' not in PREVIEWS


def test_transaction_previews_start_with_labeled_accessible_placeholders():
    # Arithmetic/rounding are exercised by the production JS/Python parity
    # test; this contract covers the pre-JavaScript accessible markup only.
    for identifier in ('transaction_amount_preview', 'edit_transaction_amount_preview'):
        match = re.search(rf'<div id="{identifier}"[^>]*>(.*?)</div>', ASSETS, re.S)
        assert match is not None
        assert 'class="tx-preview"' in match[0]
        assert 'aria-live="polite"' in match[0]
        assert '<span class="tx-preview__label">Purchase Cost:</span>' in match[1]
        assert '<span class="tx-preview__value">—</span>' in match[1]


def test_touched_multiword_labels_are_title_case():
    for label in ('Total Amount', 'Purchase Cost', 'Net Proceeds'):
        assert label in ASSETS + PREVIEWS
