"""Committed domain history shares the Phase 13 receipt and transaction owner."""

import json
from dataclasses import FrozenInstanceError
from decimal import Decimal as D, localcontext

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError

from portfolio_app import db
from portfolio_app.models import FinancialAudit, MutationReceipt, User, PortfolioEvent
from portfolio_app.repositories.financial_audit_repository import AUDITED_FIELDS, FinancialAuditRepository
from portfolio_app.services.financial_audit import canonical_snapshot
from portfolio_app.services.mutation import mutation_transaction
from tests.test_financial_baseline import ledger
from tests.test_portfolio_transfers import pair, buy, transfer, day, PC
from tests.test_mutation_integrity import create_case, edit_case, client_for, token, post


def history(p, **filters):
    return p.svc.audit_repo.history(**filters)


@pytest.mark.parametrize('kind', ['Buy', 'Sell', 'Deposit', 'Withdrawal', 'Dividend', 'Transfer'])
def test_create_exact_snapshot_and_successful_retry_has_one_audit(pair, app, kind):
    path, values, model = create_case(pair, kind)
    client, intent = client_for(app, pair.uid), token(app, pair.uid)
    previous = FinancialAudit.query.count()
    first = post(client, path, values, intent)
    assert first.status_code == 200, first.json
    row = model.query.order_by(model.id.desc()).first()
    events = history(pair, entity_type=model.__tablename__, entity_id=row.id)
    assert len(events) == 1
    revision = events[0]
    assert revision.action == 'create' and revision.before_state is None
    assert revision.after_state == canonical_snapshot({name: getattr(row, name) for name in AUDITED_FIELDS[model]})
    assert set(json.loads(revision.after_state)) == set(AUDITED_FIELDS[model])
    receipt = db.session.get(MutationReceipt, revision.mutation_receipt_id)
    assert receipt.user_id == pair.uid and receipt.response_json
    assert receipt.operation_key not in revision.after_state and intent not in revision.after_state
    snapshot = PC.get_financial_snapshot(pair.uid)
    assert post(client, path, values, intent).json == first.json
    assert FinancialAudit.query.count() == previous + 1
    assert PC.get_financial_snapshot(pair.uid) == snapshot


@pytest.mark.parametrize('kind', ['transaction', 'funding', 'dividend', 'transfer'])
def test_edit_delete_and_noop_revision_contract(pair, app, kind):
    path, values, row = edit_case(pair, kind)
    filters = dict(entity_type=row.__tablename__, entity_id=row.id)
    original = history(pair, **filters)[-1].after_state
    client = client_for(app, pair.uid)
    current, stale = token(app, pair.uid), token(app, pair.uid)
    response = post(client, path, values, current)
    assert response.status_code == 200, response.json
    revision = history(pair, **filters)[-1]
    assert revision.action == 'update' and revision.before_state == original
    assert revision.after_state != original
    assert revision.after_state == canonical_snapshot({name: getattr(row, name) for name in AUDITED_FIELDS[type(row)]})
    count = FinancialAudit.query.count()
    assert post(client, path, values, current).json == response.json
    assert post(client, path, values, stale).status_code == 409
    assert post(client, path, values, token(app, pair.uid)).status_code == 200
    assert FinancialAudit.query.count() == count  # Retry, stale rejection, normalized no-op.
    delete_path = path.replace('/edit/', '/delete/')
    intent = token(app, pair.uid)
    deleted = post(client, delete_path, {}, intent)
    assert deleted.status_code == 200, deleted.json
    removal = history(pair, **filters)[-1]
    assert removal.action == 'delete' and removal.after_state is None
    # A no-op edit may update only automatic metadata; deleted facts still match.
    before, after = json.loads(removal.before_state), json.loads(revision.after_state)
    before.pop('updated_at', None)
    after.pop('updated_at', None)
    assert before == after
    assert post(client, delete_path, {}, intent).json == deleted.json
    assert FinancialAudit.query.count() == count + 1


