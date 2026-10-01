"""Static contracts for the preset's Geist and Tabler identity."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / 'portfolio_app' / 'templates'
STATIC = ROOT / 'portfolio_app' / 'static'
TOKENS = STATIC / 'css' / 'tokens.css'
SPRITE = TEMPLATES / 'components' / 'icon_sprite.html'
ICON_MACRO = TEMPLATES / 'macros' / 'icons.html'


def _sources(root, suffixes):
    return [
        path for path in root.rglob('*')
        if path.is_file() and path.suffix in suffixes
    ]


def test_all_shells_load_only_geist_required_weights():
    expected = (
        'https://fonts.googleapis.com/css2?'
        'family=Geist:wght@400;500;600&display=swap'
    )
    for name in ('base.html', 'auth_base.html', 'landing.html'):
        source = (TEMPLATES / name).read_text(encoding='utf-8')
        assert expected in source
        assert 'family=Inter' not in source

    tokens = TOKENS.read_text(encoding='utf-8')
    assert '--font-sans: "Geist", ui-sans-serif, system-ui' in tokens
    assert '--font-heading: var(--font-sans);' in tokens
    assert '--bs-body-font-family: var(--font-sans);' in tokens


def test_chart_typography_consumes_the_shared_font_token():
    for name in ('overview_charts.js', 'landing.js'):
        source = (STATIC / 'js' / name).read_text(encoding='utf-8')
        assert "window.Chart.defaults.font.family = cssVar('--font-sans');" in source
        assert 'Inter' not in source


def test_bootstrap_icon_font_and_consumers_are_fully_removed():
    paths = _sources(TEMPLATES, {'.html'}) + _sources(STATIC, {'.css', '.js'})
    combined = '\n'.join(path.read_text(encoding='utf-8') for path in paths)
    assert 'bootstrap-icons' not in combined
    assert not re.search(r'\bbi-[a-z0-9-]+\b', combined)
    assert not re.search(r'\.bi\b', combined)


def test_icon_macro_owns_tabler_geometry_and_accessibility_contract():
    source = ICON_MACRO.read_text(encoding='utf-8')
    for contract in (
        'viewBox="0 0 24 24"',
        'fill="none"',
        'stroke="currentColor"',
        'stroke-width="2"',
        'stroke-linecap="round"',
        'stroke-linejoin="round"',
        'focusable="false"',
        'role="img" aria-label="{{ label }}"',
        'aria-hidden="true"',
    ):
        assert contract in source


def test_sprite_symbols_are_unique_and_every_reference_resolves():
    sprite = SPRITE.read_text(encoding='utf-8')
    symbols = re.findall(r'<symbol id="op-icon-([a-z0-9-]+)"', sprite)
    assert len(symbols) == len(set(symbols))
    assert symbols

    references = set()
    for path in _sources(TEMPLATES, {'.html'}):
        if path in {SPRITE, ICON_MACRO}:
            continue
        source = path.read_text(encoding='utf-8')
        references.update(re.findall(r"icon\('([a-z0-9-]+)'", source))
        references.update(re.findall(r"\('([a-z0-9-]+)', '[^']+',", source))

    shell = (STATIC / 'js' / 'shell.js').read_text(encoding='utf-8')
    references.update(re.findall(r"icon: '([a-z0-9-]+)'", shell))
    references.update(re.findall(r"create\('([a-z0-9-]+)'", (
        STATIC / 'js' / 'main.js'
    ).read_text(encoding='utf-8')))
    assert references <= set(symbols)


def test_dynamic_icons_use_the_same_sprite_name_contract():
    shell = (STATIC / 'js' / 'shell.js').read_text(encoding='utf-8')
    main = (STATIC / 'js' / 'main.js').read_text(encoding='utf-8')
    assert "window.OnePortfolioIcons = Object.freeze({ create: createIcon });" in shell
    assert "use.setAttribute('href', '#op-icon-' + name);" in shell
    assert "window.OnePortfolioIcons.create('alert-circle', 'me-2')" in main
    assert 'ICON_ALIASES' not in shell


def test_raw_svg_geometry_is_centralized():
    raw_svg_templates = []
    for path in _sources(TEMPLATES, {'.html'}):
        source = path.read_text(encoding='utf-8')
        if '<svg' in source:
            raw_svg_templates.append(path.relative_to(TEMPLATES).as_posix())
    assert sorted(raw_svg_templates) == [
        'components/icon_sprite.html',
        'components/logo_mark.html',
        'macros/icons.html',
    ]
