"""Colour maths shared by the design-token guardrails.

Everything here models what a browser actually does — sRGB compositing and
WCAG 2.1 relative luminance — so a test can predict the pixel a reader ends
up looking at rather than the value an author typed.

Not a test module: no `test_` prefix, so pytest collects nothing from it.
"""

import re

import pytest


TEXT_MIN = 4.5
NON_TEXT_MIN = 3.0


def parse_veil(value):
    """`rgb(r g b / a)` -> ((r, g, b), a)."""
    match = re.fullmatch(
        r'rgb\(\s*(\d+)\s+(\d+)\s+(\d+)\s*/\s*([\d.]+)\s*\)', value.strip()
    )
    assert match, f'expected rgb(r g b / a), got {value!r}'
    r, g, b, alpha = match.groups()
    return (int(r), int(g), int(b)), float(alpha)


def composite(colour, veil):
    """Paint a translucent veil over an opaque colour, as the browser does.

    `colour` may be a hex string or an (r, g, b) tuple; the return matches
    the input form.
    """
    (vr, vg, vb), alpha = veil
    as_hex = isinstance(colour, str)
    parts = to_rgb(colour) if as_hex else colour
    blended = tuple(
        round(c * (1 - alpha) + v * alpha)
        for c, v in zip(parts, (vr, vg, vb))
    )
    return '#' + ''.join(f'{c:02x}' for c in blended) if as_hex else blended


def stack(*veils):
    """Alpha-composite several veils of the same colour into one.

    Transparency multiplies, so `n` veils leave `Π(1 - aᵢ)` of the picture
    showing. Checking either layer alone would be wrong in opposite
    directions.
    """
    remaining = 1.0
    for _, alpha in veils:
        remaining *= (1 - alpha)
    return veils[0][0], 1 - remaining


def to_rgb(hex_colour):
    value = hex_colour.lstrip('#')
    if len(value) == 3:
        value = ''.join(ch * 2 for ch in value)
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


_LINEAR = [
    (c / 255 / 12.92) if c / 255 <= 0.04045
    else (((c / 255 + 0.055) / 1.055) ** 2.4)
    for c in range(256)
]


def relative_luminance(colour):
    r, g, b = to_rgb(colour) if isinstance(colour, str) else colour
    return 0.2126 * _LINEAR[r] + 0.7152 * _LINEAR[g] + 0.0722 * _LINEAR[b]


def contrast(foreground, background):
    a = relative_luminance(foreground)
    b = relative_luminance(background)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def declarations(block):
    """Every `--name: value;` pair in a chunk of CSS, last one winning."""
    found = {}
    for name, value in re.findall(r'(--[\w-]+)\s*:\s*([^;]+);', block):
        found[name.lstrip('-')] = value.strip()
    return found


def resolve(name, declared, seen=None):
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
        return resolve(match.group(1).lstrip('-'), declared, seen)

    pytest.fail(f'--{name} resolves to {value!r}, which is not a flat colour')


def theme_tokens(css, theme):
    """Flatten the primitives plus one theme's role block into a lookup.

    Light is the base `:root` definition; dark is the explicit
    `[data-theme="dark"]` block layered on top of it.
    """
    declared = {}
    for block in re.findall(r':root\s*\{([^}]*)\}', css):
        declared.update(declarations(block))

    if theme == 'dark':
        dark = re.search(r':root\[data-theme="dark"\]\s*\{([^}]*)\}', css)
        assert dark, 'no explicit [data-theme="dark"] block found'
        declared.update(declarations(dark.group(1)))

    return declared
