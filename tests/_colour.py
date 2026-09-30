"""Colour maths shared by design-token guardrails.

The preset is authored in OKLCH. Conversion follows the CSS Color 4 OKLab
matrices before WCAG 2.1 luminance is calculated in linear sRGB.
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


def _linear_to_srgb(channel):
    channel = max(0.0, min(1.0, channel))
    encoded = 12.92 * channel if channel <= 0.0031308 else (
        1.055 * (channel ** (1 / 2.4)) - 0.055
    )
    return round(encoded * 255)


def _oklab_to_rgb(lightness, a, b):
    l_ = lightness + 0.3963377774 * a + 0.2158037573 * b
    m_ = lightness - 0.1055613458 * a - 0.0638541728 * b
    s_ = lightness - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    return tuple(map(_linear_to_srgb, (
        4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    )))


def _oklch_to_rgb(lightness, chroma, hue):
    from math import cos, radians, sin

    angle = radians(hue)
    return _oklab_to_rgb(
        lightness,
        chroma * cos(angle),
        chroma * sin(angle),
    )


def mix_oklab(first, second, first_weight):
    """Mix two opaque OKLCH literals in Cartesian OKLab coordinates."""
    from math import cos, radians, sin

    def coordinates(value):
        match = re.fullmatch(
            r'oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\)',
            value.strip(),
        )
        assert match, f'expected opaque OKLCH literal, got {value!r}'
        lightness, chroma, hue = map(float, match.groups())
        angle = radians(hue)
        return lightness, chroma * cos(angle), chroma * sin(angle)

    first_oklab = coordinates(first)
    second_oklab = coordinates(second)
    second_weight = 1 - first_weight
    mixed = tuple(
        a * first_weight + b * second_weight
        for a, b in zip(first_oklab, second_oklab)
    )
    return _oklab_to_rgb(*mixed)


def to_rgba(colour):
    value = colour.strip()
    if value.startswith('#'):
        raw = value.lstrip('#')
        if len(raw) == 3:
            raw = ''.join(ch * 2 for ch in raw)
        return tuple(int(raw[i:i + 2], 16) for i in (0, 2, 4)) + (1.0,)

    match = re.fullmatch(
        r'oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)'
        r'(?:\s*/\s*([\d.]+)(%?))?\s*\)', value,
    )
    assert match, f'unsupported colour literal {colour!r}'
    lightness, chroma, hue, alpha, percent = match.groups()
    opacity = float(alpha) / 100 if alpha and percent else float(alpha or 1)
    return _oklch_to_rgb(float(lightness), float(chroma), float(hue)) + (opacity,)


def to_rgb(colour):
    return to_rgba(colour)[:3]


_LINEAR = [
    (c / 255 / 12.92) if c / 255 <= 0.04045
    else (((c / 255 + 0.055) / 1.055) ** 2.4)
    for c in range(256)
]


def relative_luminance(colour):
    r, g, b = to_rgb(colour) if isinstance(colour, str) else colour[:3]
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
    """Follow `var(--x)` chains down to a supported colour literal."""
    seen = seen or set()
    if name in seen:
        pytest.fail(f'circular token reference at --{name}')
    seen.add(name)

    value = declared.get(name)
    if value is None:
        pytest.fail(f'token --{name} is not defined for this theme')

    if value.startswith(('#', 'oklch(')):
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
