"""Legibility of copy that sits over the hero photograph.

Everywhere else in the product, text sits on a token, and a contrast check is
arithmetic on two hex values. Over a hero it sits on a *photograph*, so the
background is whatever the picture happens to be doing under each word — and
the only honest way to check that is to open the file and look.

That is what makes the backdrop visible. A scrim sized for a hypothetical
image has to assume pure black under light text and pure white under dark,
and no photograph is ever both; sizing it against the shipped picture instead
takes roughly 0.3 off the required alpha, which is the whole difference
between a photograph and a wash.

The trade is explicit and it runs in both directions:

- Swap the picture for a darker one and these tests demand a heavier shade,
  by exactly as much as the new pixels require.
- Let the shade drift heavier than the picture needs and
  `test_the_shade_is_no_heavier_than_the_photograph_requires` fails, because
  "the image should be visible" is a requirement too, not a preference.

Every measurement is made on the WebP, which is the universal fallback and
therefore the copy guaranteed to be what a reader sees. The AVIF is the same
picture at a better compression ratio; it only has to exist.
"""

from pathlib import Path

import pytest

from tests._colour import (
    TEXT_MIN,
    composite,
    contrast,
    parse_veil,
    resolve,
    theme_tokens,
    to_rgb,
)

# WCAG's large-text floor. It applies from 24px, or 18.66px bold; the hero
# title is 56px semibold and nothing else on the hero qualifies.
LARGE_TEXT_MIN = 3.0

Image = pytest.importorskip(
    'PIL.Image',
    reason='Pillow is required to measure the hero photograph (requirements-dev.txt)',
)

TOKENS = Path('portfolio_app/static/css/tokens.css')
HERO_WEBP = Path('portfolio_app/static/img/hero.webp')
HERO_AVIF = Path('portfolio_app/static/img/hero.avif')

# Regions of the photograph, as fractions of the image, that copy can land
# over. Both are deliberately wider than any single viewport puts text on:
# `object-fit: cover` crops differently at every window size, so a fixed
# rectangle has to cover the union of what the crop can expose, not one
# screenshot of it.
#
#   landing  the copy column occupies the left 46% of the hero (the shade's
#            plateau) between the header and the floor. Widened to 52% to
#            absorb the horizontal crop, which slides the mapping right.
#   auth     a half-viewport panel is always taller than 16:9, so it scales
#            the picture by height and crops the sides. How much it crops
#            depends entirely on the window: a laptop shows the middle half,
#            an ultrawide shows nearly all of it. Hence almost the full
#            frame, and its full height — the quote is centred vertically,
#            which means it moves.
COPY_REGIONS = {
    'landing hero': (0.00, 0.52, 0.20, 0.80),
    'auth showcase': (0.05, 0.95, 0.00, 1.00),
}

# The floating header spans the full width, and sits in the top band of
# whatever the crop exposes.
HEADER_REGION = (0.00, 1.00, 0.00, 0.18)

# The product card floats on the right half of the marketing hero. Padded
# left, because a horizontal crop slides the mapping inward.
CARD_REGION = (0.45, 1.00, 0.00, 1.00)

# What is printed on that card, and the floor each needs. Listing the inks
# the preview actually shows is the point: the fill is bounded by the worst
# of them, so a guess in either direction is wrong. A role the card does not
# print would cap the glass for nothing, and a role it does print but that
# nobody listed goes unmeasured — which is how the delta pill came to sit
# under the floor while this test passed.
#
# `--fg-muted` covers the labels and the legend, `--fg-default` the figures,
# and the two semantic hues are what the sample data happens to show. In the
# light theme `--pos` is the binding one: a small green number stands further
# from a cream surface than grey type does.
CARD_SURFACES = {
    'bg-surface': {
        'fg-muted': TEXT_MIN,
        'fg-default': TEXT_MIN,
        'pos': TEXT_MIN,
        'income': TEXT_MIN,
    },
    # The chrome carries no type today. `--fg-muted` is checked on it anyway
    # because it is the more hostile of the two surfaces, so a label that
    # lands there later fails here rather than in a screenshot.
    'bg-inset': {'fg-muted': TEXT_MIN},
}

# Sample at 1/4 scale. Averaging 4x4 blocks is not a shortcut: a glyph stroke
# covers several pixels and the eye integrates across them, so a lone
# specular pixel is not what a reader's contrast is set by. Finer than a
# stroke would make the test answer a question nobody is asking.
SAMPLE_REDUCTION = 4

