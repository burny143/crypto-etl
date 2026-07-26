import { useState } from "react";
import { useTradeStore } from "@/stores/tradeStore";
import { LineChart, ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { clsx } from "clsx";

export function IndicatorControls() {
  const { indicators, MAX_VISIBLE_INDICATORS, toggleIndicator, updateIndicatorParams } = useTradeStore();
  const [expanded, setExpanded] = useState<string | null>(null);

  const enabledCount = indicators.filter((i) => i.enabled).length;
  const atLimit = enabledCount >= MAX_VISIBLE_INDICATORS;

  return (
    <div className="flex flex-col h-full">
      <div className="p-3 border-b border-surface-border shrink-0">
        <div className="flex items-center gap-2">
          <LineChart className="w-4 h-4 text-accent" />
          <span className="panel-header flex-1">Indicators</span>
          <span className="text-[10px] text-text-muted">
            {enabledCount}/{MAX_VISIBLE_INDICATORS} on chart
          </span>
        </div>
        {atLimit && (
          <p className="text-[10px] text-yellow-500 mt-1 leading-tight">
            Max {MAX_VISIBLE_INDICATORS} on chart — disable one first
          </p>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {indicators.map((ind) => {
          const isExpanded = expanded === ind.def.name;
          const disabled = !ind.enabled && atLimit;
          return (
            <div
              key={ind.def.name}
              className={clsx(
                "rounded-md transition-colors",
                ind.enabled ? "bg-accent/5" : "hover:bg-surface-alt/50",
                disabled && "opacity-40",
              )}
            >
              <div className="flex items-center gap-2 px-2 py-1.5">
                <button
                  onClick={() => !disabled && toggleIndicator(ind.def.name)}
                  className={clsx(
                    "w-8 h-4 rounded-full relative transition-colors shrink-0",
                    ind.enabled
                      ? "bg-accent"
                      : disabled
                        ? "bg-surface-border/40 cursor-not-allowed"
                        : "bg-surface-border",
                  )}
                >
                  <div
                    className={clsx(
                      "w-3 h-3 bg-white rounded-full absolute top-0.5 transition-all",
                      ind.enabled ? "left-4" : "left-0.5",
                    )}
                  />
                </button>

                <span
                  className={clsx(
                    "text-xs flex-1",
                    ind.enabled ? "text-text-primary font-medium" : "text-text-secondary",
                  )}
                >
                  {ind.def.label}
                </span>

                {ind.loading && <Loader2 className="w-3 h-3 text-text-muted animate-spin" />}

                {ind.def.params.length > 0 && (
                  <button
                    onClick={() => setExpanded(isExpanded ? null : ind.def.name)}
                    className="text-text-muted hover:text-text-primary"
                  >
                    {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                  </button>
                )}
              </div>

              {isExpanded && ind.def.params.length > 0 && (
                <div className="px-3 pb-2 space-y-1.5">
                  {ind.def.params.map((param) => (
                    <div key={param.key} className="flex items-center gap-2">
                      <label className="text-[10px] text-text-muted w-14 shrink-0">
                        {param.label}
                      </label>
                      <input
                        type="number"
                        min={param.min}
                        max={param.max}
                        step={param.type === "float" ? 0.5 : 1}
                        value={ind.params[param.key] ?? param.default}
                        onChange={(e) => {
                          const val =
                            param.type === "float"
                              ? parseFloat(e.target.value)
                              : parseInt(e.target.value, 10);
                          if (!isNaN(val)) {
                            updateIndicatorParams(ind.def.name, {
                              ...ind.params,
                              [param.key]: val,
                            });
                          }
                        }}
                        className="text-input w-full text-[11px] py-1"
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
