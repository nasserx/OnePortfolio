# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the development server
python app.py                          # localhost:5000, debug=True

# Run tests
pytest -v                              # All tests
pytest -v test_app.py::test_name       # Single test

# Production entry point (PythonAnywhere)
wsgi.py                                # Creates application = create_app()
```

No linting config is configured. CI runs on Python 3.8, 3.10, 3.12 via `.github/workflows/ci.yml`.

## Architecture

The app follows a layered clean architecture pattern:

```
Routes (Blueprints) → Services → Repositories → Models (SQLAlchemy)
        ↓                ↓
   Forms (validation)  Calculators (financial math)
```

### Dependency Injection via `g`

`portfolio_app/services/factory.py` is the DI container. Call `get_services()` in any route to get a `Services` instance cached in Flask's `g` for the current request. All repos and services are instantiated once per request with `user_id` context. Routes never instantiate services directly.

```python
svc = get_services()
svc.portfolio_service.create_portfolio(...)
svc.transaction_service.add_transaction(...)
```

### Models → Tables

The DB schema has been through several renames (tracked in migrations). Current model names:
- `Portfolio` (table: `portfolio`, formerly `fund`, formerly `capital`) — cash balance, belongs to User (`user_id` is NOT NULL with `ON DELETE CASCADE`)
- `PortfolioEvent` (table: `portfolio_event`) — Deposit/Withdrawal/Initial events
- `Transaction` — Buy/Sell with calculated `net_amount`
- `Symbol` — tracked ticker per portfolio (table: `symbol`, formerly `asset`)
- `Dividend` — income per symbol

Realized P&L is **computed dynamically** from `Transaction` rows (average-cost method) — there is no snapshot table. The previous `ClosedTrade` table was removed because its rows orphaned under SQLite's default FK-OFF mode and surfaced as ghost profit after deletions.

### Migrations

`portfolio_app/__init__.py` → `_run_migrations()` runs on every app startup before `db.create_all()`. All 24+ steps are idempotent (check column/table existence via SQLAlchemy inspector before altering). Never delete migration steps — add new ones at the end. SQLite FK enforcement is disabled for the duration of the migration (some legacy tables had stale FK targets from the `capital → fund → portfolio` rename chain) and re-enabled before the connection returns to the pool. An engine-connect listener (`_enable_sqlite_foreign_keys`) keeps `PRAGMA foreign_keys=ON` for all subsequent connections.

### Forms

Custom form base class in `portfolio_app/forms/base_form.py` (not Flask-WTF). `validate()` populates `self.errors` (dict) and `self.cleaned_data`. Flask-WTF is only used for CSRF tokens.

### Calculators

`PortfolioCalculator` (static methods) handles:
- Average cost method (ACM) on buys
- Cash balance = deposits − withdrawals − buys + sells + dividends
- Realized P&L computed on demand by walking the transactions table per symbol (no snapshot)
- Category/asset-class summary for dashboard cards

`TransactionManager` creates `Transaction` objects with computed `net_amount`.

## Frontend

**Templates:** `base.html` is the shell (sidebar, topbar, theme toggle). All pages extend it. Auth pages extend `auth_base.html`.

**`static/js/main.js`** exports one `InvestmentPortfolioApp` class initialized on `DOMContentLoaded`. Key internal classes:
- `FormValidator` — declarative rules-based client-side validation (replaces HTML5 native validation)
- `ModalAjaxHandler` — modal form submissions via AJAX; on success stores message in `sessionStorage` and reloads; on error shows inline field errors
- `AlertManager` — auto-dismisses server-rendered alerts (3s success, 6s error); picks up pending AJAX alerts from `sessionStorage`
- `DecimalInputHandler` — sanitizes decimal inputs, disables spinner/wheel
- `TransactionFormHandler` — dynamic Buy/Sell cost preview

Modal AJAX routes return JSON: `{success: bool, message: str, error: str}`. Field errors are matched to inputs by message content.

## Environment Variables

```bash
SECRET_KEY=<secrets.token_hex(32)>
EMAIL_USER=<gmail address>
EMAIL_PASSWORD=<gmail app password>
APP_BASE_URL=https://yourapp.pythonanywhere.com
DATABASE_URL=sqlite:///portfolio.db     # optional, defaults to sqlite
SESSION_COOKIE_SECURE=1                 # HTTPS production only
DEV_AUTO_LOGIN=1                        # dev only — auto-login as first user
```

## Key Conventions

- `PortfolioRepository` filters all queries by `user_id`. Other repositories filter by `portfolio_id`; ownership is enforced transitively by services calling `portfolio_repo.get_by_id()` first.
- `recalculate_all_averages_for_symbol()` updates each transaction's `average_cost` and `net_amount` after add/edit/delete — no snapshot writes
- Flash messages for full-page forms; `sessionStorage` + page reload for AJAX modal forms
- `Utils.escapeHtml()` must be used before inserting any user-provided string into the DOM via JS
- Decimal arithmetic uses Python's `Decimal` type throughout the backend; `decimal_utils.py` has helpers
