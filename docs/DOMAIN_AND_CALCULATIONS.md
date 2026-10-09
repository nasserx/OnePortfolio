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
| Purchase Cost Return | Total Realized Earnings ÷ historical Purchase Cost × 100 | `purchase_cost_return` |
| Paid-In Capital | Portfolio: gross external deposits + Transfer In; account: gross external deposits only | `paid_in_capital` |
| Capital Return | Total Realized Earnings ÷ Paid-In Capital × 100 | `capital_return` |
| Funding Entries | Initial funding, deposits and withdrawals recorded by `PortfolioEvent` | Existing event model |
| Asset Entries | Buy, Sell and Dividend records displayed for an asset | Existing transaction/dividend models |

Gross deposits (`gross_deposits`) are Initial + Deposit inflows before withdrawals.
They are not Net Contributions. They form the consolidated return denominator;
portfolio return also includes incoming internal transfers.

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

## Cumulative accounting returns

Displayed Cumulative P&L is `total_realized_earnings`: Realized Trading P&L + cash Dividends.
The percentage is cumulative and non-annualized; investment duration is not an
input. It is an accounting ratio, not market-based investment performance.

- Assets: earnings divided by historical Purchase Cost, including buy fees.
- Overview portfolio rows: earnings divided by gross external deposits (including
  Initial funding and redeposits) plus all incoming internal transfers.
- Overview Book Value card: consolidated earnings divided by gross external
  deposits only. Never sum portfolio capital bases containing transfers or average
  their percentages.

Withdrawals and outgoing transfers do not reduce historical paid-in capital.
Repeated deposits and incoming transfer round trips increase it and can dilute
local return. Internal transfers never change consolidated earnings or capital.
Reinvesting retained profits/dividends is not a portfolio contribution; each new
purchase does increase historical asset Purchase Cost. Different scope returns
are therefore intentional, even for the same symbol or reused money.

Deposit 1,000 and earn 1,500: Book Value 2,500 and Return +150%, regardless of
duration. Withdraw all 2,500: earnings and Return remain 1,500 and +150%, although
Net Contributions is -1,500. Redeposit 1,000: paid-in capital becomes 2,000 and
Return +75%. An internal transfer round trip of 1,000 produces the same dilution
in the receiving portfolio, but consolidated Return remains +150%.

Positive capital permits negative, positive, or zero earnings. Zero capital is
undefined (`None` / JSON `null` / display dash), not 0%. Negative capital is invalid
and raises a calculation error; it is never clamped or converted to an absolute
value. Dividend-only assets show earnings but no percentage without purchases;
their earnings still contribute to a funded portfolio's return. Closed assets
retain historical earnings and Purchase Cost. Open assets remain at cost; no
unrealized market gain/loss is inferred.

Reconcile earnings independently as Book Value + Withdrawals + Transfer Out
- Deposits - Transfer In at portfolio scope, or Book Value + Withdrawals -
Deposits at account scope. Dividends are already in Book Value through cash;
do not add them again to these identities.

All history means the current authoritative records. Edits/deletions update
derived results; append-only audit revisions are evidence, never calculation inputs.

## Retained Realized Trading Return

The retained sale, asset, portfolio and global trading-return fields use Realized Trading P&L divided by
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
| total_realized_earnings | Cumulative P&L (summaries) |
| purchase_cost_return / capital_return | Return (summaries) |
| realized_trading_pnl | Realized P&L (sale rows) |
| realized_trading_return | Return (sale rows, including accessible label and hover text) |
| transaction_amount | Total Amount (shared Buy/Sell column) |
| total_purchase_cost | Purchase Cost |
| average_unit_cost | Avg. Cost |
| position_cost_basis | Cost Basis |
| book_value | Book Value |

Overview: Book Value hero, then Cumulative P&L with the Return pill;
supporting facts are Net Contributions, Cash and Dividends. P&L includes dividends
in the existing slot; there is no additional earnings card.

Portfolios: Entries, Net Contributions, Cash and Cost Basis. No duplicated
Book Value summary and no help icons. Assets: Entries, Purchase Cost, Quantity,
Avg. Cost, Cumulative P&L, Return and Dividends, without help icons.

Expanded Assets transaction rows use Realized P&L and Return (including accessible
label and hover text), retaining sale-specific calculations without
attributing dividends to individual sales. The short Return header fits the
existing narrow column without changing the table layout.

The shared Buy/Sell column remains Total Amount: Purchase Cost including fees for
buys, Net Proceeds after fees for sells. The calculated form preview uses Purchase
Cost for buys and Net Proceeds for sells. Internal `realized_trading_*` identifiers
and API fields retain their precise trading-only meanings.

Only Overview has help indicators: Book Value, Net Contributions and one shared
Cumulative P&L / Return indicator after the return pill. Their formulas are:

- **Book Value** = Cash + Cost Basis
- **Net Contributions** = Deposits − Withdrawals
- **Cumulative P&L** = Net Sale Proceeds − Released Cost Basis + Dividends
- **Return** = Cumulative P&L ÷ Gross External Deposits × 100

The shared indicator contains exactly the last two formula lines, explaining
only the consolidated metrics. Gross External Deposits includes Initial funding
and Deposit events, each counted once; Initial funding is not added again.
Asset and portfolio return policies remain documented above, not in this tooltip.
Only the leading metric names are bold, not the equals signs or formulas.

Shared info dots preserve hover/focus tooltips, keyboard focusability and accessible
labels. Cash and Dividends have no help icons. Number formatting, financial tones
and the original disclosure-button interaction are unchanged.