# How much margin over the measured floor the shipped shade may keep. Enough
# to absorb antialiasing and a re-encode of the picture; not enough to hide a
# decision to darken the hero "just a bit" until it is a wash again.
SHADE_HEADROOM = 0.10

# The only foreground role allowed loose over a photograph, and the reason
# the hero's copy does not use a quieter step for its secondary lines. Every
# role below this one needs roughly 0.79 against this picture where the
# default needs 0.47 — tinting text down over an image costs the image.
HERO_FOREGROUND = 'fg-default'


@pytest.fixture(scope='module')
def css():
    assert TOKENS.exists(), f'{TOKENS} not found'
    return TOKENS.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def photograph():
    assert HERO_WEBP.exists(), f'{HERO_WEBP} not found'
    return Image.open(HERO_WEBP).convert('RGB')


_SAMPLES = {}


def _sample(photograph, region):
    """The distinct colours of one region, box-averaged to stroke scale.

    Distinct, because a region is tens of thousands of pixels drawn from a
    few thousand colours and only the colour matters here — the same value
    tested again cannot fail differently.
    """
    if region not in _SAMPLES:
        x0, x1, y0, y1 = region
        width, height = photograph.size
        box = (int(width * x0), int(height * y0),
               int(width * x1), int(height * y1))
        raw = photograph.crop(box).reduce(SAMPLE_REDUCTION).tobytes()
        _SAMPLES[region] = {
            (raw[i], raw[i + 1], raw[i + 2]) for i in range(0, len(raw), 3)
        }
    return _SAMPLES[region]


def _required_alpha(pixels, veil_colour, foreground, floor):
    """The lightest veil under which every pixel still clears `floor`.

    Contrast is monotonic in the veil's alpha here: the veil is the page's
    own colour, which is the far end of the range the text was designed
    against, so more of it always moves the background away from the ink.
    That makes a bisection exact rather than approximate — 20 halvings put
    the answer inside a millionth, far below the precision a stylesheet can
    express.
    """
    low, high = 0.0, 1.0
    for _ in range(20):
        mid = (low + high) / 2
        veil = (veil_colour, mid)
        if all(contrast(foreground, composite(p, veil)) >= floor for p in pixels):
            high = mid
        else:
            low = mid
    return high


def _shade(css, theme):
    return parse_veil(theme_tokens(css, theme)['hero-shade'])


