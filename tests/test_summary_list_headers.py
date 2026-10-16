"""Rendered list semantics and shared geometry; browser acceptance is separate."""
from datetime import datetime
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
import re

import pytest

from portfolio_app import db
from portfolio_app.models.user import User
from portfolio_app.services.factory import Services
from tests._auth import authenticate_client


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    @property
    def text(self):
        return ''.join(child if isinstance(child, str) else child.text for child in self.children)

    def find(self, predicate):
        result = []
        for child in self.children:
            if isinstance(child, Node):
                if predicate(child):
                    result.append(child)
                result.extend(child.find(predicate))
        return result

    def by_class(self, name):
        return self.find(lambda n: name in n.attrs.get('class', '').split())


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.root = Node()
        self.stack = [self.root]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, text):
        self.stack[-1].children.append(text)


@pytest.fixture
def summary_client(app):
    with app.app_context():
        user = User(username='summary-reader', email='summary@example.com', is_verified=True)
        db.session.add(user)
        db.session.commit()
        uid = user.id
        services = Services(user_id=uid)
        for name in ('Growth', 'Income'):
            portfolio = services.portfolio_service.create_portfolio(name, user_id=uid)
            services.portfolio_service.deposit_funds(portfolio.id, Decimal('1000'), date=datetime(2024, 1, 1))
            services.transaction_service.add_transaction(
                portfolio_id=portfolio.id, transaction_type='Buy', symbol='ABC',
                price=Decimal('10'), quantity=Decimal('1.25'), fees=Decimal('0'),
                date=datetime(2024, 1, 2),
            )
    client = app.test_client()
    authenticate_client(client, uid)
    return client


@pytest.mark.parametrize('url,kind,identity,labels,values', [
    ('/transactions/', 'assets', 'Asset', ['Entries', 'Purchase Cost', 'Quantity', 'Avg. Cost', 'Cumulative P&L', 'Return', 'Dividends'],
     ['1', '12.50', '1.25', '10.00', '0.00', '0.00%', '0.00']),
    ('/portfolios/', 'portfolios', 'Portfolio', ['Entries', 'Net Contributions', 'Cash', 'Cost Basis'],
     ['1', '1,000.00', '987.50', '12.50']),
])
def test_one_header_with_labelled_values_and_unchanged_controls(summary_client, url, kind, identity, labels, values):
    response = summary_client.get(url)
    assert response.status_code == 200
    doc = Document(response.get_data(as_text=True)).root
    section, = doc.find(lambda n: n.attrs.get('data-summary-list') == kind)
    header, = section.by_class('summary-list__columns')
    assert [n.text for n in header.by_class('summary-list__label')] == labels
    assert header.by_class('disclosure__identity')[0].text == identity
    assert header.by_class('disclosure__actions')[0].text == 'Actions'
    assert header.attrs['aria-hidden'] == 'true'
    assert 'surface-card' not in header.attrs['class'].split()
    assert 'surface-table' not in header.attrs['class'].split()
    assert 'Category' not in header.text
    body, = section.find(lambda n: 'data-summary-body' in n.attrs)
    assert not body.by_class('summary-list__sticky')
    list_node, = body.find(lambda n: n.attrs.get('role') == 'list')
    rows = list_node.find(lambda n: n.attrs.get('role') == 'listitem')
    assert len(rows) == 2
    for row in rows:
        toggle, = row.by_class('disclosure__toggle')
        assert toggle.tag == 'button' and toggle.attrs['aria-expanded'] == 'false'
        panel, = row.by_class('disclosure__panel')
        assert toggle.attrs['aria-controls'] == panel.attrs['id'] and 'hidden' in panel.attrs
        assert [n.text.strip() for n in toggle.by_class('metric__label')] == labels
        assert all('visually-hidden' in n.attrs['class'] for n in toggle.by_class('metric__label'))
        assert [' '.join(n.text.split()) for n in toggle.by_class('metric__value')] == values
        assert not toggle.by_class('action-menu__trigger')
        assert row.by_class('action-menu__trigger')
        assert panel.find(lambda n: n.tag == 'table')
    help_node, = doc.find(lambda n: n.attrs.get('id') == kind + '-scroll-help')
    assert 'Left and Right' in help_node.text
    for region in section.find(lambda n: 'data-summary-header' in n.attrs or 'data-summary-body' in n.attrs):
        assert region.attrs['role'] == 'region'
        assert region.attrs['aria-describedby'] == help_node.attrs['id']
        assert region.attrs['tabindex'] == '0'


def test_shared_geometry_sticky_ownership_and_fixed_menu_escape():
    css = Path('portfolio_app/static/css/app.css').read_text(encoding='utf-8')
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    def rule(selector):
        return re.search(r'(?:^|[{}])\s*' + re.escape(selector) + r'\s*\{([^}]+)', css)[1]
    sticky = rule('.summary-list__sticky')
    assert 'position: sticky' in sticky and 'top: 0' in sticky
    assert 'z-index: var(--z-sticky)' in sticky
    assert 'background-color: var(--background)' in sticky
    assert 'text-transform: uppercase' in rule('.summary-list__columns')
    assert 'font-weight: var(--weight-emphasis)' in rule('.summary-list__columns')
    for selector in ('.summary-list__sticky', '.summary-list__columns', '.disclosure__head'):
        declarations = rule(selector)
        assert not re.search(r'(?:^|[;\n])\s*(?:border(?:-radius)?|box-shadow|outline)\s*:', declarations)
    for selector in ('.summary-list__columns', '.disclosure__head'):
        assert not re.search(r'(?:^|[;\n])\s*background(?:-color)?\s*:', rule(selector))
    assert '.disclosure__head:has(button.disclosure__toggle:hover)' in css
    assert 'grid-template-columns: var(--summary-columns)' in rule('.disclosure__metrics')
    assert 'min-width: var(--summary-min-width)' in rule('.summary-list__track')
    assert 'padding: var(--space-1)' in rule('.summary-list__track')
    assert 'width: 1rem' in rule('.summary-list__chevron-space')
    assert 'scrollbar-width: none' in rule('.summary-list__body-scroll')
    assert 'scrollbar-width: none' not in rule('.summary-list__header-scroll,\n  .summary-list__body-scroll')
    for selector in ('.summary-list__track', '.summary-list__items', '.summary-list__header-scroll,\n  .summary-list__body-scroll', '.disclosure__item'):
        declarations = rule(selector)
        # These would trap fixed Popper menus or add a nested vertical viewport.
        assert not re.search(r'(?:^|[;\n])\s*(?:transform|filter|backdrop-filter|contain|will-change|height|max-height|z-index)\s*:', declarations)
    assert 'animation-name: op-fade-in' in rule('.disclosure.enter')
    main = Path('portfolio_app/static/js/main.js').read_text(encoding='utf-8')
    assert "strategy: 'fixed'" in main and "boundary: 'viewport'" in main
    assert '--metric-columns: 2' not in css and '--metric-columns: 3' not in css
