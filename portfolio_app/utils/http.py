"""HTTP utility functions for AJAX request handling."""

from flask import request, jsonify


def is_ajax_request():
    """Check if request is AJAX/modal request."""
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json


def json_response(success, message=None, error=None, errors=None, **kwargs):
    """Create JSON response for AJAX requests.

    Args:
        success: True for 2xx, False for 4xx.
        message: optional success message (for the toast on reload).
        error: legacy single-string error — still accepted but new code
            should prefer ``errors`` so the client can place each message
            on its own input.
        errors: structured ``{field_name: msg, '__all__': msg}`` dict.
            ``__all__`` is rendered as a modal-level banner; the rest go
            inline under their respective fields.
    """
    response_data = {'success': success}
    if message:
        response_data['message'] = message
    if errors:
        response_data['errors'] = errors
    if error:
        response_data['error'] = error
    response_data.update(kwargs)
    status_code = 200 if success else 400
    return jsonify(response_data), status_code