def test_high_precision_domain_values_dates_and_notes_never_use_float(pair):
    p = pair
    price = D('123.12345678901234567890123456789012345')
    quantity = D('0.12345678901234567890123456789012345')
    fees = D('0.00000000000000000000000000000000001')
    when = day(2).replace(hour=12, minute=34, second=56, microsecond=123456)
    with localcontext() as ambient:
        ambient.prec = 3
        row = p.svc.transaction_service.add_transaction(p.a, 'Buy', 'BTC', price, quantity, fees,
                                                      date=when, notes='Exact: \u03c0\nsecond line')
    created = history(p, entity_type='transaction', entity_id=row.id)[0]
    state = json.loads(created.after_state, parse_float=lambda _: pytest.fail('JSON float'))
    assert state['price'] == str(price) and state['quantity'] == str(quantity)
    assert D(state['fees']) == fees and 'E' not in state['fees']
    assert state['date'] == '2024-01-02T12:34:56.123456'
    assert state['notes'] == 'Exact: \u03c0\nsecond line'
    assert state['portfolio_id'] == p.a
    p.svc.transaction_service.update_transaction(row.id, notes='notes only')
    changed = json.loads(history(p, entity_type='transaction', entity_id=row.id)[-1].after_state)
    for field in ('price', 'quantity', 'fees', 'date'):
        assert changed[field] == state[field]
    assert canonical_snapshot({'a': D('-0.000')}) == '{"a":"0"}'
    with pytest.raises(TypeError):
        canonical_snapshot({'amount': 0.1})


@pytest.mark.parametrize('kind', ['funding', 'dividend', 'transfer'])
def test_other_financial_snapshots_preserve_exact_persisted_amount(pair, kind):
    amount = D('1.123456789012345678901234567890123456789')
    if kind == 'funding':
        pair.svc.portfolio_service.deposit_funds(pair.a, amount, date=day(2), notes='exact')
        row = PortfolioEvent.query.order_by(PortfolioEvent.id.desc()).first()
        field = 'amount_delta'
    elif kind == 'dividend':
        row = pair.svc.transaction_service.add_dividend(pair.a, 'BTC', amount, day(2), notes='exact')
        field = 'amount'
    else:
        row = pair.svc.transfer_service.create(pair.a, pair.b, amount, day(2), notes='exact')
        field = 'amount'
    snapshot = json.loads(history(pair, entity_type=row.__tablename__, entity_id=row.id)[-1].after_state)
    assert snapshot[field] == str(amount)
    assert snapshot['notes'] == 'exact'


def test_distinct_identical_intentions_have_distinct_receipts_and_audits(pair, app):
    path, values, _ = create_case(pair, 'Buy')
    client = client_for(app, pair.uid)
    for _ in range(2):
        assert post(client, path, values, token(app, pair.uid)).status_code == 200
    events = history(pair, entity_type='transaction')
    assert len(events) == len({e.entity_id for e in events}) == len({e.mutation_receipt_id for e in events}) == 2


@pytest.mark.parametrize('case', ['invalid', 'cash', 'oversell', 'foreign', 'csrf'])
def test_rejected_requests_do_not_record_history(pair, app, case):
    path, values, _ = create_case(pair, 'Buy')
    if case == 'invalid': values['quantity'] = 'NaN'
    if case == 'cash': values['price'] = '1100'
    if case == 'oversell': values['transaction_type'] = 'Sell'
    uid = pair.uid
    if case == 'foreign':
        outsider = User(username='outsider', email='outside@audit.test', is_verified=True)
        db.session.add(outsider)
        db.session.commit()
        uid = outsider.id
    client, intent = client_for(app, uid), token(app, uid)
    before, receipts = FinancialAudit.query.count(), MutationReceipt.query.count()
    previous_csrf = app.config['WTF_CSRF_ENABLED']
    try:
        if case == 'csrf': app.config['WTF_CSRF_ENABLED'] = True
        assert post(client, path, values, intent).status_code in (400, 404)
    finally:
        app.config['WTF_CSRF_ENABLED'] = previous_csrf
    assert FinancialAudit.query.count() == before
    assert MutationReceipt.query.count() == receipts


