# Canonical financial reads and transaction projections

## Boundary and data flow

`PortfolioCalculator` remains the database-facing facade. It loads user-scoped
records and sums individually loaded Decimal funding/income values. It composes the pure
builders in `financial_snapshots.py`, which use `financial_math.py` and the
Phase 2 `transaction_order.py` helper. No database dependencies were added to
the pure modules.

```text
Scoped transactions / funding / Dividend records
    -> PortfolioCalculator loaders and existing normalization
    -> shared canonical transaction ordering
    -> financial_math via financial_snapshots builders
    -> immutable Asset / Portfolio / GlobalFinancialSnapshot
    -> legacy dictionary adapters -> pages, reporting, JSON
```

Asset snapshots contain fresh replay totals (quantity, purchase cost, open and
released basis, average cost, proceeds, trading P&L), income, and current return
results. Portfolio snapshots contain their asset snapshots, transaction rollup,
gross funding, net contributions, withdrawals, cash, income, book value, and
current return results. Global snapshots contain portfolio snapshots and the
existing dashboard totals. There are no market-value or unrealized-P&L fields.

Snapshot dataclasses are frozen, their mappings are read-only copies, and they
contain no ORM objects. Adapters return fresh dictionaries. They are not stored
in a table, placed in Flask `g`, or cached between calls. New reads reflect
committed edits/deletions; old snapshots remain stable. The Overview route builds
one global snapshot for both its cards and portfolio rows, replaying each symbol
once. A snapshot is an in-memory read model, not a new database isolation policy.

## Duplication map and disposition

| Location | Classification before Phase 3 | After Phase 3 |
| --- | --- | --- |
| `financial_math.py` | Authoritative pure trade replay, cash, scoped returns, book value | Unchanged arithmetic foundation |
| `portfolio_calculator.py` summary / dashboard / realized performance / transaction summaries | Repeated symbol replays and independent aggregate assembly | Load snapshots; adapt the same replay results |
| `routes/portfolios.py` | Duplicate book value, earnings, percentage and undefined-return arithmetic | Consume portfolio snapshot metrics |
| `routes/transactions.py` | Duplicate asset earnings/percentage and dividend row sums | Consume asset snapshots and canonical income-by-symbol totals |
| `routes/dashboard.py` | Consumer; separate summary and totals reads | One composed snapshot for Overview; same facade for summary API |
| `/api/holdings` | Lightweight quantity calculation and string serialization | Retained: sequence-independent quantity, tested against snapshot quantity |
| `Transaction.net_pnl` / `net_pnl_percent` | Stored-average transaction-row projection | Removed in the transaction-projection phase; canonical replay supplies row P&L/return |
| `Transaction.calculate_net_amount`, `TransactionManager`, average recalculation | Write-side derived fields | Compatibility retained through Phase 5; removed in Phase 6 |
| Portfolio/Transaction services | Validation walks, proposed cash deltas, fees versus proceeds | Retained validation, not reporting calculations |
| Forms | Input validation and normalization | Unchanged |
| `allocation_charts.py` | Positive-value filtering, Top-N/Other percentages and chart serialization | Retained presentation calculation over canonical portfolio rows |
| Templates, formatters, JS | Display, input handling, chart rendering, serialization | Unchanged |
| Migrations | Historical schema/data transformations | Unchanged; not a live reporting path |
| Tests | Characterization, accounting identities, UI contracts | Existing expectations retained; read-model contracts added |

The old route ROI implementation and `_build_symbol_performance_row` are removed.
Existing calculator entry points used by services/tests are thin adapters, not
alternative formula implementations. The list-summary entry point also uses the
same asset builder and therefore the same ordering boundary.

## Legacy name adapters

Internal `funding_inflows` maps to `total_contributed`; `net_contributions` maps
to `total_capital`; `cash_balance` maps to `cash`, `withdrawable_cash`, or global
`total_cash`. Existing summary keys (`cost_basis`, `positions`, `total_buy_cost`,
`total_sell_cost`, `return_amount`, etc.) are intentionally unchanged. This is
not the later terminology rename. UI labels, tooltips, templates, and number
formatters retain their visible semantics. Phase 4 changes action payloads only.

