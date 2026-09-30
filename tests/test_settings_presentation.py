"""Presentation contracts for the Settings content panels."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETTINGS_TEMPLATE = ROOT / 'portfolio_app' / 'templates' / 'auth' / 'settings.html'
APP_CSS = ROOT / 'portfolio_app' / 'static' / 'css' / 'app.css'


def test_content_panel_headings_share_horizontal_icon_label_contract():
    template = SETTINGS_TEMPLATE.read_text(encoding='utf-8')
    headings = re.findall(
        r'<h3 class="settings-section-heading mb-4">\s*'
        r"\{\{ icon\('([^']+)'\) \}\}<span>([^<]+)</span>\s*</h3>",
        template,
    )
    assert headings == [
        ('user-circle', 'Profile'),
        ('shield-lock', 'Security'),
        ('user-cog', 'Account'),
    ]

    css = APP_CSS.read_text(encoding='utf-8')
    rule = css.split('.settings-section-heading {', 1)[1].split('}', 1)[0]
    assert 'display: flex;' in rule
    assert 'align-items: center;' in rule
    assert 'gap: var(--space-2);' in rule
    assert 'settings-sidebar' not in rule


def test_sidebar_navigation_contract_is_independent():
    template = SETTINGS_TEMPLATE.read_text(encoding='utf-8')
    assert template.count('settings-sidebar-link') == 3
    assert 'settings-section-heading settings-sidebar-link' not in template
