import { useTradeStore } from "@/stores/tradeStore";
import type { Timeframe } from "@/types";
import { RefreshCw, BarChart3 } from "lucide-react";
import { clsx } from "clsx";
import { SymbolDropdown } from "./SymbolDropdown";

const TIMEFRAMES: Timeframe[] = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"];

export function TopBar() {
  const {
    symbols,
    selectedSymbol,
    selectedTimeframe,
    setTimeframe,
    loadOHLCV,
    refreshResearch,
    refreshPositions,
    refreshPortfolio,
    ohlcvLoading,
    showVolume,
    setShowVolume,
  } = useTradeStore();

  const handleRefresh = async () => {
    await loadOHLCV();
    await refreshResearch();
    await refreshPositions();
    await refreshPortfolio();
  };

  return (
    <header className="h-12 border-b border-surface-border bg-surface-alt flex items-center px-4 gap-4 shrink-0">
      <div className="flex items-center gap-2 mr-2">
        <div className="w-6 h-6 rounded-full bg-accent flex items-center justify-center">
          <span className="text-white text-xs font-bold">C</span>
        </div>
        <span className="text-sm font-semibold text-text-primary hidden sm:inline">
          Crypto Terminal
        </span>
      </div>

      <SymbolDropdown />

      <div className="flex gap-1 bg-surface rounded-md p-0.5 border border-surface-border">
        {TIMEFRAMES.map((tf) => (
          <button
            key={tf}
            onClick={() => setTimeframe(tf)}
            className={clsx(
              "px-2.5 py-1 text-[11px] font-mono font-medium rounded transition-colors",
              selectedTimeframe === tf
                ? "bg-accent text-white"
                : "text-text-secondary hover:text-text-primary",
            )}
          >
            {tf}
          </button>
        ))}
      </div>

      <button
        onClick={() => setShowVolume(!showVolume)}
        className={clsx(
          "flex items-center gap-1.5 px-2 py-1 rounded-md text-xs transition-colors",
          showVolume
            ? "bg-accent/20 text-accent"
            : "text-text-muted hover:text-text-secondary",
        )}
        title={showVolume ? "Hide volume" : "Show volume"}
      >
        <BarChart3 className="w-3.5 h-3.5" />
        <span className="hidden sm:inline text-xs">Vol</span>
      </button>

      <div className="flex-1" />

      <button
        onClick={handleRefresh}
        disabled={ohlcvLoading}
        className="btn-secondary flex items-center gap-1.5"
        title="Refresh all data"
      >
        <RefreshCw className={`w-3.5 h-3.5 ${ohlcvLoading ? "animate-spin" : ""}`} />
        <span className="hidden sm:inline text-xs">Refresh</span>
      </button>
    </header>
  );
}
