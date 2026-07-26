import { useState, useCallback } from "react";
import { useTradeStore } from "@/stores/tradeStore";
import { AVAILABLE_INDICATORS } from "@/types";
import type { SignalConfig, SignalCondition, SignalOperator, SignalSide, SignalLogic } from "@/types";

const OPERATORS: { value: SignalOperator; label: string }[] = [
  { value: "gt", label: ">" },
  { value: "lt", label: "<" },
  { value: "cross_above", label: "Cross ↑" },
  { value: "cross_below", label: "Cross ↓" },
];

export function SignalPanel() {
  const { signalResult, signalLoading, signalError, runSignal, clearSignal } = useTradeStore();
  const [conditions, setConditions] = useState<SignalCondition[]>([
    {
      indicator: "rsi",
      params: { period: 14 },
      operator: "lt",
      value: 30,
      side: "long",
    },
  ]);
  const [logic, setLogic] = useState<SignalLogic>("any");

  const addCondition = useCallback(() => {
    setConditions((prev) => [
      ...prev,
      {
        indicator: "rsi",
        params: { period: 14 },
        operator: "lt",
        value: 30,
        side: "long",
      },
    ]);
  }, []);

  const removeCondition = useCallback((index: number) => {
    setConditions((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const updateCondition = useCallback(
    (index: number, patch: Partial<SignalCondition>) => {
      setConditions((prev) =>
        prev.map((c, i) => (i === index ? { ...c, ...patch } : c)),
      );
    },
    [],
  );

  const handleRun = useCallback(() => {
    const config: SignalConfig = { conditions, logic };
    runSignal(config);
  }, [conditions, logic, runSignal]);

  const disabled = signalLoading || conditions.length === 0;

  return (
    <div className="p-3 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-text uppercase tracking-wider">
          Signal Engine
        </h3>
        {signalResult && (
          <button
            onClick={clearSignal}
            className="text-[10px] text-text-muted hover:text-text transition-colors"
          >
            Clear
          </button>
        )}
      </div>

      {/* Conditions */}
      <div className="space-y-2 max-h-[300px] overflow-y-auto">
        {conditions.map((cond, i) => (
          <ConditionRow
            key={i}
            condition={cond}
            onChange={(patch) => updateCondition(i, patch)}
            onRemove={() => removeCondition(i)}
          />
        ))}
      </div>

      {/* Add condition */}
      {conditions.length < 5 && (
        <button
          onClick={addCondition}
          className="w-full text-[11px] text-accent hover:text-accent-hover border border-dashed border-surface-border rounded py-1.5 transition-colors"
        >
          + Add Condition
        </button>
      )}

      {/* Logic selector */}
      <div className="flex items-center gap-2">
        <label className="text-[11px] text-text-muted">Logic:</label>
        <select
          value={logic}
          onChange={(e) => setLogic(e.target.value as SignalLogic)}
          className="flex-1 bg-surface-alt border border-surface-border rounded px-2 py-1 text-[11px] text-text outline-none focus:border-accent"
        >
          <option value="any">Any (OR)</option>
          <option value="all">All (AND)</option>
        </select>
      </div>

      {/* Run button */}
      <button
        onClick={handleRun}
        disabled={disabled}
        className={`w-full py-1.5 rounded text-[11px] font-medium transition-colors ${
          disabled
            ? "bg-surface-alt text-text-muted cursor-not-allowed"
            : "bg-accent text-white hover:bg-accent-hover"
        }`}
      >
        {signalLoading ? "Computing…" : "Run Signal"}
      </button>

      {/* Error */}
      {signalError && (
        <div className="text-[10px] text-red-400 bg-red-400/10 rounded p-2">
          {signalError}
        </div>
      )}

      {/* Results summary */}
      {signalResult && (
        <div className="space-y-1 text-[10px] text-text-muted">
          <div className="font-semibold text-text text-[11px]">Signal Summary</div>
          <div className="flex gap-3">
            <span className="text-green-400">
              Buy: {signalResult.filter((s) => s.signal === 1).length}
            </span>
            <span className="text-red-400">
              Sell: {signalResult.filter((s) => s.signal === -1).length}
            </span>
            <span>
              Neutral: {signalResult.filter((s) => s.signal === 0).length}
            </span>
          </div>
          {signalResult.length > 0 && (
            <div className="text-[9px]">
              Last: {signalResult[signalResult.length - 1]?.signal === 1 ? "BUY" : signalResult[signalResult.length - 1]?.signal === -1 ? "SELL" : "NEUTRAL"}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Condition Row ───

interface ConditionRowProps {
  condition: SignalCondition;
  onChange: (patch: Partial<SignalCondition>) => void;
  onRemove: () => void;
}

function ConditionRow({ condition, onChange, onRemove }: ConditionRowProps) {
  const indicatorDef = AVAILABLE_INDICATORS.find((d) => d.name === condition.indicator);
  const hasValueKey = indicatorDef && ["bb", "macd", "stoch_rsi", "kc"].includes(indicatorDef.name);

  return (
    <div className="bg-surface-alt rounded p-2 space-y-1.5 border border-surface-border">
      {/* Header */}
      <div className="flex items-center justify-between">
        <select
          value={condition.indicator}
          onChange={(e) => onChange({ indicator: e.target.value })}
          className="flex-1 bg-surface border border-surface-border rounded px-1.5 py-1 text-[11px] text-text outline-none focus:border-accent"
        >
          {AVAILABLE_INDICATORS.map((def) => (
            <option key={def.name} value={def.name}>
              {def.label}
            </option>
          ))}
        </select>
        <button
          onClick={onRemove}
          className="ml-1.5 text-red-400 hover:text-red-300 text-[13px] leading-none p-0.5"
          title="Remove condition"
        >
          ×
        </button>
      </div>

      {/* Params inline */}
      <div className="flex flex-wrap gap-1">
        {indicatorDef?.params.map((p) => (
          <label key={p.key} className="flex items-center gap-1 text-[10px] text-text-muted">
            {p.label}:
            <input
              type="number"
              value={condition.params[p.key] ?? p.default}
              onChange={(e) =>
                onChange({
                  params: { ...condition.params, [p.key]: Number(e.target.value) },
                })
              }
              min={p.min}
              max={p.max}
              className="w-12 bg-surface border border-surface-border rounded px-1 py-0.5 text-[10px] text-text outline-none focus:border-accent"
            />
          </label>
        ))}
      </div>

      {/* Value key for multi-value indicators */}
      {hasValueKey && (
        <div className="flex items-center gap-1">
          <span className="text-[10px] text-text-muted">Band:</span>
          <select
            value={condition.value_key ?? "mid"}
            onChange={(e) => onChange({ value_key: e.target.value })}
            className="flex-1 bg-surface border border-surface-border rounded px-1.5 py-0.5 text-[10px] text-text outline-none focus:border-accent"
          >
            {indicatorDef?.name === "bb" || indicatorDef?.name === "kc" ? (
              <>
                <option value="upper">Upper</option>
                <option value="mid">Mid</option>
                <option value="lower">Lower</option>
              </>
            ) : indicatorDef?.name === "macd" ? (
              <>
                <option value="macd">MACD</option>
                <option value="signal">Signal</option>
                <option value="hist">Histogram</option>
              </>
            ) : (
              <>
                <option value="k">K</option>
                <option value="d">D</option>
              </>
            )}
          </select>
        </div>
      )}

      {/* Operator + value + side */}
      <div className="flex items-center gap-1">
        <select
          value={condition.operator}
          onChange={(e) => onChange({ operator: e.target.value as SignalOperator })}
          className="bg-surface border border-surface-border rounded px-1 py-0.5 text-[10px] text-text outline-none focus:border-accent"
        >
          {OPERATORS.map((op) => (
            <option key={op.value} value={op.value}>
              {op.label}
            </option>
          ))}
        </select>
        <input
          type="number"
          value={condition.value}
          onChange={(e) => onChange({ value: Number(e.target.value) })}
          className="w-16 bg-surface border border-surface-border rounded px-1 py-0.5 text-[10px] text-text outline-none focus:border-accent"
        />
        <select
          value={condition.side}
          onChange={(e) => onChange({ side: e.target.value as SignalSide })}
          className={`ml-auto bg-surface border border-surface-border rounded px-1 py-0.5 text-[10px] outline-none focus:border-accent ${
            condition.side === "long" ? "text-green-400" : "text-red-400"
          }`}
        >
          <option value="long">LONG</option>
          <option value="short">SHORT</option>
        </select>
      </div>
    </div>
  );
}
