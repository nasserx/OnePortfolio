# Architecture

OnePortfolio is a Flask application built around an application factory and layered request handling.

## Application Factory

`portfolio_app/__init__.py` defines `create_app(config_class=Config)`. The factory loads configuration, initializes extensions, conditionally registers the Google OAuth client foundation, registers blueprints, wires context processors and error handlers, calls the SQLite migration runner in `portfolio_app/migrations.py`, and creates missing tables.

The same factory is used by `app.py`, `wsgi.py`, and tests.

## Request Layers

The main application flow is:

`Routes -> Services -> Repositories -> Models`

Supporting layers:

- **Forms** validate request data and normalize user input.
- **Calculators** perform financial calculations from persisted records.
- **Templates** render the current state.

Routes should stay thin: they parse HTTP concerns, call forms/services/calculators, and select templates or JSON responses.

The Google OAuth backend uses Authlib and is disabled by default. When enabled with complete configuration, the app registers a Google OpenID Connect client during app creation. Authlib owns state, nonce, signature, issuer, audience, and expiry validation; the callback explicitly constrains the issuer to Google's accepted issuer identifiers and the audience to the configured client ID, and requires an ID token before consuming Authlib-produced userinfo. Transport-isolated real-Authlib contract tests protect that delegated boundary. The auth blueprint exposes backend login and callback routes for existing verified local accounts only. Previously linked Google identities resolve by provider plus Google's stable OpenID Connect `sub` claim. On first successful Google sign-in, a verified Google email may create one Google identity link for a matching verified local account.

`OAuthIdentity` stores the persistent provider-subject link. Automatic registration, manual account-management UI, unlinking, and OAuth token or provider-payload persistence are not implemented.

Flask-Login authentication uses the signed client-side Flask session and its signed remember cookie; individual sessions are not stored server-side. Each serialized login identity binds the user id to the database-backed `User.auth_generation`. A successful local password change or password reset increments that generation in the same database commit as the new password, so sessions and remember state issued for an earlier generation no longer authenticate on their next request. New local and Google OIDC logins use the current generation, and password changes do not alter stored OAuth identity links. Pre-generation id-only identities are treated explicitly as generation zero for upgrade compatibility and stop authenticating after the user's generation advances.

Public password-reset initiation is rate-limited both by client origin and by normalized target email before reset state is rotated or mail is sent. Known and unknown addresses retain the same public confirmation response. Flask-Limiter storage is selected through `RATELIMIT_STORAGE_URI`; its default `memory://` storage is authoritative only when one application process owns the counters, while multi-process deployments must provide a supported shared backend.

## Services Container

`portfolio_app/services/factory.py` provides a `Services` container. Routes call `get_services()`, which stores one container per request on Flask `g`.

The container creates repositories and services with the current `user_id`, so each request gets a consistent scoped set of collaborators.

## Repositories and User Scoping

Repositories wrap database access. User-owned records are scoped through `Portfolio.user_id`; repository reads that accept ids should return nothing when the id does not belong to the current user.

This is a core safety property. Service and route code should avoid bypassing repositories for user-scoped mutations unless it preserves the same scoping.

Application users manage their own accounts and tenant-scoped portfolio data. The public application exposes no privileged cross-user role; exceptional deployment or database maintenance is outside its authorization model.

## Models

Models live in `portfolio_app/models/`:

- `User`: accounts, password hash, authentication generation, and lockout state. Its legacy admin flag is runtime-inert pending schema cleanup.
- `PendingRegistration`: staged signup and verification code state.
- `OAuthIdentity`: external provider subject linked to a local user; no tokens or secrets.
- `Portfolio`: user-owned portfolio bucket.
- `PortfolioEvent`: capital entries.
- `Symbol`: tracked asset symbol per portfolio.
- `Transaction`: buy/sell asset entries.
- `Dividend`: current model name for income records.

Pending email-change claims are bounded by their verification-code lifetime.
Expired or incomplete pending-email state is non-reserving and is cleared when
an account workflow encounters it, so it cannot indefinitely hold an address.

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

Overview reads records through scoped services/repositories, then calls calculator helpers to build totals, portfolio summaries, and allocation chart data.

## Templates, Static Files, and Tokens

Templates live in `portfolio_app/templates/`. Static files live in `portfolio_app/static/`.

`portfolio_app/static/css/tokens.css` is the primary design-token source. `style.css` and page templates consume those tokens. JavaScript is mostly in `portfolio_app/static/js/main.js`; Overview chart rendering uses `portfolio_app/static/js/overview_charts.js`.

Third-party frontend assets use exact versions. Stable CDN scripts and
stylesheets loaded directly by production HTML carry SHA-384 Subresource
Integrity metadata and anonymous CORS mode. Bootstrap CSS remains an explicit
exception because `tokens.css` imports it into the `vendor` cascade layer;
Google Fonts responses are also not assigned fixed integrity values. The
enforced CSP uses one cryptographically random nonce per request for executable
inline scripts, with the same nonce present in the response header and rendered
script elements; script `unsafe-inline` is disabled and inline event-handler
attributes remain prohibited. Inline styles remain permitted for current UI
behavior. jsDelivr remains an explicit external-script trust boundary, with
intended directly loaded stable assets protected by the integrity metadata above.

See [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) for UI constraints.

## Important Files

- `portfolio_app/__init__.py`: application factory and app-level wiring.
- `portfolio_app/migrations.py`: SQLite schema migration runner and migration steps.
- `config.py`: environment-driven configuration.
- `portfolio_app/services/factory.py`: per-request services container.
- `portfolio_app/services/transaction_service.py`: asset entries, income, symbols, chronology, and cash/quantity rules.
- `portfolio_app/services/portfolio_service.py`: portfolios and capital entries.
- `portfolio_app/calculators/portfolio_calculator.py`: database-backed financial aggregation.
- `portfolio_app/calculators/allocation_charts.py`: Overview allocation chart data for By Book Value and By Capital.
- `portfolio_app/calculators/financial_math.py`: pure financial math.
- `portfolio_app/routes/`: HTTP endpoints.
- `tests/`: regression and behavior tests.

## Architectural Risks

- `portfolio_app/__init__.py` is large because it still contains app wiring, extension setup, error handlers, security headers, and blueprint registration.
- `PortfolioCalculator` is large because it owns portfolio, asset, cash, and return calculations.
- `TransactionService` is large because it coordinates asset entries, income, symbols, validations, and recalculation.

Safe future work should define boundaries first, add tests around existing behavior, then move one responsibility at a time. Avoid broad rewrites that mix behavior changes with file movement.