## Preserved policies and deliberate precision seams

- Trade replay remains moving weighted average, capitalizing buy fees and
  deducting sell fees. Ordering remains effective calendar date, Buy before Sell,
  then database ID. Presentation lists remain independently ordered.
- Cash uses the same sequential `calculate_cash_balance` function for reporting
  and validation, including excluded-transaction validation reads. Negative cash
  remains possible. No new funding or withdrawal restrictions were added.
- Portfolio/global return remains `(trading P&L + income) / gross deposits`;
  asset return remains `(trading P&L + income) / historical purchase outflows`.
  The shared existing function retains its absolute-denominator convention.
  Valid purchase outflows/deposits are positive, so delegating the old route
  formulas preserves their results. Unsupported negative purchase/deposit inputs
  are not a new financial policy.
- Undefined return remains numeric zero plus a dash for reporting, and `None`
  plus a dash in the Assets template adapter. Sell-row undefined return remains
  `None` in the canonical transaction projection.
- Phase 4 removes SQL monetary SUMs and the separate `legacy_income_details`
  override. Every income consumer uses `income_by_symbol`, built from Decimal
  column reads in ID order, grouped by normalized symbol. Portfolio income sums
  those groups in their first-seen order; standalone asset reads use the same
  groups. Column reads avoid stale, unexpired ORM attributes containing values
  assigned before storage conversion. Funding sums individually loaded signed
  deltas in ID order (gross deposits filter Initial/Deposit before summing).
  These reads remain user-scoped and perform no explicit writes.
- Historical Phase 4 correction (before schema 36): two SQLite income inputs `0.00000000006`
  load as two `0.0000000001` rows. All income/cash/return projections now use
  `0.0000000002`, rather than reporting `0.0000000001` while Assets reported
  `0.0000000002`. Likewise two funding inputs `0.006` load as two `0.01` rows;
  gross/net funding is now `0.02`, not the SQL-reduced `0.01`. These are explicit
  legacy environment/schema results. Schema 36 preserves those observed values
  on upgrade; new inputs persist exactly, totaling `0.00000000012` and `0.012`.
- Summary total book value remains sum of portfolio book values; dashboard
  total remains sum of cash plus sum of basis. Phase 7 makes both finite sums
  exact, eliminating association-dependent precision differences.
- Phase 4 closing-sale precision rule: if a positive position's entire remaining
  quantity is sold, release the actual remaining cost pool, calculate the closing
  P&L as net proceeds minus that pool, and leave basis/average exactly zero.
  For the 5/3 example, basis changes from `-1E-27` to `0`, released basis from
  `5.000000000000000000000000001` to `5`, and realized P&L from
  `3.999999999999999999999999999` to `4`. This is not epsilon clamping: nonzero
  quantities retain even arbitrarily small pools. New buys after closure start
  with the exact zero pool; no write-side projection replay remains.
- JSON summary Decimal fields now use exact fixed-point strings; IDs remain
  numbers, text stays text, and None remains null. Holdings stays a string and
  now expands scientific notation before the Sell Max input receives it.
  No production caller of `/api/portfolio-summary` or `Dividend.to_dict` was found
  in the repository; regression callers support/assert the exact-text contract.
  Out-of-repository clients must consume these monetary fields as decimal text.
  Chart data remains a separate, presentation-only numeric contract.

## Exact storage and remaining risks (Phase 6)

Schema 36 removes `Transaction.average_cost` and `Transaction.net_amount`, their
defaults/check constraint, and all compatibility writers. Canonical replay still
supplies every derived financial result. TransactionManager persists raw facts;
TransactionService retains cash/fee/quantity-walk validation but no longer writes
historical projections. Metadata-only edits still preserve raw fields.

