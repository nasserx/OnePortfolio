"""Final presentation contracts for Settings and passwordless authentication."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / 'portfolio_app' / 'templates'
APP_CSS = ROOT / 'portfolio_app' / 'static' / 'css' / 'app.css'
COMPONENTS_CSS = ROOT / 'portfolio_app' / 'static' / 'css' / 'components.css'


def _source(relative_path):
    return (TEMPLATES / relative_path).read_text(encoding='utf-8')


def _rule(css, selector):
    matches = re.findall(re.escape(selector) + r'\s*\{([^}]*)\}', css)
    assert matches, f'missing rule: {selector}'
    return max(matches, key=len)


def test_settings_shell_uses_shared_panels_and_independent_tab_navigation():
    template = _source('auth/settings.html')
    assert '<nav aria-label="Settings Sections">' in template
    assert template.count('class="card settings-panel"') == 3
    assert template.count('settings-sidebar-link') == 3
    assert 'settings-section-heading settings-sidebar-link' not in template
    assert template.count('data-bs-toggle="tab"') == 3
    assert all(label in template for label in ('Profile', 'Security', 'Account'))

    css = APP_CSS.read_text(encoding='utf-8')
    sidebar = _rule(css, '.settings-sidebar-link')
    assert 'color: var(--muted-foreground)' in sidebar
    assert 'border-radius: var(--radius-lg)' in sidebar
    active = _rule(css, '.settings-sidebar-link.active')
    assert 'background-color: var(--accent)' in active
    assert 'color: var(--accent-foreground)' in active
    assert not re.search(r'financial-|chart-|destructive', sidebar + active)


def test_settings_content_headings_and_information_rows_share_contracts():
    template = _source('auth/settings.html')
    headings = re.findall(
        r'<h2 class="settings-section-heading">\s*'
        r"\{\{ icon\('([^']+)'\) \}\}<span>([^<]+)</span>\s*</h2>",
        template,
    )
    assert headings == [
        ('user-circle', 'Profile'),
        ('shield-lock', 'Security'),
        ('user-cog', 'Account'),
    ]
    assert 'Sign-In Method' in template
    assert 'Email Verification Code' in template
    assert 'Update Email' in template
    assert 'class="settings-action-row"' in template

    css = APP_CSS.read_text(encoding='utf-8')
    heading = _rule(css, '.settings-section-heading')
    assert 'display: flex' in heading
    assert 'align-items: center' in heading
    assert 'gap: var(--space-2)' in heading
    action = _rule(css, '.settings-action-title')
    assert 'gap: var(--space-2)' in action
    assert 'color: var(--foreground)' in action


def test_settings_content_heading_icons_inherit_the_shared_fixed_icon_size():
    app = APP_CSS.read_text(encoding='utf-8')
    components = COMPONENTS_CSS.read_text(encoding='utf-8')
    heading_icon = _rule(app, '.settings-section-heading .icon')
    shared_icon = _rule(components, '.icon')

    assert 'width:' not in heading_icon
    assert 'height:' not in heading_icon
    assert 'var(--icon-' not in heading_icon
    assert 'width: 1rem' in shared_icon
    assert 'height: 1rem' in shared_icon
    assert 'flex: none' in shared_icon
    assert 'width: 100%' not in shared_icon
    assert '.settings-sidebar-link .icon' not in app


def test_settings_forms_keep_routes_names_csrf_and_destructive_description():
    template = _source('auth/settings.html')
    for endpoint in (
        'auth.delete_account_request',
        'auth.delete_account_cancel',
        'auth.delete_account_verify',
    ):
        assert f"url_for('{endpoint}')" in template
    assert template.count('name="csrf_token"') == 4
    assert 'name="code"' in template
    assert 'class="btn btn-danger btn-sm"' in template
    assert 'aria-labelledby="delete-account-title"' in template
    assert 'aria-describedby="delete-account-description delete-account-warning"' in template


def test_auth_shell_is_centered_shared_surface_without_marketing_showcase():
    template = _source('auth_base.html')
    assert 'class="auth-card surface-card"' in template
    assert "include 'components/icon_sprite.html'" in template
    assert 'family=Geist:' in template
    assert 'auth__showcase' not in template
    assert 'auth__preview' not in template

    css = APP_CSS.read_text(encoding='utf-8')
    auth = _rule(css, '.auth')
    card = _rule(css, '.auth-card')
    assert 'place-items: center' in auth
    assert 'background-color: var(--background)' in auth
    assert 'width: min(24rem, 100%)' in card
    assert not re.search(r'#[0-9a-f]{3,8}\b|(?:oklch|rgba?)\(', auth + card, re.I)


def test_passwordless_auth_forms_use_shared_fields_and_accessible_labels():
    login = _source('auth/login.html')
    verify = _source('auth/verify_code.html')
    reauth = _source('auth/reauthenticate.html')
    update = _source('auth/update_email.html')

    assert '<label class="form-label" for="email">Email Address</label>' in login
    assert 'name="password"' not in login
    assert 'name="email"' in login
    assert 'name="csrf_token"' in login
    assert '<label class="form-label auth-code-label" for="code">Verification Code</label>' in verify
    assert 'autocomplete="one-time-code"' in verify
    assert "digits.length === 6" in verify
    assert 'Send New Code' in verify
    assert 'Confirm It’s You' in reauth
    assert 'Send Code' in reauth
    assert 'New Email Address' in update
    assert 'name="email"' in update
    assert "url_for('auth.update_email')" in update


def test_auth_status_and_rate_limit_use_shared_contracts_and_title_case():
    login = _source('auth/login.html')
    verify = _source('auth/verify_code.html')
    rate_limit = _source('errors/rate_limit.html')
    assert 'role="alert"' in login
    assert 'role="alert"' in verify
    assert 'alert-dismissible fade show' in login
    assert 'Rate Limit Reached' in rate_limit
    assert 'Slow Down for a Moment' in rate_limit
    assert 'Back Home' in rate_limit
    assert "include 'components/logo_mark.html'" in rate_limit


def test_scoped_templates_use_tabler_macro_without_bootstrap_icons_or_raw_svg():
    sources = '\n'.join(
        _source(path)
        for path in (
            'auth/settings.html',
            'auth/update_email.html',
            'auth/login.html',
            'auth/verify_code.html',
            'auth/reauthenticate.html',
            'errors/rate_limit.html',
        )
    )
    assert 'bi-' not in sources
    assert '<svg' not in sources
    assert "from 'macros/icons.html' import icon" in sources


def test_scoped_css_uses_canonical_roles_without_raw_component_colours():
    css = APP_CSS.read_text(encoding='utf-8')
    scoped = css.split('7. SETTINGS', 1)[1].split('9. RECORD SUB-TABLES', 1)[0]
    assert not re.search(r'#[0-9a-f]{3,8}\b|(?:oklch|rgba?)\(', scoped, re.I)
    for legacy in (
        '--bg-canvas', '--fg-default', '--fg-muted', '--fg-subtle',
        '--field-border', '--field-bg-disabled', '--nav-active-bg',
        '--nav-active-fg', '--brand', '--intro-wash',
    ):
        assert legacy not in scoped
