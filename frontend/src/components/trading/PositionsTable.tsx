import { useTradeStore } from "@/stores/tradeStore";
import { closePosition } from "@/lib/api";
import { Wallet, XCircle, Loader2, TrendingUp } from "lucide-react";
import { clsx } from "clsx";
import { useState } from "react";
import type { PaperPosition } from "@/types";

export function PositionsTable() {
  const { positions, portfolio, equityCurve, refreshPositions, refreshPortfolio } =
    useTradeStore();
  const [closingId, setClosingId] = useState<number | null>(null);

  const handleClose = async (pos: PaperPosition) => {
    setClosingId(pos.id);
    try {
      await closePosition({ symbol: pos.symbol, side: pos.side });
      await Promise.all([refreshPositions(), refreshPortfolio()]);
    } catch (err) {
      console.error("Close failed:", err);
    } finally {
      setClosingId(null);
    }
  };

  return (
    <div className="p-3">
      {portfolio && (
        <div className="grid grid-cols-2 gap-2 mb-3">
          <div className="bg-surface rounded p-2">
            <div className="text-[10px] text-text-muted">Equity</div>
            <div className="text-sm font-semibold font-mono text-text-primary">
              ${portfolio.total_equity.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </div>
          </div>
          <div className="bg-surface rounded p-2">
            <div className="text-[10px] text-text-muted">Cash</div>
            <div className="text-sm font-semibold font-mono text-text-primary">
              ${portfolio.cash.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </div>
          </div>
          <div className="bg-surface rounded p-2">
            <div className="text-[10px] text-text-muted">Unreal. P&L</div>
            <div className={clsx("text-sm font-semibold font-mono", portfolio.total_unrealized_pnl >= 0 ? "text-positive" : "text-negative")}>
              {portfolio.total_unrealized_pnl >= 0 ? "+" : ""}${portfolio.total_unrealized_pnl.toFixed(2)}
            </div>
          </div>
          <div className="bg-surface rounded p-2">
            <div className="text-[10px] text-text-muted">Real. P&L</div>
            <div className={clsx("text-sm font-semibold font-mono", portfolio.total_realized_pnl >= 0 ? "text-positive" : "text-negative")}>
              {portfolio.total_realized_pnl >= 0 ? "+" : ""}${portfolio.total_realized_pnl.toFixed(2)}
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center gap-2 mb-2">
        <Wallet className="w-4 h-4 text-accent" />
        <span className="panel-header flex-1">Positions ({positions.length})</span>
      </div>

      {positions.length === 0 ? (
        <div className="text-center py-6 text-text-muted">
          <TrendingUp className="w-6 h-6 mx-auto mb-1 opacity-30" />
          <p className="text-xs">No open positions</p>
          <p className="text-[10px] mt-0.5">Place a paper trade above</p>
        </div>
      ) : (
        <div className="space-y-1.5">
          {positions.map((pos) => (
            <div key={pos.id} className="bg-surface rounded p-2 border border-surface-border">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-semibold text-text-primary">{pos.symbol}</span>
                  <span className={clsx("text-[10px] font-semibold px-1 py-0.5 rounded", pos.side === "long" ? "bg-positive/10 text-positive" : "bg-negative/10 text-negative")}>
                    {pos.side}
                  </span>
                </div>
                <button
                  onClick={() => handleClose(pos)}
                  disabled={closingId === pos.id}
                  className="text-text-muted hover:text-negative transition-colors"
                  title="Close position"
                >
                  {closingId === pos.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <XCircle className="w-3.5 h-3.5" />}
                </button>
              </div>
              <div className="grid grid-cols-3 gap-1 text-[10px]">
                <div>
                  <span className="text-text-muted">Qty</span>
                  <div className="font-mono text-text-primary">{pos.quantity}</div>
                </div>
                <div>
                  <span className="text-text-muted">Entry</span>
                  <div className="font-mono text-text-primary">
                    ${pos.entry_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </div>
                </div>
                <div>
                  <span className="text-text-muted">P&L</span>
                  <div className={clsx("font-mono", (pos.unrealized_pnl ?? 0) >= 0 ? "text-positive" : "text-negative")}>
                    {pos.unrealized_pnl != null ? `${pos.unrealized_pnl >= 0 ? "+" : ""}$${pos.unrealized_pnl.toFixed(2)}` : "—"}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {equityCurve.length > 1 && (
        <div className="mt-3 pt-2 border-t border-surface-border">
          <div className="flex items-center gap-1 mb-1">
            <span className="text-[10px] text-text-muted">Equity Progress</span>
          </div>
          <div className="h-1.5 bg-surface rounded-full overflow-hidden">
            <div
              className="h-full bg-accent rounded-full transition-all"
              style={{ width: `${Math.min(100, ((portfolio?.total_equity ?? 100000) / 200000) * 100)}%` }}
            />
          </div>
          <div className="flex justify-between text-[9px] text-text-muted mt-0.5">
            <span>$100K</span>
            <span>$200K</span>
          </div>
        </div>
      )}
    </div>
  );
}
