"""Source-level recipe/state contracts; user owns rendered visual acceptance.

Targets were inspected from ui.shadcn.com/r/styles/base-nova on 2026-10-12.
Behavioral feedback and transport remain covered by test_form_feedback and
modal_form_errors.js; these guards prevent CSS from bypassing that lifecycle.
"""

from pathlib import Path
import re

import pytest

from tests._colour import theme_tokens
from tests.test_modal_accessible_names import _logged_in_client


ROOT = Path('portfolio_app')
CSS = (ROOT / 'static/css/components.css').read_text(encoding='utf-8')
TOKENS = (ROOT / 'static/css/tokens.css').read_text(encoding='utf-8')
APP = (ROOT / 'static/css/app.css').read_text(encoding='utf-8')
CALENDAR = (ROOT / 'static/css/flatpickr-nova.css').read_text(encoding='utf-8')


def rule(css, selector):
    found = re.search(re.escape(selector) + r'\s*\{([^}]*)\}', css)
    assert found, selector
    return found.group(1)


def test_roles_do_not_conflate_titles_headers_and_descriptions():
    # Colour-token helpers flatten :root blocks; typography has a separate
    # responsive override, tested explicitly in the Phase 4 size contract.
    assert re.search(r'--text-sm:\s*([^;]+)', TOKENS)[1] == '0.75rem'
    for source, selector, color in (
        (CSS, '.panel__title', 'card-foreground'),
        (CSS, '.table thead th', 'foreground'),
        (CSS, 'label.form-label', 'foreground'),
        (APP, '.ledger__row--head', 'foreground'),
        (APP, '.hero-figure__label', 'card-foreground'),
        (CSS, '.supporting-item__label', 'muted-foreground'),
        (APP, '.metric__label', 'muted-foreground'),
    ):
        assert f'color: var(--{color})' in rule(source, selector)
    assert 'height: var(--row-h)' in rule(CSS, '.table thead th')
    assert 'font-size: var(--text-sm)' in rule(CSS, '.notes-counter')


@pytest.mark.parametrize('theme,alpha', [('light', '20%'), ('dark', '40%')])
def test_invalid_states_use_reference_ring_without_changing_input_fill(theme, alpha):
    tokens = theme_tokens(TOKENS, theme)
    assert alpha in tokens['control-invalid-ring']
    invalid = rule(CSS, '.tx-type-tab[aria-invalid="true"]')
    assert 'border-color: var(--control-invalid-border)' in invalid
    assert 'box-shadow: 0 0 0 3px var(--control-invalid-ring)' in invalid
    assert 'background' not in invalid
    assert not re.search(r'(?<![\w-]):invalid\b\s*[{,]', CSS)
    assert '.was-validated' not in CSS
    assert '.form-control[aria-invalid="true"]' in CSS


def test_disabled_select_is_not_a_disabled_input_and_readonly_keeps_input_recipe():
    assert 'var(--control-background-disabled)' in rule(CSS, '.form-control:disabled')
    assert '.form-select:disabled { background-color: var(--control-background); }' in CSS
    common = rule(CSS, '.form-control:disabled,\n  .form-select:disabled')
    assert 'opacity: 0.5' in common
    assert 'color:' not in common
    readonly = rule(CSS, '.form-control[readonly]')
    assert not any(prop in readonly for prop in ('background', 'opacity', 'pointer-events'))


def test_action_menu_trigger_and_icons_have_independent_reference_sizes():
    trigger = rule(CSS, '.btn-icon')
    small = rule(CSS, '.btn-icon.btn-sm')
    assert 'width: var(--control-h)' in trigger
    assert 'height: var(--control-h)' in trigger
    assert 'width: var(--control-h-sm)' in small
    assert 'height: var(--control-h-sm)' in small
    assert 'width: 1rem' in rule(CSS, '.btn-icon.btn-sm .icon')
    assert '.btn:active:not([aria-haspopup])' in CSS
    assert not re.search(r'\.btn:active\s*\{', CSS)
    assert 'background-color: var(--muted)' in rule(CSS, '.btn-icon[aria-expanded="true"]')
    assert '.dropdown-menu.show { animation: op-fade-in' in CSS
    assert 'pointer-events: none' in rule(CSS, '.dropdown-item[aria-disabled="true"]')


