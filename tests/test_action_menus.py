"""Rendered contracts for entity and row action menus."""

import json
from datetime import datetime
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

from portfolio_app import db
from portfolio_app.models.user import User
from tests._auth import authenticate_client
from portfolio_app.services.factory import Services


VOID_TAGS = {
    'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
    'link', 'meta', 'param', 'source', 'track', 'wbr',
}
COMPONENTS_CSS = (
    Path(__file__).resolve().parents[1]
    / 'portfolio_app' / 'static' / 'css' / 'components.css'
)
MAIN_JS = (
    Path(__file__).resolve().parents[1]
    / 'portfolio_app' / 'static' / 'js' / 'main.js'
)
APP_CSS = (
    Path(__file__).resolve().parents[1]
    / 'portfolio_app' / 'static' / 'css' / 'app.css'
)
TEMPLATES = Path(__file__).resolve().parents[1] / 'portfolio_app' / 'templates'


class _ActionItem:
    def __init__(self, attrs):
        self.attrs = attrs
        self.text_parts = []
        self.icons = []

    @property
    def text(self):
        return ' '.join(self.text_parts)


class _ActionMenu:
    def __init__(self):
        self.trigger = {}
        self.trigger_icons = []
        self.menu = {}
        self.items = []

    def item(self, text):
        return next(item for item in self.items if item.text == text)


class _ActionMenuParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.menus = []
        self._depth = 0
        self._current = None
        self._menu_depth = None
        self._trigger_depth = None
        self._item = None
        self._item_depth = None

    @staticmethod
    def _classes(attrs):
        return set((attrs.get('class') or '').split())

    def _open(self, tag, raw_attrs):
        attrs = dict(raw_attrs)
        classes = self._classes(attrs)

        if self._current is None and tag == 'div' and 'action-menu' in classes:
            self._current = _ActionMenu()
            self._menu_depth = self._depth
            self.menus.append(self._current)

        if self._current is None:
            return

        if tag == 'button' and 'action-menu__trigger' in classes:
            self._current.trigger = attrs
            self._trigger_depth = self._depth
        elif tag == 'ul' and 'action-menu__menu' in classes:
            self._current.menu = attrs
        elif tag == 'button' and 'dropdown-item' in classes:
            self._item = _ActionItem(attrs)
            self._item_depth = self._depth
            self._current.items.append(self._item)
        elif tag == 'i':
            if self._item is not None:
                self._item.icons.append(classes)
            elif self._trigger_depth is not None:
                self._current.trigger_icons.append(classes)

    def handle_starttag(self, tag, attrs):
        self._open(tag, attrs)
        if tag not in VOID_TAGS:
            self._depth += 1

    def handle_startendtag(self, tag, attrs):
        self._open(tag, attrs)

    def handle_data(self, data):
        if self._item is not None and data.strip():
            self._item.text_parts.append(data.strip())

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        self._depth -= 1
        if self._item is not None and self._depth == self._item_depth:
            self._item = None
            self._item_depth = None
        if self._trigger_depth is not None and self._depth == self._trigger_depth:
            self._trigger_depth = None
        if self._current is not None and self._depth == self._menu_depth:
            self._current = None
            self._menu_depth = None


def _seed_user():
    user = User(
        username='action_menu_user',
        email='action_menu_user@example.com',
        is_verified=True,
    )
    user.password_hash = 'legacy-test-hash'
    db.session.add(user)
    db.session.commit()
    return user.id


def _seed_activity(user_id):
    svc = Services(user_id=user_id)
    portfolio = svc.portfolio_service.create_portfolio('Growth', user_id=user_id)
    event = svc.portfolio_service.deposit_funds(
        portfolio.id, Decimal('5000'), date=datetime(2024, 1, 1),
    ).events.one()
    svc.transaction_service.add_symbol(portfolio.id, 'AAPL')
    transaction = svc.transaction_service.add_transaction(
        portfolio_id=portfolio.id,
        transaction_type='Buy',
        symbol='AAPL',
        price=Decimal('100'),
        quantity=Decimal('10'),
        fees=Decimal('0'),
        date=datetime(2024, 1, 2),
    )
    income = svc.transaction_service.add_dividend(
        portfolio_id=portfolio.id,
        symbol='AAPL',
        amount=Decimal('75'),
        date=datetime(2024, 1, 4),
    )
    return {
        'portfolio_id': portfolio.id,
        'event_id': event.id,
        'transaction_id': transaction.id,
        'income_id': income.id,
    }


