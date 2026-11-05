"""Rendered list semantics and shared geometry; browser acceptance is separate."""
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import re

import pytest

from portfolio_app import db
from portfolio_app.models.user import User
from portfolio_app.services.factory import Services
from tests._auth import authenticate_client
from tests._html import Document


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


def test_dotted_and_underscored_assets_open_their_own_records(summary_client, app):
    with app.app_context():
        user = User.query.filter_by(username='summary-reader').one()
        svc = Services(user_id=user.id)
        portfolio = svc.portfolio_repo.get_all()[0]
        for symbol in ('BRK.B', 'BRK_B'):
            svc.transaction_service.add_transaction(
                portfolio_id=portfolio.id, transaction_type='Buy', symbol=symbol,
                price=Decimal('1'), quantity=Decimal('1'), fees=Decimal('0'),
                date=datetime(2024, 1, 3),
            )
    response = summary_client.get('/transactions/')
    assert response.status_code == 200
    doc = Document(response.get_data(as_text=True)).root
    cards = doc.by_class('symbol-card')
    assert {'BRK.B', 'BRK_B'} <= {card.attrs['data-symbol'] for card in cards}
    for item in cards:
        toggle, = item.by_class('disclosure__toggle')
        target, = doc.find(lambda n: n.attrs.get('id') == toggle.attrs['aria-controls'])
        panel, = item.by_class('disclosure__panel')
        assert target is panel


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
        classes = row.attrs['class'].split()
        assert 'surface-row' in classes
        assert 'surface-card' not in classes
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
        assert all(n.attrs.get('scope') == 'col' for n in panel.find(lambda n: n.tag == 'th'))
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
    assert 'color: var(--foreground)' in rule('.summary-list__columns')
    shared_type = rule('.ledger__row--head,\n  .summary-list__columns')
    assert 'font-size: var(--text-xs)' in shared_type
    assert 'font-size:' not in rule('.summary-list__columns')
    assert 'gap:' not in rule('.disclosure') + rule('.summary-list__items')
    assert 'border-bottom: 1px solid var(--border)' in rule('.summary-list__columns')
    assert 'min-height: var(--row-h)' in rule('.summary-list__columns')
    assert 'padding: var(--cell-pad-y) var(--cell-pad-x)' in rule('.disclosure__head')
    assert 'text-align: left' in rule('.metric')
    for selector in ('.summary-list__sticky', '.summary-list__columns', '.disclosure__head'):
        declarations = rule(selector)
        assert not re.search(r'(?:^|[;\n])\s*(?:border(?:-radius)?|box-shadow|outline)\s*:', declarations)
    for selector in ('.summary-list__columns', '.disclosure__head'):
        assert not re.search(r'(?:^|[;\n])\s*background(?:-color)?\s*:', rule(selector))
    assert '.disclosure__head:hover' in css
    assert 'grid-template-columns: var(--summary-columns)' in rule('.disclosure__metrics')
    assert 'min-width: var(--summary-min-width)' in rule('.summary-list__track')
    assert 'padding:' not in rule('.summary-list__track')
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


@pytest.mark.parametrize('url', ['/transactions/', '/portfolios/'])
def test_empty_expanded_content_retains_inline_feedback_and_disclosure(app, url):
    with app.app_context():
        user = User(username='empty-summary', email='empty-summary@example.com', is_verified=True)
        db.session.add(user)
        db.session.commit()
        uid = user.id
        services = Services(user_id=uid)
        portfolio = services.portfolio_service.create_portfolio('Unfunded', user_id=uid)
        services.transaction_service.add_symbol(portfolio.id, 'EMPTY')
    client = app.test_client()
    authenticate_client(client, uid)
    response = client.get(url)
    assert response.status_code == 200
    doc = Document(response.get_data(as_text=True)).root
    row, = doc.by_class('disclosure__item')
    assert 'surface-row' in row.attrs['class']
    panel, = row.by_class('disclosure__panel')
    assert 'hidden' in panel.attrs
    empty, = panel.by_class('inline-empty')
    assert not panel.find(lambda n: n.tag == 'table')
    if url == '/transactions/':
        button, = empty.find(lambda n: n.tag == 'button')
        assert 'js-add-transaction-btn' in button.attrs['class']
        assert 'Add Entry' in button.text
    else:
        assert 'No entries yet' in empty.text
