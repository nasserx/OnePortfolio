"""Durable drift guards for the final cross-page presentation cleanup."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'portfolio_app' / 'static'
TEMPLATES = ROOT / 'portfolio_app' / 'templates'


def test_removed_presentation_contracts_do_not_return():
    css = '\n'.join(
        path.read_text(encoding='utf-8')
        for path in (STATIC / 'css').glob('*.css')
    )
    main = (STATIC / 'js' / 'main.js').read_text(encoding='utf-8')

    for obsolete in ('--icon-sm', '.fw-500', '.surface-popover'):
        assert obsolete not in css
    for obsolete in ('.app-navbar', "classList.toggle('scrolled'"):
        assert obsolete not in main


def test_brand_refresh_has_one_visible_mark_and_one_master_asset_boundary():
    logo = TEMPLATES / 'components' / 'logo_mark.html'
    favicon_links = TEMPLATES / 'components' / 'favicon_links.html'
    master = STATIC / 'icons' / 'favicon.svg'
    generator = ROOT / 'scripts' / 'generate_app_icons.py'

    for path in (logo, favicon_links, master, generator):
        assert path.is_file()

    shells = '\n'.join(
        (TEMPLATES / name).read_text(encoding='utf-8')
        for name in ('base.html', 'landing.html', 'errors/rate_limit.html')
    )
    assert shells.count("include 'components/logo_mark.html'") == 3

    script = generator.read_text(encoding='utf-8')
    assert 'MASTER_SVG = ICONS_DIR / "favicon.svg"' in script
    assert '"--validate-only"' in script
    assert 'generate_svg_variants()' in script
