"""Static contracts for the Flask translation of shadcn's Nova recipes."""

from pathlib import Path
import re


COMPONENTS = Path('portfolio_app/static/css/components.css')
BASE = Path('portfolio_app/static/css/base.css')
TOKENS = Path('portfolio_app/static/css/tokens.css')
FLATPICKR = Path('portfolio_app/static/css/flatpickr-nova.css')


def _rule(css, selector):
    match = re.search(re.escape(selector) + r'\s*\{([^}]*)\}', css)
    assert match, f'missing rule: {selector}'
    return match.group(1)


def test_button_uses_compact_nova_geometry_and_focus_recipe():
    css = COMPONENTS.read_text(encoding='utf-8')
    button = _rule(css, '.btn')
    assert 'min-height: var(--control-h)' in button
    assert 'border-radius: var(--radius-lg)' in button
    assert '--btn-line: transparent' in button

    focus = _rule(css, '.btn:focus-visible')
    assert 'border-color: var(--ring)' in focus
    assert 'box-shadow: 0 0 0 3px var(--focus-ring-soft)' in focus
    assert 'outline: 2px' not in focus

    small = _rule(css, '.btn-sm')
    assert 'min-height: var(--control-h-sm)' in small
    large = _rule(css, '.btn-lg')
    assert 'min-height: 2.25rem' in large


def test_inputs_and_native_select_follow_nova_and_theme_contract():
    css = COMPONENTS.read_text(encoding='utf-8')
    fields = _rule(css, '.form-control,\n  .form-select')
    assert 'min-height: var(--control-h)' in fields
    assert 'border: 1px solid var(--input)' in fields
    assert 'border-radius: var(--radius-lg)' in fields
    assert 'background-color: var(--control-background)' in fields

    focus = _rule(css, '.form-control:focus,\n  .form-select:focus')
    assert 'border-color: var(--ring)' in focus
    assert 'box-shadow: 0 0 0 3px var(--focus-ring-soft)' in focus
    assert 'focus-indicator' not in focus

    select_rules = re.findall(r'(?m)^  \.form-select\s*\{([^}]*)\}', css)
    assert select_rules
    select = select_rules[-1]
    assert 'color-scheme: light' in select
    options = _rule(css, '.form-select option,\n  .form-select optgroup')
    assert 'background-color: var(--popover)' in options
    assert 'color: var(--popover-foreground)' in options
    assert ':root[data-theme="dark"] .form-select { color-scheme: dark; }' in css
    assert ':root:not([data-theme="light"]) .form-select { color-scheme: dark; }' in css
    disabled = _rule(css, '.form-control:disabled,\n  .form-select:disabled')
    assert 'opacity: 0.5' in disabled
    assert '.form-control[readonly]' not in disabled
    readonly = _rule(css, '.form-control[readonly]')
    assert 'cursor: default' in readonly

    tokens = TOKENS.read_text(encoding='utf-8')
    assert "viewBox='0 0 24 24'" in tokens
    assert "d='M8 9l4-4l4 4m0 6l-4 4l-4-4'" in tokens


def test_card_dialog_tabs_and_menu_use_recipe_radius_tiers():
    css = COMPONENTS.read_text(encoding='utf-8')
    card = _rule(css, '.card,\n  .panel,\n  .surface-card,\n  .surface-table')
    assert 'border-radius: var(--radius-xl)' in card
    assert 'border: 0' in card
    assert 'box-shadow: 0 0 0 1px var(--surface-ring)' in card

    dialog = _rule(css, '.surface-dialog,\n  .modal-content')
    assert 'border-radius: var(--radius-xl)' in dialog
    assert '0 0 0 1px var(--surface-ring)' in dialog

    tabs = _rule(css, '.segmented')
    assert 'padding: 3px' in tabs
    assert 'border-radius: var(--radius-lg)' in tabs
    assert 'background-color: var(--muted)' in tabs
    trigger = _rule(css, '.segmented__option')
    assert 'border-radius: var(--radius-md)' in trigger

    menu = _rule(css, '.dropdown-menu')
    assert 'border-radius: var(--radius-lg)' in menu
    item = _rule(css, '.dropdown-item')
    assert 'border-radius: var(--radius-md)' in item
    assert 'gap: 0.375rem' in item
    assert 'font-size: var(--text-sm)' in item
    assert 'cursor: default' in item
    menu_geometry = re.findall(r'(?m)^  \.dropdown-menu\s*\{([^}]*)\}', css)[-1]
    assert 'min-width: 8rem' in menu_geometry
    divider = _rule(css, '.dropdown-divider')
    assert 'margin: var(--space-1) calc(-1 * var(--space-1))' in divider


