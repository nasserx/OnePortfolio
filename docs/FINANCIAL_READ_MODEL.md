# Canonical financial reads and transaction projections

The [canonical glossary](DOMAIN_AND_CALCULATIONS.md) defines all financial names
and formulas. This document defines their implementation boundaries.

## Authority and data flow

```text
Raw exact persisted records
  -> user-scoped PortfolioCalculator loading / normalization
  -> canonical date / Buy-before-Sell / ID ordering
  -> financial_math replay via financial_snapshots
  -> immutable transaction, asset, portfolio and global projections
  -> canonical dictionaries -> templates / reporting / JSON
```

Only raw Transaction type, price, quantity, fees, date, portfolio and symbol
determine trading results. Funding comes from PortfolioEvent signed amount_delta;
Dividend Income comes from Dividend amount. Internal cash comes from the linked
PortfolioTransfer endpoints, amount and effective date. No derived accounting fields are stored.

One symbol replay produces both aggregate state and individual transaction
projections. Assets renders the projection map by transaction ID independently
of newest-first row presentation. No per-row history queries or replays occur.
Transaction serialization requires the explicit projection and portfolio name;
raw exact price/quantity/fees, not presentation values, populate edit inputs.

Snapshots are frozen dataclasses with read-only mappings and no ORM references.
Adapters return fresh dictionaries. They are not persisted, cached or hidden
inside model properties. New reads reflect edits/deletions; old snapshots remain
stable. This is not a new database concurrency or transaction-isolation guarantee.

## Read models and consumers

- Asset: replay totals, `dividend_income`, earnings/trading-return metrics and
  per-transaction projections.
- Portfolio: assets, transaction rollup, `gross_deposits`, `net_contributions`,
  `cash_balance`, `dividend_income`, withdrawals, `dividend_income_by_symbol`
  plus `transfer_in`, `transfer_out`, `net_internal_transfers` and canonical financial metrics.
- Global: portfolio snapshots, summed canonical metrics and total Book Value.
- Overview composes one global snapshot for its hero, facts and portfolio rows.
- Portfolios uses portfolio snapshots; Book Value remains calculated even though
  its duplicated summary display was removed.
- Assets uses asset snapshots and Dividend rows. No independent route formulas.
- `get_realized_earnings_for_portfolio`, `get_user_symbol_financials` and
  `get_symbol_financials` are read adapters, not performance methodologies.
- `/api/portfolio-summary` serializes the same canonical portfolio rows.
- `/api/holdings` remains a lightweight, sequence-independent quantity read.
- Allocation charts retain positive-value filtering, Top-N/Other grouping and
  presentation-only numeric serialization. Allocation is not trading return.
- Services retain chronological quantity walks, prospective daily cash paths and fee
  validation. These are mutation safeguards, not alternate reporting engines.

Dividend totals sum individually loaded exact Decimal rows in ID order, grouped
by normalized symbol. Funding sums signed loaded rows; gross deposits filter
Initial/Deposit entries. No financial SQL SUM/AVG or numeric coercion over TEXT.

## Return and earnings

`calculate_realized_trading_return` is the only trading-return formula:
Realized Trading P&L / Released Cost Basis * 100. It is used at sale, asset,
portfolio and global scope. Components are summed before division.

`calculate_realized_earnings_metrics` supplies:
`realized_trading_pnl`, `released_cost_basis`, `dividend_income`,
`total_realized_earnings`, `realized_trading_return` and
`trading_return_display`.

Dividend Income is investment cash dividends/distributions only. It contributes
to earnings, cash and Book Value, not trading P&L or trading return. Funding and
open basis are excluded from return. Zero released basis is undefined; a
break-even sale with positive basis produces a genuine zero percentage.

Partial-sale basis is rounded canonical average multiplied exactly by sold
quantity. P&L uses net proceeds minus that same released component. Full closure
releases the remaining pool exactly; no arbitrary epsilon applies to open positions.
All six accounting identities reconcile using these shared canonical components.

