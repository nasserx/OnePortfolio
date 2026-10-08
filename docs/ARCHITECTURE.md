# Architecture

OnePortfolio is a Flask application built around an application factory and layered request handling.

## Application Factory

`portfolio_app/__init__.py` defines `create_app(config_class=Config)`. The factory loads configuration, initializes extensions, registers blueprints, wires context processors and error handlers, and calls `run_startup_schema()` in `portfolio_app/migrations.py`, which runs the migration pass and then creates missing tables inside one exclusive startup schema lock.

The same factory is used by `app.py`, `wsgi.py`, and tests.

## Request Layers

The main application flow is:

`Routes -> Services -> Repositories -> Models`

Supporting layers:

- **Forms** validate request data and normalize user input.
- **Calculators** perform financial calculations from persisted records.
- **Templates** render the current state.

Routes should stay thin: they parse HTTP concerns, call forms/services/calculators, and select templates or JSON responses.

Authentication is email plus a one-time code. `AuthService` stages new accounts
through `PendingRegistration` and owns persisted `AuthChallenge` records for
both existing and new email targets. Challenge digests are HMAC-bound to their
purpose and target; plaintext codes are never persisted. Login challenges
expire after 10 minutes, allow five failed attempts, rotate on resend, and are
claimed atomically for single-use verification. Request and verification routes
are rate-limited by both client origin and normalized email target and expose
generic responses for known and unknown addresses.

Flask-Login continues to use signed client-side Flask sessions; no server-side
session store or remember identity is used. Each serialized identity binds the
user id to `User.auth_generation`, which remains the global revocation source
of truth. The signed session also carries authentication issue, last-seen, and
recent-auth timestamps. Sessions fail closed without those timestamps, use a
rolling seven-day inactivity timeout, have a 30-day absolute lifetime, and
consider authentication recent for 15 minutes. Successful verification clears
pre-login session state before establishing the authenticated session.

Password and Google OAuth runtime routes are absent. Legacy password hashes,
reset/lockout columns, and `OAuthIdentity` rows remain inert for a short rollback
window; migration 35 advances every user's `auth_generation` so pre-cutover
sessions and remember identities cannot survive. Flask-Limiter storage is
selected through `RATELIMIT_STORAGE_URI`; its default `memory://` storage is
authoritative only when one application process owns the counters, while
multi-process deployments must provide a supported shared backend.

## Services Container

`portfolio_app/services/factory.py` provides a `Services` container. Routes call `get_services()`, which stores one container per request on Flask `g`.

The container creates repositories and services with the current `user_id`, so each request gets a consistent scoped set of collaborators.

## Repositories and User Scoping

Repositories wrap database access. User-owned records are scoped through `Portfolio.user_id`; repository reads that accept ids should return nothing when the id does not belong to the current user.

This is a core safety property. Service and route code should avoid bypassing repositories for user-scoped mutations unless it preserves the same scoping.

Application users manage their own accounts and tenant-scoped portfolio data. The public application exposes no privileged cross-user role; exceptional deployment or database maintenance is outside its authorization model.

## Models

Models live in `portfolio_app/models/`:

- `User`: accounts, authentication generation, inert rollback password/reset/lockout state, and pending account-security state. The legacy application-admin column has no model field and is dropped from upgraded databases by migration Step 32.
- `PendingRegistration`: staged passwordless signup state.
- `AuthChallenge`: purpose-bound authentication-code digest, expiry, attempt, and atomic-consumption state.
- `OAuthIdentity`: inert rollback data for a former external provider link; no tokens or secrets.
- `Portfolio`: user-owned portfolio bucket.
- `PortfolioEvent`: funding entries.
- `PortfolioTransfer`: one exact cash movement linking two same-owner portfolios;
  restrictive foreign keys protect the other endpoint during portfolio deletion.
- `Symbol`: tracked asset symbol per portfolio.
- `Transaction`: buy/sell asset entries.
- `Dividend`: investment cash dividend/distribution records.

Pending email-change claims are bounded by their verification-code lifetime.
Expired or incomplete pending-email state is non-reserving and is cleared when
an account workflow encounters it, so it cannot indefinitely hold an address.