`ExactDecimalText` stores transaction price/quantity/fees, Dividend amount and
PortfolioEvent amount_delta as SQLite TEXT, exposing Decimal to Python. Its
conversion is context-independent fixed-point text, with fractional trailing
zeros removed and all numerical zeros represented as `0`. No float input,
non-finite value, fixed storage scale, or database rounding is permitted. Decimal,
integer and exact input text are supported; malformed/noncanonical stored text
fails closed on read. Existing form/service domain rules remain authoritative.
Funding inputs are not newly limited to cents; Max remains a cent-floor action.
Withdrawal sign changes use `copy_negate()` so even >28-digit raw amounts are
not rounded before persistence.

Migration 36 uses the historical Numeric result processor **once** to obtain the
old application's observed Decimal, then binds canonical strings to TEXT. It
cannot recover previously lost digits. See [migration safety](MIGRATIONS.md).
No financial SQL SUM/AVG, numeric coercion, comparison or ordering over these
TEXT values is used by production accounting. Python Decimal reads/aggregation
remain canonical. IDs/counts/dates/booleans and all display formatting are unchanged.

Phase 6 deliberately retained the ambient 28-digit arithmetic boundary while
making persistence exact. Phase 7 converts its price-times-one characterization
to a correctness test and protects calculation/validation/aggregation with the
explicit policy below. Exact persistence still does not imply infinite-precision
division; no global context is changed.

Legacy malformed/non-normalized records remain reconciliation concerns. Optional
unscoped calculator calls remain an internal convention; application consumers
pass user IDs. Reads retain SQLAlchemy session semantics, with no new cache or
concurrency/isolation guarantee. Direct SQL writers must use canonical strings:
SQLite TEXT affinity alone cannot enforce the full Decimal grammar or sign policy.

## Canonical transaction-projection phase

### Authority and one-replay architecture

Authoritative trade facts are portfolio, symbol, type, price, quantity, fee and
effective date/order (calendar date, Buy before Sell, database ID). Funding and
Dividend raw records remain authoritative for their respective cash flows.

`replay_symbol_transactions` in `financial_math.py` consumes one already-ordered
symbol history and returns a frozen `AssetReplayResult` containing a read-only
summary and a tuple of frozen `TransactionFinancialProjection` values. The
existing `calculate_symbol_transaction_summary` is just a dictionary adapter over
that replay, not another implementation. `build_asset_snapshot` applies the
shared ordering helper once, then exposes the same replay's aggregates and an
immutable `transaction_projections` map keyed by persisted transaction ID.
Unsaved/id-less pure records remain represented in the replay tuple, not the ID map.

Each projection contains gross amount, fee, purchase cost, net sale proceeds,
signed cash effect, applicable average unit cost, released basis, realized trading
P&L, trade return, and post-transaction quantity/basis/average. For Buys, the
applicable average is the post-buy average and trading P&L/return are None. For
Sells, it is the pre-sale average; zero released basis produces a None return.
`cash_amount` adapts purchase cost or net sale proceeds to the existing Total
Amount display. It does not read the stored `net_amount` column.

The sale P&L stored in each projection is the **same Decimal contribution** added
to aggregate realized P&L. Phase 7 calculates partial P&L as `net proceeds - released
basis`, algebraically identical to `(price - average) * quantity - fee` but using
the exact same finite component as the remaining pool. Closing sales retain
Phase 4's exact-pool release. Row return is that canonical sale
P&L divided by canonical released basis times 100. No ten-decimal stored-average
rounding is reintroduced, and no aggregate formulas or Return policies change.

For buys 1 @ 1 and 2 @ 2 followed by selling 1 @ 3, the old stored average
`1.6666666667` gave row P&L `1.3333333333`. Phase 5 unified canonical row and
aggregate P&L at `1.333333333333333333333333333`. Phase 7 refines that shared
result to `1.` followed by 55 threes under the explicit division policy.
The BTC sale gives proceeds 558, released basis 555, P&L 3, and return
`3 / 555 * 100`; subsequent funding does not change that row projection.

### Consumers and serialization

