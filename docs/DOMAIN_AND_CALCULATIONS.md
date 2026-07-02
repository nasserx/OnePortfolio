# Domain and Calculations

All financial calculations use `Decimal`.

## Realized P&L

Realized P&L is trading profit or loss from `Sell` transactions only.

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

Total Income is the sum of Income records only. It remains separate from Realized P&L everywhere.

## Total Cash

`Total Cash = Total Capital - Buy outflows including fees + Sell proceeds after fees + Total Income`

Income increases Total Cash.

## Positions

Positions are the cost basis of currently open asset quantities. Income does not affect Positions.

## Book Value

`Book Value = Total Cash + Positions`

Income affects Book Value through Total Cash.

## Portfolio Return

`Portfolio Return = (Realized P&L + Total Income) / Gross Deposits * 100`

The denominator is gross deposits: Initial and Deposit capital entries only. Withdrawals do not reduce this denominator.

When gross deposits are zero, the internal numeric percentage remains zero where a number is required, and the display value is `—`.

## Asset Return

`Asset Return = (Asset Realized P&L + Asset Income) / Total Buy Cost * 100`

The denominator is total buy cost, including buy fees.

When total buy cost is zero, the internal numeric percentage remains zero where a number is required, and the display value is `—`.