def test_tooltip_help_error_and_financial_delta_follow_nova_recipes():
    css = COMPONENTS.read_text(encoding='utf-8')

    tooltip_root = _rule(css, '.tooltip')
    assert '--bs-tooltip-opacity: 1' in tooltip_root
    assert 'opacity: 1 !important' not in tooltip_root
    tooltip = _rule(css, '.tooltip .tooltip-inner')
    assert 'max-width: 20rem' in tooltip
    assert 'padding: 0.375rem var(--space-3)' in tooltip
    assert 'border-radius: var(--radius-md)' in tooltip
    assert 'background-color: var(--foreground)' in tooltip
    assert 'color: var(--background)' in tooltip
    assert 'font-size: var(--text-xs)' in tooltip
    assert 'box-shadow' not in tooltip

    arrow = re.findall(r'(?m)^  \.tooltip \.tooltip-arrow::before\s*\{([^}]*)\}', css)[-1]
    assert 'width: 0.625rem' in _rule(
        css, '.tooltip .tooltip-arrow,\n  .tooltip .tooltip-arrow::before'
    )
    assert 'background-color: var(--foreground)' in arrow
    assert 'border-radius: 2px' in arrow
    assert 'transform: rotate(45deg)' in arrow

    trigger = _rule(css, '.info-dot')
    for expected in (
        'width: 1.5rem', 'height: 1.5rem',
        'border-radius: var(--radius-md)', 'background-color: transparent',
    ):
        assert expected in trigger
    trigger_focus = _rule(css, '.info-dot:focus-visible')
    assert 'border-color: var(--ring)' in trigger_focus
    assert 'box-shadow: 0 0 0 3px var(--focus-ring-soft)' in trigger_focus

    error = _rule(css, '.invalid-feedback')
    assert 'color: var(--destructive)' in error
    assert 'font-size: var(--text-sm)' in error

    delta = _rule(css, '.delta')
    assert 'height: 1.25rem' in delta
    assert 'padding: 0.125rem var(--space-2)' in delta
    assert 'border-radius: var(--radius-4xl)' in delta
    assert 'font-size: var(--text-xs)' in delta


def test_table_uses_nova_neutral_rows_and_single_separator_recipe():
    css = COMPONENTS.read_text(encoding='utf-8')
    table = _rule(css, '.table')
    assert 'color: var(--foreground)' in table
    assert 'font-size: var(--text-sm)' in table

    header = _rule(css, '.table thead th')
    assert 'background-color: transparent' in header
    assert 'color: var(--foreground)' in header
    assert 'font-weight: var(--weight-medium)' in header

    cells = _rule(css, '.table tbody tr > *')
    assert 'background-color: transparent' in cells
    assert 'transition:' in cells

    row = _rule(css, '.table tbody tr:not(:last-child) > *')
    assert 'border-bottom: 1px solid var(--border)' in row
    hover = _rule(css, '.table tbody tr:hover > *')
    assert 'background-color: var(--muted-half)' in hover
    selected = _rule(css, '.table tbody tr[data-state="selected"] > *')
    assert 'background-color: var(--muted)' in selected


def test_secondary_badge_uses_official_nova_recipe():
    css = COMPONENTS.read_text(encoding='utf-8')
    badge = _rule(css, '.badge')
    assert 'height: 1.25rem' in badge
    assert 'padding: 0.125rem var(--space-2)' in badge
    assert 'border: 1px solid transparent' in badge
    assert 'border-radius: var(--radius-4xl)' in badge
    assert 'font-size: var(--text-xs)' in badge

    secondary = _rule(css, '.badge--secondary')
    assert 'background-color: var(--secondary)' in secondary
    assert 'color: var(--secondary-foreground)' in secondary
    assert not re.search(
        r'financial-|(?:portfolio-)?chart-|#[0-9a-f]{3,8}\b|(?:oklch|rgba?)\(',
        secondary,
        re.I,
    )

    assets = Path('portfolio_app/templates/assets.html').read_text(encoding='utf-8')
    assert 'class="badge badge--secondary">{{ item.portfolio.name }}</span>' in assets