@pytest.mark.parametrize('kind', ['Buy', 'Sell', 'Deposit', 'Withdrawal', 'Dividend', 'Transfer'])
@pytest.mark.parametrize('failure_table', ['mutation_receipt', 'financial_audit'])
def test_failure_after_financial_or_audit_insert_rolls_back_everything(pair, app, kind, failure_table):
    path, values, model = create_case(pair, kind)
    client, intent = client_for(app, pair.uid), token(app, pair.uid)
    snapshot = PC.get_financial_snapshot(pair.uid)
    counts = (model.query.count(), MutationReceipt.query.count(), FinancialAudit.query.count())
    def fail(connection, cursor, statement, parameters, context, many):
        if statement.startswith('INSERT INTO ' + failure_table):
            cursor.close()
            raise RuntimeError('injected after SQL insert')
    event.listen(db.engine, 'after_cursor_execute', fail)
    try:
        assert post(client, path, values, intent).status_code == 409
    finally:
        event.remove(db.engine, 'after_cursor_execute', fail)
    assert (model.query.count(), MutationReceipt.query.count(), FinancialAudit.query.count()) == counts
    assert PC.get_financial_snapshot(pair.uid) == snapshot
    assert post(client, path, values, intent).status_code == 200


@pytest.mark.parametrize('kind', ['transaction', 'funding', 'dividend', 'transfer'])
@pytest.mark.parametrize('operation', ['edit', 'delete'])
def test_failure_after_revision_insert_restores_edited_or_deleted_facts(pair, app, kind, operation):
    path, values, row = edit_case(pair, kind)
    if operation == 'delete': path, values = path.replace('/edit/', '/delete/'), {}
    raw = canonical_snapshot({name: getattr(row, name) for name in AUDITED_FIELDS[type(row)]})
    before, revisions = PC.get_financial_snapshot(pair.uid), history(pair)
    identifier, model = row.id, type(row)
    def fail(connection, cursor, statement, parameters, context, many):
        if statement.startswith('INSERT INTO financial_audit'):
            cursor.close()
            raise RuntimeError('injected after revision INSERT')
    client, intent = client_for(app, pair.uid), token(app, pair.uid)
    event.listen(db.engine, 'after_cursor_execute', fail)
    try:
        assert post(client, path, values, intent).status_code == 409
    finally:
        event.remove(db.engine, 'after_cursor_execute', fail)
    restored = db.session.get(model, identifier)
    assert canonical_snapshot({name: getattr(restored, name) for name in AUDITED_FIELDS[model]}) == raw
    assert PC.get_financial_snapshot(pair.uid) == before
    assert history(pair) == revisions


@pytest.mark.parametrize('kind', ['symbol', 'portfolio'])
def test_compound_deletion_preserves_each_child_under_one_receipt(pair, kind):
    p = pair
    tx = buy(p, p.a, '100', 1)
    div = p.svc.transaction_service.add_dividend(p.a, 'BTC', D('10'), day(1))
    symbol = p.svc.transaction_service.add_symbol(p.a, 'BTC')
    before = {(type(row).__tablename__, row.id): history(p, entity_type=row.__tablename__, entity_id=row.id)[-1].after_state
              for row in (tx, div, symbol)}
    start = history(p)[-1].id
    if kind == 'symbol':
        p.svc.transaction_service.delete_symbol(p.a, 'BTC')
    else:
        p.svc.portfolio_service.delete_portfolio(p.a)
    removed = [r for r in history(p) if r.id > start]
    assert len(removed) == (3 if kind == 'symbol' else 5)
    assert len({r.mutation_receipt_id for r in removed}) == 1
    assert all(r.action == 'delete' and r.after_state is None for r in removed)
    for r in removed:
        key = r.entity_type, r.entity_id
        if key in before: assert r.before_state == before[key]
    assert db.session.get(User, p.uid) is not None


