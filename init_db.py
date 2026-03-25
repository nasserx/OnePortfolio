#!/usr/bin/env python3
"""
Database initialization script for production deployment.
Run this script once after deploying to create database tables and apply migrations.
"""

from portfolio_app import create_app, db
from portfolio_app.models import User, Fund, Transaction, Asset, FundEvent  # noqa: F401


def init_db():
    """Initialize the database with tables and migrations."""
    app = create_app()

    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        print("Applying migrations...")
        _run_migrations(app)
        print("Database initialization complete.")


def _run_migrations(app):
    """Apply incremental schema changes that SQLAlchemy create_all() cannot handle."""
    import sqlalchemy as sa
    with app.app_context():
        with db.engine.connect() as conn:
            inspector = sa.inspect(db.engine)

            capital_cols = {c['name'] for c in inspector.get_columns('capital')}

            # 1. Add user_id column if missing
            if 'user_id' not in capital_cols:
                print("Adding user_id column to capital table...")
                conn.execute(sa.text(
                    'ALTER TABLE capital ADD COLUMN user_id INTEGER REFERENCES "user"(id)'
                ))
                conn.commit()
                capital_cols.add('user_id')



if __name__ == '__main__':
    init_db()