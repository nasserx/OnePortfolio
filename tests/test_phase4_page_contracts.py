"""Source and rendered integration contracts; visual acceptance belongs to users."""
from html.parser import HTMLParser
from pathlib import Path
import re

from portfolio_app import db
from portfolio_app.models.user import User
from tests._auth import authenticate_client

ROOT = Path(__file__).resolve().parents[1] / 'portfolio_app'


def source(path):
    return (ROOT / path).read_text(encoding='utf-8')


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.nodes = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.nodes.append((tag, dict(attrs)))

    def by_id(self, element_id):
        return next(attrs for _, attrs in self.nodes if attrs.get('id') == element_id)


def test_typography_preserves_brand_and_removes_lightweight_overrides():
    components = source('static/css/components.css')
    brand = re.search(r'\.brand\s*\{([^}]+)', components)[1]
    assert 'font-weight: var(--weight-semibold)' in brand
    assert 'font-size: var(--brand-font-size)' in brand
    assert 'letter-spacing: -0.02em' in brand
    tokens = source('static/css/tokens.css')
    assert '--brand-font-size: 1.125rem;' in tokens
    assert '--weight-semibold: 600;' in tokens
    for file in ('tokens.css', 'app.css', 'base.css', 'components.css', 'landing.css', 'flatpickr-nova.css'):
        assert '--weight-light' not in source('static/css/' + file)
    # One shared mapping for both themes; numeric preset primitives stay intact.
    all_css = '\n'.join(path.read_text(encoding='utf-8') for path in (ROOT / 'static/css').glob('*.css'))
    for role, value in (('body', '450'), ('emphasis', '550')):
        assert re.findall(r'--weight-' + role + r':\s*([^;]+);', all_css) == [value]
    assert 'var(--weight-regular)' not in all_css
    # The Overview return percentage intentionally uses a lighter weight than
    # the P&L amount; other typography keeps the shared semantic mapping.
    return_rule = re.search(
        r'\.hero-figure__return-value\s*\{([^}]+)\}', source('static/css/app.css')
    ).group(0)
    assert 'font-weight: var(--weight-medium);' in return_rule
    assert 'font-size: var(--text-sm);' in return_rule
    assert 'var(--weight-medium)' not in all_css.replace(return_rule, '', 1)
    # Native semantic strong/b regain their normal bolder weight, as in the
    # reference reset; no application-wide lighter emphasis override remains.
    assert 'strong, b {' not in source('static/css/base.css')


def test_component_weights_preserve_nova_hierarchy_with_approved_adjustment():
    def weight(file, selector):
        css = source('static/css/' + file)
        body = re.search(r'^\s*' + re.escape(selector) + r'\s*\{([^}]+)', css, re.M)[1]
        return re.search(r'font-weight:\s*var\(([^)]+)\)', body)[1]

    for file, selectors in {
        'base.css': ['h1', 'h2', 'h3, h4, h5, h6'],
        'components.css': ['.btn', '.panel__title', '.modal-title', '.table thead th',
                           'label.form-label', '.badge', '.record-type', '.tx-type-tab',
                           '.supporting-item__value', '.empty-state-title', '.dropdown-header',
                           '.pagination__control', '.segmented__option'],
        'app.css': ['.page__title', '.hero-figure__label', '.hero-figure__value', '.auth-title',
                    '.navlink.active', '.ledger__row--head', '.metric__value',
                    '.settings-sidebar-link', '.settings-section-heading', '.auth-inner-title'],
        'landing.css': ['.lp-title', '.lp-head h2', '.lp-shot__value', '.lp-card h3', '.lp-step h3'],
        'flatpickr-nova.css': ['.op-flatpickr .flatpickr-current-month'],
    }.items():
        for selector in selectors:
            assert weight(file, selector) == '--weight-emphasis', selector

    for file, selectors in {
        'base.css': ['body'],
        'components.css': ['.supporting-item__label', '.marker', '.user-avatar'],
        'app.css': ['.navlink', '.metric__label', '.userchip__name'],
        'landing.css': ['.lp-nav__links a', '.lp-shot__label'],
        'flatpickr-nova.css': ['.op-flatpickr span.flatpickr-weekday'],
    }.items():
        for selector in selectors:
            assert weight(file, selector) == '--weight-body', selector