Assets obtains the projection map from the same asset snapshot as its summary.
Its rows select the projection by ID. Raw ORM rows remain the source of editable
price/quantity/fee, notes and date payloads. Presentation still reverses the
repository list independently of ascending accounting order; no row-level replay
or history query is introduced.

The context-free `Transaction.net_pnl` and `net_pnl_percent` properties are
removed. A standalone row cannot infer historical basis. `Transaction.to_dict`
requires keyword arguments `projection` and `portfolio_name`, checking that the
projection's transaction/portfolio IDs match. It does not query a relationship
or replay history. Legacy JSON keys `net_amount`, `average_cost`, `net_pnl` and
`net_pnl_percent` now adapt canonical values, serialized as exact Decimal text
(or None). Raw editable fields remain raw exact text. No existing production
caller of this serializer was found; its explicit-context contract is regression
tested, including with both legacy columns configured to raise on access.

Snapshots remain point-in-time values: callers must obtain a fresh snapshot after
financial edits. Passing an old projection alongside newer records is not a live
recalculation API. No persistent cache or new isolation/concurrency policy exists.

### Stored-field disposition after Phase 6

| Field/path | Classification | Status |
| --- | --- | --- |
| `Transaction.average_cost` column | Legacy persisted derived data | Removed; no active read/write |
| `PortfolioCalculator.recalculate_all_averages_for_symbol` | Legacy derived write | Removed |
| `Transaction.net_amount` column | Legacy persisted derived data | Removed; no active read/write |
| `Transaction.calculate_net_amount` | Legacy derived write | Removed |
| TransactionService add / financial update / delete | Raw mutation and validation | No compatibility replay; validation walks retained |
| Model derivative defaults and net_amount check constraint | Obsolete schema | Removed atomically |
| Assets row financial cells | Display | Canonical projection; raw edit payloads unchanged |
| Transaction serializer legacy keys | Serialization adapter | Canonical projection only; explicit context required |
| Summary `average_cost`, `realized_pnl`, `realized_cost_basis`, `total_sell_cost` | Canonical calculation/aggregation | Fresh replay values, not model-column reads |
| Tests inspecting stored values/corruption | Test-only | Corrupt derivatives now belong to pre-migration fixtures; final-schema tests assert absence |
| Existing migrations/rebuild SQL | Migration/history | Preserved unchanged; can copy legacy columns, not a live reporting path |

Legacy serialized keys `net_amount` and `average_cost` remain canonical projection
adapters, not persisted fields. Historical migration code still references the old
columns when upgrading older schemas; it is not an active application write path.

Regression coverage includes permutations and same-day ties, fees, partial/multiple
sales, full liquidation, historical insertion, exact row/aggregate reconciliation,
BTC, corrupted legacy fields, read-only results, exact JSON text, and constant query
count / one replay per asset as the displayed row count grows. Existing formatting,
return denominators, cash and edit-roundtrip tests remain in force.

## Phase 4: calculation, action and display precision

- Calculation: Phase 7 replaces the former ambient 28-digit context with the
  explicit policy below. Moving average and scoped return denominators remain.
  No global context change, epsilon tolerances, market values, or new income
  policy. Cash accumulation uses the shared canonical trade order.
- Action: `parse_financial_decimal` is the form/service input authority. Dot is
  the decimal separator; commas must be correctly grouped thousands. Leading/
  trailing whitespace, signs, `.5`, `1.`, and scientific notation are accepted.
  Internal whitespace, malformed commas (`1,5`), underscores, invalid/blank text,
  NaN/sNaN and infinities are rejected. Form wrappers retain required/optional
  blank and positive/nonnegative policies. Services also validate before mutations
  or comparisons, including callers bypassing forms. Python float/bool action
  inputs are rejected; use Decimal, integer or exact text instead.
- Action serialization: `decimal_text` uses Decimal fixed-point formatting
  without a float or quantization. Trade, income and funding edit attributes use
  it before JSON encoding. JS dialog population trims only fractional trailing
  zeros; scientific notation expansion uses string operations. Invalid input is
  no longer sanitized into a different amount (e.g. `-1` into `1`).
