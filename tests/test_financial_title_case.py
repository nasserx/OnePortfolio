"""Scoped Title Case contracts for authenticated financial UI copy."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = (ROOT / 'portfolio_app' / 'templates' / 'base.html').read_text(
    encoding='utf-8'
)
LANDING = (ROOT / 'portfolio_app' / 'templates' / 'landing.html').read_text(
    encoding='utf-8'
)
TEMPLATES = {
    name: (ROOT / 'portfolio_app' / 'templates' / f'{name}.html').read_text(
        encoding='utf-8'
    )
    for name in ('index', 'portfolios', 'assets')
}


def test_overview_short_financial_labels_use_title_case_source_copy():
    source = TEMPLATES['index']
    for label in (
        'Book Value',
        'Net Contributions',
        'Cash',
        'Dividends',
        'Realized P&L',
        'Portfolio Split',
        'By Book Value',
        'By Net Contributions',
        'View Assets',
        'No Portfolios Yet',
        'Create Portfolio',
    ):
        assert label in source


def test_portfolio_short_financial_labels_use_title_case_source_copy():
    source = TEMPLATES['portfolios']
    for label in (
        'New Portfolio',
        'Net Contributions',
        'Cash',
        'Cost Basis',
        'No Portfolios Yet',
        'Create Portfolio',
    ):
        assert label in source
    assert 'Available To Withdraw' not in source


def test_asset_short_financial_labels_use_title_case_source_copy():
    source = TEMPLATES['assets']
    for label in (
        'All Portfolios',
        'Search Asset',
        'Add Asset',
        'Purchase Cost',
        'Avg. Cost',
        'Realized Return',
        'Add Dividends',
        'Add Entry',
        'Total Amount',
        'No Assets Yet',
    ):
        assert label in source


def test_scoped_templates_do_not_retain_known_legacy_lowercase_ui_forms():
    source = '\n'.join(TEMPLATES.values())
    legacy_ui_fragments = (
        "call fact('Total capital')",
        "call fact('Total cash')",
        "call fact('Total dividend_income')",
        "call metric('Total capital')",
        "call metric('Total cash')",
        "call metric('Book value')",
        "call metric('Total buy cost')",
        "call metric('Average cost')",
        "call metric('Realized return')",
        '>By book value</button>',
        '>By capital</button>',
        '>View assets</span>',
        '>Create portfolio</span>',
        '>New portfolio</span>',
        '>Add asset</span>',
        '>Add dividend_income</span>',
        ' No portfolios yet',
        ' No assets yet',
        '>All portfolios</a>',
        'placeholder="Search asset…"',
    )
    for fragment in legacy_ui_fragments:
        assert fragment not in source


def test_title_case_is_source_copy_not_css_transformation():
    source = '\n'.join(TEMPLATES.values())
    assert 'text-transform: capitalize' not in source


def test_cross_page_short_controls_use_title_case_source_copy():
    assert '>Skip to Content</a>' in BASE
    assert '>Skip to Content</a>' in LANDING
    assert 'Sign Out' in BASE

    assets = TEMPLATES['assets']
    assert assets.count('>Select Portfolio…</option>') == 3
    assert '>Select Type…</option>' in assets
    for legacy in ('Sign out', 'Skip to content', 'Select portfolio...',
                   'Select type...'):
        assert legacy not in '\n'.join((BASE, LANDING, assets))
