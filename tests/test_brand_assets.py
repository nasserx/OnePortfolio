"""Integrity contracts for the monochrome ascending-bar and arrow brand assets."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import pytest
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / 'portfolio_app' / 'static' / 'icons'
TEMPLATES = ROOT / 'portfolio_app' / 'templates'
CSS_ROOT = ROOT / 'portfolio_app' / 'static' / 'css'
COMPONENT_CSS = CSS_ROOT / 'components.css'
GENERATOR_PATH = ROOT / 'scripts' / 'generate_app_icons.py'

_SPEC = importlib.util.spec_from_file_location('generate_app_icons', GENERATOR_PATH)
assert _SPEC and _SPEC.loader
GENERATOR = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(GENERATOR)


def _svg_elements(svg_path=ICONS / 'favicon.svg'):
    root = ET.parse(svg_path).getroot()
    paths = [element for element in root.iter() if element.tag.endswith('path')]
    backgrounds = [
        element for element in root.iter()
        if element.attrib.get('data-brand-background')
    ]
    return root, paths, backgrounds


def _logo_css_rules():
    """Return every CSS rule capable of targeting a visible brand element."""
    logo_selector = re.compile(
        r'(?<![\w-])\.(?:brand-logo|auth-logo|brand)(?![\w-])'
    )
    for path in CSS_ROOT.glob('*.css'):
        source = path.read_text(encoding='utf-8')
        for match in re.finditer(r'([^{}]+)\{([^{}]*)\}', source):
            selectors, declarations = match.groups()
            if logo_selector.search(selectors):
                yield path, selectors.strip(), declarations


def test_master_is_clean_vector_growth_symbol_on_tile():
    source = (ICONS / 'favicon.svg').read_text(encoding='utf-8')
    root, paths, backgrounds = _svg_elements()
    info = GENERATOR.inspect_svg(ICONS / 'favicon.svg')
    assert root.attrib['viewBox'] == '0 0 64 64'
    assert len(paths) == len(backgrounds) == 1
    assert len(list(root)) == 2
    assert paths[0].attrib['data-brand-mark'] == 'oneportfolio-growth'
    assert paths[0].attrib.get('stroke') is None
    assert info['artwork_fill'] == '#FFFFFF'
    assert info['background_fill'] == '#000000'
    contours = GENERATOR._path_contours(info['path_data'])
    bounds = [(min(x for x, y in c), min(y for x, y in c),
               max(x for x, y in c), max(y for x, y in c)) for c in contours]
    assert len(bounds) == 3
    assert bounds[0][1] > bounds[1][1] > bounds[2][1]
    assert {b[3] for b in bounds} == {52}
    assert bounds[0][2] < bounds[1][0]
    # The arrowhead extends left above the second bar, never into its body.
    assert all(2 < x < 62 and 2 < y < 62 for c in contours for x, y in c)
    assert not re.search(r'<(?:image|mask|clipPath|filter|metadata)\b|base64', source)


def test_svg_favicon_variants_invert_both_regions_from_master():
    master = (ICONS / 'favicon.svg').read_text(encoding='utf-8')
    for path, artwork in GENERATOR.SVG_VARIANTS.items():
        source = path.read_text(encoding='utf-8')
        _root, marks, backgrounds = _svg_elements(path)
        assert len(marks) == 1
        assert len(backgrounds) == 1
        assert marks[0].attrib['d'] == _svg_elements()[1][0].attrib['d']
        assert marks[0].attrib['fill'] == artwork
        assert marks[0].attrib['fill-rule'] == 'evenodd'
        assert source.count('<rect') == 1
        assert 'data-brand-background' in source
        assert source == GENERATOR.svg_variant(master, artwork)
        assert min(
            GENERATOR.contrast_ratio(artwork, surface)
            for surface in GENERATOR.TARGET_SURFACES[path]
        ) >= 4.5
        red, green, blue = GENERATOR._hex_rgb(artwork)
        assert red == green == blue


def test_raster_derivatives_are_deterministic_platform_compositions():
    for name, size in GENERATOR.APP_PNGS.items():
        asset = ICONS / name
        opaque = name == 'apple-touch-icon.png'
        assert asset.read_bytes() == GENERATOR.render_app_icon_png_bytes(size, opaque=opaque)
        result = GENERATOR.validate_png(asset, size, opaque=opaque)
        assert result['opaque'] == opaque
        assert (result['transparent_pixels'] == 0) == opaque


def test_ico_frames_match_the_canonical_geometry_at_small_sizes(tmp_path):
    inventory = GENERATOR.inspect_ico(ICONS / 'favicon.ico')
    assert [(e['width'], e['height']) for e in inventory] == [(16, 16), (32, 32), (48, 48)]
    for size, path in GENERATOR.extract_ico_pngs(ICONS / 'favicon.ico', tmp_path).items():
        assert path.read_bytes() == GENERATOR.render_png_bytes(ICONS / 'favicon-light.svg', size)
        assert GENERATOR.validate_png(path, size)['transparent_pixels'] > 0


def test_reference_sizes_keep_bars_arrow_and_gaps_clear_in_both_themes(tmp_path):
    for name, artwork, background in (
        ('light', '#FFFFFF', '#000000'), ('dark', '#000000', '#FFFFFF'),
    ):
        for size in GENERATOR.REFERENCE_SIZES:
            output = tmp_path / f'{name}-{size}.png'
            output.write_bytes(GENERATOR.render_png_bytes(ICONS / f'favicon-{name}.svg', size))
            GENERATOR.validate_png(output, size, expected_artwork=artwork,
                                   expected_background=background)


def test_manifest_references_generated_assets_without_new_platform_claims():
    manifest = json.loads((ICONS / 'site.webmanifest').read_text(encoding='utf-8'))
    assert manifest['name'] == 'OnePortfolio'
    assert manifest['short_name'] == 'OnePortfolio'
    assert manifest['theme_color'] == '#171717'
    assert manifest['background_color'] == '#ffffff'
    assert manifest['icons'] == GENERATOR.manifest_icons()
    assert {i['purpose'] for i in manifest['icons']} == {'any'}
    for icon in manifest['icons']:
        source = icon['src'].split('?')[0]
        relative_source = source[len('/static/'):] if source.startswith('/static/') else source
        assert (
            ROOT / 'portfolio_app' / 'static'
            / relative_source
        ).is_file()


def test_one_current_color_logo_component_owns_all_visible_marks():
    component = (TEMPLATES / 'components' / 'logo_mark.html').read_text(
        encoding='utf-8',
    )
    css = COMPONENT_CSS.read_text(encoding='utf-8')
    brand_rule = re.search(r'\.brand-logo\s*\{([^}]*)\}', css).group(1)
    master_path = _svg_elements()[1][0].attrib['d']
    assert component.count('<svg') == 1
    assert component.count('<path') == 1
    assert '<img' not in component
    assert component.count('<rect') == 1
    assert 'brand-logo' in component
    assert 'fill="currentColor"' in component
    assert 'viewBox="2 2 60 60"' in component
    assert 'fill-rule="evenodd"' in component
    assert f'd="{master_path}"' in component
    assert 'color: inherit' in brand_rule
    assert not re.search(
        r'background|border|box-shadow|padding|mask',
        brand_rule,
    )
    assert 'financial-' not in brand_rule
    assert 'chart-' not in brand_rule

    expected_consumers = {
        'base.html',
        'landing.html',
        'auth/login.html',
        'auth/verify_code.html',
        'auth/reauthenticate.html',
        'errors/rate_limit.html',
    }
    actual_consumers = set()
    for template in TEMPLATES.rglob('*.html'):
        source = template.read_text(encoding='utf-8')
        relative = template.relative_to(TEMPLATES).as_posix()
        if "include 'components/logo_mark.html'" in source:
            actual_consumers.add(relative)
        if template.name not in {'icon_sprite.html', 'logo_mark.html'}:
            assert 'oneportfolio-growth' not in source
    assert actual_consumers == expected_consumers


def test_tile_is_vector_owned_without_extra_css_decoration():
    """Only the generated SVG owns geometry; CSS selects semantic colours."""
    component = (TEMPLATES / 'components' / 'logo_mark.html').read_text(encoding='utf-8')
    assert component.count('<rect') == 1
    assert not re.search(r'<(?:image|mask|filter|use)\b', component)
    css = COMPONENT_CSS.read_text(encoding='utf-8')
    assert '.brand-logo > rect { fill: var(--foreground); }' in css
    assert '.brand-logo__symbol { fill: var(--background); }' in css

    forbidden_properties = re.compile(
        r'(?m)^\s*(?:background(?:-\w+)?|border(?:-\w+)?|box-shadow|'
        r'padding(?:-\w+)?|mask(?:-\w+)?|filter)\s*:'
    )
    rules = list(_logo_css_rules())
    assert rules
    for path, selectors, declarations in rules:
        assert '::before' not in selectors and '::after' not in selectors, (
            f'{path.name}: `{selectors}` adds pseudo-element geometry to the '
            'visible brand contract'
        )
        assert not forbidden_properties.search(declarations), (
            f'{path.name}: `{selectors}` paints or pads the visible logo'
        )


def test_generator_has_no_browser_or_per_size_geometry():
    source = GENERATOR_PATH.read_text(encoding='utf-8')
    assert 'Microsoft Edge' not in source
    assert '--headless' not in source
    assert 'subprocess' not in source
    assert 'MASTER_SVG = ICONS_DIR / "favicon.svg"' in source
    assert 'render_app_icon_png_bytes(' in source
    assert 'app_icon_composition' not in source
    assert 'generate_logo_component()' in source
    assert 'oneportfolio-growth' in source
    assert '"--validate-only"' in source


def test_validate_only_contract_accepts_current_generated_assets():
    GENERATOR.validate()


def test_visible_logo_component_is_an_exact_generated_master_derivative():
    master = (ICONS / 'favicon.svg').read_text(encoding='utf-8')
    component = (TEMPLATES / 'components' / 'logo_mark.html').read_text(
        encoding='utf-8',
    )
    assert component == GENERATOR.logo_component_text(master)


@pytest.mark.parametrize('old,new', [
    ('rx="14"', 'rx="0"'),
    ('H39.5V24', 'H35V24'),
    ('M13 43', 'M0 43'),
    ('V52H26Z', 'V51H26Z'),
])
def test_validation_rejects_broken_tile_gap_bounds_or_baseline(old, new):
    master = (ICONS / 'favicon.svg').read_text(encoding='utf-8')
    assert old in master
    with pytest.raises(GENERATOR.IconValidationError):
        GENERATOR.inspect_svg_text(master.replace(old, new), 'broken.svg')