def test_transaction_direction_selected_states_are_narrow_and_semantic():
    css = COMPONENTS.read_text(encoding='utf-8')
    neutral = _rule(css, '.tx-type-tab')
    assert 'background-color: transparent' in neutral
    assert 'color: var(--muted-foreground)' in neutral
    assert 'border: 1px solid transparent' in neutral
    assert 'financial-' not in neutral
    assert 'transform' not in neutral

    buy_selector = (
        '.tx-tab-buy.active,\n'
        '  .tx-tab-buy.active:hover,\n'
        '  .tx-tab-buy.active:focus,\n'
        '  .tx-tab-buy.active:focus-visible'
    )
    buy = _rule(css, buy_selector)
    assert 'background-color: var(--financial-positive-soft)' in buy
    assert 'border-color: var(--financial-positive-line)' in buy
    assert 'color: var(--financial-positive)' in buy
    assert not re.search(r'negative|destructive|chart-', buy)
    assert 'box-shadow' not in buy

    sell_selector = (
        '.tx-tab-sell.active,\n'
        '  .tx-tab-sell.active:hover,\n'
        '  .tx-tab-sell.active:focus,\n'
        '  .tx-tab-sell.active:focus-visible'
    )
    sell = _rule(css, sell_selector)
    assert 'background-color: var(--financial-negative-soft)' in sell
    assert 'border-color: var(--financial-negative-line)' in sell
    assert 'color: var(--financial-negative)' in sell
    assert not re.search(r'positive|destructive|chart-', sell)
    assert 'box-shadow' not in sell

    neutral_hover = _rule(css, '.tx-type-tab:hover')
    assert 'background-color: var(--accent)' in neutral_hover
    assert 'color: var(--accent-foreground)' in neutral_hover
    assert 'financial-' not in neutral_hover
    assert css.index('.tx-type-tab:hover') < css.index('.tx-tab-buy.active,')
    assert not re.search(r'(?m)^\s*\.tx-type-tab\.active\s*\{', css)

    base = BASE.read_text(encoding='utf-8')
    focus = _rule(base, ':where(a, button, [role="button"], [tabindex]):focus-visible')
    assert 'var(--focus-ring-soft)' in focus

    for selector in ('.btn', '.segmented__option', '.navlink'):
        body = _rule(css, selector) if selector != '.navlink' else None
        if body is not None:
            assert 'financial-' not in body

    assets = Path('portfolio_app/templates/assets.html').read_text(encoding='utf-8')
    assert "if (typeSelect) typeSelect.value = 'Buy';" in assets
    assert "if (!typeSelect.value) typeSelect.value = 'Buy';" in assets
    assert "buyBtn.classList.toggle('active', isBuy);" in assets
    assert "sellBtn.classList.toggle('active', isSell);" in assets
    assert "setType('Buy');" in assets
    assert "setType('Sell');" in assets
    assert 'tx-theme-buy' not in assets
    assert 'tx-theme-sell' not in assets


def test_ordinary_focus_has_no_hard_coded_white_double_outline():
    combined = '\n'.join(
        path.read_text(encoding='utf-8') for path in (BASE, COMPONENTS, TOKENS)
    )
    assert '--focus-indicator' not in combined
    assert 'outline: 2px solid var(--focus-indicator)' not in combined
    assert '@media (forced-colors: active)' in combined
    assert 'outline: 2px solid CanvasText' in combined


def test_selection_and_caret_are_one_global_preset_derived_contract():
    base = BASE.read_text(encoding='utf-8')
    tokens = TOKENS.read_text(encoding='utf-8')
    selection_match = re.search(r'(?m)^  ::selection\s*\{([^}]*)\}', base)
    assert selection_match
    selection = selection_match.group(1)
    assert 'background-color: var(--selection-background)' in selection
    assert 'color: var(--selection-foreground)' in selection
    assert tokens.count('--selection-background: var(--primary);') == 1
    assert tokens.count('--selection-foreground: var(--primary-foreground);') == 1
    assert tokens.count('--caret-color: var(--foreground);') == 1

    caret_match = re.search(
        r'(?m)^  :where\(input, textarea, \[contenteditable="true"\]\)\s*'
        r'\{([^}]*)\}',
        base,
    )
    assert caret_match
    caret = caret_match.group(1)
    assert 'caret-color: var(--caret-color)' in caret
    autofill = _rule(
        base,
        'input:-webkit-autofill,\n  input:-webkit-autofill:hover,\n  input:-webkit-autofill:focus,\n  textarea:-webkit-autofill,\n  select:-webkit-autofill',
    )
    assert 'caret-color: var(--caret-color)' in autofill

    author_selection = re.sub(
        r'@media \(forced-colors: active\)\s*\{.*?\n  \}', '', base, flags=re.S
    )
    assert author_selection.count('::selection') == 1
    selection_contract = selection + caret
    assert not re.search(r'financial-|(?:portfolio-)?chart-|brand-', selection_contract)
    assert ':root ::selection' in base
    assert 'background-color: Highlight' in base
    assert 'color: HighlightText' in base
    assert 'caret-color: auto' in base


def test_flatpickr_consumes_canonical_roles_in_both_theme_paths():
    css = FLATPICKR.read_text(encoding='utf-8')
    calendar = _rule(css, '.op-flatpickr.flatpickr-calendar')
    for expected in (
        'background-color: var(--popover)',
        'color: var(--popover-foreground)',
        'border-radius: var(--radius-xl)',
        '0 0 0 1px var(--surface-ring)',
    ):
        assert expected in calendar
    assert ':root[data-theme="dark"] .op-flatpickr.flatpickr-calendar' in css
    assert ':root:not([data-theme="light"]) .op-flatpickr.flatpickr-calendar' in css
    assert '.flatpickr-day.selected' in css
    assert '.flatpickr-day.flatpickr-disabled' in css
    assert '.flatpickr-monthDropdown-months option' in css

    for template in ('assets.html', 'portfolios.html'):
        source = Path('portfolio_app/templates', template).read_text(encoding='utf-8')
        assert source.index('flatpickr.min.css') < source.index('flatpickr-nova.css')