def _percentage(value):
    """`94%` -> 0.94."""
    text = value.strip()
    assert text.endswith('%'), f'expected a percentage, got {value!r}'
    return float(text[:-1]) / 100


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_hero_copy_clears_its_floor_against_the_actual_photograph(
    css, photograph, theme
):
    declared = theme_tokens(css, theme)
    foreground = resolve(HERO_FOREGROUND, declared)
    veil_colour, shipped = _shade(css, theme)

    failures = []
    for name, region in COPY_REGIONS.items():
        needed = _required_alpha(
            _sample(photograph, region), veil_colour, foreground, TEXT_MIN
        )
        if shipped < needed:
            failures.append(
                f'{theme}/{name}: --hero-shade is {shipped:.3f}, but the '
                f'darkest and lightest pixels under the copy need '
                f'{needed:.3f} for --{HERO_FOREGROUND} to hold {TEXT_MIN}:1'
            )

    assert not failures, 'hero copy legibility:\n  ' + '\n  '.join(failures)


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_the_shade_is_no_heavier_than_the_photograph_requires(
    css, photograph, theme
):
    """The backdrop is meant to be seen. Excess veil is a regression.

    Without this the hero degrades one safe-looking tweak at a time: nothing
    ever fails, and a year later the picture is a texture behind a fog. The
    floor below is the strictest of the copy regions, so the shade has one
    number to sit just above.
    """
    declared = theme_tokens(css, theme)
    foreground = resolve(HERO_FOREGROUND, declared)
    veil_colour, shipped = _shade(css, theme)

    needed = max(
        _required_alpha(
            _sample(photograph, region), veil_colour, foreground, TEXT_MIN
        )
        for region in COPY_REGIONS.values()
    )

    assert shipped <= needed + SHADE_HEADROOM, (
        f'{theme}: --hero-shade is {shipped:.3f} where {needed:.3f} is '
        f'enough. Anything above {needed + SHADE_HEADROOM:.3f} is dimming '
        f'the photograph for no legibility gain — take it back down, or '
        f'change the picture the shade is being sized against.'
    )


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_the_floating_header_needs_no_veil_of_its_own(css, photograph, theme):
    """The marketing header sits on the hero with nothing behind it.

    That is only possible because the shade is uniform: the sky at the top
    of the picture is veiled exactly as much as the mountains under the
    title, so the header is already standing on the guarantee. Every earlier
    version had to darken a band down the top of the hero to hold this row
    up, and in the dark theme that band was the most conspicuous thing on
    the page.

    If this fails, the honest fix is a heavier `--hero-shade` — not a band.
    A band buys legibility in one strip by making the picture visibly
    patchy, which is the trade this hero exists to refuse.
    """
    declared = theme_tokens(css, theme)
    foreground = resolve(HERO_FOREGROUND, declared)
    veil_colour, shipped = _shade(css, theme)

    needed = _required_alpha(
        _sample(photograph, HEADER_REGION), veil_colour, foreground, TEXT_MIN
    )

    assert shipped >= needed, (
        f'{theme}: --hero-shade is {shipped:.3f}, but the sky behind the '
        f'floating header needs {needed:.3f} for --{HERO_FOREGROUND} to '
        f'hold {TEXT_MIN}:1'
    )


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_the_hero_title_gradient_survives_the_photograph(
    css, photograph, theme
):
    """Both ends of the brand gradient, at the large-text floor.

    3:1 rather than 4.5:1 is not a relaxation — WCAG sets it for text this
    size, and it is the entire reason a violet can go over a photograph
    when the body copy beside it cannot. Check both stops: a gradient is
    only as legible as its lighter end in the light theme and its darker
    end in the dark one, and which of the two that is flips with the theme.
    """
    declared = theme_tokens(css, theme)
    veil_colour, shipped = _shade(css, theme)
    pixels = _sample(photograph, COPY_REGIONS['landing hero'])

    failures = []
    for role in ('hero-title-from', 'hero-title-to'):
        colour = resolve(role, declared)
        needed = _required_alpha(pixels, veil_colour, colour, LARGE_TEXT_MIN)
        if shipped < needed:
            failures.append(
                f'{theme}: --{role} ({colour}) needs a shade of {needed:.3f} '
                f'to hold {LARGE_TEXT_MIN}:1 over this picture, but '
                f'--hero-shade is {shipped:.3f}'
            )

    assert not failures, 'hero title gradient:\n  ' + '\n  '.join(failures)


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_a_translucent_card_on_the_hero_still_carries_its_quietest_label(
    css, photograph, theme
):
    """The product card is glass, and glass lets the picture into the type.

    The constraint is never the card — it is the quietest ink printed on it,
    and raising that ink is what buys transparency. The photograph is sampled
    under the shade first, exactly as it reaches the card, and then the card's
    own fill is composited on top.

    Anything the card lays *over* its own surface has to come off before it
    reaches here: a tinted wash under type of the same hue pulls the
    background toward the ink, which is a veil running the wrong way. The
    delta pill on the marketing card drops its `--pos-soft` fill for exactly
    that reason.

    `backdrop-filter: blur()` is deliberately not modelled. Blurring moves
    every pixel toward its local mean and so can never produce a value
    outside the range checked here, which makes ignoring it the
    conservative choice rather than a gap.
    """
    declared = theme_tokens(css, theme)
    veil_colour, shade = _shade(css, theme)
    fill = _percentage(declared['hero-card-fill'])

    shaded = [
        composite(p, (veil_colour, shade))
        for p in _sample(photograph, CARD_REGION)
    ]

    failures = []
    for surface_role, roles in CARD_SURFACES.items():
        surface = to_rgb(resolve(surface_role, declared))
        for role, floor in roles.items():
            ink = resolve(role, declared)
            worst = min(
                contrast(ink, composite(p, (surface, fill))) for p in shaded
            )
            if worst < floor:
                failures.append(
                    f'{theme}: --{role} on a {fill:.0%} --{surface_role} '
                    f'card falls to {worst:.2f}:1 over the hero, needs '
                    f'{floor}:1'
                )

    assert not failures, 'hero card legibility:\n  ' + '\n  '.join(failures)


def test_the_fallback_encoding_ships_alongside_the_preferred_one():
    """AVIF is offered first; WebP is what a browser without it falls back to.

    Losing the fallback is silent — the `<source>` still resolves for most
    readers — so the absence only shows up on the machines least able to
    report it.
    """
    assert HERO_AVIF.exists(), f'{HERO_AVIF} is missing; the <picture> in ' \
        'components/hero_image.html offers it as the preferred encoding'
    assert HERO_WEBP.exists(), f'{HERO_WEBP} is missing; it is the <img> src'
