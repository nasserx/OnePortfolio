"""Static conformance checks for the b1YmpWHpo Flask foundation."""

import re
from pathlib import Path

import pytest

from tests._colour import declarations, theme_tokens


TOKENS_PATH = Path('portfolio_app/static/css/tokens.css')
COMPONENTS_PATH = Path('portfolio_app/static/css/components.css')
CSS_PATHS = tuple(Path('portfolio_app/static/css').glob('*.css'))

LIGHT = {
    'background': 'oklch(1 0 0)',
    'foreground': 'oklch(0.145 0 0)',
    'card': 'oklch(1 0 0)',
    'card-foreground': 'oklch(0.145 0 0)',
    'popover': 'oklch(1 0 0)',
    'popover-foreground': 'oklch(0.145 0 0)',
    'primary': 'oklch(0.205 0 0)',
    'primary-foreground': 'oklch(0.985 0 0)',
    'secondary': 'oklch(0.97 0 0)',
    'secondary-foreground': 'oklch(0.205 0 0)',
    'muted': 'oklch(0.97 0 0)',
    'muted-foreground': 'oklch(0.556 0 0)',
    'accent': 'oklch(0.97 0 0)',
    'accent-foreground': 'oklch(0.205 0 0)',
    'destructive': 'oklch(0.577 0.245 27.325)',
    'border': 'oklch(0.922 0 0)',
    'input': 'oklch(0.922 0 0)',
    'ring': 'oklch(0.708 0 0)',
    'chart-1': 'oklch(0.809 0.105 251.813)',
    'chart-2': 'oklch(0.623 0.214 259.815)',
    'chart-3': 'oklch(0.546 0.245 262.881)',
    'chart-4': 'oklch(0.488 0.243 264.376)',
    'chart-5': 'oklch(0.424 0.199 265.638)',
    'sidebar': 'oklch(0.985 0 0)',
    'sidebar-foreground': 'oklch(0.145 0 0)',
    'sidebar-primary': 'oklch(0.205 0 0)',
    'sidebar-primary-foreground': 'oklch(0.985 0 0)',
    'sidebar-accent': 'oklch(0.97 0 0)',
    'sidebar-accent-foreground': 'oklch(0.205 0 0)',
    'sidebar-border': 'oklch(0.922 0 0)',
    'sidebar-ring': 'oklch(0.708 0 0)',
}

DARK = {
    **LIGHT,
    'background': 'oklch(0.145 0 0)',
    'foreground': 'oklch(0.985 0 0)',
    'card': 'oklch(0.205 0 0)',
    'card-foreground': 'oklch(0.985 0 0)',
    'popover': 'oklch(0.205 0 0)',
    'popover-foreground': 'oklch(0.985 0 0)',
    'primary': 'oklch(0.922 0 0)',
    'primary-foreground': 'oklch(0.205 0 0)',
    'secondary': 'oklch(0.269 0 0)',
    'secondary-foreground': 'oklch(0.985 0 0)',
    'muted': 'oklch(0.269 0 0)',
    'muted-foreground': 'oklch(0.708 0 0)',
    'accent': 'oklch(0.269 0 0)',
    'accent-foreground': 'oklch(0.985 0 0)',
    'destructive': 'oklch(0.704 0.191 22.216)',
    'border': 'oklch(1 0 0 / 10%)',
    'input': 'oklch(1 0 0 / 15%)',
    'ring': 'oklch(0.556 0 0)',
    'sidebar': 'oklch(0.205 0 0)',
    'sidebar-foreground': 'oklch(0.985 0 0)',
    'sidebar-primary': 'oklch(0.488 0.243 264.376)',
    'sidebar-primary-foreground': 'oklch(0.985 0 0)',
    'sidebar-accent': 'oklch(0.269 0 0)',
    'sidebar-accent-foreground': 'oklch(0.985 0 0)',
    'sidebar-border': 'oklch(1 0 0 / 10%)',
    'sidebar-ring': 'oklch(0.556 0 0)',
}


@pytest.fixture(scope='module')
def tokens_css():
    return TOKENS_PATH.read_text(encoding='utf-8')


@pytest.mark.parametrize(('theme', 'expected'), [('light', LIGHT), ('dark', DARK)])
def test_official_preset_values_are_exact(tokens_css, theme, expected):
    actual = theme_tokens(tokens_css, theme)
    assert {name: actual[name] for name in expected} == expected


def test_radius_derivation_matches_generated_shadcn_contract(tokens_css):
    actual = theme_tokens(tokens_css, 'light')
    assert actual['radius'] == '0.625rem'
    assert actual['radius-sm'] == 'calc(var(--radius) * 0.6)'
    assert actual['radius-md'] == 'calc(var(--radius) * 0.8)'
    assert actual['radius-lg'] == 'var(--radius)'
    assert actual['radius-xl'] == 'calc(var(--radius) * 1.4)'
    assert actual['radius-2xl'] == 'calc(var(--radius) * 1.8)'
    assert actual['radius-3xl'] == 'calc(var(--radius) * 2.2)'
    assert actual['radius-4xl'] == 'calc(var(--radius) * 2.6)'