- Withdrawal Max: `withdrawal_max_text` floors positive raw cash to executable
  cents using ROUND_DOWN, returning `0.00` for nonpositive cash. `1.005` and
  `1.009` produce `1.00`; `1.019` produces `1.01`. Page actions and error-modal
  payloads use the same helper. The service still authoritatively checks cash.
- Display: existing Python/JS formatters and money/percentage/quantity macros
  are unchanged, including ROUND_HALF_UP, commas, M/B/T, signs, tones and dashes.
  Preview totals never submit as accounting values; raw form fields do.

### Float/conversion inventory

| Path | Classification | Disposition |
| --- | --- | --- |
| Trade/income edit `%.10f`, funding edit `%.2f` | Unsafe action round trip | Exact `decimal_text` attributes |
| Edit-dialog `parseFloat` / `toFixed` fallback | Unsafe action round trip | Exact string expansion |
| Withdrawal Max using formatted cash | Unsafe action rounding | Raw cash floored to cents |
| Input sanitizer / scientific-notation helper | Unsafe textual numeric reinterpretation | Preserve invalid input; exact string normalization |
| Metadata-only trade edit replay | Avoidable re-entry through stored-value precision | Save metadata without recalculating financial fields |
| Summary API Decimal-to-float, Dividend `to_dict.amount` | Lossy reporting serialization | Exact strings; complete in-repository consumer search |
| Transaction `to_dict` decimal strings | Exact reporting serialization | Retained |
| Holdings numeric enable check | Client convenience only; original exact string submitted | Retained; API guarantees fixed-point input |
| JS `parseNumberStrict`, dividend positivity checks | Client validation only | Retained; server parser authoritative |
| Buy/sell preview `parseFloat` and `Utils.formatMoney` | Presentation only | Retained; calculated total is not a submitted field |
| Allocation chart float adapters and Decimal reconstruction of chart totals | Presentation only | Retained; never used by snapshots or actions |
| `display_formatters.js`, chart tooltip `Number`, shell countup | Presentation only | Retained |
| Landing demo `Number`, icon scripts, colour/layout tests | Demo/nonfinancial | Retained |

Regression commands: `python -B -m pytest -p no:cacheprovider -q` and
`node tests/precision_boundaries.js`. The latter executes the production JS
normalizer and edit-population functions without launching an app or browser.

## Phase 7: three independent precision layers

1. **Persistence precision:** schema 36's `ExactDecimalText` stores finite raw
   Decimals as canonical ordinary decimal TEXT. It has no significant-digit or
   fixed-scale ceiling. Parsers/services retain their sign and finite-value
   validation; this phase adds no user-facing precision restriction, migration,
   or storage conversion. Digits lost before schema 36 cannot be reconstructed.
2. **Calculation precision:** `utils/financial_arithmetic.py` supplies exact
   finite arithmetic and a deterministic division policy. No arithmetic relies
   on the calling thread's Decimal context.
3. **Display precision:** existing formatters, templates, JS and CSS are unchanged.
   ROUND_HALF_UP money formatting, precision rules, compact notation, signs and
   undefined dashes remain separate. Exact JSON/action strings expose the actual
   higher-precision results; actions never parse rounded display text.

### Exact finite operations

`exact_sum`, `exact_add`, `exact_subtract`, and `exact_multiply` use private
`decimal.Context` objects sized to hold the entire finite result. Sum capacity is
`max(adjusted exponent) - min(coefficient exponent) + 1 + digits(nonzero count)`;
the final term allows carries. Product capacity is the sum of the operands'
coefficient digit counts. Subtraction/sign reversal uses `copy_negate`, not
ambient unary minus. `Inexact` is trapped: these operations may not silently
discard digits. Zero-only sums return Decimal zero.

Operand-sized exact-operation contexts are capacity bounds, **not different
rounding budgets**. They never round a financial result. This distinction avoids
mixing approximate operations at arbitrary precisions within a replay.

### One division budget per symbol replay

