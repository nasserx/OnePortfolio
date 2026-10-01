from html.parser import HTMLParser
import json
from pathlib import Path
import re

from flask import render_template


EXPECTED_ICONS = [
    {
        "href": "/static/icons/favicon.svg",
        "type": "image/svg+xml",
        "sizes": "any",
        "media": None,
    },
    {
        "href": "/static/icons/favicon-light.svg",
        "type": "image/svg+xml",
        "sizes": "any",
        "media": "(prefers-color-scheme: light)",
    },
    {
        "href": "/static/icons/favicon-dark.svg",
        "type": "image/svg+xml",
        "sizes": "any",
        "media": "(prefers-color-scheme: dark)",
    },
]


class _IconLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.icons = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "link" and "icon" in (values.get("rel") or "").split():
            self.icons.append({
                key: values.get(key)
                for key in ("href", "type", "sizes", "media")
            })


class _BrandLogoParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.logos = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        classes = (values.get("class") or "").split()
        if tag == "svg" and "brand-logo" in classes:
            self.logos.append(values)


def _icons(html):
    parser = _IconLinkParser()
    parser.feed(html)
    return parser.icons


def _brand_logos(html):
    parser = _BrandLogoParser()
    parser.feed(html)
    return parser.logos


def test_every_rendered_head_uses_the_shared_favicon_declarations(app):
    client = app.test_client()
    rendered = [
        client.get("/").get_data(as_text=True),
        client.get("/login").get_data(as_text=True),
    ]
    with app.test_request_context("/"):
        rendered.append(render_template("base.html"))

    for html in rendered:
        assert _icons(html) == EXPECTED_ICONS

    for name in ("base.html", "auth_base.html", "landing.html"):
        source = Path("portfolio_app/templates", name).read_text(encoding="utf-8")
        head = source[source.index("<head>"):source.index("</head>")]
        assert head.count("{% include 'components/favicon_links.html' %}") == 1
        assert 'rel="icon"' not in head


def test_favicon_declaration_order_selects_one_theme_variant():
    for scheme, expected_href in (
        ("light", "/static/icons/favicon-light.svg"),
        ("dark", "/static/icons/favicon-dark.svg"),
    ):
        matching = [
            icon
            for icon in EXPECTED_ICONS
            if icon["media"] in (None, f"(prefers-color-scheme: {scheme})")
        ]
        assert matching[-1]["href"] == expected_href
        assert sum(icon["href"] == expected_href for icon in matching) == 1

    assert len({icon["href"] for icon in EXPECTED_ICONS}) == len(EXPECTED_ICONS)


def test_brand_component_uses_one_neutral_current_color_mark(app):
    with app.test_request_context("/"):
        logos = _brand_logos(render_template("components/logo_mark.html"))

    assert logos == [
        {
            "class": "brand-logo",
            "viewbox": "8 8 48 48",
            "fill": "currentColor",
            "focusable": "false",
            "aria-hidden": "true",
        }
    ]
    css = Path('portfolio_app/static/css/components.css').read_text(encoding='utf-8')
    brand_rule = re.search(r'\.brand-logo\s*\{([^}]*)\}', css).group(1)
    assert 'color: inherit' in brand_rule
    assert not re.search(r'background|border|box-shadow|padding|mask', brand_rule)


def test_brand_component_honours_class_and_accessibility_overrides(app):
    with app.test_request_context("/"):
        logos = _brand_logos(render_template(
            "components/logo_mark.html",
            logo_class="auth-logo",
            logo_decorative=False,
            logo_alt="OnePortfolio",
        ))

    assert logos == [{
        'class': 'brand-logo auth-logo',
        'viewbox': '8 8 48 48',
        'fill': 'currentColor',
        'focusable': 'false',
        'role': 'img',
        'aria-label': 'OnePortfolio',
    }]


def test_every_brand_surface_uses_the_same_shared_mark(app):
    client = app.test_client()
    rendered = [
        client.get("/").get_data(as_text=True),
        client.get("/login").get_data(as_text=True),
    ]
    with app.test_request_context("/"):
        rendered.append(render_template("base.html"))

    for html in rendered:
        logos = _brand_logos(html)
        assert len(logos) == 1
        assert logos[0]['class'].split()[0] == 'brand-logo'

    # Variant selection is a styling concern; no template may hard-code it.
    for name in ("base.html", "auth_base.html", "landing.html"):
        source = Path("portfolio_app/templates", name).read_text(encoding="utf-8")
        assert "logo_surface" not in source


def test_brand_assets_and_metadata_follow_neutral_theme_policy():
    icon_root = Path('portfolio_app/static/icons')
    expected = {
        'favicon.svg': '#757575',
        'favicon-light.svg': '#0A0A0A',
        'favicon-dark.svg': '#FAFAFA',
    }
    for name, colour in expected.items():
        source = (icon_root / name).read_text(encoding='utf-8')
        assert f'data-brand-mark="oneportfolio-quarter-pie" fill="{colour}"' in source
        assert 'viewBox="0 0 64 64"' in source
        assert source.count('<path ') == 1
        assert '<rect' not in source
        assert 'data-brand-background' not in source
        assert '<mask' not in source
        assert '<image' not in source
        assert not re.search(r'#(?:6A55E8|5B45E8|9D88FF)', source, re.IGNORECASE)

    manifest = json.loads((icon_root / 'site.webmanifest').read_text(encoding='utf-8'))
    assert manifest['theme_color'] == '#171717'
    assert manifest['background_color'] == '#ffffff'
    assert {icon['purpose'] for icon in manifest['icons']} == {'any'}

    for name in ('base.html', 'auth_base.html', 'landing.html'):
        source = Path('portfolio_app/templates', name).read_text(encoding='utf-8')
        assert '<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)">' in source
        assert '<meta name="theme-color" content="#0a0a0a" media="(prefers-color-scheme: dark)">' in source
