import type {
  IndicatorPoint,
  PaperOrder,
  PaperPosition,
  PortfolioSummary,
  EquityPoint,
  ResearchEntry,
  TechnicalSummary,
  SignalConfig,
  SignalResponse,
  SymbolMeta,
} from "@/types";

const API_BASE = "/api/v1";

// ─── Symbols ───

export async function fetchSymbols(): Promise<SymbolMeta[]> {
  const { supabase } = await import("./supabase");
  const { data, error } = await supabase
    .from("symbols")
    .select("*")
    .eq("active", true)
    .order("sort_order");

  if (error) {
    console.error("Failed to fetch symbols:", error);
    return [];
  }
  return data ?? [];
}

// ─── OHLCV ───

export interface FetchOHLCVParams {
  symbol: string;
  timeframe: string;
  limit?: number;
  startDate?: string;
  endDate?: string;
}

export async function fetchOHLCV({
  symbol,
  timeframe,
  limit = 500,
  startDate,
  endDate,
}: FetchOHLCVParams) {
  const { supabase } = await import("./supabase");

  let query = supabase
    .from("crypto_historical")
    .select("datetime,open,high,low,close,volume,bar_change_pct")
    .eq("symbol", symbol)
    .eq("timeframe", timeframe)
    .order("datetime", { ascending: false })
    .limit(limit);

  if (startDate) query = query.gte("datetime", startDate);
  if (endDate) query = query.lte("datetime", endDate);

  const { data, error } = await query;

  if (error) {
    console.error("OHLCV fetch error:", error);
    return [];
  }

  return (data ?? []).reverse();
}

/**
 * Fetch older bars before a given datetime (paginated scroll-back).
 * Returns empty array when no more history exists.
 */
export async function fetchOlderOHLCV(params: {
  symbol: string;
  timeframe: string;
  before: string;
  limit?: number;
}): Promise<OHLCVBarRaw[]> {
  const { supabase } = await import("./supabase");
  const { symbol, timeframe, before, limit = 500 } = params;

  const { data, error } = await supabase
    .from("crypto_historical")
    .select("datetime,open,high,low,close,volume,bar_change_pct")
    .eq("symbol", symbol)
    .eq("timeframe", timeframe)
    .lt("datetime", before)
    .order("datetime", { ascending: false })
    .limit(limit);

  if (error) {
    console.error("OHLCV fetch older error:", error);
    return [];
  }
  return (data ?? []).reverse();
}

/** Raw row shape returned by Supabase for OHLCV queries */
export interface OHLCVBarRaw {
  datetime: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  bar_change_pct?: number;
}

// ─── Indicators ───

export interface IndicatorQuery {
  symbol: string;
  timeframe: string;
  indicator_name: string;
  params?: Record<string, number>;
  force_recompute?: boolean;
}

export async function fetchIndicator(query: IndicatorQuery): Promise<IndicatorPoint[]> {
  const params = new URLSearchParams();
  if (query.params) {
    for (const [key, value] of Object.entries(query.params)) {
      params.set(key, String(value));
    }
  }
  if (query.force_recompute) params.set("force_recompute", "true");
  params.set("limit", "500");

  try {
    const res = await fetch(
      `${API_BASE}/indicators/${query.symbol}/${query.timeframe}/${query.indicator_name}?${params}`,
    );
    if (!res.ok) return [];
    const json = await res.json();
    return json.values ?? [];
  } catch (err) {
    console.error("Indicator fetch error:", err);
    return [];
  }
}

// ─── Research ───

export async function fetchResearch(
  symbol: string,
  limit = 20,
): Promise<ResearchEntry[]> {
  try {
    const res = await fetch(`${API_BASE}/research/${symbol}?limit=${limit}`);
    if (!res.ok) return [];
    const json = await res.json();
    return json.entries ?? [];
  } catch (err) {
    console.error("Research fetch error:", err);
    return [];
  }
}

export async function fetchTechnicalAnalysis(
  symbol: string,
  timeframe: string,
): Promise<TechnicalSummary | null> {
  try {
    const res = await fetch(
      `${API_BASE}/research/analysis/${symbol}/${timeframe}`,
    );
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.error("Technical analysis error:", err);
    return null;
  }
}

// ─── Paper Trading ───

export async function placeOrder(params: {
  symbol: string;
  side: "long" | "short";
  quantity: number;
  order_type?: string;
  price?: number | null;
  notes?: string;
}) {
  const res = await fetch(`${API_BASE}/paper/orders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...params, order_type: params.order_type ?? "market" }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return await res.json();
}

export async function closePosition(params: {
  symbol: string;
  side: "long" | "short";
  quantity?: number;
}) {
  const res = await fetch(`${API_BASE}/paper/close`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return await res.json();
}

export async function fetchPositions(): Promise<PaperPosition[]> {
  try {
    const res = await fetch(`${API_BASE}/paper/positions`);
    if (!res.ok) return [];
    const json = await res.json();
    return json.positions ?? [];
  } catch {
    return [];
  }
}

export async function fetchOrders(symbol?: string): Promise<PaperOrder[]> {
  const params = symbol ? `?symbol=${symbol}` : "";
  try {
    const res = await fetch(`${API_BASE}/paper/orders${params}`);
    if (!res.ok) return [];
    const json = await res.json();
    return json.orders ?? [];
  } catch {
    return [];
  }
}

export async function fetchPortfolio(): Promise<PortfolioSummary | null> {
  try {
    const res = await fetch(`${API_BASE}/paper/portfolio`);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function fetchEquityCurve(): Promise<EquityPoint[]> {
  try {
    const res = await fetch(`${API_BASE}/paper/equity`);
    if (!res.ok) return [];
    const json = await res.json();
    return json.equity_curve ?? [];
  } catch {
    return [];
  }
}

export async function resetPaperAccount() {
  const res = await fetch(`${API_BASE}/paper/reset`, { method: "POST" });
  if (!res.ok) throw new Error("Reset failed");
  return await res.json();
}

// ─── Signal Engine ───

export async function fetchSignal(
  symbol: string,
  timeframe: string,
  config: SignalConfig,
  limit = 500,
): Promise<SignalResponse | null> {
  try {
    const res = await fetch(`${API_BASE}/signal`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol,
        timeframe,
        conditions: config.conditions,
        logic: config.logic,
        limit,
      }),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.error("Signal fetch error:", err);
    return null;
  }
}
