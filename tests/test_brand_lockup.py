"""The OnePortfolio brand lockup has one size everywhere it appears.

`.brand` owns the mark size, wordmark typography, and gap. These checks keep
page stylesheets and template call sites from creating divergent lockups.

The standalone mark on the auth and error pages appears without the wordmark,
centred above a card, but deliberately inherits the same shared 20px mark size.
That keeps every visible application use on one sizing and transparency
contract.
"""

import re
from pathlib import Path

_CSS = Path('portfolio_app/static/css')
_TEMPLATES = Path('portfolio_app/templates')
_PARTIAL = _TEMPLATES / 'components' / 'logo_mark.html'

# Dimensions the lockup owns, and the value each is expected to resolve to.
# Named rather than measured so a change here is a decision someone typed.
_OWNED = {
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


def test_the_mark_is_sized_by_shared_css_not_by_its_call_sites():
    css = _components_css()
    shared = _rule(css, '.brand-logo')
    assert shared['width'] == '1.25rem'
    assert shared['height'] == '1.25rem'
    assert 'logo_size' not in _PARTIAL.read_text(encoding='utf-8')


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


def test_shell_landing_and_auth_marks_share_the_shared_size_owner():
    css = _components_css()
    assert _rule(css, '.brand-logo')
    assert '.auth-logo {' not in css

    for template in _TEMPLATES.rglob('*.html'):
        source = template.read_text(encoding='utf-8')
        if "include 'components/logo_mark.html'" in source:
            assert 'logo_size' not in source


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
    mark = _rem_to_px(_rule(_components_css(), '.brand-logo')['width'])

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