The user-facing term is Dividend Income. The `Dividend` model remains accurate
for investment cash dividends/distributions, not generic income.

## Calculators

`portfolio_app/calculators/portfolio_calculator.py` is the database-facing calculator facade. It derives totals from source records:

- Net Contributions
- Cash Balance
- Position Cost Basis
- book value
- Realized Trading P&L
- Dividend Income
- total realized earnings (money) and realized trading return (percentage)
- asset-level summaries

`portfolio_app/calculators/financial_math.py` contains pure deterministic financial calculations, including Average Cost Method transaction-list math and return percentage/display math. It has no Flask, SQLAlchemy, repository, service, or model dependency.

Calculators should use `Decimal` for financial math and should not introduce cached financial totals without a clear invalidation strategy.

Phase 8 uses one `calculate_realized_trading_return(pnl, released_basis)` function
for sale, asset, portfolio and global views. It divides summed trading P&L by
summed released basis, never averages percentages. Dividend Income, funding and
open basis are not inputs. `calculate_realized_earnings_metrics` separately
exposes monetary `total_realized_earnings = realized_trading_pnl + dividend_income`.
Zero basis is `None`/JSON null/dash, distinct from a break-even sale's Decimal zero.
These are realized trading measures, not total performance, TWR, MWR or XIRR.

Aggregate consumers now use immutable asset, portfolio, and global snapshots
from `calculators/financial_snapshots.py`. `PortfolioCalculator` loads scoped
inputs; the snapshot builders compose the existing pure arithmetic and canonical
ordering helper. Routes consume snapshot adapters instead of defining financial
formulas. See [Canonical financial reads](FINANCIAL_READ_MODEL.md) for the
canonical API contracts, exact storage and remaining calculation limits.

One `replay_symbol_transactions` call now produces both aggregate state and
immutable per-transaction financial projections. Asset snapshots expose those
projections by transaction ID; Assets uses them independently of presentation
order. Schema 36 removes stored `Transaction.average_cost` and `net_amount`
and their compatibility writers. Context-free model P&L properties are removed;
transaction serialization requires an explicit canonical projection and portfolio
name, with no hidden history/relationship queries. Raw edit inputs remain separate.

Financial persistence uses `utils/exact_decimal.py::ExactDecimalText`: finite
Decimal -> canonical ordinary decimal TEXT -> Decimal, without binary float or
scale quantization. It covers transaction price/quantity/fees, Dividend amount,
and PortfolioEvent amount_delta. Numeric sign CHECKs move to service validation;
NOT NULL, TEXT storage checks and ownership foreign keys remain in SQLite.
Services preserve quantity walks and cash validation without writing derived
history. Financial aggregation stays in Python, never SQL arithmetic on TEXT.
Calculation uses `utils/financial_arithmetic.py`, not the ambient Decimal context:
finite sums/differences/products are exact in operand-sized private contexts,
and each symbol replay fixes one deterministic half-even division budget from
all raw operands. Division precision is `max(28, 2*S + C) + 28`, where `S` is
the significant decimal-position span (including units) and `C` the operand-count
carry digits. The minimum 56 digits retains the former 28-digit resolution plus
28 guard digits; the dynamic term covers raw product widths and larger inputs.
No process-wide context is changed. Snapshot aggregation and mutation validation
share exact finite helpers; services do not silently round holdings/cash checks.