def _render_pages(app):
    with app.app_context():
        user_id = _seed_user()
        ids = _seed_activity(user_id)

    client = app.test_client()
    authenticate_client(client, user_id)

    rendered = {}
    for path in ('/portfolios/', '/transactions/'):
        response = client.get(path)
        assert response.status_code == 200, path
        html = response.get_data(as_text=True)
        parser = _ActionMenuParser()
        parser.feed(html)
        rendered[path] = (html, parser.menus)
    return rendered, ids


def _by_label(menus):
    return {menu.trigger['aria-label']: menu for menu in menus}


def test_action_menus_render_the_expected_entity_actions(app):
    rendered, _ids = _render_pages(app)
    portfolio_menus = _by_label(rendered['/portfolios/'][1])
    asset_menus = _by_label(rendered['/transactions/'][1])

    assert [item.text for item in portfolio_menus['Actions for portfolio Growth'].items] == [
        'Rename', 'Deposit', 'Withdraw', 'Remove',
    ]
    assert [item.text for item in portfolio_menus['Actions for Deposit entry on 2024-01-01'].items] == [
        'Edit', 'Remove',
    ]
    assert [item.text for item in asset_menus['Actions for AAPL in Growth'].items] == [
        'Buy / Sell', 'Add income', 'Remove',
    ]
    assert [item.text for item in asset_menus['Actions for Buy entry for AAPL on 2024-01-02'].items] == [
        'Edit', 'Remove',
    ]
    assert [item.text for item in asset_menus['Actions for income entry for AAPL on 2024-01-04'].items] == [
        'Edit', 'Remove',
    ]

    assert 'data-bs-target="#newPortfolioModal"' in rendered['/portfolios/'][0]
    assert 'class="btn btn-primary js-add-symbol-btn"' in rendered['/transactions/'][0]


def test_action_menu_triggers_keep_bootstrap_and_accessibility_contracts(app):
    rendered, _ids = _render_pages(app)
    menus = rendered['/portfolios/'][1] + rendered['/transactions/'][1]

    assert len(menus) == 5
    for menu in menus:
        classes = set(menu.trigger['class'].split())
        assert {'btn', 'btn-icon', 'dropdown-toggle', 'action-menu__trigger'} <= classes
        assert menu.trigger['type'] == 'button'
        assert menu.trigger['data-bs-toggle'] == 'dropdown'
        assert menu.trigger['data-bs-boundary'] == 'viewport'
        assert menu.trigger['aria-expanded'] == 'false'
        assert menu.trigger['aria-haspopup'] == 'true'
        assert menu.trigger['aria-label'].startswith('Actions for ')
        assert menu.trigger['aria-label'] != 'Actions'
        assert {'dropdown-menu', 'dropdown-menu-end', 'action-menu__menu'} <= set(
            menu.menu['class'].split()
        )
        assert menu.trigger_icons == [{'bi', 'bi-three-dots-vertical'}]


def test_action_menus_share_viewport_safe_popper_positioning():
    source = MAIN_JS.read_text(encoding='utf-8')

    assert "querySelectorAll('.action-menu__trigger')" in source
    assert "boundary: 'viewport'" in source
    assert "strategy: 'fixed'" in source

    css = COMPONENTS_CSS.read_text(encoding='utf-8')
    dropdown_show_rule = css.split('.dropdown-menu.show', 1)[1].split('}', 1)[0]
    assert 'op-fade-in' in dropdown_show_rule
    assert 'op-scale-in' not in dropdown_show_rule
    assert 'transform' not in dropdown_show_rule

    app_css = APP_CSS.read_text(encoding='utf-8')
    assert '.disclosure.enter { animation-name: op-fade-in; }' in app_css
    assert 'animation: op-fade-in var(--dur-3) var(--ease-out);' in app_css
    assert 'op-reveal' not in app_css