For raw operand collection `V` (price, quantity, fees of every ordered row):

- Ignore numerical zeros for span calculation; ignore trailing coefficient zeros.
- `H = max(0, max(adjusted exponent + 1))`.
- `L = min(0, min(exponent after removing trailing coefficient zeros))`.
- `S = H - L`, the span of decimal positions, including the units boundary.
- `C = digits(max(1, len(V)))`, carry allowance for the number of operands.
- **Division precision `P = max(28, 2*S + C) + 28`.**

The old 28-digit working resolution is a floor, with a further 28 guard digits:
small-input recurring divisions therefore have 56 significant digits. Doubling
the raw span covers price-times-quantity width; `C` accounts for accumulation;
the guard margin retains another full former working precision for recurring
averages. This is an explicit approximation policy, not a proof of unlimited
relative accuracy after arbitrary cancellation. High-precision or widely
separated inputs scale `P` instead of being truncated to a fixed 56 digits.

One immutable `FinancialArithmetic` instance fixes `P` for **all** divisions in
that symbol replay: pre-sale/post-buy averages, post-step/final averages, and
sale returns. Exact finite operations preserve their outputs without further
rounding. Standalone scoped returns and cross-asset weighted-average adapters
derive their own budget by the same rule from their direct operands. They do
not repeat a symbol replay. Percentages divide first, then multiply by 100
exactly, preserving the current formula order.

Every division uses **ROUND_HALF_EVEN**, deliberately independent of display
ROUND_HALF_UP. Context precision, rounding, exponent bounds, traps and flags are
constructed explicitly; no `getcontext().prec` mutation occurs. The exponent
range uses Python Decimal's platform bounds. Decimal context methods perform
arithmetic directly; the legacy `return_display` string uses an explicit local
context to preserve its existing half-even formatting under any caller context.

### Reconciliation and intentional precision differences

Partial-sale released basis remains rounded canonical average times sold
quantity, now multiplied exactly. P&L is net proceeds minus that **same** released
component, algebraically equivalent to `(price-average)*quantity-fees` without
independent finite rounding. Pool subtraction and row/aggregate accumulation are
exact. All six accounting identities therefore reconcile exactly using the
finite canonical components, including recurring-average histories. Closing a
valid exact-zero quantity releases the entire remaining pool; nonzero quantities
are never epsilon-clamped. Row and aggregate results share one replay.

For basis 5 / quantity 3, the canonical average is `1.` followed by 54 sixes and
a seven (56 significant digits). Selling one at 3 releases that basis, realizes
`1.` followed by 55 threes, and leaves `3.` followed by 55 threes. Selling the
remaining two releases the remaining pool exactly; cumulative P&L is 4 and
quantity/basis/average are zero. The former 28-digit tail is intentionally
replaced, not used as an expected tolerance.

Funding, income, held quantity, cash, book value, portfolio/global rollups,
withdrawals, fee checks, cash mutation deltas and chronological validation walks
use the same exact finite helpers. Allocation percentages use the division
policy before existing presentation-only float chart adapters. No arithmetic
was added to routes. Return numerators/denominators, negative-cash policy and
canonical ordering are unchanged.

### Limits and test evidence

Recurring division is approximate; terminating division also observes `P` if
its expansion needs more digits. Guards cannot guarantee arbitrary relative
accuracy under cancellation. Adding records can increase a replay's budget and
refine previously calculated low-order digits. Snapshots remain read-time views.
Extreme exponent spans or record counts require corresponding memory/CPU, and
Python Decimal's platform limits still apply; this is not unlimited arithmetic
or a new input resource-limit policy. Unsupported sizes fail rather than being
silently clamped. Existing display-only formatters retain their own limits.

Tests compare exact finite operations against independent rational arithmetic,
exercise >28-digit database-to-replay facts, recurring partial/full sales and all
accounting identities, and run canonical snapshots under ambient precisions
3/9/28/90 with altered rounding, exponent bounds and Inexact/Rounded traps.
Results are identical and ambient settings/flags are unchanged.
