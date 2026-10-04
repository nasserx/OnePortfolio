# Canonical financial reads (Phases 3–4)

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
| `Transaction.net_pnl` / `net_pnl_percent` | Stored-average transaction-row projection | Deliberately retained, not aggregate truth |
| `Transaction.calculate_net_amount`, `TransactionManager`, average recalculation | Write-side derived fields | Deliberately retained |
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
  `None` in the unchanged model property.
- Phase 4 removes SQL monetary SUMs and the separate `legacy_income_details`
  override. Every income consumer uses `income_by_symbol`, built from Decimal
  column reads in ID order, grouped by normalized symbol. Portfolio income sums
  those groups in their first-seen order; standalone asset reads use the same
  groups. Column reads avoid stale, unexpired ORM attributes containing values
  assigned before storage conversion. Funding sums individually loaded signed
  deltas in ID order (gross deposits filter Initial/Deposit before summing).
  These reads remain user-scoped and perform no explicit writes.
- Intentional precision correction: two SQLite income inputs `0.00000000006`
  load as two `0.0000000001` rows. All income/cash/return projections now use
  `0.0000000002`, rather than reporting `0.0000000001` while Assets reported
  `0.0000000002`. Likewise two funding inputs `0.006` load as two `0.01` rows;
  gross/net funding is now `0.02`, not the SQL-reduced `0.01`. These are explicit
  environment/schema regressions, not promises that subscale inputs persist exactly.
- Summary total book value remains sum of portfolio book values; dashboard
  total remains sum of cash plus sum of basis. Their Decimal association order
  is preserved, including potential extreme-precision differences.
- Phase 4 closing-sale precision rule: if a positive position's entire remaining
  quantity is sold, release the actual remaining cost pool, calculate the closing
  P&L as net proceeds minus that pool, and leave basis/average exactly zero.
  For the 5/3 example, basis changes from `-1E-27` to `0`, released basis from
  `5.000000000000000000000000001` to `5`, and realized P&L from
  `3.999999999999999999999999999` to `4`. This is not epsilon clamping: nonzero
  quantities retain even arbitrarily small pools. Write-side replay clears its
  pool on exact zero quantity too, so a new buy cannot inherit the residue.
- JSON summary Decimal fields now use exact fixed-point strings; IDs remain
  numbers, text stays text, and None remains null. Holdings stays a string and
  now expands scientific notation before the Sell Max input receives it.
  No production caller of `/api/portfolio-summary` or `Dividend.to_dict` was found
  in the repository; regression callers support/assert the exact-text contract.
  Out-of-repository clients must consume these monetary fields as decimal text.
  Chart data remains a separate, presentation-only numeric contract.

## Stored derivatives and remaining risks

`Transaction.average_cost` is still recalculated and persisted after mutations.
The transaction table's Sell-row P&L/return continues to use that stored average,
including ten-decimal storage rounding. `Transaction.net_amount` is still
recalculated/persisted and displayed/serialized on transaction rows. Neither
field is read as an input to aggregate snapshot calculations. Write-side replay
is intentionally not unified with aggregate replay in this phase.

Phase 4 exempts metadata-only edits from that replay: when price, quantity, fees,
symbol and effective calendar date are unchanged, save notes (and any same-day
time edit) without rewriting derived values. Otherwise a notes-only save can
change the stored average when recomputation uses already-rounded SQLite inputs.
Actual financial/date-order edits still follow the existing validation/replay.

Consequently stored rows can still disagree with fresh aggregate replay. SQLite
Numeric conversion, finite Decimal-context rounding on open positions, and
legacy malformed/non-normalized records remain future
reconciliation concerns. The optional unscoped calculator mode remains an
explicit internal convention; application consumers pass user IDs. Database
reads retain normal SQLAlchemy session behavior and do not introduce writes or
a new concurrency/isolation guarantee. There is no new cache-invalidation risk.

No schema, migration, income-type, transfer, or return-policy change is part of
either phase. **SQLite NUMERIC exact persistence is not solved.** Stored prices,
quantities, fees, income, funding, averages and net amounts can still round or
lose digits in SQLAlchemy/SQLite conversions. A notes-only edit preserves the
loaded financial values; it cannot recover digits already lost on initial save.

## Phase 4: calculation, action and display precision

- Calculation: existing Decimal context (normally 28 significant digits), moving
  average and scoped return denominators remain. No global context change, epsilon
  tolerances, market values, or new income policy. Cash accumulation uses the
  shared canonical trade order, not an implicit same-date database order.
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
