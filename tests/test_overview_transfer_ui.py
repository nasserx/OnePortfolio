"""Presentation-only Phase 12 contracts; canonical accounting is unchanged."""

from pathlib import Path
import re

import pytest

from portfolio_app import db
from portfolio_app.models.user import User
from portfolio_app.services.factory import Services
from tests._auth import authenticate_client
from tests.test_financial_baseline import ledger
from tests.test_final_financial_vocabulary import FinancialPage
from tests.test_portfolio_transfers import pair, day, D, buy


@pytest.mark.parametrize('sale_price,tone,percentage,amount,arrow', [
    ('120', 'pos', '+20.00%', '+20.00', 'arrow-up-right'),
    ('80', 'neg', '-20.00%', '-20.00', 'arrow-down-right'),
    ('100', 'flat', '0.00%', '0.00', None),
    (None, 'flat', '—', '0.00', None),
])
def test_overview_groups_return_with_pnl_not_book_value(pair, app, sale_price, tone, percentage, amount, arrow):
    buy(pair, pair.a, '100', 1)
    if sale_price:
        pair.svc.transaction_service.add_transaction(pair.a, 'Sell', 'BTC', D(sale_price), D('1'), D('0'), date=day(2))
    client = app.test_client()
    authenticate_client(client, pair.uid)
    html = client.get('/').get_data(as_text=True)
    hero = html.split('id="overview-headline"', 1)[1].split('<section class="card alloc-panel"', 1)[0]
    headline, realized = hero.split('<div class="hero-figure__realized">', 1)
    realized, facts = realized.split('<div class="hero-figure__facts">', 1)
    assert 'fmt_' not in hero
    assert 'Realized Return' not in headline and 'delta' not in headline
    assert 'Realized P&amp;L' in realized and 'Realized Return' in realized
    assert amount in realized and percentage in realized
    assert f'delta--{tone}' in realized
    if arrow:
        assert f'#op-icon-{arrow}' in realized
    else:
        assert '#op-icon-arrow-' not in realized
    assert facts.count('class="fact"') == 3
    assert 'fact supporting-item' not in facts and 'Realized P&amp;L' not in facts
    assert facts.index('Net Contributions') < facts.index('Cash') < facts.index('Dividends')
    assert hero.count('class="info-dot"') == 3
    assert hero.count('data-bs-trigger="hover focus"') == 3
    for formula in ('Book Value = Cash + Cost Basis', 'Net Contributions = Deposits − Withdrawals'):
        assert f'aria-label="{formula}"' in hero
    assert realized.count('class="info-dot"') == 1
    label = realized.split('class="hero-figure__pnl-label">', 1)[1].split('</span>', 1)[0]
    assert label == 'Realized P&amp;L'
    assert realized.index('class="info-dot"') > realized.index('class="delta ')
    # No extra labels/headings; exactly two formula lines, with only the
    # leading concept names emphasized. HTMLParser decodes attribute entities.
    hint, _ = FinancialPage(realized).help[0]
    assert hint['data-bs-html'] == 'true'
    assert hint['data-bs-title'] == (
        '<span class="tooltip-formulas">'
        '<span class="tooltip-formula"><strong>Realized P&amp;L</strong> = '
        'Net Sale Proceeds − Released Cost Basis</span>'
        '<span class="tooltip-formula"><strong>Realized Return</strong> = '
        'Realized P&amp;L ÷ Released Cost Basis × 100</span>'
        '</span>'
    )
    assert hint['aria-label'] == hint['title'] == (
        'Realized P&L = Net Sale Proceeds − Released Cost Basis\n'
        'Realized Return = Realized P&L ÷ Released Cost Basis × 100'
    )
    assert not FinancialPage(facts.split('Cash', 1)[1]).help


def test_transfer_menu_and_context_are_scoped_and_non_destructive(pair, app):
    foreign = User(username='hidden_owner', email='hidden-owner@example.com', is_verified=True)
    foreign.password_hash = 'test'
    db.session.add(foreign)
    db.session.commit()
    Services(user_id=foreign.id).portfolio_service.create_portfolio('PRIVATE PORTFOLIO', user_id=foreign.id)
    client = app.test_client()
    authenticate_client(client, pair.uid)
    html = client.get('/portfolios/').get_data(as_text=True)
    menu = html.split('js-rename-portfolio-btn', 1)[1].split('{% endcall %}', 1)[0].split('</ul>', 1)[0]
    labels = ['Rename', 'Deposit', 'Withdraw', 'Transfer', 'dropdown-divider', 'Remove']
    assert [menu.index(label) for label in labels] == sorted(menu.index(label) for label in labels)
    assert '#op-icon-arrows-exchange' in menu
    transfer = menu.split('data-transfer-action="create"', 1)[1].split('</button>', 1)[0]
    assert '#op-icon-arrow-up-circle' not in transfer
    assert 'PRIVATE PORTFOLIO' not in html
    modal = html.split('id="transferModal"', 1)[1].split('id="deleteTransferModal"', 1)[0]
    assert 'id="transfer_source_picker" hidden' in modal
    assert re.search(r'id="transfer_source_portfolio_id"[^>]*disabled', modal)
    assert 'id="transfer_context_source" type="hidden" name="source_portfolio_id"' in modal
    assert '<label class="form-label" for="transfer_source_name">From Portfolio</label>' in modal
    source = re.search(r'<input\s+id="transfer_source_name"([^>]*)>', modal).group(1)
    assert 'class="form-control"' in source and 'type="text"' in source
    assert 'readonly' in source and 'name=' not in source
    assert '<p id="transfer_source_name"' not in modal
    assert '<select id="transfer_destination_portfolio_id"' in modal
    assert 'aria-labelledby="transferModalTitle"' in modal
    assert 'aria-label="Close"' in modal
    assert 'transfer-error' not in modal and 'alert-danger' not in modal


def test_transfer_errors_retain_shared_form_and_field_contracts(pair, app):
    client = app.test_client()
    authenticate_client(client, pair.uid)
    data = dict(source_portfolio_id=pair.a, destination_portfolio_id=pair.b, amount='1001', date='2024-01-02')
    headers = {'X-Requested-With': 'XMLHttpRequest'}
    result = client.post('/portfolios/transfers/add', data=data, headers=headers).json
    assert 'Insufficient cash' in result['errors']['__all__']
    data['amount'] = 'invalid'
    assert 'amount' in client.post('/portfolios/transfers/add', data=data, headers=headers).json['errors']


def test_pnl_wraps_without_shrinking_or_new_financial_styles():
    css = Path('portfolio_app/static/css/app.css').read_text(encoding='utf-8')
    block = css.split('.hero-figure__realized {', 1)[1].split('}', 1)[0]
    assert 'flex-wrap: wrap' in block
    assert '.hero-figure__return' in css
    assert 'overflow-wrap: anywhere' in css.split('.hero-figure__pnl-value {', 1)[1].split('}', 1)[0]
    assert re.search(r'@media \(max-width: 32rem\).*?\.hero-figure__facts\s*\{\s*grid-template-columns: minmax\(0, 1fr\)', css, re.S)