def test_compact_scale_preserves_mobile_readability_and_control_geometry():
    tokens = source('static/css/tokens.css')
    root = tokens.split(':root {', 1)[1].split('}', 1)[0]
    for name, value in {
        'text-2xs': '0.6875rem', 'text-xs': '0.6875rem', 'text-sm': '0.75rem',
        'text-md': '0.8125rem', 'text-lg': '0.875rem', 'text-xl': '1rem',
        'text-2xl': '1.125rem', 'num-sm': '0.75rem', 'num-lg': '0.9375rem',
        'control-h': '2rem', 'control-h-sm': '1.75rem', 'row-h': '2.5rem',
        'weight-regular': '400', 'weight-medium': '500',
        'weight-body': '450', 'weight-emphasis': '550',
        'num-hero': 'clamp(2rem, 1.2rem + 2.6vw, 3.25rem)',
    }.items():
        assert f'--{name}: {value};' in root
    mobile = tokens.split('@media (max-width: 47.999rem)', 1)[1]
    for name, value in {'text-xs': '0.75rem', 'text-2xs': '0.75rem',
                        'text-sm': '0.8125rem', 'text-detail': '0.8125rem',
                        'num-sm': '0.8125rem', 'chart-text-size': '12'}.items():
        assert f'--{name}: {value};' in mobile
    components = source('static/css/components.css')
    assert components.index('@media (max-width: 47.999rem)') > components.index('.command-input-control {')
    assert '.form-control, .form-select, .command-input-control { font-size: 1rem; }' in components
    assert 'font-size: var(--text-xs)' in re.search(r'\.btn-sm\s*\{([^}]+)', components)[1]
    hero = re.search(r'\.hero-figure__value\s*\{([^}]+)', source('static/css/app.css'))[1]
    assert 'font-size: var(--num-hero)' in hero
    assert 'font-weight: var(--weight-emphasis)' in hero
    overview = source('templates/index.html')
    assert 'title="{{ totals.book_value|fmt_money }}">{{ totals.book_value|fmt_display_money }}' in overview
    for selector in ('.lp-title', '.lp-head h2', '.lp-close__panel h2', '.lp-shot__value'):
        body = re.search(re.escape(selector) + r'\s*\{([^}]+)', source('static/css/landing.css'))[1]
        assert 'font-size: var(--' in body


def test_chart_typography_uses_shared_weights_and_responsive_size_tokens():
    for file in ('overview_charts.js', 'landing.js'):
        chart = source('static/js/' + file)
        assert "window.Chart.defaults.font.weight = cssVar('--weight-body');" in chart
        for role in ('titleFont', 'bodyFont'):
            assert role + ": function () { return { weight: cssVar('--weight-emphasis'), size: Number(cssVar('--chart-text-size')) }; }" in chart


def test_settings_responsive_rule_follows_desktop_and_changes_orientation():
    css = source('static/css/app.css')
    desktop = css.index('.settings-sidebar {')
    narrow = css.index('@media (max-width: 56rem)', desktop)
    assert narrow > desktop
    responsive = css[narrow:css.index('.settings-tab-content', narrow)]
    assert '.settings-sidebar { display: grid;' in responsive
    assert 'repeat(3, minmax(0, 1fr))' in responsive
    assert 'flex-wrap: wrap' in responsive
    template = source('templates/auth/settings.html')
    assert "window.matchMedia('(max-width: 56rem)')" in template
    assert "narrow.matches ? 'horizontal' : 'vertical'" in template
    assert "narrow.addEventListener('change', syncOrientation)" in template


def test_rendered_settings_and_palette_have_real_semantic_associations(app):
    with app.app_context():
        user = User(username='phase4_user', email='phase4@example.com', is_verified=True)
        user.password_hash = 'legacy-test-hash'
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    client = app.test_client()
    authenticate_client(client, user_id)
    response = client.get('/settings')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    parsed = Elements(html)
    command = parsed.by_id('commandPaletteInput')
    assert command['role'] == 'combobox'
    assert command['aria-label'] == 'Search commands'
    assert command['aria-autocomplete'] == 'list'
    assert parsed.by_id(command['aria-controls'])['role'] == 'listbox'
    assert parsed.by_id('commandPaletteStatus')['role'] == 'status'
    assert parsed.by_id('commandPaletteStatus')['aria-live'] == 'polite'
    assert parsed.by_id('settingsTabs')['aria-orientation'] == 'vertical'
    assert len([1 for tag, attrs in parsed.nodes if tag == 'dl' and attrs.get('class') == 'settings-field']) == 3
    assert len([1 for tag, attrs in parsed.nodes if tag == 'dd' and attrs.get('class') == 'settings-field-value']) == 3
    assert 'settings-readonly-field' not in html
    assert any(tag == 'button' and attrs.get('aria-label') == 'Close navigation' and 'data-nav-close' in attrs
               for tag, attrs in parsed.nodes)
    scripts = [attrs.get('src', '') for tag, attrs in parsed.nodes if tag == 'script' and 'src' in attrs]
    overlay = next(index for index, url in enumerate(scripts) if '/js/overlays.js' in url)
    shell = next(index for index, url in enumerate(scripts) if '/js/shell.js' in url)
    assert overlay < shell


def test_all_programmatic_financial_dialogs_use_shared_return_path():
    for path in ('templates/assets.html', 'templates/portfolios.html', 'static/js/portfolio_transfers.js'):
        text = source(path)
        assert 'window.OnePortfolioDialogs.show(' in text
        assert 'new bootstrap.Modal' not in text
        assert 'bootstrap.Modal.getOrCreateInstance' not in text
    coordinator = source('static/js/overlays.js')
    assert "window.bootstrap.Modal.getOrCreateInstance(element)" in coordinator
    assert 'new FocusTrap' not in coordinator
    assert 'focus: false' not in coordinator
    assert '_focustrap' not in coordinator


def test_calendar_stays_with_modal_owner_and_preserves_date_contract():
    main = source('static/js/main.js')
    assert "const modal = el.closest('.modal');" in main
    assert 'appendTo: modal || document.body' in main
    assert "dateFormat: 'Y-m-d'" in main
    assert 'allowInput: true' in main
    assert 'clickOpens: !el.disabled && !el.readOnly' in main
    assert 'if (el._flatpickr) el._flatpickr.close();' in main
    assert '.modal > .op-flatpickr.flatpickr-calendar' in source('static/css/flatpickr-nova.css')