## Phase 9 API and identifier changes

These are intentional unversioned contract changes. In-repository callers and
tests were migrated together; no external-client dependency was confirmed.
External clients must update keys rather than rely on permanent aliases.

| Previous key/name (historical) | Current contract |
| --- | --- |
| total_capital, capital | net_contributions |
| total_cash, cash | cash_balance |
| positions, total_positions, cost_basis, held_cost_basis | position_cost_basis |
| total_value | book_value |
| total_contributed, funding_inflows | gross_deposits |
| total_buy_cost | total_purchase_cost |
| total_sell_cost, realized_proceeds | net_sale_proceeds |
| realized_cost_basis, return_base | released_cost_basis |
| average_cost (open-position summary) | average_unit_cost |
| realized_pnl, net_pnl | realized_trading_pnl |
| total_income, snapshot income | dividend_income |
| return_percent, trade_return_percent, net_pnl_percent | realized_trading_return |
| return_display | trading_return_display |
| transaction JSON net_amount | transaction_amount |
| transaction JSON average_cost | applicable_average_unit_cost |

Transaction `applicable_average_unit_cost` is post-buy for Buy and pre-sale for
Sell; it is deliberately not confused with the remaining position's average.
`transaction_amount` is purchase cost for Buy and net proceeds for Sell, the
existing Total Amount semantics. It is derived, not persisted.

The Phase 8 historical monetary key `return_amount` was already replaced by
`total_realized_earnings`. Obsolete percentage helpers, snapshot `.income`
aliases, duplicate capital getters, return-base aliases and duplicated
net-sale-proceeds keys are absent. A portfolio transaction-summary read now
exposes the canonical released basis rather than selectively hiding that field.
Allocation chart dataset `capital_chart` is now `net_contributions_chart`.

All authoritative JSON financial values remain exact ordinary Decimal strings;
IDs remain numbers and undefined percentages remain null. Chart numbers are
presentation-only and never re-enter accounting. No new binary-float boundary
was introduced. URLs and raw mutation field names remain unchanged.

## Persistence precision

Schema 36 introduced `ExactDecimalText` for Transaction price/quantity/fees,
Dividend amount and PortfolioEvent amount_delta; schema 37 adds PortfolioTransfer
amount with the same unrestricted accepted Decimal precision. Finite Decimal -> canonical
ordinary decimal TEXT -> Decimal never passes through float. Fractional trailing
zeros are removed; all numeric zero representations normalize to `0`.
No new fixed scale or significant-digit limit is imposed. Float/non-finite input
and malformed/noncanonical stored text are rejected.

Historical migration 36 removed stored `Transaction.average_cost` and
`Transaction.net_amount`, their defaults/checks and compatibility writers.
Historical migration references retain their original names. The upgrade uses
the old Numeric result processor once to preserve the application-observed value,
then writes exact text. It cannot recover digits lost before migration.
See [migration safety](MIGRATIONS.md).

Service sign/quantity validation remains authoritative. SQLite retains NOT NULL,
TEXT-storage checks, foreign keys, indexes and cascades. Direct SQL writers must
use canonical strings; TEXT affinity alone does not enforce the entire decimal
grammar or business rules. Phase 9 creates no migration.

## Phase 7: three independent precision layers

### Calculation precision

Finite addition, subtraction and multiplication are exact through operand-sized
private Decimal contexts with Inexact trapped. Only division is rounded.
No process-wide or ambient Decimal configuration is read or changed.

For division, working precision is `max(28, 2*S + C) + 28`:
S is the significant decimal-position span including units; C is the operand-count
carry digits. The minimum 56 digits retains 28 digits plus 28 guards; dynamic
capacity covers wider raw products and accumulation. Rounding is ROUND_HALF_EVEN.
Trailing coefficient zeros do not inflate the budget.

