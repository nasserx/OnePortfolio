"""Contrast guardrails for the design tokens.

Colour choices in `tokens.css` are the one place where a small aesthetic
tweak can silently push text below a legibility threshold — the change looks
fine on the author's monitor and fails for everyone else. These tests parse
the real stylesheet, so they track the shipped values rather than a copy that
can drift.

Targets follow WCAG 2.1 AA: 4.5:1 for text, 3:1 for the `faint` step, which
is reserved for placeholders, disabled hints and decorative icons.
"""

import re
from pathlib import Path

import pytest


TOKENS = Path('portfolio_app/static/css/tokens.css')

TEXT_MIN = 4.5
NON_TEXT_MIN = 3.0

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


def _relative_luminance(hex_colour):
    value = hex_colour.lstrip('#')
    if len(value) == 3:
        value = ''.join(ch * 2 for ch in value)
    channels = []
    for i in (0, 2, 4):
        c = int(value[i:i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(foreground, background):
    a = _relative_luminance(foreground)
    b = _relative_luminance(background)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def _declarations(block):
    """Every `--name: value;` pair in a chunk of CSS, last one winning."""
    found = {}
    for name, value in re.findall(r'(--[\w-]+)\s*:\s*([^;]+);', block):
        found[name.lstrip('-')] = value.strip()
    return found


def _resolve(name, declared, seen=None):
    """Follow `var(--x)` chains down to a literal hex colour."""
    seen = seen or set()
    if name in seen:
        pytest.fail(f'circular token reference at --{name}')
    seen.add(name)

    value = declared.get(name)
    if value is None:
        pytest.fail(f'token --{name} is not defined for this theme')

    if value.startswith('#'):
        return value

    match = re.fullmatch(r'var\(\s*(--[\w-]+)\s*\)', value)
    if match:
        return _resolve(match.group(1).lstrip('-'), declared, seen)

    pytest.fail(f'--{name} resolves to {value!r}, which is not a flat colour')


def _theme_tokens(css, theme):
    """Flatten the primitives plus one theme's role block into a lookup.

    Light is the base `:root` definition; dark is the explicit
    `[data-theme="dark"]` block layered on top of it.
    """
    root_blocks = re.findall(r':root\s*\{([^}]*)\}', css)
    declared = {}
    for block in root_blocks:
        declared.update(_declarations(block))

    if theme == 'dark':
        dark = re.search(r':root\[data-theme="dark"\]\s*\{([^}]*)\}', css)
        assert dark, 'no explicit [data-theme="dark"] block found'
        declared.update(_declarations(dark.group(1)))

    return declared


@pytest.fixture(scope='module')
def css():
    assert TOKENS.exists(), f'{TOKENS} not found'
    return TOKENS.read_text(encoding='utf-8')


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_every_text_role_clears_its_contrast_floor(css, theme):
    declared = _theme_tokens(css, theme)

    failures = []
    for role, floor in FOREGROUNDS.items():
        fg = _resolve(role, declared)
        for surface in SURFACES:
            bg = _resolve(surface, declared)
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
    declared = _theme_tokens(css, theme)
    ladder = [_relative_luminance(_resolve(n, declared))
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


def test_on_brand_text_is_legible_on_the_brand_fill(css):
    """The primary button's label sits on the brand colour, not a surface."""
    for theme in ('light', 'dark'):
        declared = _theme_tokens(css, theme)
        brand = _resolve('brand', declared)
        on_brand = _resolve('fg-on-brand', declared)
        ratio = contrast(on_brand, brand)
        assert ratio >= 4.5, \
            f'{theme}: --fg-on-brand ({on_brand}) on --brand ({brand}) is {ratio:.2f}:1'
