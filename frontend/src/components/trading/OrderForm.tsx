import { useState } from "react";
import { useTradeStore } from "@/stores/tradeStore";
import { placeOrder } from "@/lib/api";
import { ShoppingCart, Loader2, DollarSign } from "lucide-react";
import { clsx } from "clsx";

export function OrderForm() {
  const { selectedSymbol, refreshPositions, refreshPortfolio } = useTradeStore();

  const [side, setSide] = useState<"long" | "short">("long");
  const [quantity, setQuantity] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedSymbol || !quantity) return;

    const qty = parseFloat(quantity);
    if (isNaN(qty) || qty <= 0) {
      setError("Enter a valid quantity");
      return;
    }

    setSubmitting(true);
    setError(null);
    setSuccess(null);

    try {
      const result = await placeOrder({
        symbol: selectedSymbol,
        side,
        quantity: qty,
      });
      setSuccess(`${side === "long" ? "Bought" : "Shorted"} ${qty} ${selectedSymbol} @ $${result.fill_price?.toFixed(2) ?? "market"}`);
      setQuantity("");
      await Promise.all([refreshPositions(), refreshPortfolio()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Order failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="p-3 shrink-0">
      <div className="flex items-center gap-2 mb-2">
        <ShoppingCart className="w-4 h-4 text-accent" />
        <span className="panel-header flex-1">Paper Trade</span>
        {selectedSymbol && (
          <span className="text-[10px] text-text-muted font-mono">{selectedSymbol}</span>
        )}
      </div>

      <form onSubmit={handleSubmit} className="space-y-2">
        <div className="flex gap-1">
          <button
            type="button"
            onClick={() => setSide("long")}
            className={clsx(
              "flex-1 py-1.5 rounded text-xs font-semibold transition-colors",
              side === "long"
                ? "bg-positive text-white"
                : "bg-surface-alt text-text-secondary hover:text-text-primary",
            )}
          >
            Buy / Long
          </button>
          <button
            type="button"
            onClick={() => setSide("short")}
            className={clsx(
              "flex-1 py-1.5 rounded text-xs font-semibold transition-colors",
              side === "short"
                ? "bg-negative text-white"
                : "bg-surface-alt text-text-secondary hover:text-text-primary",
            )}
          >
            Sell / Short
          </button>
        </div>

        <div className="relative">
          <DollarSign className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-muted" />
          <input
            type="number"
            step="any"
            min="0"
            placeholder="Quantity (e.g. 0.01)"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            className="text-input w-full pl-7 text-xs"
            disabled={submitting}
          />
        </div>

        {error && <p className="text-[11px] text-negative">{error}</p>}
        {success && <p className="text-[11px] text-positive">{success}</p>}

        <button
          type="submit"
          disabled={submitting || !quantity || !selectedSymbol}
          className={clsx(
            "w-full py-1.5 rounded text-xs font-semibold transition-colors flex items-center justify-center gap-1.5",
            side === "long"
              ? "bg-positive text-white hover:bg-green-500 disabled:bg-positive/30"
              : "bg-negative text-white hover:bg-red-500 disabled:bg-negative/30",
          )}
        >
          {submitting && <Loader2 className="w-3 h-3 animate-spin" />}
          {side === "long" ? "Open Long Position" : "Open Short Position"}
        </button>
      </form>
    </div>
  );
}
