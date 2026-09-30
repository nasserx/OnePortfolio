"""Architecture guards for shared Nova surfaces and compound controls."""

from pathlib import Path
import re


APP = Path('portfolio_app/static/css/app.css')
BASE = Path('portfolio_app/static/css/base.css')
COMPONENTS = Path('portfolio_app/static/css/components.css')
TEMPLATES = Path('portfolio_app/templates')


def _rule(css, selector):
    match = re.search(re.escape(selector) + r'\s*\{([^}]*)\}', css)
    assert match, f'missing rule: {selector}'
    return match.group(1)


def _assert_no_outer_edge(body, selector):
    forbidden = ('border:', 'border-radius:', 'background-color:', 'box-shadow:')
    for declaration in forbidden:
        assert declaration not in body, f'{selector} owns {declaration}'


def test_shared_surface_contract_owns_each_outer_edge_once():
    components = COMPONENTS.read_text(encoding='utf-8')
    surface = _rule(
        components,
        '.card,\n  .panel,\n  .surface-card,\n  .surface-table',
    )
    assert 'border: 0' in surface
    assert 'border-radius: var(--radius-xl)' in surface
    assert 'background-color: var(--card)' in surface
    assert surface.count('0 0 0 1px var(--surface-ring)') == 1

    app = APP.read_text(encoding='utf-8')
    for selector in ('.hero-figure', '.ledger', '.disclosure__item'):
        _assert_no_outer_edge(_rule(app, selector), selector)


def test_surface_consumers_are_declared_in_templates():
    index = (TEMPLATES / 'index.html').read_text(encoding='utf-8')
    portfolios = (TEMPLATES / 'portfolios.html').read_text(encoding='utf-8')
    assets = (TEMPLATES / 'assets.html').read_text(encoding='utf-8')
    macros = (TEMPLATES / 'macros' / 'ui.html').read_text(encoding='utf-8')
    auth = (TEMPLATES / 'auth_base.html').read_text(encoding='utf-8')

    assert 'class="hero-figure surface-card"' in index
    assert 'class="card alloc-panel"' in index
    assert 'class="ledger surface-table"' in index
    assert 'portfolio-card surface-card surface-interactive' in portfolios
    assert 'symbol-card surface-card surface-interactive' in assets
    assert 'class="empty-state surface-card"' in macros
    assert 'class="auth-card surface-card"' in auth
    assert 'auth__showcase' not in auth


def test_disclosure_has_neutral_hover_and_container_focus_contract():
    components = COMPONENTS.read_text(encoding='utf-8')
    app = APP.read_text(encoding='utf-8')
    focus = _rule(
        components,
        '.surface-interactive:has(.surface-interactive__control:focus-visible)',
    )
    assert 'var(--surface-ring)' in focus
    assert 'var(--focus-ring-soft)' in focus

    assert '.disclosure__item:not(:has(.disclosure__toggle[aria-expanded="true"]))' not in app
    assert '.disclosure__head:has(.disclosure__toggle:hover)' in app
    hover_rule = re.search(
        r'\.disclosure__head:has\(\.disclosure__toggle:focus-visible\)\s*\{([^}]*)\}',
        app,
    )
    assert hover_rule
    assert 'background-color: var(--muted-half)' in hover_rule.group(1)
    assert not re.search(r'financial-|destructive', hover_rule.group(1))
    assert '.disclosure__panel' not in hover_rule.group(0)

    for template in ('portfolios.html', 'assets.html'):
        source = (TEMPLATES / template).read_text(encoding='utf-8')
        assert 'disclosure__toggle surface-interactive__control' in source
        assert 'disclosure__head' in source


def test_table_edges_use_one_canonical_separator_layer():
    components = COMPONENTS.read_text(encoding='utf-8')
    app = APP.read_text(encoding='utf-8')

    cells = _rule(components, '.table > :not(caption) > * > *')
    assert 'border-bottom-width: 0' in cells
    header = _rule(components, '.table thead th')
    rows = _rule(components, '.table tbody tr:not(:last-child) > *')
    assert 'border-bottom: 1px solid var(--border)' in header
    assert 'border-bottom: 1px solid var(--border)' in rows
    assert rows.count('border-bottom:') == 1

    ledger_row = _rule(app, '.ledger__row')
    panel = _rule(app, '.disclosure__panel')
    assert 'border-bottom: 1px solid var(--border)' in ledger_row
    assert 'border-top: 1px solid var(--border)' in panel
    assert 'line-subtle' not in ledger_row + panel


