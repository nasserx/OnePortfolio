# Domain and Calculations

This is the canonical financial glossary. All financial arithmetic uses Decimal.
Storage, calculation and display precision are separate contracts; see
[Financial read models](FINANCIAL_READ_MODEL.md).

## Canonical glossary

| Concept | Meaning / formula | Canonical identifier |
| --- | --- | --- |
| Net Contributions | External Deposits − External Withdrawals, including initial funding in deposits | `net_contributions` |
| Net Internal Transfers | Transfer In − Transfer Out | `net_internal_transfers` |
| Cash Balance | Net Contributions + Net Internal Transfers − Buy Outflows + Net Sale Proceeds + Dividend Income | `cash_balance` |
| Position Cost Basis | Remaining acquisition cost of open positions, including allocated buy fees | `position_cost_basis` |
| Book Value | Cash Balance + Position Cost Basis | `book_value` |
| Total Purchase Cost | Sum of all historical buy outflows, including buy fees | `total_purchase_cost` |
| Average Unit Cost | Position Cost Basis ÷ current Quantity; zero after complete liquidation | `average_unit_cost` |
| Released Cost Basis | Acquisition cost released by sales through canonical moving-average replay | `released_cost_basis` |
| Net Sale Proceeds | Gross sale proceeds − sell fees | `net_sale_proceeds` |
| Realized Trading P&L | Net Sale Proceeds − Released Cost Basis | `realized_trading_pnl` |
| Dividend Income | Cash dividends/distributions received from investments | `dividend_income` |
| Total Realized Earnings | Realized Trading P&L + Dividend Income; a money amount | `total_realized_earnings` |
| Realized Trading Return | Realized Trading P&L ÷ Released Cost Basis × 100 | `realized_trading_return` |
| Funding Entries | Initial funding, deposits and withdrawals recorded by `PortfolioEvent` | Existing event model |
| Asset Entries | Buy, Sell and Dividend records displayed for an asset | Existing transaction/dividend models |

Gross deposits (`gross_deposits`) are Initial + Deposit inflows before withdrawals.
They are not Net Contributions and are not a return denominator.

