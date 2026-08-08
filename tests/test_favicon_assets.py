from html.parser import HTMLParser
from pathlib import Path

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
        if tag == "img" and "brand-logo" in classes:
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


def test_brand_component_emits_both_theme_variants(app):
    """The UI is theme-switchable at runtime, so a single baked-in artwork
    choice can never be right. The component emits both variants and CSS
    reveals the one matching the active theme."""
    with app.test_request_context("/"):
        logos = _brand_logos(render_template("components/logo_mark.html"))

    assert logos == [
        {
            "src": "/static/icons/favicon-light.svg",
            "width": "32",
            "height": "32",
            "class": "brand-logo brand-logo--light op-logo-mark",
            "alt": "",
            "aria-hidden": "true",
            "decoding": "async",
        },
        {
            "src": "/static/icons/favicon-dark.svg",
            "width": "32",
            "height": "32",
            "class": "brand-logo brand-logo--dark op-logo-mark",
            "alt": "",
            "aria-hidden": "true",
            "decoding": "async",
        },
    ]


def test_brand_component_honours_size_and_class_overrides(app):
    with app.test_request_context("/"):
        logos = _brand_logos(render_template(
            "components/logo_mark.html",
            logo_size=26,
            logo_class="op-logo-mark auth-logo",
        ))

    assert [logo["width"] for logo in logos] == ["26", "26"]
    assert [logo["height"] for logo in logos] == ["26", "26"]
    for logo in logos:
        assert logo["class"].endswith("op-logo-mark auth-logo")


def test_every_brand_surface_ships_both_variants(app):
    client = app.test_client()
    rendered = [
        client.get("/").get_data(as_text=True),
        client.get("/login").get_data(as_text=True),
    ]
    with app.test_request_context("/"):
        rendered.append(render_template("base.html"))

    for html in rendered:
        logos = _brand_logos(html)
        assert logos
        assert {logo["src"] for logo in logos} == {
            "/static/icons/favicon-light.svg",
            "/static/icons/favicon-dark.svg",
        }

    # Variant selection is a styling concern; no template may hard-code it.
    for name in ("base.html", "auth_base.html", "landing.html"):
        source = Path("portfolio_app/templates", name).read_text(encoding="utf-8")
        assert "logo_surface" not in source
