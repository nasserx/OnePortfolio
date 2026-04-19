"""History blueprint - Unified activity log for all portfolio operations."""

import logging
from datetime import datetime
from flask import Blueprint, render_template, request
from flask_login import login_required
from portfolio_app.models.fund_event import FundEvent
from portfolio_app.models.transaction import Transaction
from portfolio_app.services import get_services

logger = logging.getLogger(__name__)

history_bp = Blueprint('history', __name__)

VALID_TABS = ('all', 'deposit', 'withdrawal', 'buy', 'sell')


def _parse_date(date_str, end_of_day=False):
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str.strip(), '%Y-%m-%d')
        if end_of_day:
            dt = dt.replace(hour=23, minute=59, second=59)
        return dt
    except ValueError:
        return None


def _normalize_type(event_type):
    """Map 'Initial' to 'Deposit' for display — users see no distinction."""
    return 'Deposit' if event_type == 'Initial' else event_type


def _build_entries(fund_ids, fund_by_id, from_dt, to_dt):
    """Fetch and normalize all FundEvents + Transactions within filters."""
    entries = []

    # ── FundEvents (Deposit / Withdrawal / Initial) ───────────────────
    if fund_ids:
        eq = FundEvent.query.filter(FundEvent.fund_id.in_(fund_ids))
        if from_dt:
            eq = eq.filter(FundEvent.date >= from_dt)
        if to_dt:
            eq = eq.filter(FundEvent.date <= to_dt)

        for ev in eq.all():
            fund = fund_by_id.get(ev.fund_id)
            entries.append({
                'source':     'event',
                'id':         ev.id,
                'type':       _normalize_type(ev.event_type),
                'fund_id':    ev.fund_id,
                'fund_name':  fund.name if fund else '',
                'symbol':     None,
                'quantity':   None,
                'price':      None,
                'amount':     abs(float(ev.amount_delta)),
                'fees':       None,
                'date':       ev.date,
                'date_short': ev.date_short,
                'notes':      ev.notes or '',
            })

    # ── Transactions (Buy / Sell) ─────────────────────────────────────
    if fund_ids:
        tq = Transaction.query.filter(Transaction.fund_id.in_(fund_ids))
        if from_dt:
            tq = tq.filter(Transaction.date >= from_dt)
        if to_dt:
            tq = tq.filter(Transaction.date <= to_dt)

        for tx in tq.all():
            fund = fund_by_id.get(tx.fund_id)
            entries.append({
                'source':     'transaction',
                'id':         tx.id,
                'type':       tx.transaction_type,
                'fund_id':    tx.fund_id,
                'fund_name':  fund.name if fund else '',
                'symbol':     (tx.symbol or '').upper(),
                'quantity':   float(tx.quantity),
                'price':      float(tx.price),
                'amount':     float(tx.net_amount),
                'fees':       float(tx.fees),
                'date':       tx.date,
                'date_short': tx.date_short,
                'notes':      tx.notes or '',
            })

    entries.sort(key=lambda x: x['date'] or datetime.min, reverse=True)
    return entries


def _tab_counts(entries):
    counts = {'all': 0, 'deposit': 0, 'withdrawal': 0, 'buy': 0, 'sell': 0}
    for e in entries:
        counts['all'] += 1
        t = e['type'].lower()
        if t in counts:
            counts[t] += 1
    return counts


@history_bp.route('/history')
@login_required
def history_list():
    """Unified history page for all portfolio operations."""
    svc = get_services()
    funds = svc.fund_repo.get_all()
    fund_by_id = {f.id: f for f in funds}

    # ── Filters ───────────────────────────────────────────────────────
    raw_portfolio = request.args.get('portfolio', '').strip()
    raw_from      = request.args.get('from', '').strip()
    raw_to        = request.args.get('to', '').strip()
    tab           = request.args.get('tab', 'all').lower()
    if tab not in VALID_TABS:
        tab = 'all'

    # Portfolio filter
    selected_fund_id = None
    if raw_portfolio:
        try:
            pid = int(raw_portfolio)
            if pid in fund_by_id:
                selected_fund_id = pid
        except ValueError:
            pass

    target_ids = [selected_fund_id] if selected_fund_id else [f.id for f in funds]

    from_dt = _parse_date(raw_from)
    to_dt   = _parse_date(raw_to, end_of_day=True)

    # ── Data ──────────────────────────────────────────────────────────
    all_entries = _build_entries(target_ids, fund_by_id, from_dt, to_dt)
    counts      = _tab_counts(all_entries)

    tab_filters = {
        'all':        lambda e: True,
        'deposit':    lambda e: e['type'] == 'Deposit',
        'withdrawal': lambda e: e['type'] == 'Withdrawal',
        'buy':        lambda e: e['type'] == 'Buy',
        'sell':       lambda e: e['type'] == 'Sell',
    }
    entries = [e for e in all_entries if tab_filters[tab](e)]

    return render_template(
        'history.html',
        funds=funds,
        entries=entries,
        counts=counts,
        tab=tab,
        selected_fund_id=selected_fund_id,
        raw_from=raw_from,
        raw_to=raw_to,
    )