One symbol cost-pool replay fixes its division budget from raw operands.
Percentage projection uses the same operand-derived helper at every scope,
so identical P&L/basis components produce identical percentages. Aggregation
and validation use the same exact finite helpers.

For basis 5 / quantity 3, Average Unit Cost is 1 followed by 54 sixes and a seven
after the decimal point (56 significant digits). A partial sale releases this
canonical finite component. Full liquidation releases the actual remaining pool
and closes basis exactly. The engine does not claim an exact infinite expansion.

### Action precision

Forms use the shared finite Decimal parser. Raw/edit/JSON values use exact text,
never float formatting or formatted display strings. Notes-only edits preserve
raw numbers. Withdrawal Max floors the date-specific safe amount to executable cents;
zero/negative headroom produces no positive Max. Funding storage itself is not
newly restricted to cents.

### Display precision

Existing formatters retain separators, signs, monetary/price/fee/quantity and
Average Unit Cost display rules, compact M/B/T notation, percentages, tones and
undefined dashes. Display ROUND_HALF_UP is separate from internal division rounding.
The legacy display-string adapter retains its explicit half-even formatting.
Higher storage/calculation precision does not alter these formatting conventions.

## Presentation / accessibility

Overview retains its compact four-fact grid; Total Realized Earnings remains
internal/API-only, with no earnings card. Portfolios has four summary metrics
without Book Value. Assets retains seven compact summary metrics. Display labels
deliberately differ from internal identifiers: see the glossary's display mapping.
Only Overview has formula info dots, for Book Value, Net Contributions, Realized
P&L and Realized Return. They have aria labels and explicit hover/focus triggers.
Cash, Dividends, Assets and Portfolios have no help indicators. The original whole-row
disclosure buttons and existing number-formatting/visual conventions remain intact.

The `income` tone/CSS role remains an intentional design token, not a generic
income domain model. Dividend, PortfolioEvent, existing mutation routes, and
deposit_funds/withdraw_funds action names remain accurate and unchanged.

## Remaining limits

Recurring division remains approximate; terminating division also observes its
working budget. Guards cannot promise arbitrary relative accuracy after cancellation.
Adding historical transactions can increase replay precision and refine low-order
digits. Extremely large exponents/spans/history require resources and remain
subject to Python Decimal platform limits.

Optional unscoped calculator calls remain an internal convention; application
consumers pass user IDs. Malformed/non-normalized legacy data and concurrent
edits require the existing validation/isolation policy, not new snapshot caching.

Realized Trading Return is not total portfolio performance. Market valuation,
unrealized P&L, TWR, MWR/XIRR, FX and benchmarks remain outside scope.
Dividend accounting is unchanged.

## Cash-account policy

Phase 10 intentionally changes mutation acceptance, not accounting formulas.
OnePortfolio models a cash account, without margin, loans, broker credit or
settlement rules. A valid history closes every effective calendar day at cash >= 0.
Ending cash alone is insufficient: a Jan 1 Buy 555 followed by Jan 2 Deposit 555
is invalid even though final cash is zero. Record funding on or before the Buy's
date. The funded BTC sequence still realizes 3 on released basis 555.

`calculators/daily_cash.py` derives immutable `DailyCashLedger`/`DailyCash` rows:
opening cash + external funding inflows + transfer in + net sale proceeds + dividends
− buy outflows − external withdrawals − transfer out = closing cash.
All finite arithmetic uses the exact Decimal helpers.
Trade cash effects share `financial_math.transaction_cash_effect` with aggregate
Cash. Last closing cash reconciles to canonical portfolio Cash for valid raw facts.
No daily balances are stored. Phase 10 required no migration; Phase 11 adds only
the raw linked transfer table in schema 37.

Cash validation nets all effects on the same recorded date, irrespective of clock
time or insertion order. Same-day inflows can fund outflows. This is NOT broker
settlement modeling. Cost-basis replay independently retains date ASC, Buy before
Sell, ID ASC. New service records resolve the existing UTC-now default once if
no date is supplied; forms require dates. Legacy null dates map to `date.min`,
before dated history, consistently with canonical trade ordering. Their actual
economic date cannot be recovered without a user correction.

