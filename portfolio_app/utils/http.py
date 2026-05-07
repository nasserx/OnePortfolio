"""HTTP utility functions for AJAX request handling."""

from flask import request, jsonify


def is_ajax_request():
    """Check if request is AJAX/modal request."""
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json


def field_error_response(message, field_map, default_field='__all__'):
    """AJAX error response that places a service-layer message on its field.

    Service-layer ``ValueError`` / ``ValidationError`` messages (e.g.
    "Insufficient amount.", "Insufficient quantity.") originate from a
    specific business rule that ties to a specific input. The message
    itself doesn't carry that mapping, so each route declares which of
    its own input names a given message belongs to. Anything not in the
    map falls through to ``default_field`` (typically ``__all__``, which
    surfaces as a modal-level banner).
    """
    field = field_map.get(message, default_field)
    return json_response(False, errors={field: message})


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
