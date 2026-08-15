"""The OnePortfolio brand lockup: one size, everywhere it appears.

The mark and the wordmark are one unit, and until recently they were sized in
three places at once — `.brand` in `components.css` set the type, while every
template that rendered the lockup passed its own `logo_size` to
`components/logo_mark.html`. Nothing held those numbers together, so the
marketing header and the app shell could drift apart a pixel at a time and no
test would notice.

`.brand` owns all of it now. What is checked here is that it keeps owning it:
one declaration per dimension, no page stylesheet quietly restating them, and
no call site reaching past the class to size the mark itself.

The standalone mark on the auth and error pages is deliberately *not* part of
this. It appears without the wordmark, centred above a card, and is a
different piece of furniture that happens to use the same image.
"""

import re
from pathlib import Path

_CSS = Path('portfolio_app/static/css')
_TEMPLATES = Path('portfolio_app/templates')
_PARTIAL = _TEMPLATES / 'components' / 'logo_mark.html'

# Dimensions the lockup owns, and the value each is expected to resolve to.
# Named rather than measured so a change here is a decision someone typed.
_OWNED = {
    '--brand-mark-size': '2rem',
    'font-size': 'var(--text-lg)',
    'font-weight': 'var(--weight-semibold)',
    'gap': 'var(--space-2)',
}


def _rule(css, selector):
    match = re.search(rf'(?<![\w.-]){re.escape(selector)}\s*\{{([^}}]*)\}}', css)
    assert match is not None, f'no `{selector} {{ ... }}` rule found'
    return {
        name.strip(): value.strip()
        for name, value in re.findall(r'([\w-]+)\s*:\s*([^;]+);', match.group(1))
    }


def _components_css():
    return (_CSS / 'components.css').read_text(encoding='utf-8')


def _rem_to_px(value):
    assert value.endswith('rem'), f'expected a rem length, got {value!r}'
    return float(value[:-3]) * 16


def test_the_lockup_declares_every_dimension_it_owns():
    """Mark size, wordmark size and weight, and the gap — all on `.brand`."""
    brand = _rule(_components_css(), '.brand')

    for prop, expected in _OWNED.items():
        assert brand.get(prop) == expected, (
            f'`.brand` declares {prop}: {brand.get(prop)!r}, expected '
            f'{expected!r}. This class is the only owner of the lockup\'s '
            f'dimensions; changing one is fine, moving it elsewhere is not.'
        )


def test_the_mark_is_sized_by_the_class_not_by_its_call_sites():
    """The rendered size comes from CSS, and the attribute agrees with it.

    `logo_mark.html` still writes `width`/`height` attributes, because the
    mark has to reserve its box before the stylesheet arrives — an image that
    lays out at zero and then jumps is worse than one that is briefly the
    wrong size. Those attributes are a fallback, not a second opinion, so the
    partial's default has to be exactly what `--brand-mark-size` resolves to.
    """
    css = _components_css()

    sized = _rule(css, '.brand .op-logo-mark')
    assert sized.get('width') == 'var(--brand-mark-size)'
    assert sized.get('height') == 'var(--brand-mark-size)'

    declared = _rem_to_px(_rule(css, '.brand')['--brand-mark-size'])
    default = re.search(
        r'logo_size\|default\((\d+)\)', _PARTIAL.read_text(encoding='utf-8')
    )
    assert default is not None, 'logo_mark.html no longer defaults its size'

    assert float(default.group(1)) == declared, (
        f'logo_mark.html reserves {default.group(1)}px but --brand-mark-size '
        f'renders at {declared:.0f}px. The attribute is what the browser lays '
        f'out before CSS loads; if the two disagree the mark visibly jumps.'
    )


def test_no_template_that_renders_the_lockup_sizes_the_mark_itself():
    """A `logo_size` beside a `.brand` is the duplication this replaced."""
    offenders = []
    for template in _TEMPLATES.rglob('*.html'):
        source = template.read_text(encoding='utf-8')
        if 'class="brand"' in source and 'logo_size' in source:
            offenders.append(template.name)

    assert not offenders, (
        f'{offenders} size the brand mark inline. The lockup takes its size '
        f'from `.brand`; passing `logo_size` beside it puts the number back '
        f'in the template where it cannot be kept in step.'
    )


def test_no_page_stylesheet_restates_the_lockup():
    """One owner means the page stylesheets stay out of it.

    `app.css` and `landing.css` are alternatives — only one loads at a time —
    so a rule in either is invisible from the other, which is exactly how a
    shared component ends up with two different sizes.
    """
    for name in ('app.css', 'landing.css'):
        css = (_CSS / name).read_text(encoding='utf-8')
        for selector in re.findall(r'([^{}]*\.brand[\w-]*[^{},]*)\{([^}]*)\}', css):
            body = selector[1]
            for prop in _OWNED:
                assert prop not in body, (
                    f'{name} sets {prop} on `{selector[0].strip()}`; the '
                    f'lockup is owned by .brand in components.css'
                )


def test_the_lockup_still_fits_the_rows_that_hold_it():
    """Both headers reserve their own height, and the mark has to clear it.

    Neither row was resized for this. The check is that it did not need to
    be — a mark taller than its container silently grows the shell's header
    or the marketing bar, which is the regression a size bump invites.
    """
    mark = _rem_to_px(_rule(_components_css(), '.brand')['--brand-mark-size'])

    rows = {
        'app.css': ('.sidenav__brand', 'height'),
        'landing.css': ('.lp-nav__inner', 'height'),
    }
    for name, (selector, prop) in rows.items():
        css = (_CSS / name).read_text(encoding='utf-8')
        row = _rem_to_px(_rule(css, selector)[prop])
        assert mark <= row, (
            f'the brand mark is {mark:.0f}px inside `{selector}`, which '
            f'reserves {row:.0f}px ({name}). The row would grow to fit it.'
        )