def test_expanded_financial_tables_share_nova_row_contract():
    components = COMPONENTS.read_text(encoding='utf-8')
    app = APP.read_text(encoding='utf-8')
    table_section = components.split('6. TABLES', 1)[1].split('7. BADGES', 1)[0]
    assert not re.search(r'#[0-9a-f]{3,8}\b|(?:oklch|rgba?)\(', table_section, re.I)

    table = _rule(components, '.table')
    for variable in (
        '--bs-table-bg: transparent',
        '--bs-table-accent-bg: transparent',
        '--bs-table-striped-bg: transparent',
        '--bs-table-hover-bg: transparent',
        '--bs-table-border-color: transparent',
    ):
        assert variable in table

    resting = _rule(components, '.table tbody tr > *')
    hover = _rule(components, '.table tbody tr:hover > *')
    selected = _rule(components, '.table tbody tr[data-state="selected"] > *')
    assert 'background-color: transparent' in resting
    assert 'background-color: var(--muted-half)' in hover
    assert 'background-color: var(--muted)' in selected
    assert 'transform' not in hover
    assert 'box-shadow' not in hover
    assert 'border' not in hover
    assert not re.search(r'financial-|destructive|oklch|#[0-9a-f]', hover, re.I)

    header = _rule(components, '.table thead th')
    assert 'background-color: transparent' in header
    assert 'color: var(--foreground)' in header
    assert 'font-weight: var(--weight-medium)' in header
    assert 'border-bottom: 1px solid var(--border)' in header

    panel = _rule(app, '.disclosure__panel')
    assert 'background-color: var(--card)' in panel
    assert '.disclosure__panel .table thead th' not in app

    for template in ('portfolios.html', 'assets.html'):
        source = (TEMPLATES / template).read_text(encoding='utf-8')
        assert 'records-table' in source
        assert 'table-hover' not in source
        assert 'table-light' not in source
        table = re.search(r'<table class="([^"]*records-table[^"]*)">', source)
        assert table
        for obsolete in (
            'table-sm', 'align-middle', 'mb-0', 'transactions-table',
            'dashboard-actions-table', 'portfolio-events-table',
        ):
            assert obsolete not in table.group(1).split()

    cells = _rule(components, '.table > :not(caption) > * > *')
    assert 'vertical-align: middle' in cells


def test_command_input_is_flat_and_independent_from_standalone_fields():
    components = COMPONENTS.read_text(encoding='utf-8')
    app = APP.read_text(encoding='utf-8')
    base = BASE.read_text(encoding='utf-8')
    template = (TEMPLATES / 'base.html').read_text(encoding='utf-8')

    command = _rule(components, '.command-input-group')
    command_focus = _rule(components, '.command-input-group:focus-within')
    inner = _rule(components, '.command-input-control')
    assert 'border: 0' in inner
    assert 'border-radius: 0' in inner
    assert 'box-shadow: none' in inner
    assert 'outline: 0' in inner

    assert 'height: var(--control-h)' in command
    assert 'border: 0' in command
    assert 'background-color: transparent' in command
    assert 'border-radius: var(--radius-lg)' in command
    assert 'box-shadow: none' in command
    assert 'outline: 0' in command
    assert 'border: 0' in command_focus
    assert 'background-color: var(--accent)' in command_focus
    assert 'box-shadow: none' in command_focus
    assert 'outline: 0' in command_focus
    assert not re.search(r'var\(--(?:ring|focus-ring)', command_focus)
    placeholder = _rule(
        components,
        '.command-input-control::placeholder',
    )
    assert 'color: var(--muted-foreground)' in placeholder
    focus_icon = _rule(components, '.command-input-group:focus-within > .icon')
    focus_control = _rule(
        components,
        '.command-input-group:focus-within > .command-input-control',
    )
    assert 'color: var(--accent-foreground)' in focus_icon
    assert 'color: var(--accent-foreground)' in focus_control
    assert '@media (forced-colors: active)' in base

    assert 'class="palette__search"' in template
    assert 'class="command-input-group"' in template
    assert 'palette__input command-input-control' in template
    assert 'compound-field' not in components
    assert 'compound-field' not in template
    command_input = re.search(r'<input[^>]+id="commandPaletteInput"[^>]*>', template)
    assert command_input and 'form-control' not in command_input.group(0)
    _assert_no_outer_edge(_rule(app, '.palette__dialog'), '.palette__dialog')
    palette_layout = _rule(app, '.palette__search')
    assert 'padding: var(--space-1)' in palette_layout
    assert 'padding-bottom: 0' in palette_layout
    assert not re.search(r'border|border-radius|background|box-shadow', palette_layout)
    assert '.palette__input {' not in app
    assert ':where(a, button, [role="button"], [tabindex]):focus-visible' in base
    assert re.search(r'(?m)^  :focus-visible\s*\{', base) is None


def test_sidebar_search_owns_one_sidebar_specific_focus_recipe():
    app = APP.read_text(encoding='utf-8')
    template = (TEMPLATES / 'base.html').read_text(encoding='utf-8')
    trigger = _rule(app, '.nav-search')
    focus = _rule(app, '.nav-search:focus-visible')
    assert 'height: var(--control-h)' in trigger
    assert 'border: 1px solid var(--sidebar-border)' in trigger
    assert 'border-radius: var(--radius-lg)' in trigger
    assert 'background-color: var(--background)' in trigger
    assert 'border-color: var(--sidebar-ring)' in focus
    assert 'var(--sidebar-ring) 50%' in focus
    sidebar_trigger = re.search(
        r'<button[^>]+class="nav-search"[^>]*data-palette-open[^>]*>',
        template,
    )
    assert sidebar_trigger
    assert 'command-input-group' not in sidebar_trigger.group(0)
