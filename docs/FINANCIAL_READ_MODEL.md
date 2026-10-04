# Canonical financial reads (Phase 3)

## Boundary and data flow

`PortfolioCalculator` remains the database-facing facade. It loads user-scoped
records and the existing SQL funding/income reductions. It composes the pure
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
| `routes/transactions.py` | Duplicate asset earnings/percentage and dividend row sums | Consume asset snapshots and explicit detail-income projection |
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
formatters did not change.

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
- SQL funding and portfolio/symbol income sums are unchanged. **Assets income
  retains its prior Decimal sum of loaded rows**, now explicitly named
  `legacy_income_details`. This can differ from SQL SUM at precision boundaries:
  two SQLite inputs of `0.00000000006` produce SQL total `0.0000000001`, but
  loaded ten-decimal rows sum to `0.0000000002`. The Assets adapter preserves the
  latter in income/return; reporting preserves the former. A regression test
  documents this remaining precision projection rather than concealing it.
  Reconciling it is deferred, not claimed complete by this architecture change.
- Summary total book value remains sum of portfolio book values; dashboard
  total remains sum of cash plus sum of basis. Their Decimal association order
  is preserved, including potential extreme-precision differences. Tiny residual
  cost pools after repeating-average liquidation are not clamped.
- JSON summary serialization remains float-based; holdings remains a string.
  Existing formatters, grouping, signs, percentages, dash behavior, and tones
  remain unchanged.

## Stored derivatives and remaining risks

`Transaction.average_cost` is still recalculated and persisted after mutations.
The transaction table's Sell-row P&L/return continues to use that stored average,
including ten-decimal storage rounding. `Transaction.net_amount` is still
recalculated/persisted and displayed/serialized on transaction rows. Neither
field is read as an input to aggregate snapshot calculations. Write-side replay
is intentionally not unified with aggregate replay in this phase.

Consequently stored rows can still disagree with fresh aggregate replay. SQL
income versus row-sum income, SQL Numeric conversion, Decimal residuals, JSON
float conversion, and legacy malformed/non-normalized records remain future
reconciliation concerns. The optional unscoped calculator mode remains an
explicit internal convention; application consumers pass user IDs. Database
reads retain normal SQLAlchemy session behavior and do not introduce writes or
a new concurrency/isolation guarantee. There is no new cache-invalidation risk.

No schema, migration, income-type, transfer, return-policy, or precision change
is part of Phase 3.