def test_application_has_one_fixed_density_and_no_preference_runtime(tokens_css):
    base_template = Path('portfolio_app/templates/base.html').read_text(encoding='utf-8')
    shell = Path('portfolio_app/static/js/shell.js').read_text(encoding='utf-8')
    combined_runtime = '\n'.join((base_template, shell, tokens_css))

    for obsolete in (
        'op:density',
        'data-density',
        'density-toggle',
        'density-label',
        '--density-scale',
        'Compact density',
        'Comfortable density',
    ):
        assert obsolete not in combined_runtime

    declared = theme_tokens(tokens_css, 'light')
    assert declared['control-h'] == '2rem'
    assert declared['row-h'] == '2.5rem'
    assert declared['cell-pad-y'] == '0.5rem'
    assert declared['card-pad'] == '1rem'
    assert "localStorage.getItem('op:theme')" in base_template
    assert "theme: 'op:theme'" in shell
    assert 'function readStored' not in shell


def test_system_and_explicit_dark_roles_cannot_drift(tokens_css):
    system = re.search(
        r':root:not\(\[data-theme="light"\]\)\s*\{([^}]*)\}', tokens_css
    )
    explicit = re.search(r':root\[data-theme="dark"\]\s*\{([^}]*)\}', tokens_css)
    assert system and explicit
    system_roles = declarations(system.group(1))
    explicit_roles = declarations(explicit.group(1))
    for role in (*DARK, *(f'portfolio-chart-{index}' for index in range(1, 6))):
        assert system_roles[role] == explicit_roles[role]


def test_no_invented_or_legacy_palette_tokens_exist(tokens_css):
    forbidden = (
        '--chart-6', '--chart-7', '--chart-other', '--cat-', '--brand-500',
        '--brand-600', '--green-light', '--red-light', '--blue-light', '--n-50',
    )
    for token in forbidden:
        assert token not in tokens_css
    assert not re.search(
        r'--(?:n-\d+|brand-\d+|green-|red-|blue-|amber-|cat-)', tokens_css
    )


def test_chart_tokens_are_visualization_only():
    components = COMPONENTS_PATH.read_text(encoding='utf-8')
    for selector, body in re.findall(r'([^{}]+)\{([^{}]*)\}', components):
        assert not re.search(r'var\(--chart-[1-5]\)', body), selector

    for path in CSS_PATHS:
        if path == TOKENS_PATH or path == COMPONENTS_PATH:
            continue
        assert not re.search(r'var\(--chart-[1-5]\)', path.read_text(encoding='utf-8'))

    overview_js = Path('portfolio_app/static/js/overview_charts.js').read_text(
        encoding='utf-8'
    )
    assert 'var PALETTE_SIZE = 5;' in overview_js
    assert "cssVar('--chart-other'" not in overview_js
    assert "cssVar('--portfolio-chart-' + i)" in overview_js
    assert "name === 'Other Portfolios') return this.colors[4]" in overview_js


def test_portfolio_chart_extension_is_separate_and_visualization_only(tokens_css):
    light = theme_tokens(tokens_css, 'light')
    dark = theme_tokens(tokens_css, 'dark')
    assert [light[f'portfolio-chart-{i}'] for i in range(1, 6)] == [
        'var(--chart-3)',
        'oklch(0.58 0.12 210)',
        'oklch(0.55 0.16 300)',
        'oklch(0.56 0.12 165)',
        'oklch(0.64 0.14 70)',
    ]
    assert [dark[f'portfolio-chart-{i}'] for i in range(1, 6)] == [
        'var(--chart-2)',
        'oklch(0.72 0.12 210)',
        'oklch(0.70 0.14 300)',
        'oklch(0.70 0.12 165)',
        'oklch(0.76 0.13 75)',
    ]

    allowed = ('allocation-legend', 'swatch')
    for path in CSS_PATHS:
        if path == TOKENS_PATH:
            continue
        css = path.read_text(encoding='utf-8')
        for selector, body in re.findall(r'([^{}]+)\{([^{}]*)\}', css):
            if re.search(r'var\(--portfolio-chart-[1-5]\)', body):
                assert all(part in selector for part in allowed), (
                    f'{path}: {selector.strip()}'
                )

    allowed_js = {'overview_charts.js', 'landing.js'}
    for path in Path('portfolio_app/static/js').glob('*.js'):
        if '--portfolio-chart-' in path.read_text(encoding='utf-8'):
            assert path.name in allowed_js


