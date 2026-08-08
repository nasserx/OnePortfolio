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


# What is allowed to sit over a hero photograph. `--fg-muted` is the floor
# for text and `--fg-subtle` is decoration only (the small proof icons):
# through the scrim, `--fg-subtle` reaches 4.06:1 and `--fg-faint` misses
# even the non-text bar, so neither is a text colour over imagery.
HERO_FOREGROUNDS = {
    'fg-default': TEXT_MIN,
    'fg-muted': TEXT_MIN,
    'fg-subtle': NON_TEXT_MIN,
}

# The extremes a photograph can put under a word. Checking both means the
# guarantee survives swapping the picture for a different one.
IMAGE_EXTREMES = ('#000000', '#ffffff')

# Chrome that floats on a hero — the marketing header's links, wordmark and
# bare controls — is protected by `--hero-scrim-band` stacked over the
# scrim's most open step, not by a panel of its own. Only `--fg-default`
# survives out there.
HERO_CHROME_FOREGROUNDS = {'fg-default': TEXT_MIN}


def _parse_veil(value):
    """`rgb(r g b / a)` -> ((r, g, b), a)."""
    match = re.fullmatch(
        r'rgb\(\s*(\d+)\s+(\d+)\s+(\d+)\s*/\s*([\d.]+)\s*\)', value.strip()
    )
    assert match, f'--solid-hover-veil is {value!r}, expected rgb(r g b / a)'
    r, g, b, alpha = match.groups()
    return (int(r), int(g), int(b)), float(alpha)


def _composite(hex_colour, veil):
    """Paint a translucent veil over an opaque colour, as the browser does."""
    (vr, vg, vb), alpha = veil
    value = hex_colour.lstrip('#')
    parts = [int(value[i:i + 2], 16) for i in (0, 2, 4)]
    return '#' + ''.join(
        f'{round(c * (1 - alpha) + v * alpha):02x}'
        for c, v in zip(parts, (vr, vg, vb))
    )


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


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_solid_button_labels_stay_legible_at_rest_and_on_hover(css, theme):
    """A button's label sits on its fill, not on a page surface.

    Hover is checked too, and with the white overlay composited in: a hover
    state that brightens past the threshold makes the label fade exactly as
    the pointer lands on it, which is the worst possible moment for it.
    """
    declared = _theme_tokens(css, theme)
    veil = _parse_veil(declared['solid-hover-veil'])

    failures = []
    for fill_role, label_role, hover_role, veiled in SOLID_BUTTONS:
        label = _resolve(label_role, declared)
        hover_fill = _resolve(hover_role, declared)
        states = (
            ('rest', _resolve(fill_role, declared)),
            ('hover', _composite(hover_fill, veil) if veiled else hover_fill),
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
        declared = _theme_tokens(css, theme)
        fill = _resolve('brand-solid', declared)
        for surface in SURFACES:
            bg = _resolve(surface, declared)
            ratio = contrast(fill, bg)
            assert ratio >= NON_TEXT_MIN, (
                f'{theme}: --brand-solid ({fill}) on --{surface} ({bg}) '
                f'is {ratio:.2f}:1'
            )


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_hero_copy_is_legible_over_any_photograph(css, theme):
    """Hero copy must not depend on which pixel lands under it.

    A hero backdrop is a photograph, so the colour behind a word is whatever
    the image happens to be doing there — and the image can be replaced. The
    scrim is what makes that safe: `--hero-scrim-strong` is the strength the
    copy always sits on, so it is checked against both extremes a photograph
    can produce. `soft` and `edge` are deliberately not checked; they cover
    regions that carry no text, and the layouts must keep it that way.
    """
    declared = _theme_tokens(css, theme)
    scrim = _parse_veil(declared['hero-scrim-strong'])

    failures = []
    for role, floor in HERO_FOREGROUNDS.items():
        fg = _resolve(role, declared)
        for pixel in IMAGE_EXTREMES:
            behind = _composite(pixel, scrim)
            ratio = contrast(fg, behind)
            if ratio < floor:
                failures.append(
                    f'{theme}: --{role} ({fg}) over a {pixel} image pixel '
                    f'under --hero-scrim-strong resolves to {behind} '
                    f'= {ratio:.2f}:1, needs {floor}:1'
                )

    assert not failures, 'hero legibility:\n  ' + '\n  '.join(failures)


def _stack(*veils):
    """Alpha-composite several veils of the same colour into one."""
    remaining = 1.0
    for _, alpha in veils:
        remaining *= (1 - alpha)
    return veils[0][0], 1 - remaining


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_hero_chrome_is_legible_where_the_scrim_is_most_open(css, theme):
    """The floating header's worst case is the top *corner* of the hero.

    There the copy scrim has eased all the way down to `--hero-scrim-edge`,
    and the only thing holding the header up is `--hero-scrim-band`. Those
    two stack, so the check has to stack them too — testing the band alone
    would flatter it, and testing `edge` alone would condemn it.
    """
    declared = _theme_tokens(css, theme)
    band = _parse_veil(declared['hero-scrim-band'])
    edge = _parse_veil(declared['hero-scrim-edge'])
    combined = _stack(band, edge)

    failures = []
    for role, floor in HERO_CHROME_FOREGROUNDS.items():
        fg = _resolve(role, declared)
        for pixel in IMAGE_EXTREMES:
            ratio = contrast(fg, _composite(pixel, combined))
            if ratio < floor:
                failures.append(
                    f'{theme}: --{role} ({fg}) over a {pixel} pixel under '
                    f'band+edge ({combined[1]:.3f}) is {ratio:.2f}:1'
                )

    assert not failures, 'hero chrome legibility:\n  ' + '\n  '.join(failures)
