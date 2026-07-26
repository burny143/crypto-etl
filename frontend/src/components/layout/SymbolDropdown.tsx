import { useState, useRef, useEffect, useMemo } from "react";
import { useTradeStore } from "@/stores/tradeStore";
import { Search, ChevronDown } from "lucide-react";
import { clsx } from "clsx";

export function SymbolDropdown() {
  const { symbols, selectedSymbol, setSymbol } = useTradeStore();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const selected = symbols.find((s) => s.symbol === selectedSymbol);

  const filtered = useMemo(() => {
    if (!query) return symbols;
    const q = query.toLowerCase();
    return symbols.filter(
      (s) =>
        s.symbol.toLowerCase().includes(q) ||
        (s.display_name ?? "").toLowerCase().includes(q) ||
        (s.base_asset ?? "").toLowerCase().includes(q),
    );
  }, [symbols, query]);

  // Close on click outside
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery("");
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Focus the search input when opening
  useEffect(() => {
    if (open && inputRef.current) {
      inputRef.current.focus();
    }
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        setQuery("");
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  const handleSelect = (symbol: string) => {
    setSymbol(symbol);
    setOpen(false);
    setQuery("");
  };

  return (
    <div ref={containerRef} className="relative min-w-[180px]">
      <button
        onClick={() => setOpen(!open)}
        className={clsx(
          "select-input w-full flex items-center gap-2 text-sm",
          open && "border-accent",
        )}
      >
        <span className="flex-1 text-left truncate">
          {selected ? (selected.display_name ?? selected.symbol) : "Select pair…"}
        </span>
        <ChevronDown
          className={clsx(
            "w-3.5 h-3.5 text-text-muted shrink-0 transition-transform",
            open && "rotate-180",
          )}
        />
      </button>

      {open && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-surface-alt border border-surface-border rounded-lg shadow-lg z-50 overflow-hidden">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-surface-border">
            <Search className="w-3.5 h-3.5 text-text-muted shrink-0" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search pairs…"
              className="bg-transparent text-sm text-text-primary placeholder:text-text-muted outline-none border-none w-full"
            />
          </div>

          <div className="max-h-[320px] overflow-y-auto">
            {filtered.length === 0 ? (
              <div className="px-3 py-6 text-center text-text-muted text-xs">
                No pairs matching "{query}"
              </div>
            ) : (
              filtered.map((s) => (
                <button
                  key={s.symbol}
                  onClick={() => handleSelect(s.symbol)}
                  className={clsx(
                    "w-full flex items-center gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-accent/10",
                    s.symbol === selectedSymbol
                      ? "bg-accent/10 text-accent font-semibold"
                      : "text-text-primary",
                  )}
                >
                  <span className="font-mono text-xs">{s.symbol}</span>
                  {s.display_name && s.display_name !== s.symbol && (
                    <span className="text-text-muted text-[11px] truncate ml-auto">
                      {s.display_name}
                    </span>
                  )}
                </button>
              ))
            )}
          </div>

          <div className="px-3 py-1.5 border-t border-surface-border text-[10px] text-text-muted text-center">
            {symbols.length} pairs
          </div>
        </div>
      )}
    </div>
  );
}