@pytest.mark.parametrize('kind', ['symbol', 'portfolio'])
def test_compound_deletion_and_all_child_revisions_rollback_together(pair, kind):
    buy(pair, pair.a, '100', 1)
    pair.svc.transaction_service.add_dividend(pair.a, 'BTC', D('10'), day(1))
    pair.svc.transaction_service.add_symbol(pair.a, 'BTC')
    before, revisions = PC.get_financial_snapshot(pair.uid), history(pair)
    def fail(connection, cursor, statement, parameters, context, many):
        if statement.startswith('INSERT INTO financial_audit'):
            # Bulk INSERT RETURNING has unread rows at this hook. Release the
            # injected cursor so its lifetime cannot contaminate pooled reuse.
            cursor.close()
            raise RuntimeError('injected after deletion audit')
    event.listen(db.engine, 'after_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='injected'):
            if kind == 'symbol': pair.svc.transaction_service.delete_symbol(pair.a, 'BTC')
            else: pair.svc.portfolio_service.delete_portfolio(pair.a)
    finally:
        event.remove(db.engine, 'after_cursor_execute', fail)
    assert PC.get_financial_snapshot(pair.uid) == before
    assert history(pair) == revisions


def test_portfolio_creation_rename_and_initial_funding_are_grouped(pair):
    from portfolio_app.models import Portfolio
    with mutation_transaction():
        portfolio = pair.svc.portfolio_service.create_portfolio('New')
        # Initial is a legacy-supported funding type; its raw fact is captured too.
        db.session.add(PortfolioEvent(portfolio_id=portfolio.id, event_type='Initial', amount_delta=D('5'), date=day(1)))
    events = history(pair, mutation_receipt_id=history(pair)[-1].mutation_receipt_id)
    assert {e.entity_type for e in events} == {'portfolio', 'portfolio_event'}
    assert all(e.action == 'create' for e in events)
    pair.svc.portfolio_service.rename_portfolio(portfolio.id, 'Renamed')
    revision = history(pair, entity_type='portfolio', entity_id=portfolio.id)[-1]
    assert json.loads(revision.before_state)['name'] == 'New'
    assert json.loads(revision.after_state)['name'] == 'Renamed'
    assert db.session.get(Portfolio, portfolio.id).name == 'Renamed'


def test_nested_edits_capture_original_and_final_committed_state_once(pair):
    row = buy(pair, pair.a, '100', 1)
    with mutation_transaction():
        pair.svc.transaction_service.update_transaction(row.id, notes='intermediate')
        pair.svc.transaction_service.update_transaction(row.id, notes='final')
    events = history(pair, entity_type='transaction', entity_id=row.id)
    assert len(events) == 2
    assert json.loads(events[1].before_state)['notes'] == json.loads(events[0].after_state)['notes']
    assert json.loads(events[1].after_state)['notes'] == 'final'
    count = FinancialAudit.query.count()
    with mutation_transaction():
        pair.svc.transaction_service.update_transaction(row.id, notes='intermediate')
        pair.svc.transaction_service.update_transaction(row.id, notes='final')
    assert FinancialAudit.query.count() == count


def test_created_then_deleted_inside_one_operation_has_no_fabricated_revision(pair):
    count = FinancialAudit.query.count()
    with mutation_transaction():
        row = buy(pair, pair.a, '100', 1)
        pair.svc.transaction_service.delete_transaction(row.id)
    assert FinancialAudit.query.count() == count


def test_linked_portfolio_rejection_no_audit_and_transfer_endpoint_history(pair):
    row = transfer(pair)
    count = FinancialAudit.query.count()
    with pytest.raises(ValueError): pair.svc.portfolio_service.delete_portfolio(pair.a)
    assert FinancialAudit.query.count() == count
    pair.svc.transfer_service.update(row.id, destination_portfolio_id=pair.c)
    revision = history(pair, entity_type='portfolio_transfer', entity_id=row.id)[-1]
    assert json.loads(revision.before_state)['destination_portfolio_id'] == pair.b
    assert json.loads(revision.after_state)['destination_portfolio_id'] == pair.c


def test_append_only_guards_and_immutable_tenant_scoped_reader(pair):
    revision = history(pair)[0]
    with pytest.raises(FrozenInstanceError): revision.action = 'delete'
    assert FinancialAuditRepository(None).history() == ()
    assert FinancialAuditRepository(pair.uid + 999).get_by_id(revision.id) is None
    assert FinancialAuditRepository(pair.uid + 999).history(mutation_receipt_id=revision.mutation_receipt_id) == ()
    for name in ('add', 'update', 'delete', 'commit'):
        assert not hasattr(pair.svc.audit_repo, name)
    row = db.session.get(FinancialAudit, revision.id)
    row.action = 'delete'
    with pytest.raises(RuntimeError, match='append-only'): db.session.flush()
    db.session.rollback()
    db.session.delete(row)
    with pytest.raises(RuntimeError, match='append-only'): db.session.flush()
    db.session.rollback()
    for statement in ('UPDATE financial_audit SET entity_id=999 WHERE id=:id', 'DELETE FROM financial_audit WHERE id=:id'):
        with pytest.raises(IntegrityError): db.session.execute(text(statement), {'id': revision.id})
        db.session.rollback()
    rows = history(pair)
    assert list(rows) == sorted(rows, key=lambda r: (r.created_at, r.id))
    assert pair.svc.audit_repo.history(limit=1, offset=1) == rows[1:2]


def test_account_deletion_removes_only_that_accounts_history(pair, monkeypatch):
    from portfolio_app.services.factory import Services
    outsider = User(username='other', email='other@audit.test', is_verified=True)
    db.session.add(outsider)
    db.session.commit()
    other = Services(user_id=outsider.id)
    other.portfolio_service.create_portfolio('Private')
    expected = other.audit_repo.history()
    transfer(pair)
    auth = pair.svc.auth_service
    monkeypatch.setattr(auth, '_deletion_code_is_live', lambda user: True)
    monkeypatch.setattr('portfolio_app.services.auth_service.verify_otp', lambda *a, **k: True)
    auth.confirm_account_deletion(db.session.get(User, pair.uid), '123456')
    assert history(pair) == ()
    assert MutationReceipt.query.filter_by(user_id=pair.uid).count() == 0
    assert other.audit_repo.history() == expected


def test_failed_account_delete_restores_cascaded_history_and_receipts(pair, monkeypatch):
    transfer(pair)
    before, revisions = PC.get_financial_snapshot(pair.uid), history(pair)
    receipts = MutationReceipt.query.count()
    auth = pair.svc.auth_service
    monkeypatch.setattr(auth, '_deletion_code_is_live', lambda user: True)
    monkeypatch.setattr('portfolio_app.services.auth_service.verify_otp', lambda *a, **k: True)
    def fail(connection, cursor, statement, parameters, context, many):
        if statement.startswith('DELETE FROM user '):
            cursor.close()
            raise RuntimeError('injected after account cascade')
    event.listen(db.engine, 'after_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='injected'):
            auth.confirm_account_deletion(db.session.get(User, pair.uid), '123456')
    finally:
        event.remove(db.engine, 'after_cursor_execute', fail)
    assert PC.get_financial_snapshot(pair.uid) == before
    assert history(pair) == revisions
    assert MutationReceipt.query.count() == receipts


def test_audit_reads_and_metadata_revisions_do_not_change_accounting(pair):
    buy(pair, pair.a, '100', 1)
    pair.svc.transaction_service.add_transaction(pair.a, 'Sell', 'BTC', D('110'), D('1'), D('0'), date=day(2))
    pair.svc.transaction_service.add_dividend(pair.a, 'BTC', D('10'), day(2))
    transfer(pair)
    before = PC.get_financial_snapshot(pair.uid)
    pair.svc.portfolio_service.rename_portfolio(pair.a, 'Renamed')
    # Snapshot labels change, but every financial total remains identical.
    assert PC.get_financial_snapshot(pair.uid).totals == before.totals
    assert before.totals['net_internal_transfers'] == D('0')
    for pid in (pair.a, pair.b):
        assert pair.svc.portfolio_service.cash_account.ledger(pid).closing_cash == PC.get_portfolio_snapshot(pid, user_id=pair.uid).cash_balance
    assert history(pair)
    assert PC.get_financial_snapshot(pair.uid).totals == before.totals
