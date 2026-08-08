"""Contrast guardrails for the design tokens.

Colour choices in `tokens.css` are the one place where a small aesthetic
tweak can silently push text below a legibility threshold — the change looks
fine on the author's monitor and fails for everyone else. These tests parse
the real stylesheet, so they track the shipped values rather than a copy that
can drift.

Targets follow WCAG 2.1 AA: 4.5:1 for text, 3:1 for the `faint` step, which
is reserved for placeholders, disabled hints and decorative icons.

Text over the hero photograph is a different problem — the background there
is an image, not a token — and lives in `test_hero_legibility.py`.
"""

from pathlib import Path

import pytest

from tests._colour import (
    NON_TEXT_MIN,
    TEXT_MIN,
    composite,
    contrast,
    parse_veil,
    relative_luminance,
    resolve,
    theme_tokens,
)


TOKENS = Path('portfolio_app/static/css/tokens.css')

# Foreground roles that carry text, and the floor each must clear against
# every surface in its theme.
FOREGROUNDS = {
    'fg-default': TEXT_MIN,
    'fg-muted': TEXT_MIN,
    'fg-subtle': TEXT_MIN,
    'fg-faint': NON_TEXT_MIN,
    'pos': TEXT_MIN,
    'neg': TEXT_MIN,
    'income': TEXT_MIN,
    'warn': TEXT_MIN,
    'brand': TEXT_MIN,
}

SURFACES = ('bg-canvas', 'bg-surface', 'bg-raised', 'bg-inset')

# Solid buttons: (fill role, label role, hover fill role, veiled on hover?).
# The semantic solids hover by painting `--solid-hover-veil` over their fill,
# so that veil is part of the shipped hover colour and part of this check.
# `.btn-primary` is excluded from that rule — it swaps its fill instead.
SOLID_BUTTONS = (
    ('brand-solid', 'fg-on-brand', 'brand-solid-hover', False),
    ('pos', 'fg-on-solid', 'pos', True),
    ('neg', 'fg-on-solid', 'neg', True),
    ('warn', 'fg-on-solid', 'warn', True),
)


@pytest.fixture(scope='module')
def css():
    assert TOKENS.exists(), f'{TOKENS} not found'
    return TOKENS.read_text(encoding='utf-8')


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_every_text_role_clears_its_contrast_floor(css, theme):
    declared = theme_tokens(css, theme)

    failures = []
    for role, floor in FOREGROUNDS.items():
        fg = resolve(role, declared)
        for surface in SURFACES:
            bg = resolve(surface, declared)
            ratio = contrast(fg, bg)
            if ratio < floor:
                failures.append(
                    f'{theme}: --{role} ({fg}) on --{surface} ({bg}) '
                    f'is {ratio:.2f}:1, needs {floor}:1'
                )

    assert not failures, 'contrast regressions:\n  ' + '\n  '.join(failures)


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_surface_ladder_is_ordered_and_separated(css, theme):
    """Canvas -> surface -> raised must step consistently in one direction.

    Elevation is carried mostly by these steps rather than by shadow, so a
    ladder that flattens or inverts quietly removes the product's depth cues.
    """
    declared = theme_tokens(css, theme)
    ladder = [relative_luminance(resolve(n, declared))
              for n in ('bg-canvas', 'bg-surface', 'bg-raised')]

    if theme == 'dark':
        assert ladder[0] < ladder[1] < ladder[2], \
            f'dark surfaces must get lighter as they rise, got {ladder}'
    else:
        assert ladder[0] < ladder[1] <= ladder[2], \
            f'light surfaces must get lighter as they rise, got {ladder}'

    for lower, higher in zip(ladder, ladder[1:]):
        assert higher - lower > 0.002, \
            f'{theme}: adjacent surfaces are too close to tell apart ({ladder})'


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_solid_button_labels_stay_legible_at_rest_and_on_hover(css, theme):
    """A button's label sits on its fill, not on a page surface.

    Hover is checked too, and with the white overlay composited in: a hover
    state that brightens past the threshold makes the label fade exactly as
    the pointer lands on it, which is the worst possible moment for it.
    """
    declared = theme_tokens(css, theme)
    veil = parse_veil(declared['solid-hover-veil'])

    failures = []
    for fill_role, label_role, hover_role, veiled in SOLID_BUTTONS:
        label = resolve(label_role, declared)
        hover_fill = resolve(hover_role, declared)
        states = (
            ('rest', resolve(fill_role, declared)),
            ('hover', composite(hover_fill, veil) if veiled else hover_fill),
        )
        for state, fill in states:
            ratio = contrast(label, fill)
            if ratio < TEXT_MIN:
                failures.append(
                    f'{theme}: --{label_role} ({label}) on --{fill_role} '
                    f'{state} ({fill}) is {ratio:.2f}:1'
                )

    assert not failures, 'button label contrast:\n  ' + '\n  '.join(failures)


def test_brand_fill_is_distinguishable_from_the_page(css):
    """The solid brand is a shape, so it needs 3:1 against what surrounds it.

    This is the constraint that forces `--brand` and `--brand-solid` apart in
    dark mode: one violet cannot both carry white text and stay bright enough
    to read as text itself.
    """
    for theme in ('light', 'dark'):
        declared = theme_tokens(css, theme)
        fill = resolve('brand-solid', declared)
        for surface in SURFACES:
            bg = resolve(surface, declared)
            ratio = contrast(fill, bg)
            assert ratio >= NON_TEXT_MIN, (
                f'{theme}: --brand-solid ({fill}) on --{surface} ({bg}) '
                f'is {ratio:.2f}:1'
            )