Three independent contracts now apply: **persistence** stores exact raw decimal
TEXT without a fixed scale; **calculation** preserves finite operations exactly
and rounds divisions under the documented local policy; **display** keeps all
existing visible precision/rounding/formatters. Recurring expansions remain
approximate, and extreme input spans remain bounded by platform/resources.
See [Calculation precision](FINANCIAL_READ_MODEL.md#phase-7-three-independent-precision-layers).
See [schema 36 conversion and rollback](MIGRATIONS.md#schema-36-exact-decimal-storage).

## Forms

Forms live in `portfolio_app/forms/`. They validate request payloads for auth, portfolios, funding entries, assets, asset entries, and Dividend Income. They also normalize common inputs before service code receives them.

## Main Data Flow

Internal transfers use `TransferService`/`PortfolioTransferRepository`, the same
cash mutation reservation and canonical daily ledger. A single row is projected
into two portfolio histories by `portfolio_history.py`; it is never rewritten as
Deposit/Withdrawal. Prospective edit/delete validation covers every old/new
endpoint before one commit. Portfolio snapshots expose signed internal flows
separately from external Net Contributions; global flows cancel. Schema 37 adds
the raw transfer table without changing existing financial rows.

Individual portfolio deletion is blocked while a transfer is linked. Confirmed
whole-account deletion resolves only transfers with both endpoints owned by that
account before the existing portfolio cascades, in the same transaction.

Cash-account validation uses `services/cash_account.py` and the pure
`calculators/daily_cash.py` ledger. All cash-affecting service mutations compare
complete pre/prospective end-of-day paths before changing ORM records. This is
separate from the unchanged canonical Buy-before-Sell cost-basis walk. Same-day
inflows/outflows net together; there is no intraday or settlement model. Legacy
deficits remain readable and can be repaired without worsening their historical
minimum. See [cash policy](FINANCIAL_READ_MODEL.md#cash-account-policy).

Typical asset-entry creation:

1. Route receives POST data.
2. Form validates and cleans fields.
3. Route calls `TransactionService`.
4. Service checks ownership, cash, quantity, chronology, and business rules.
5. Repository/model changes are written.
6. Subsequent reads replay raw facts into financial projections; no derived history is written.
7. Route returns JSON or redirects.

Overview reads records through scoped services/repositories, then calls calculator helpers to build totals, portfolio summaries, and allocation chart data.

## Templates, Static Files, and Tokens

Templates live in `portfolio_app/templates/`. Static files live in `portfolio_app/static/`.

`portfolio_app/static/css/tokens.css` is the primary design-token source. `base.css`, `components.css`, `app.css`, `landing.css`, and page templates consume those tokens. JavaScript is mostly in `portfolio_app/static/js/main.js`; Overview chart rendering uses `portfolio_app/static/js/overview_charts.js`.

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
- `portfolio_app/services/transaction_service.py`: asset entries, Dividend Income, symbols, chronology, and cash/quantity rules.
- `portfolio_app/services/portfolio_service.py`: portfolios and funding entries.
- `portfolio_app/calculators/portfolio_calculator.py`: database-backed financial aggregation.
- `portfolio_app/calculators/allocation_charts.py`: Overview allocation chart data for By Book Value and By Net Contributions.
- `portfolio_app/calculators/financial_math.py`: pure financial math.
- `portfolio_app/routes/`: HTTP endpoints.
- `tests/`: regression and behavior tests.

## Architectural Risks

- `portfolio_app/__init__.py` is large because it still contains app wiring, extension setup, error handlers, security headers, and blueprint registration.
- `PortfolioCalculator` is large because it owns portfolio, asset, cash, and return calculations.
- `TransactionService` is large because it coordinates asset entries, Dividend Income, symbols, validations, and recalculation.

Safe future work should define boundaries first, add tests around existing behavior, then move one responsibility at a time. Avoid broad rewrites that mix behavior changes with file movement.

## Final financial vocabulary and presentation

All active financial read-model/JSON keys use the canonical names in
[the glossary](DOMAIN_AND_CALCULATIONS.md). Temporary capital/cash/return aliases
were removed in Phase 9; the complete API rename map is in
[Financial reads](FINANCIAL_READ_MODEL.md#phase-9-api-and-identifier-changes).
Dividend and PortfolioEvent remain valid persistence models. No schema change.
Overview remains a compact four-fact layout with no earnings card; Portfolios
removes its duplicated Book Value summary. The glossary defines concise display
labels separately from precise internal/API identifiers. Only Overview's Book Value,
Net Contributions, Realized P&L and Realized Return have hover/focus info dots.
Assets and Portfolios retain their original disclosure controls without help icons.
Formatting functions and color roles remain
unchanged. No financial policy or arithmetic precision change accompanies renaming.
