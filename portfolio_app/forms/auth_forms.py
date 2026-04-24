"""Forms for authentication: login, register, change password,
forgot password, and reset password.
"""

import re
from typing import Callable, Optional
from portfolio_app.forms.base_form import BaseForm
from portfolio_app.utils.messages import MESSAGES

# Simple email pattern — rejects obvious non-emails without being overly strict.
_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


class LoginForm(BaseForm):
    """Form for user login."""

    def validate(self) -> bool:
        username = self._validate_required_string('username', MESSAGES['USERNAME_REQUIRED'])
        if username:
            self.cleaned_data['username'] = username

        password = self._validate_required_string('password', MESSAGES['PASSWORD_REQUIRED'])
        if password:
            self.cleaned_data['password'] = password

        return not self.has_errors()


class RegisterForm(BaseForm):
    """Form for new user registration."""

    def __init__(
        self,
        data: dict,
        check_username_taken: Optional[Callable[[str], bool]] = None,
        check_email_taken: Optional[Callable[[str], bool]] = None,
    ):
        super().__init__(data)
        self.check_username_taken = check_username_taken
        self.check_email_taken = check_email_taken

    def validate(self) -> bool:
        # --- Username ---
        username = self._validate_required_string('username', MESSAGES['USERNAME_REQUIRED'])
        if username:
            if len(username) < 3:
                self.errors['username'] = MESSAGES['USERNAME_TOO_SHORT']
            elif len(username) > 80:
                self.errors['username'] = MESSAGES['USERNAME_TOO_LONG']
            elif not all(c.isalpha() or c == '_' for c in username):
                self.errors['username'] = MESSAGES['USERNAME_INVALID_CHARS']
            elif self.check_username_taken and self.check_username_taken(username):
                self.errors['username'] = MESSAGES['USERNAME_TAKEN']
            else:
                self.cleaned_data['username'] = username

        # --- Email ---
        email = self._validate_required_string('email', MESSAGES['EMAIL_REQUIRED'])
        if email:
            email = email.lower()
            if not _EMAIL_RE.match(email):
                self.errors['email'] = MESSAGES['EMAIL_INVALID']
            elif len(email) > 120:
                self.errors['email'] = MESSAGES['EMAIL_TOO_LONG']
            elif self.check_email_taken and self.check_email_taken(email):
                self.errors['email'] = MESSAGES['EMAIL_TAKEN']
            else:
                self.cleaned_data['email'] = email

        # --- Password ---
        password = self._validate_required_string('password', MESSAGES['PASSWORD_REQUIRED'])
        if password:
            if len(password) < 8:
                self.errors['password'] = MESSAGES['PASSWORD_TOO_SHORT']
            else:
                self.cleaned_data['password'] = password

        # --- Confirm password ---
        confirm = self._validate_required_string('confirm_password', MESSAGES['PASSWORD_CONFIRM_REQUIRED'])
        if confirm and password and not self.errors.get('password'):
            if confirm != password:
                self.errors['confirm_password'] = MESSAGES['PASSWORDS_NO_MATCH']
            else:
                self.cleaned_data['confirm_password'] = confirm

        return not self.has_errors()


class ChangePasswordForm(BaseForm):
    """Form for changing a logged-in user's password."""

    def validate(self) -> bool:
        current = self._validate_required_string('current_password', MESSAGES['CURRENT_PASSWORD_REQUIRED'])
        if current:
            self.cleaned_data['current_password'] = current

        new_password = self._validate_required_string('new_password', MESSAGES['NEW_PASSWORD_REQUIRED'])
        if new_password:
            if len(new_password) < 8:
                self.errors['new_password'] = MESSAGES['NEW_PASSWORD_TOO_SHORT']
            else:
                self.cleaned_data['new_password'] = new_password

        confirm = self._validate_required_string('confirm_new_password', MESSAGES['NEW_PASSWORD_CONFIRM_REQUIRED'])
        if confirm and new_password and not self.errors.get('new_password'):
            if confirm != new_password:
                self.errors['confirm_new_password'] = MESSAGES['PASSWORDS_NO_MATCH']
            else:
                self.cleaned_data['confirm_new_password'] = confirm

        return not self.has_errors()


class ForgotPasswordForm(BaseForm):
    """Form for requesting a password reset email."""

    def validate(self) -> bool:
        email = self._validate_required_string('email', MESSAGES['EMAIL_REQUIRED'])
        if email:
            email = email.lower()
            if not _EMAIL_RE.match(email):
                self.errors['email'] = MESSAGES['EMAIL_INVALID']
            else:
                self.cleaned_data['email'] = email

        return not self.has_errors()


class ResetPasswordForm(BaseForm):
    """Form for setting a new password via a reset token."""

    def validate(self) -> bool:
        password = self._validate_required_string('password', MESSAGES['PASSWORD_REQUIRED'])
        if password:
            if len(password) < 8:
                self.errors['password'] = MESSAGES['PASSWORD_TOO_SHORT']
            else:
                self.cleaned_data['password'] = password

        confirm = self._validate_required_string('confirm_password', MESSAGES['PASSWORD_CONFIRM_REQUIRED'])
        if confirm and password and not self.errors.get('password'):
            if confirm != password:
                self.errors['confirm_password'] = MESSAGES['PASSWORDS_NO_MATCH']
            else:
                self.cleaned_data['confirm_password'] = confirm

        return not self.has_errors()


class VerifyCodeForm(BaseForm):
    """Form for entering a 6-digit OTP code (verification or deletion confirmation)."""

    def validate(self) -> bool:
        code = self._validate_required_string('code', MESSAGES['VERIFICATION_CODE_REQUIRED'])
        if code:
            code = code.strip()
            if not code.isdigit() or len(code) != 6:
                self.errors['code'] = MESSAGES['VERIFICATION_CODE_INVALID_FORMAT']
            else:
                self.cleaned_data['code'] = code

        return not self.has_errors()


class ConfirmDeletionForm(VerifyCodeForm):
    """Alias of VerifyCodeForm used for account deletion OTP confirmation."""


class UpdateEmailForm(BaseForm):
    """Form for updating the logged-in user's email address."""

    def __init__(
        self,
        data: dict,
        check_email_taken: Optional[Callable[[str], bool]] = None,
    ):
        super().__init__(data)
        self.check_email_taken = check_email_taken

    def validate(self) -> bool:
        # --- New email ---
        email = self._validate_required_string('email', MESSAGES['EMAIL_REQUIRED'])
        if email:
            email = email.lower()
            if not _EMAIL_RE.match(email):
                self.errors['email'] = MESSAGES['EMAIL_INVALID']
            elif len(email) > 120:
                self.errors['email'] = MESSAGES['EMAIL_TOO_LONG']
            elif self.check_email_taken and self.check_email_taken(email):
                self.errors['email'] = MESSAGES['EMAIL_IN_USE']
            else:
                self.cleaned_data['email'] = email

        # --- Password confirmation ---
        password = self._validate_required_string('password', MESSAGES['EMAIL_PASSWORD_CONFIRM_REQUIRED'])
        if password:
            self.cleaned_data['password'] = password

        return not self.has_errors()