def test_entity_markers_are_neutral_and_index_independent():
    components = COMPONENTS_PATH.read_text(encoding='utf-8')
    marker = re.search(r'\.marker\s*\{([^}]*)\}', components)
    assert marker
    assert 'var(--muted)' in marker.group(1)
    assert 'var(--muted-foreground)' in marker.group(1)
    assert '--chart-' not in marker.group(1)
    assert 'allocation-marker-' not in components

    macro = Path('portfolio_app/templates/macros/ui.html').read_text(encoding='utf-8')
    marker_macro = re.search(r'macro marker.*?endmacro', macro, re.DOTALL)
    assert marker_macro
    assert 'allocation-marker-' not in marker_macro.group(0)
    assert 'index' not in marker_macro.group(0)

    for name in ('index.html', 'portfolios.html'):
        source = Path('portfolio_app/templates', name).read_text(encoding='utf-8')
        assert not re.search(r'marker\([^)]*,', source)


def test_every_migration_alias_has_a_current_stylesheet_consumer(tokens_css):
    match = re.search(
        r'Temporary migration aliases.*?:root\s*\{([^}]*)\}', tokens_css, re.S
    )
    assert match
    aliases = set(declarations(match.group(1)))
    expected = {
        'bg-canvas', 'bg-surface', 'bg-raised', 'bg-inset', 'bg-hover',
        'fg-default', 'fg-muted', 'fg-subtle', 'fg-faint', 'fg-on-brand',
        'line-subtle', 'line-default', 'line-strong',
        'nav-active-bg', 'nav-active-fg',
        'field-bg', 'field-bg-disabled', 'field-border',
        'tooltip-bg', 'tooltip-fg',
        'brand', 'brand-hover', 'brand-solid', 'brand-soft',
        'brand-soft-hover', 'brand-line', 'intro-wash',
    }
    assert aliases == expected

    consumers = '\n'.join(
        path.read_text(encoding='utf-8')
        for path in Path('portfolio_app/static/css').glob('*.css')
        if path != TOKENS_PATH
    )
    for alias in aliases:
        assert f'var(--{alias})' in consumers, f'--{alias} has no CSS consumer'


def test_icon_sprite_has_unique_consumed_symbols_and_live_aliases():
    sprite_path = Path('portfolio_app/templates/components/icon_sprite.html')
    sprite = sprite_path.read_text(encoding='utf-8')
    symbols = re.findall(r'id="op-icon-([^"]+)"', sprite)
    assert len(symbols) == len(set(symbols))
    assert set(symbols) == {
        'dashboard', 'wallet', 'package', 'search', 'chevron-left',
        'chevron-up', 'chevron-right', 'chevron-down', 'settings', 'logout',
        'moon', 'sun', 'menu', 'x',
        'circle-check', 'alert-circle', 'alert-triangle', 'info-circle',
        'arrow-up-right', 'arrow-down-right', 'arrow-right', 'plus',
        'arrow-left', 'folder-plus', 'square-plus', 'dots-vertical', 'edit',
        'arrow-down-circle', 'arrow-up-circle', 'trash', 'filter',
        'cash-banknote', 'shield-lock', 'broadcast', 'notebook', 'calculator',
        'chart-pie', 'check', 'brand-github', 'mail', 'user', 'user-cog',
        'user-circle', 'calendar', 'mail-check', 'refresh',
    }

    consumers = '\n'.join(
        path.read_text(encoding='utf-8')
        for root in (Path('portfolio_app/templates'), Path('portfolio_app/static/js'))
        for path in root.rglob('*')
        if path.is_file() and path.suffix in {'.html', '.js'} and path != sprite_path
    )
    for symbol in symbols:
        assert symbol in consumers, f'op-icon-{symbol} has no consumer'

    shell = Path('portfolio_app/static/js/shell.js').read_text(encoding='utf-8')
    for obsolete in ("gear: 'settings'", "'grid-1x2': 'dashboard'",
                     'ICON_ALIASES', 'arrow-return-right', 'plus-lg',
                     'box-seam', 'wallet2'):
        assert obsolete not in shell
    assert 'data-command-icon="plus"' in consumers


def test_financial_roles_are_isolated_to_financial_value_components():
    allowed_selectors = ('.num--pos', '.num--neg', '.num--income', '.num--flat',
                         '.delta--pos', '.delta--neg', '.delta--flat',
                         '.tx-tab-buy.active', '.tx-tab-sell.active')
    for path in CSS_PATHS:
        if path == TOKENS_PATH:
            continue
        css = path.read_text(encoding='utf-8')
        for selector, body in re.findall(r'([^{}]+)\{([^{}]*)\}', css):
            if 'var(--financial-' in body:
                assert any(name in selector for name in allowed_selectors), (
                    f'{path}: {selector.strip()}'
                )


def test_reusable_css_keeps_raw_colours_in_token_layer():
    literal = re.compile(r'#[0-9a-fA-F]{3,8}\b|\brgba?\(|\boklch\(')
    for path in CSS_PATHS:
        if path == TOKENS_PATH:
            continue
        assert not literal.search(path.read_text(encoding='utf-8')), path