def test_action_items_preserve_dispatch_classes_and_payloads(app):
    rendered, ids = _render_pages(app)
    portfolio_menus = _by_label(rendered['/portfolios/'][1])
    asset_menus = _by_label(rendered['/transactions/'][1])

    portfolio = portfolio_menus['Actions for portfolio Growth']
    assert portfolio.item('Rename').attrs['class'].endswith('js-rename-portfolio-btn')
    assert portfolio.item('Rename').attrs['data-portfolio-id'] == str(ids['portfolio_id'])
    assert portfolio.item('Rename').attrs['data-name'] == 'Growth'
    assert portfolio.item('Deposit').attrs['class'].endswith('js-deposit-funds-btn')
    assert portfolio.item('Deposit').attrs['data-portfolio-id'] == str(ids['portfolio_id'])
    assert portfolio.item('Deposit').attrs['data-name'] == 'Growth'
    assert portfolio.item('Withdraw').attrs['class'].endswith('js-withdraw-funds-btn')
    assert 'data-withdrawable-cash' in portfolio.item('Withdraw').attrs
    assert portfolio.item('Remove').attrs['class'].endswith('js-delete-portfolio-btn')

    event = portfolio_menus['Actions for Deposit entry on 2024-01-01']
    assert json.loads(event.item('Edit').attrs['data-event'])['id'] == ids['event_id']
    assert event.item('Edit').attrs['class'].endswith('js-edit-portfolio-event-btn')
    assert event.item('Remove').attrs['data-event-id'] == str(ids['event_id'])
    assert event.item('Remove').attrs['class'].endswith('js-delete-portfolio-event-btn')

    asset = asset_menus['Actions for AAPL in Growth']
    assert asset.item('Buy / Sell').attrs['class'].endswith('js-add-transaction-btn')
    assert asset.item('Buy / Sell').attrs['data-symbol'] == 'AAPL'
    assert asset.item('Add income').attrs['class'].endswith('js-add-dividend-btn')
    assert asset.item('Remove').attrs['class'].endswith('js-delete-symbol-btn')
    assert asset.item('Remove').attrs['data-tx-count'] == '1'
    assert asset.item('Remove').attrs['data-income-count'] == '1'

    transaction = asset_menus['Actions for Buy entry for AAPL on 2024-01-02']
    assert json.loads(transaction.item('Edit').attrs['data-tx'])['id'] == ids['transaction_id']
    assert transaction.item('Edit').attrs['class'].endswith('js-edit-transaction-btn')
    assert transaction.item('Remove').attrs['data-tx-id'] == str(ids['transaction_id'])
    assert transaction.item('Remove').attrs['class'].endswith('js-delete-transaction-btn')

    income = asset_menus['Actions for income entry for AAPL on 2024-01-04']
    assert json.loads(income.item('Edit').attrs['data-div'])['id'] == ids['income_id']
    assert income.item('Edit').attrs['class'].endswith('js-edit-dividend-btn')
    assert income.item('Remove').attrs['data-div-id'] == str(ids['income_id'])
    assert income.item('Remove').attrs['class'].endswith('js-delete-dividend-btn')


def test_existing_delegated_dispatch_still_owns_every_menu_action():
    sources = {
        'portfolios.html': {
            'js-rename-portfolio-btn', 'js-deposit-funds-btn', 'js-withdraw-funds-btn',
            'js-delete-portfolio-btn', 'js-edit-portfolio-event-btn',
            'js-delete-portfolio-event-btn',
        },
        'assets.html': {
            'js-add-transaction-btn', 'js-add-dividend-btn',
            'js-delete-symbol-btn', 'js-edit-transaction-btn',
            'js-delete-transaction-btn', 'js-edit-dividend-btn',
            'js-delete-dividend-btn',
        },
    }

    for template_name, hooks in sources.items():
        source = (TEMPLATES / template_name).read_text(encoding='utf-8')
        for hook in hooks:
            assert ".closest('.{0}')".format(hook) in source


def test_remove_items_keep_destructive_presentation(app):
    rendered, _ids = _render_pages(app)
    menus = rendered['/portfolios/'][1] + rendered['/transactions/'][1]

    for menu in menus:
        for item in menu.items:
            classes = set(item.attrs['class'].split())
            if item.text == 'Remove':
                assert 'dropdown-item--danger' in classes
                assert {'bi', 'bi-trash'} in item.icons
            else:
                assert 'dropdown-item--danger' not in classes

    css = COMPONENTS_CSS.read_text(encoding='utf-8')
    dropdown_item_rule = css.split('.dropdown-item {', 1)[1].split('}', 1)[0]
    assert 'font-size: var(--text-xs);' in dropdown_item_rule
    assert 'line-height: var(--leading-normal);' in dropdown_item_rule
    assert 'padding: var(--space-2) var(--space-3);' in dropdown_item_rule
    assert '.dropdown-item--danger { color: var(--neg); }' in css
    assert '.dropdown-item--danger:hover,' in css
    assert 'background-color: var(--neg-soft);' in css
