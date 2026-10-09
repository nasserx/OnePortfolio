"""Existing route tests submit fresh signed form intents like rendered forms.

Integrity tests use auto_mutation_tokens=False to exercise missing, replayed
and stale tokens explicitly. This changes test clients only, never validation.
"""

from flask.testing import FlaskClient


class MutationClient(FlaskClient):
    auto_mutation_tokens = True

    def open(self, *args, **kwargs):
        path = args[0] if args and isinstance(args[0], str) else kwargs.get('path', '')
        protected = path.startswith(('/transactions/', '/portfolios/')) or path == '/settings/delete/verify'
        if self.auto_mutation_tokens and kwargs.get('method', '').upper() == 'POST' and protected:
            data = kwargs.get('data') or {}
            if isinstance(data, dict) and 'mutation_token' not in data:
                with self.session_transaction() as state:
                    identity = state.get('_user_id', '')
                if identity:
                    from portfolio_app.utils.mutation_requests import issue_mutation_token
                    from flask import g
                    with self.application.test_request_context():
                        g.pop('_mutation_revisions', None)
                        user = self.application.login_manager._user_callback(identity)
                        if user is not None:
                            token = issue_mutation_token(user.id)
                            kwargs['data'] = {**data, 'mutation_token': token}
        return super().open(*args, **kwargs)
