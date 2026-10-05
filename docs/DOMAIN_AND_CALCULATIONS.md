# Domain and Calculations

All financial calculations use `Decimal`.

## Realized P&L

Realized P&L is profit or loss from completed sales only.

Formula per sell:

`(sell price - average cost) * quantity - sell fees`

Average cost uses the Average Cost Method over chronological asset entries. Income is never added to Realized P&L.

### Average Cost Method Ordering

Asset entries are processed per portfolio and symbol in chronological order. When multiple entries share the same calendar date, buys are processed before sells, then rows are ordered by database id. This preserves deterministic average-cost behavior for same-day entries.

For buys:

`running cost += price * quantity + buy fees`

`running quantity += quantity`

For sells:

`average cost = running cost / running quantity`

`realized P&L += (sell price - average cost) * sold quantity - sell fees`

`running cost -= average cost * sold quantity`

`running quantity -= sold quantity`

## Total Income

Current Income records represent cash dividend/distribution income from investments,
regardless of payment schedule. They do not represent interest, staking, rewards,
airdrops, or miscellaneous income. The `Dividend` model is unchanged.
Dividend Income remains separate from Realized Trading P&L everywhere.

## Total Cash

`Total Cash = Total Capital - Buy outflows including fees + Sell proceeds after fees + Total Income`

Income increases Total Cash.

## Positions

Positions are the recorded cost basis of current asset quantities. Income does not affect Positions.

## Book Value

`Book Value = Total Cash + recorded cost basis of current positions`

Income affects Book Value through Total Cash.

## Realized Trading Return — All Scopes

`Realized Trading Return = Realized Trading P&L / Released Cost Basis * 100`

For an individual sale, use that sale's P&L and released basis. For an asset,
portfolio, or global view, sum realized trading P&L and released basis first,
then divide. Never average percentages. Buy fees are already capitalized in
released basis; sell fees already reduce proceeds/P&L. Do not deduct them again.

Dividend Income is excluded from the numerator. Deposits, withdrawals, historical
purchase outflows and still-open cost basis are excluded from the denominator.
Only the basis actually released by sales enters the denominator.

Zero released basis means undefined (`None` internally, JSON `null`, display `—`).
Zero P&L with positive released basis means a genuine zero percentage, displayed
by the existing formatter as `0.00%`.

## Total Realized Earnings

`Total Realized Earnings = Realized Trading P&L + Dividend Income`

This is a monetary measure, not a percentage. It reconciles as:

`Book Value = Net Contributions + Total Realized Earnings`

No Dividend Return or earnings/capital percentage is calculated. Realized Trading
Return is not total portfolio performance: market prices, unrealized P&L, TWR,
MWR and XIRR are not implemented.
