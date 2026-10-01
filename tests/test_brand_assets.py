"""Integrity contracts for the monochrome hollow quarter-pie brand assets."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
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


def test_master_is_one_clean_hollow_quarter_pie_mark():
    source = (ICONS / 'favicon.svg').read_text(encoding='utf-8')
    root, paths, backgrounds = _svg_elements()

    assert root.attrib == {
        'width': '64',
        'height': '64',
        'viewBox': '0 0 64 64',
        'preserveAspectRatio': 'xMidYMid meet',
    }
    assert len(paths) == 1
    assert backgrounds == []
    mark = paths[0]
    assert mark.attrib['data-brand-mark'] == 'oneportfolio-quarter-pie'
    assert mark.attrib['fill'] == GENERATOR.DEFAULT_SURFACE_ARTWORK
    assert mark.attrib['fill-rule'] == 'evenodd'
    assert mark.attrib.get('stroke') is None
    assert len(list(root)) == 1

    path = mark.attrib['d']
    commands = re.findall(r'[A-Za-z]', path)
    assert commands == [
        'M', 'A', 'Q', 'H', 'Q', 'V', 'Q', 'Z',
        'M', 'A', 'Q', 'H', 'Q', 'V', 'Q', 'Z',
    ]
    assert re.search(r'A44 44 0 0 1', path)
    assert re.search(r'A26 26 0 0 1', path)
    assert path.count('A') == 2
    assert path.count('Z') == 2
    assert not re.search(r'[CST]', path)

    contours = GENERATOR._path_contours(path)
    assert len(contours) == 2
    contour = contours[0]
    xs = [point[0] for point in contour]
    ys = [point[1] for point in contour]
    assert min(xs) == 8
    assert max(xs) == 56
    assert min(ys) == 8
    assert max(ys) == 56
    assert (8, 12) in contour
    assert (8, 52) in contour
    assert (12, 56) in contour
    assert (52, 56) in contour

    interior = contours[1]
    interior_xs = [point[0] for point in interior]
    interior_ys = [point[1] for point in interior]
    assert min(interior_xs) == 16
    assert max(interior_xs) == 46
    assert min(interior_ys) == 18
    assert max(interior_ys) == 48

    assert not re.search(
        r'<(?:image|mask|clipPath|filter|metadata)\b|base64|display\s*:\s*none',
        source,
        re.IGNORECASE,
    )


def test_svg_favicon_variants_are_exact_transparent_derivatives_from_master():
    master = (ICONS / 'favicon.svg').read_text(encoding='utf-8')
    for path, artwork in GENERATOR.SVG_VARIANTS.items():
        source = path.read_text(encoding='utf-8')
        _root, marks, backgrounds = _svg_elements(path)
        assert len(marks) == 1
        assert backgrounds == []
        assert marks[0].attrib['d'] == _svg_elements()[1][0].attrib['d']
        assert marks[0].attrib['fill'] == artwork
        assert marks[0].attrib['fill-rule'] == 'evenodd'
        assert '<rect' not in source
        assert 'data-brand-background' not in source
        assert source == GENERATOR.svg_variant(master, artwork)
        assert min(
            GENERATOR.contrast_ratio(artwork, surface)
            for surface in GENERATOR.TARGET_SURFACES[path]
        ) >= 4.5
        red, green, blue = GENERATOR._hex_rgb(artwork)
        assert red == green == blue


def test_raster_derivatives_are_deterministic_light_icon_compositions():
    expected = {
        'apple-touch-icon.png': 180,
        'android-chrome-192x192.png': 192,
        'android-chrome-512x512.png': 512,
    }
    for name, size in expected.items():
        asset = ICONS / name
        assert asset.read_bytes() == GENERATOR.render_app_icon_png_bytes(size)
        result = GENERATOR.validate_png(asset, size)
        assert result['size'] == f'{size}x{size}'
        assert all(margin > 0 for margin in result['margins'])
        assert all(margin > 0 for margin in result['mark_margins'])
        assert result['center_delta'] <= size * 0.08
        probe = result['interior_probe'][2]
        assert probe[:3] == GENERATOR._hex_rgb(GENERATOR.LIGHT_ICON_BACKGROUND)
        assert probe[3] == 255
        assert all(
            pixel[:3] == GENERATOR._hex_rgb(GENERATOR.LIGHT_SURFACE_ARTWORK)
            and pixel[3] == 255
            for _x, _y, pixel in result['band_probes']
        )


def test_ico_frames_match_the_canonical_geometry_at_small_sizes(tmp_path):
    inventory = GENERATOR.inspect_ico(ICONS / 'favicon.ico')
    assert [(entry['width'], entry['height']) for entry in inventory] == [
        (16, 16),
        (32, 32),
        (48, 48),
    ]
    extracted = GENERATOR.extract_ico_pngs(ICONS / 'favicon.ico', tmp_path)
    source = ICONS / 'favicon-light.svg'
    for size, path in extracted.items():
        assert path.read_bytes() == GENERATOR.render_png_bytes(source, size)
        result = GENERATOR.validate_png(
            path,
            size,
            expected_background=None,
        )
        assert result['opaque_background_rgb'] is None
        assert result['transparent_pixels'] > 0
        assert result['interior_probe'][2][3] <= 32
        assert all(
            pixel[3] >= 192
            for _x, _y, pixel in result['band_probes']
        )
        assert result['mark_bbox_size'][0] >= size * 0.68
        assert result['mark_bbox_size'][1] >= size * 0.68


def test_reference_sizes_keep_the_arc_centered_and_clear(tmp_path):
    source = ICONS / 'favicon-light.svg'
    for size in GENERATOR.REFERENCE_SIZES:
        output = tmp_path / f'brand-{size}.png'
        output.write_bytes(GENERATOR.render_png_bytes(source, size))
        result = GENERATOR.validate_png(
            output,
            size,
            expected_background=None,
        )
        assert result['center_delta'] == 0
        assert len(set(result['mark_margins'])) == 1
        assert min(result['mark_margins']) >= max(2, size // 8)
        assert result['interior_probe'][2][3] <= 32
        assert all(
            pixel[3] >= 192
            for _x, _y, pixel in result['band_probes']
        )


def test_manifest_references_generated_assets_without_new_platform_claims():
    manifest = json.loads((ICONS / 'site.webmanifest').read_text(encoding='utf-8'))
    assert manifest['name'] == 'OnePortfolio'
    assert manifest['short_name'] == 'OnePortfolio'
    assert manifest['theme_color'] == '#171717'
    assert manifest['background_color'] == '#ffffff'
    assert manifest['icons'] == [
        {
            'src': '/static/icons/android-chrome-192x192.png',
            'sizes': '192x192',
            'type': 'image/png',
            'purpose': 'any',
        },
        {
            'src': '/static/icons/android-chrome-512x512.png',
            'sizes': '512x512',
            'type': 'image/png',
            'purpose': 'any',
        },
    ]
    for icon in manifest['icons']:
        source = icon['src']
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
    assert '<rect' not in component
    assert 'brand-logo' in component
    assert 'fill="currentColor"' in component
    assert 'viewBox="8 8 48 48"' in component
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
            assert 'oneportfolio-quarter-pie' not in source
    assert actual_consumers == expected_consumers


def test_visible_logo_cascade_cannot_paint_a_tile_or_pseudo_element():
    """The shared mark and its immediate wrappers remain transparent.

    Favicon SVGs deliberately have their own neutral platform background, so
    this contract inspects only the inline application mark and the CSS classes
    that can target it in the app shell, auth pages, and Landing lockup.
    """
    component = (TEMPLATES / 'components' / 'logo_mark.html').read_text(
        encoding='utf-8',
    )
    assert not re.search(
        r'<(?:rect|circle|ellipse|polygon|image|use)\b'
        r'|\b(?:style|mask|filter|class)\s*=\s*["\'][^"\']*'
        r'(?:background|border|shadow|tile)',
        component,
        re.IGNORECASE,
    )

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
    assert 'render_app_icon_png_bytes(size)' in source
    assert 'expected_background=None' in source
    assert 'generate_logo_component()' in source
    assert 'oneportfolio-quarter-pie' in source
    assert '"--validate-only"' in source


def test_validate_only_contract_accepts_current_generated_assets():
    GENERATOR.validate()


def test_visible_logo_component_is_an_exact_generated_master_derivative():
    master = (ICONS / 'favicon.svg').read_text(encoding='utf-8')
    component = (TEMPLATES / 'components' / 'logo_mark.html').read_text(
        encoding='utf-8',
    )
    assert component == GENERATOR.logo_component_text(master)
