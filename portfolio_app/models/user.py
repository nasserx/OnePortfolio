"""User model for authentication."""

from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from portfolio_app import db


class User(UserMixin, db.Model):
    """User model with Flask-Login integration."""

    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    # False until the user enters the 6-digit verification code sent to their email
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime, nullable=True)

    # One-time 6-digit verification code for registration / email update
    verification_code = db.Column(db.String(6), nullable=True)
    verification_code_expires_at = db.Column(db.DateTime, nullable=True)

    # Pending email change — stored here until OTP is confirmed, then moved to email
    pending_email = db.Column(db.String(120), nullable=True)

    # Separate OTP for account deletion — avoids conflicts with verification_code
    deletion_code = db.Column(db.String(6), nullable=True)
    deletion_code_expires_at = db.Column(db.DateTime, nullable=True)

    # Relationship: one user owns many funds
    funds = db.relationship('Fund', backref='owner', lazy='dynamic')

    def set_password(self, password: str) -> None:
        """Hash and store password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verify password against stored hash."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f'<User {self.username}>'
