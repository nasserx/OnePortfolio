"""HTTP adapter: signed form intent, optimistic revision and durable replies.

No financial formulas live here. The same database transaction contains the
service operation and its receipt. Only successful operations consume tokens.
"""

import hashlib
import json
from functools import wraps
from secrets import token_hex

from flask import current_app, request, make_response, flash, redirect, url_for, g
from flask_login import current_user
from itsdangerous import URLSafeSerializer, BadSignature

from portfolio_app import db
from portfolio_app.models.mutation_receipt import MutationReceipt
from portfolio_app.models.user import User
from portfolio_app.services.mutation import mutation_transaction, current_revision, record_mutation
from portfolio_app.utils.messages import MESSAGES


CREATE_ENDPOINTS = frozenset({
    'transactions.transaction_add', 'transactions.dividend_add', 'transactions.symbol_add',
    'portfolios.portfolios_add', 'portfolios.portfolios_deposit', 'portfolios.portfolios_withdraw',
})


def _signer():
    return URLSafeSerializer(current_app.secret_key, salt='financial-mutation-v1')


def issue_mutation_token(user_id=None):
    uid = user_id if user_id is not None else current_user.id
    # One revision per rendered page, including all of its modal forms.
    cache = getattr(g, '_mutation_revisions', {})
    if uid not in cache:
        cache[uid] = current_revision(uid)
        g._mutation_revisions = cache
    return _signer().dumps({'user': uid, 'revision': cache[uid], 'key': token_hex(32)})


def _conflict(message):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return {'success': False, 'errors': {'__all__': message}}, 409
    flash(message, 'error')
    endpoint = ('auth.settings' if request.blueprint == 'auth' else
                'transactions.transaction_list' if request.blueprint == 'transactions' else
                'portfolios.portfolios_list')
    return redirect(url_for(endpoint))


def protected_submission(view):
    @wraps(view)
    def guarded(*args, **kwargs):
        if not current_user.is_authenticated:
            return view(*args, **kwargs)  # Existing login-required handling.
        try:
            intent = _signer().loads(request.form.get('mutation_token', ''))
            if intent['user'] != current_user.id or len(intent['key']) != 64:
                raise ValueError
        except (BadSignature, ValueError, TypeError, KeyError):
            return _conflict(MESSAGES['INVALID_REQUEST'])
        uid = current_user.id
        authenticated_identity = current_user.get_id()
        payload = [(key, request.form.getlist(key)) for key in sorted(request.form)
                   if key not in ('csrf_token', 'mutation_token')]
        digest = hashlib.sha256(json.dumps([request.path, payload], ensure_ascii=True).encode()).hexdigest()
        try:
            with mutation_transaction() as state:
                # Authentication happened before writer reservation. Recheck
                # the lifetime identity after reservation/expiration: deletion
                # and rowid reuse must not retarget an already-running request.
                account = db.session.get(User, uid)
                if (account is None or not account.is_verified
                        or account.get_id() != authenticated_identity):
                    return _conflict(MESSAGES['INVALID_REQUEST'])
                receipt = MutationReceipt.query.filter_by(user_id=uid, operation_key=intent['key']).first()
                if receipt:
                    if receipt.request_digest != digest:
                        return _conflict(MESSAGES['MUTATION_REUSED'])
                    saved = json.loads(receipt.response_json)
                    response = make_response(saved['body'], saved['status'])
                    for key, value in saved['headers'].items():
                        response.headers[key] = value
                    return response
                # Creates may coexist; updates/removals require the revision
                # seen when the page was rendered, including bulk deletions.
                is_create = request.endpoint in CREATE_ENDPOINTS or (
                    request.endpoint == 'portfolios.portfolios_transfer_save' and kwargs.get('transfer_id') is None)
                is_change = not is_create
                if is_change and intent['revision'] != current_revision(uid):
                    return _conflict(MESSAGES['MUTATION_STALE'])
                response = make_response(view(*args, **kwargs))
                if state['failed'] or not state['writes'] or response.status_code >= 400:
                    state['failed'] = True
                    return response
                # Whole-account deletion removes its receipts with the account;
                # a retry is unauthenticated and cannot perform another effect.
                if db.session.get(User, uid) is not None:
                    saved = json.dumps({'body': response.get_data(as_text=True), 'status': response.status_code,
                                        'headers': {key: response.headers[key] for key in
                                                    ('Content-Type', 'Location') if key in response.headers}})
                    record_mutation(uid, intent['key'], digest, saved)
                return response
        except Exception:
            current_app.logger.exception('Financial submission failed')
            return _conflict(MESSAGES['OPERATION_FAILED'])
    return guarded


def register_mutation_requests(app):
    app.jinja_env.globals['mutation_token'] = issue_mutation_token

    @app.before_request
    def capture_render_revision():
        # Capture BEFORE page data is read, never after it. Otherwise a writer
        # between data retrieval and template rendering could bless stale
        # fields with a newer revision. Concurrent writes after this capture
        # conservatively make the form stale, even if some reads see new data.
        if request.method == 'GET' and request.endpoint in (
            'transactions.transaction_list', 'portfolios.portfolios_list', 'auth.settings',
        ) and current_user.is_authenticated:
            g._mutation_revisions = {current_user.id: current_revision(current_user.id)}

    # All POSTs on the two financial blueprints, plus confirmed account removal.
    for rule in app.url_map.iter_rules():
        if 'POST' not in rule.methods or not (
            rule.endpoint.startswith(('transactions.', 'portfolios.')) or
            rule.endpoint == 'auth.delete_account_verify'
        ):
            continue
        view = app.view_functions[rule.endpoint]
        if not getattr(view, '_protected_submission', False):
            protected = protected_submission(view)
            protected._protected_submission = True
            app.view_functions[rule.endpoint] = protected