Negative Net Contributions are valid: deposits 555 minus withdrawals 558 = −3.
This means withdrawals exceed deposits, not a loss. OnePortfolio models a cash
account: newly accepted mutations cannot create an end-of-day cash deficit in a
valid history. Legacy deficits remain visible and repairable, never clamped or
reinterpreted as borrowing. See [the cash policy](FINANCIAL_READ_MODEL.md#cash-account-policy).

## Canonical accounting

Replay is per portfolio/symbol, ordered by effective calendar date ascending,
Buy before Sell on the same date, then database ID ascending. Presentation may
independently show newest first.

Buy outflow = price × quantity + buy fee. Add that outflow to the position pool.
For a partial sale, release pre-sale Average Unit Cost × sold quantity.
For a valid full liquidation, release the entire remaining pool exactly, leaving
quantity, Position Cost Basis and Average Unit Cost at zero. Never epsilon-clamp
an open position.

Realized Trading P&L uses net proceeds minus the *same* released component used
to reduce the pool. Buy fees are included in released basis; sell fees reduce
proceeds. Fees are never deducted again from trading return.

Reconciliations:

- Portfolio Book Value = Net Contributions + Net Internal Transfers + Realized Trading P&L + Dividend Income.
- Global Book Value = Net Contributions + Realized Trading P&L + Dividend Income (internal flows cancel).
- Total Purchase Cost = Position Cost Basis + Released Cost Basis.
- Net Sale Proceeds = Released Cost Basis + Realized Trading P&L.
- Held Quantity = Bought Quantity − Sold Quantity.

Book Value is cost-based, not market value or equity marked to market.
Total Purchase Cost includes purchases since sold; it is not the current open pool.

## Internal portfolio transfers

An internal transfer moves cash between two distinct portfolios owned by the same
user. One linked `PortfolioTransfer` row supplies Transfer Out and Transfer In;
neither side is an external funding entry. Net Contributions, gross deposits and
external withdrawals exclude transfers. Transfers never affect trading P&L,
Released Cost Basis, Realized Trading Return or Dividends.

At portfolio scope, Net Internal Transfers = Transfer In − Transfer Out. At global
account scope the signed flows cancel exactly; global Cash and Book Value do not
change. Book Value always remains Cash + Cost Basis.

Both histories are checked prospectively through the daily cash ledger on create,
edit and delete, including old/new endpoints and all later dates. Phase 10's
repair-safe minimum rule still applies. Removing a spent destination inflow may
therefore be rejected. Same-day inflows can fund transfer outflows; no settlement
or intraday timing is modeled.

Transfers use exact positive finite Decimal amounts, with no newly imposed cent
scale. No Transfer Max action is provided; Withdrawal Max includes transfer cash
effects through the shared ledger. All transfers assume the same accounting unit:
currency conversion, FX and cross-user transfers are not supported.

Linked portfolios cannot be individually removed until transfers are explicitly
resolved. Confirmed whole-account deletion removes wholly owned transfers with
both portfolios atomically. History shows each side once, as Transfer Out/Transfer
In with its counterparty; the existing Entries count includes these visible rows.

## Dividend Income and realized earnings

`Dividend` is the valid persistence/domain model. These records are investment
cash dividends/distributions, regardless of monthly, quarterly, semi-annual,
annual or irregular payment schedules. They do not represent interest, staking,
rewards, airdrops or miscellaneous receipts.

Dividend Income increases Cash Balance, Book Value and Total Realized Earnings.
It does not change quantity, Position Cost Basis, Realized Trading P&L or trading return.
Total Realized Earnings is monetary, never an earnings/contributions percentage.

## Realized Trading Return — every scope

Sale, asset, portfolio and global return all use Realized Trading P&L divided by
Released Cost Basis, times 100. Aggregate numerator and denominator first; never
average percentages. Funding, Dividend Income, historical purchases not yet sold
and open Position Cost Basis are not ratio inputs.

Zero released basis means undefined: Python `None`, JSON `null`, display dash.
Positive released basis and zero P&L means genuine zero, displayed as `0.00%`.
BTC's sole sale realizes 3 against basis 555: approximately +0.5405405405% at every
scope, unaffected by withdrawing 558 and re-depositing 3.

Realized Trading Return is not total portfolio performance. Market prices,
unrealized P&L, TWR, MWR, XIRR and benchmarks are not implemented.

## User-facing placement

Internal/domain names optimize for financial precision; display labels optimize
for scanability. The mapping below is deliberate, not a second accounting model.

| Canonical identifier | Display label |
| --- | --- |
| net_contributions | Net Contributions |
| cash_balance | Cash |
| dividend_income | Dividends |
| realized_trading_pnl | Realized P&L |
| realized_trading_return | Realized Return |
| total_purchase_cost | Purchase Cost |
| average_unit_cost | Avg. Cost |
| position_cost_basis | Cost Basis |
| book_value | Book Value |

Overview: Book Value with Realized Return; supporting facts are Net Contributions,
Cash, Dividends and Realized P&L. Total Realized Earnings remains an internal/API
monetary measure; there is no redundant earnings card.

Portfolios: Funding Entries, Net Contributions, Cash and Cost Basis. No duplicated
Book Value summary and no help icons. Assets: Entries, Purchase Cost, Quantity,
Avg. Cost, Realized P&L, Realized Return and Dividends, without help icons.

Only Overview has help indicators, for Book Value, Net Contributions, Realized
P&L and Realized Return. Their concise text is respectively:

- Book Value = Cash + Cost Basis
- Net Contributions = Deposits − Withdrawals
- Realized P&L = Net Sale Proceeds − Released Cost Basis
- Realized Return = Realized P&L ÷ Released Cost Basis × 100

Shared info dots preserve hover/focus tooltips, keyboard focusability and accessible
labels. Cash and Dividends have no help icons. Number formatting, financial tones
and the original disclosure-button interaction are unchanged.
