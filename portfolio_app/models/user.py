"""User model for authentication."""

from datetime import datetime, timezone
import bcrypt
from flask_login import UserMixin
from werkzeug.security import check_password_hash
from portfolio_app import db


# bcrypt cost factor. 12 ≈ ~250ms/hash on commodity hardware (2026).
# Spec requires a minimum of 10.
_BCRYPT_ROUNDS = 12


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

    pending_email = db.Column(db.String(120), nullable=True)

    deletion_code = db.Column(db.String(6), nullable=True)
    deletion_code_expires_at = db.Column(db.DateTime, nullable=True)

    # Brute-force protection: tracks consecutive failed login attempts and
    # the wall-clock time until which the account is locked. Reset on any
    # successful authentication.
    failed_login_attempts = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)

    portfolios = db.relationship(
        'Portfolio',
        backref='owner',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )

    def set_password(self, password: str) -> None:
        """Hash and store ``password`` using bcrypt."""
        salted = bcrypt.hashpw(
            password.encode('utf-8'),
            bcrypt.gensalt(rounds=_BCRYPT_ROUNDS),
        )
        self.password_hash = salted.decode('utf-8')

    def check_password(self, password: str) -> bool:
        """Verify ``password`` against the stored hash.

        Accepts both bcrypt hashes (current scheme) and legacy werkzeug
        PBKDF2 hashes (previous scheme), so existing accounts keep working
        across the upgrade. Use :meth:`needs_rehash` after a successful
        check to decide whether to upgrade the stored hash.
        """
        if not self.password_hash:
            return False
        stored = self.password_hash
        if stored.startswith('$2'):
            try:
                return bcrypt.checkpw(password.encode('utf-8'), stored.encode('utf-8'))
            except ValueError:
                return False
        # Legacy werkzeug hash: pbkdf2:..., scrypt:..., etc.
        try:
            return check_password_hash(stored, password)
        except Exception:
            return False

    def needs_rehash(self) -> bool:
        """Return True if the stored hash should be upgraded to bcrypt."""
        return not (self.password_hash or '').startswith('$2')

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
