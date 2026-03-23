"""Forms for authentication: login, register, change password,
forgot password, and reset password.
"""

import re
from typing import Callable, Optional
from portfolio_app.forms.base_form import BaseForm

# Simple email pattern — rejects obvious non-emails without being overly strict.
_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


class LoginForm(BaseForm):
    """Form for user login."""

    def validate(self) -> bool:
        username = self._validate_required_string('username', 'Username is required.')
        if username:
            self.cleaned_data['username'] = username

        password = self._validate_required_string('password', 'Password is required.')
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
        username = self._validate_required_string('username', 'Username is required.')
        if username:
            if len(username) < 3:
                self.errors['username'] = 'Username must be at least 3 characters.'
            elif len(username) > 80:
                self.errors['username'] = 'Username cannot exceed 80 characters.'
            elif not all(c.isalpha() or c == '_' for c in username):
                self.errors['username'] = 'Only letters and underscores are allowed.'
            elif self.check_username_taken and self.check_username_taken(username):
                self.errors['username'] = 'This username is already taken.'
            else:
                self.cleaned_data['username'] = username

        # --- Email ---
        email = self._validate_required_string('email', 'Email address is required.')
        if email:
            email = email.lower()
            if not _EMAIL_RE.match(email):
                self.errors['email'] = 'Please enter a valid email address.'
            elif len(email) > 120:
                self.errors['email'] = 'Email address is too long.'
            elif self.check_email_taken and self.check_email_taken(email):
                self.errors['email'] = 'An account with this email already exists.'
            else:
                self.cleaned_data['email'] = email

        # --- Password ---
        password = self._validate_required_string('password', 'Password is required.')
        if password:
            if len(password) < 8:
                self.errors['password'] = 'Password must be at least 8 characters.'
            else:
                self.cleaned_data['password'] = password

        # --- Confirm password ---
        confirm = self._validate_required_string('confirm_password', 'Please confirm your password.')
        if confirm and password and not self.errors.get('password'):
            if confirm != password:
                self.errors['confirm_password'] = 'Passwords do not match.'
            else:
                self.cleaned_data['confirm_password'] = confirm

        return not self.has_errors()


class ChangePasswordForm(BaseForm):
    """Form for changing a logged-in user's password."""

    def validate(self) -> bool:
        current = self._validate_required_string('current_password', 'Current password is required.')
        if current:
            self.cleaned_data['current_password'] = current

        new_password = self._validate_required_string('new_password', 'New password is required.')
        if new_password:
            if len(new_password) < 8:
                self.errors['new_password'] = 'New password must be at least 8 characters.'
            else:
                self.cleaned_data['new_password'] = new_password

        confirm = self._validate_required_string('confirm_new_password', 'Please confirm your new password.')
        if confirm and new_password and not self.errors.get('new_password'):
            if confirm != new_password:
                self.errors['confirm_new_password'] = 'Passwords do not match.'
            else:
                self.cleaned_data['confirm_new_password'] = confirm

        return not self.has_errors()


class ForgotPasswordForm(BaseForm):
    """Form for requesting a password reset email."""

    def validate(self) -> bool:
        email = self._validate_required_string('email', 'Email address is required.')
        if email:
            email = email.lower()
            if not _EMAIL_RE.match(email):
                self.errors['email'] = 'Please enter a valid email address.'
            else:
                self.cleaned_data['email'] = email

        return not self.has_errors()


class ResetPasswordForm(BaseForm):
    """Form for setting a new password via a reset token."""

    def validate(self) -> bool:
        password = self._validate_required_string('password', 'Password is required.')
        if password:
            if len(password) < 8:
                self.errors['password'] = 'Password must be at least 8 characters.'
            else:
                self.cleaned_data['password'] = password

        confirm = self._validate_required_string('confirm_password', 'Please confirm your password.')
        if confirm and password and not self.errors.get('password'):
            if confirm != password:
                self.errors['confirm_password'] = 'Passwords do not match.'
            else:
                self.cleaned_data['confirm_password'] = confirm

        return not self.has_errors()