`services/cash_account.py` loads scoped raw records and validates an immutable
prospective replacement/removal/addition before any ORM mutation. Transactions,
funding, dividends and whole-asset deletion use this single policy. It covers date
changes and all later days, not just a mutation's amount delta. Ownership and
quantity-walk safeguards remain independent prerequisites.

SQLite mutations reserve the writer with `BEGIN IMMEDIATE` before service reads
and hold it through the transaction owner's commit, preventing concurrent requests
from spending the same cash or quantity. `services/mutation.py` owns the boundary;
HTTP submission receipts share that same commit. Exceptions roll back; no-op edits release the lock.
Read-only ledger/Max requests never acquire this reservation. Service callers
should enter with a clean session, not a hand-opened deferred database transaction;
direct SQL/ORM writes outside the services are not policy-validated.

For a valid pre-history, prospective minimum closing cash must stay >= 0.
For legacy-invalid history, prospective minimum must be >= the previous minimum,
using exact comparisons, without epsilon. Thus notes-only changes, partial repairs
and equal-minimum changes remain possible; a worse minimum is rejected. This is a
minimum-balance repair rule, not a requirement for pointwise improvement on every
day. Once repaired, strict validation automatically applies. History is never
fabricated, reordered or deleted automatically.

For an additional withdrawal dated D, Max is the minimum closing cash at D and
all later recorded days. If D has no record, include the carried cash at D. Clamp
only this action allowance (not reported Cash) to zero and floor it to cents.
If the affected path has a negative legacy balance, Max offers zero. An earlier
deficit outside that path does not reduce positive safe headroom at D. The authenticated,
tenant-scoped `GET /portfolios/withdrawal-max/<id>?date=YYYY-MM-DD` returns an
exact decimal string `amount`, with no-store caching. The dialog requests it for
the selected date and ignores stale date/portfolio responses. Server mutation
validation remains authoritative even after Max is requested.

## Linked transfer read and mutation contracts

`TransferService` uses the existing SQLite mutation reservation, validates every
affected portfolio with `CashAccount`, then writes one raw `PortfolioTransfer`
record within the shared mutation transaction. Edits validate removal of the old effects plus addition
of the new effects before dirtying the ORM. Deletes validate the destination
clawback too. Any failure rolls back; no independent funding rows are created.

`PortfolioTransferRepository` scopes both endpoints to the same user. The daily
ledger derives transfer components from the raw row; aggregate cash receives
the exact signed net transfer total. Portfolio snapshots and
`/api/portfolio-summary` add exact-string `transfer_in`, `transfer_out` and
`net_internal_transfers` keys. Global signed totals cancel; directional totals
measure internal movement, not external contributions or earnings.

Portfolio Book Value = Net Contributions + Net Internal Transfers + Realized P&L
+ Dividends. Global Book Value = Net Contributions + Realized P&L + Dividends.
The primary Cash + Cost Basis formula is unchanged, as is Realized Trading Return.

Portfolio history projects each linked record once per endpoint, with the same
transfer ID and raw edit payload, without persisting side records. The existing
Entries count includes each visible side once. Existing funding history order
and money formatting are preserved. No Overview card or help indicator is added.

Authenticated CSRF-protected mutation routes are POST `/portfolios/transfers/add`,
`/portfolios/transfers/edit/<id>` and `/portfolios/transfers/delete/<id>`.
Save responses include `transfer` with `id`, `source_portfolio_id`,
`destination_portfolio_id`, exact-string `amount`, effective `date` and `notes`.
Forms use existing finite Decimal/date parsers; edit fields never use displayed
money. No fixed cent restriction, no float conversion, and no Transfer Max button.
Currency/FX, cross-user transfers and securities transfers remain unsupported.