def test_button_hover_and_press_cannot_erase_keyboard_focus():
    assert CSS.index('.btn:focus-visible {') > CSS.index('.btn-icon:hover {')
    assert CSS.index('.btn:focus-visible {') > CSS.index('.btn-link:hover {')
    assert 'box-shadow' not in rule(CSS, '.btn:active:not([aria-haspopup])')
    assert 'var(--focus-ring-soft)' in rule(CSS, '.btn:focus-visible')
    assert 'var(--control-invalid-ring)' in rule(CSS, '.btn-outline-danger:focus-visible')


def test_dialog_alert_and_empty_recipes_keep_distinct_surface_and_type_roles():
    assert 'border-bottom: 0' in rule(CSS, '.modal-header')
    title = rule(CSS, '.modal-title')
    assert 'font-size: var(--text-lg)' in title
    assert 'font-weight: var(--weight-medium)' in title
    assert 'var(--muted-half)' in rule(CSS, '.modal-footer')
    assert 'column-reverse' in CSS
    assert 'min-height: 0' in rule(CSS, '.modal-dialog-scrollable .modal-content > form')
    assert 'background-color: var(--card)' in rule(CSS, '.alert')
    assert 'background' not in rule(CSS, '.alert-danger')
    assert 'var(--destructive)' in rule(CSS, '.alert-danger')
    assert 'font-size: var(--text-sm)' in rule(CSS, '.empty-state-title')
    assert 'width: 2rem' in rule(CSS, '.empty-state__icon')
    assert '.btn-close::before' not in CSS


def test_pagination_selected_is_outline_and_keyboard_focus_survives_forced_colors():
    selected = rule(CSS, '.pagination__control[aria-current="page"]')
    assert 'var(--outline-background)' in selected
    assert 'var(--outline-border)' in selected
    assert 'var(--focus-ring-soft)' in rule(CSS, '.pagination__control:focus-visible')
    utilities = CSS.split('@layer utilities', 1)[1]
    assert '@media (forced-colors: active)' in utilities
    assert 'outline: 2px solid CanvasText' in utilities


def test_calendar_distinguishes_today_selected_outside_and_disabled_days():
    assert '--calendar-cell: 1.75rem' in CALENDAR
    assert 'var(--muted)' in rule(CALENDAR, '.op-flatpickr .flatpickr-day.today')
    outside = rule(CALENDAR, '.op-flatpickr .flatpickr-day.nextMonthDay')
    assert 'var(--muted-foreground)' in outside
    assert 'opacity' not in outside
    disabled = rule(CALENDAR, '.op-flatpickr .flatpickr-day.flatpickr-disabled:hover')
    assert 'opacity: 0.5' in disabled
    assert 'var(--primary-foreground)' in rule(
        CALENDAR, '.op-flatpickr .flatpickr-day.selected:is(.prevMonthDay, .nextMonthDay)'
    )
    main = (ROOT / 'static/js/main.js').read_text(encoding='utf-8')
    assert 'prevArrow:' in main and '#op-icon-chevron-left' in main
    assert 'nextArrow:' in main and '#op-icon-chevron-right' in main
    assert "dateFormat: 'Y-m-d'" in main


def test_rendered_dialog_close_icons_keep_accessible_names_and_vendor_ownership(app):
    client = _logged_in_client(app)
    count = 0
    for path in ('/transactions/', '/portfolios/'):
        response = client.get(path)
        assert response.status_code == 200
        buttons = re.findall(
            r'<button\b[^>]*class="btn-close"[^>]*>.*?</button>',
            response.get_data(as_text=True), re.S,
        )
        assert buttons
        for button in buttons:
            assert 'aria-label="Close"' in button
            assert 'data-bs-dismiss="modal"' in button
            assert 'aria-hidden="true"' in button
            assert '#op-icon-x' in button
        count += len(buttons)
    assert count == 17
