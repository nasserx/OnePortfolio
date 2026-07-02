# Architecture

OnePortfolio is a Flask application built around an application factory and layered request handling.

## Application Factory

`portfolio_app/__init__.py` defines `create_app(config_class=Config)`. The factory loads configuration, initializes extensions, registers blueprints, wires context processors and error handlers, calls the SQLite migration runner in `portfolio_app/migrations.py`, and creates missing tables.

The same factory is used by `app.py`, `wsgi.py`, and tests.

## Request Layers

The main application flow is:

`Routes -> Services -> Repositories -> Models`

Supporting layers:

- **Forms** validate request data and normalize user input.
- **Calculators** perform financial calculations from persisted records.
- **Templates** render the current state.

Routes should stay thin: they parse HTTP concerns, call forms/services/calculators, and select templates or JSON responses.

## Services Container

`portfolio_app/services/factory.py` provides a `Services` container. Routes call `get_services()`, which stores one container per request on Flask `g`.

The container creates repositories and services with the current `user_id`, so each request gets a consistent scoped set of collaborators.

## Repositories and User Scoping

Repositories wrap database access. User-owned records are scoped through `Portfolio.user_id`; repository reads that accept ids should return nothing when the id does not belong to the current user.

This is a core safety property. Service and route code should avoid bypassing repositories for user-scoped mutations unless it preserves the same scoping.

## Models

Models live in `portfolio_app/models/`:

- `User`: accounts, password hash, admin flag, lockout state.
- `PendingRegistration`: staged signup and verification code state.
- `Portfolio`: user-owned portfolio bucket.
- `PortfolioEvent`: capital entries.
- `Symbol`: tracked asset symbol per portfolio.
- `Transaction`: buy/sell asset entries.
- `Dividend`: current model name for income records.

The user-facing term is Income even though the model is still named `Dividend`.

## Calculators

`portfolio_app/calculators/portfolio_calculator.py` is the database-facing calculator facade. It derives totals from source records:

- total capital
- total cash
- positions
- book value
- realized P&L
- total income
- return amount and return percent
- asset-level summaries

`portfolio_app/calculators/financial_math.py` contains pure deterministic financial calculations, including Average Cost Method transaction-list math and return percentage/display math. It has no Flask, SQLAlchemy, repository, service, or model dependency.

Calculators should use `Decimal` for financial math and should not introduce cached financial totals without a clear invalidation strategy.

## Forms

Forms live in `portfolio_app/forms/`. They validate request payloads for auth, portfolios, capital entries, assets, asset entries, and income. They also normalize common inputs before service code receives them.

## Main Data Flow

Typical asset-entry creation:

1. Route receives POST data.
2. Form validates and cleans fields.
3. Route calls `TransactionService`.
4. Service checks ownership, cash, quantity, chronology, and business rules.
5. Repository/model changes are written.
6. Calculator recomputes average costs where needed.
7. Route returns JSON or redirects.

Overview and chart pages read records through scoped services/repositories, then call calculator/chart helpers to build display data.

## Templates, Static Files, and Tokens

Templates live in `portfolio_app/templates/`. Static files live in `portfolio_app/static/`.

`portfolio_app/static/css/tokens.css` is the primary design-token source. `style.css` and page templates consume those tokens. JavaScript is mostly in `portfolio_app/static/js/main.js`, with chart-specific JavaScript embedded in the charts template.

See [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) for UI constraints.

## Important Files

- `portfolio_app/__init__.py`: application factory and app-level wiring.
- `portfolio_app/migrations.py`: SQLite schema migration runner and migration steps.
- `config.py`: environment-driven configuration.
- `portfolio_app/services/factory.py`: per-request services container.
- `portfolio_app/services/transaction_service.py`: asset entries, income, symbols, chronology, and cash/quantity rules.
- `portfolio_app/services/portfolio_service.py`: portfolios and capital entries.
- `portfolio_app/calculators/portfolio_calculator.py`: database-backed financial aggregation.
- `portfolio_app/calculators/financial_math.py`: pure financial math.
- `portfolio_app/routes/`: HTTP endpoints.
- `tests/`: regression and behavior tests.

## Architectural Risks

- `portfolio_app/__init__.py` is large because it still contains app wiring, extension setup, error handlers, security headers, and blueprint registration.
- `PortfolioCalculator` is large because it owns portfolio, asset, cash, and return calculations.
- `TransactionService` is large because it coordinates asset entries, income, symbols, validations, and recalculation.

Safe future work should define boundaries first, add tests around existing behavior, then move one responsibility at a time. Avoid broad rewrites that mix behavior changes with file movement.
