"""User model for authentication."""

import hashlib
from datetime import datetime, timezone
import bcrypt
from flask_login import UserMixin
from werkzeug.security import check_password_hash
from portfolio_app import db


# bcrypt cost factor. 12 ≈ ~250ms/hash on commodity hardware (2026).
# Spec requires a minimum of 10.
_BCRYPT_ROUNDS = 12


def _prehash(password: str) -> bytes:
    """SHA-256 the password before bcrypt so passwords > 72 bytes don't get
    silently truncated by bcrypt's 72-byte input cap.

    Returned as raw bytes (32 bytes), well within bcrypt's limit.
    """
    return hashlib.sha256(password.encode('utf-8')).digest()


class User(UserMixin, db.Model):
    """User model with Flask-Login integration.

    Passwords are stored as bcrypt hashes. Legacy werkzeug PBKDF2 hashes
    (from before the bcrypt switch) are still accepted on verification and
    transparently rehashed to bcrypt the next time the user logs in.
    """

    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime, nullable=True)

    verification_code = db.Column(db.String(6), nullable=True)
    verification_code_expires_at = db.Column(db.DateTime, nullable=True)
    # Number of consecutive bad-OTP attempts on the pending-email-update flow.
    # Reset on success or when a new code is generated; the code is wiped
    # after MAX_OTP_ATTEMPTS failures so the user must request a fresh one.
    verification_code_failed_attempts = db.Column(db.Integer, default=0, nullable=False)

    pending_email = db.Column(db.String(120), nullable=True)

    deletion_code = db.Column(db.String(6), nullable=True)
    deletion_code_expires_at = db.Column(db.DateTime, nullable=True)
    # Same lockout idea for the account-deletion OTP.
    deletion_code_failed_attempts = db.Column(db.Integer, default=0, nullable=False)

    # Brute-force protection: tracks consecutive failed login attempts and
    # the wall-clock time until which the account is locked. Reset on any
    # successful authentication.
    failed_login_attempts = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)

    # Single-use password-reset token id. Set by ``begin_password_reset``,
    # included inside the signed reset URL, and cleared on a successful
    # reset so the same link can never be used twice — even within the
    # itsdangerous 1-hour window.
    password_reset_jti = db.Column(db.String(32), nullable=True)

    portfolios = db.relationship(
        'Portfolio',
        backref='owner',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )
    oauth_identities = db.relationship(
        'OAuthIdentity',
        backref='user',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )

    def set_password(self, password: str) -> None:
        """Hash and store ``password`` using bcrypt over a SHA-256 prehash."""
        salted = bcrypt.hashpw(
            _prehash(password),
            bcrypt.gensalt(rounds=_BCRYPT_ROUNDS),
        )
        self.password_hash = salted.decode('utf-8')

    def check_password(self, password: str) -> bool:
        """Verify ``password`` against the stored hash.

        Accepts three formats so accounts keep working across upgrades:
          * bcrypt over SHA-256 prehash (current scheme — no truncation).
          * bcrypt over the raw password (pre-prehash bcrypt hashes).
          * werkzeug PBKDF2 (oldest legacy hashes).

        After a successful match against either legacy format,
        :meth:`needs_rehash` returns True so the caller can transparently
        upgrade the stored hash to the prehashed scheme on next login.
        """
        # Marker consumed by needs_rehash() — set inside this method only.
        self._needs_rehash_after_check = False

        if not self.password_hash:
            return False
        stored = self.password_hash

        if stored.startswith('$2'):
            # Try the prehashed format first (current scheme).
            try:
                if bcrypt.checkpw(_prehash(password), stored.encode('utf-8')):
                    return True
            except ValueError:
                pass
            # Fall back to legacy plain-bcrypt — match means we should
            # transparently upgrade to prehashed on the next set_password.
            try:
                if bcrypt.checkpw(password.encode('utf-8'), stored.encode('utf-8')):
                    self._needs_rehash_after_check = True
                    return True
            except ValueError:
                return False
            return False

        # Werkzeug PBKDF2 hash (oldest legacy).
        try:
            if check_password_hash(stored, password):
                self._needs_rehash_after_check = True
                return True
            return False
        except Exception:
            return False

    def needs_rehash(self) -> bool:
        """Return True if the most recent successful :meth:`check_password`
        matched a legacy hash format and the stored hash should be upgraded."""
        return getattr(self, '_needs_rehash_after_check', False)

    def is_locked(self, now: datetime = None) -> bool:
        """Return True if the account is currently locked out from logging in."""
        if not self.locked_until:
            return False
        moment = now or datetime.now(timezone.utc)
        # SQLite drops the tzinfo on round-trip; assume UTC for comparison.
        locked_at = self.locked_until
        if locked_at.tzinfo is None:
            locked_at = locked_at.replace(tzinfo=timezone.utc)
        return moment < locked_at

    def __repr__(self) -> str:
        return f'<User {self.username}>'
