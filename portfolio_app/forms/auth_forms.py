"""Forms for passwordless authentication and account security."""

import re

from portfolio_app.forms.base_form import BaseForm
from portfolio_app.utils.messages import MESSAGES


_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


class EmailForm(BaseForm):
    """Validate and normalize the email-first authentication input."""

    def validate(self) -> bool:
        email = self._validate_required_string('email', MESSAGES['EMAIL_REQUIRED'])
        if email:
            email = email.lower()
            if not _EMAIL_RE.match(email):
                self.errors['email'] = MESSAGES['EMAIL_INVALID']
            elif len(email) > 120:
                self.errors['email'] = MESSAGES['EMAIL_TOO_LONG']
            else:
                self.cleaned_data['email'] = email
        return not self.has_errors()


class LoginForm(EmailForm):
    """Compatibility name for the one email-first entry form."""


class VerifyCodeForm(BaseForm):
    """Validate a six-digit one-time code."""

    def validate(self) -> bool:
        code = self._validate_required_string(
            'code', MESSAGES['VERIFICATION_CODE_REQUIRED'],
        )
        if code:
            code = code.strip()
            if not code.isdigit() or len(code) != 6:
                self.errors['code'] = MESSAGES['VERIFICATION_CODE_INVALID_FORMAT']
            else:
                self.cleaned_data['code'] = code
        return not self.has_errors()


class UpdateEmailForm(EmailForm):
    """Validate a proposed replacement email address."""
