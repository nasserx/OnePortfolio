"""Routes package - Clean blueprints using Services and Forms."""

from flask import Flask


def register_blueprints(app: Flask) -> None:
    """Register all blueprints with the Flask app.

    Args:
        app: Flask application instance
    """
    from portfolio_app.routes.dashboard import dashboard_bp
    from portfolio_app.routes.funds import funds_bp
    from portfolio_app.routes.transactions import transactions_bp
    from portfolio_app.routes.charts import charts_bp
    from portfolio_app.routes.history import history_bp
    from portfolio_app.routes.auth import auth_bp
    from portfolio_app.routes.admin import admin_bp

    # Register blueprints
    # Auth routes are at root level: /login, /register, /verify/<token>, etc.
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(funds_bp, url_prefix='/funds')
    app.register_blueprint(transactions_bp, url_prefix='/transactions')
    app.register_blueprint(history_bp)
    app.register_blueprint(charts_bp)


__all__ = ['register_blueprints']
