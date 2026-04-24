"""ClosedTrade — realized P&L snapshot for each sell transaction.

A record is created (or updated) automatically every time
recalculate_all_averages_for_symbol() runs and encounters a Sell.
Deletion is handled by database CASCADE:
  - Delete the sell Transaction  → ClosedTrade is deleted automatically.
  - Delete the tracked Symbol    → all its Transactions are deleted
                                   → all its ClosedTrades follow.
  - Delete the Portfolio         → same cascade chain.

The snapshot captures the average cost *at the moment of the sale*
(Average-Cost Method), so the realized P&L is historically accurate
even if earlier buy transactions are later edited.
"""

from datetime import datetime, timezone
from sqlalchemy import Numeric, Date
from portfolio_app import db


class ClosedTrade(db.Model):
    """Immutable-by-convention P&L snapshot for a single sell transaction."""

    __tablename__ = 'closed_trade'

    id = db.Column(db.Integer, primary_key=True)

    # Parent references — both carry DB-level CASCADE DELETE
    transaction_id = db.Column(
        db.Integer,
        db.ForeignKey('transaction.id', ondelete='CASCADE'),
        nullable=False,
        unique=True,
        index=True,
    )
    portfolio_id = db.Column(
        db.Integer,
        db.ForeignKey('portfolio.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    symbol = db.Column(db.String(20), nullable=False, index=True)

    # ── Snapshot values — locked at the moment of the sale ────────────
    quantity_sold = db.Column(Numeric(20, 10), nullable=False)
    avg_cost      = db.Column(Numeric(20, 10), nullable=False)
    sell_price    = db.Column(Numeric(20, 10), nullable=False)
    fees          = db.Column(Numeric(20, 10), nullable=False, default=0)

    # ── Derived — recomputed whenever recalculate_all_averages runs ───
    cost_basis     = db.Column(Numeric(20, 10), nullable=False)
    gross_proceeds = db.Column(Numeric(20, 10), nullable=False)
    realized_pnl   = db.Column(Numeric(20, 10), nullable=False)

    closed_at  = db.Column(Date, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id':             self.id,
            'transaction_id': self.transaction_id,
            'portfolio_id':   self.portfolio_id,
            'symbol':         self.symbol,
            'quantity_sold':  float(self.quantity_sold),
            'avg_cost':       float(self.avg_cost),
            'sell_price':     float(self.sell_price),
            'fees':           float(self.fees),
            'cost_basis':     float(self.cost_basis),
            'gross_proceeds': float(self.gross_proceeds),
            'realized_pnl':   float(self.realized_pnl),
            'closed_at':      self.closed_at.isoformat() if self.closed_at else None,
        }
