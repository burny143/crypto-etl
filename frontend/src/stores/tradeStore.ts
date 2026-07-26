import { create } from "zustand";
import type {
  OHLCVBar,
  SymbolMeta,
  Timeframe,
  IndicatorState,
  PaperPosition,
  PortfolioSummary,
  EquityPoint,
  ResearchEntry,
  TechnicalSummary,
  SignalConfig,
  SignalPoint,
} from "@/types";
import { AVAILABLE_INDICATORS } from "@/types";
import * as api from "@/lib/api";

export interface TradeStore {
  symbols: SymbolMeta[];
  selectedSymbol: string | null;
  selectedTimeframe: Timeframe;
  loadingSymbols: boolean;

  ohlcvData: OHLCVBar[];
  ohlcvLoading: boolean;
  /** Earliest datetime in ohlcvData (for pagination cursor) */
  earliestDate: string | null;
  /** Whether older bars may exist before earliestDate */
  hasMoreHistory: boolean;
  /** Loading more history (pagination, not initial load) */
  loadingMore: boolean;

  indicators: IndicatorState[];

  researchEntries: ResearchEntry[];
  technicalAnalysis: TechnicalSummary | null;
  researchLoading: boolean;

  positions: PaperPosition[];
  portfolio: PortfolioSummary | null;
  equityCurve: EquityPoint[];
  tradingLoading: boolean;

  showVolume: boolean;
  MAX_VISIBLE_INDICATORS: number;

  // Signal engine
  signalConfig: SignalConfig | null;
  signalResult: SignalPoint[] | null;
  signalLoading: boolean;
  signalError: string | null;

  init: () => Promise<void>;
  setSymbol: (symbol: string) => Promise<void>;
  setTimeframe: (tf: Timeframe) => Promise<void>;
  setShowVolume: (v: boolean) => void;
  loadOHLCV: () => Promise<void>;
  loadMoreHistory: () => Promise<void>;
  toggleIndicator: (name: string) => Promise<void>;
  updateIndicatorParams: (name: string, params: Record<string, number>) => Promise<void>;
  refreshResearch: () => Promise<void>;
  refreshPositions: () => Promise<void>;
  refreshPortfolio: () => Promise<void>;
  runSignal: (config: SignalConfig) => Promise<void>;
  clearSignal: () => void;
}

export const useTradeStore = create<TradeStore>((set, get) => ({
  symbols: [],
  selectedSymbol: null,
  selectedTimeframe: "1d",
  loadingSymbols: true,

  ohlcvData: [],
  ohlcvLoading: false,
  earliestDate: null,
  hasMoreHistory: true,
  loadingMore: false,

  indicators: AVAILABLE_INDICATORS.map((def) => ({
    def,
    enabled: false,
    params: { ...def.defaultParams },
    loading: false,
  })),

  researchEntries: [],
  technicalAnalysis: null,
  researchLoading: false,

  showVolume: true,

  signalConfig: null,
  signalResult: null,
  signalLoading: false,
  signalError: null,

  positions: [],
  portfolio: null,
  equityCurve: [],
  tradingLoading: false,

  init: async () => {
    const symbols = await api.fetchSymbols();
    set({ symbols, loadingSymbols: false });
    if (symbols.length > 0) {
      const first = symbols[0].symbol;
      set({ selectedSymbol: first });
      await get().loadOHLCV();
      await get().refreshResearch();
      await get().refreshPositions();
      await get().refreshPortfolio();
    }
  },

  setSymbol: async (symbol: string) => {
    set({ selectedSymbol: symbol, ohlcvData: [], researchEntries: [], technicalAnalysis: null });
    await get().loadOHLCV();
    await get().refreshResearch();
    await get().refreshPositions();
  },

  setTimeframe: async (tf: Timeframe) => {
    set({ selectedTimeframe: tf });
    await get().loadOHLCV();
    await get().refreshResearch();
  },

  setShowVolume: (v: boolean) => {
    set({ showVolume: v });
  },

  loadOHLCV: async () => {
    const { selectedSymbol, selectedTimeframe } = get();
    if (!selectedSymbol) return;

    set({ ohlcvLoading: true, loadingMore: false, hasMoreHistory: true });
    const data = await api.fetchOHLCV({
      symbol: selectedSymbol,
      timeframe: selectedTimeframe,
      limit: 500,
    });
    const earliest = data.length > 0 ? data[0].datetime : null;
    set({
      ohlcvData: data,
      earliestDate: earliest,
      hasMoreHistory: data.length >= 500,
      ohlcvLoading: false,
    });
  },

  loadMoreHistory: async () => {
    const { selectedSymbol, selectedTimeframe, earliestDate, loadingMore, hasMoreHistory } = get();
    if (!selectedSymbol || !earliestDate || loadingMore || !hasMoreHistory) return;

    set({ loadingMore: true });
    const older = await api.fetchOlderOHLCV({
      symbol: selectedSymbol,
      timeframe: selectedTimeframe,
      before: earliestDate,
      limit: 500,
    });

    if (older.length === 0) {
      set({ hasMoreHistory: false, loadingMore: false });
      return;
    }

    const current = get().ohlcvData;
    const merged = [...older, ...current];
    set({
      ohlcvData: merged,
      earliestDate: older[0].datetime,
      hasMoreHistory: older.length >= 500,
      loadingMore: false,
    });
  },

  MAX_VISIBLE_INDICATORS: 3,

  toggleIndicator: async (name: string) => {
    const { indicators, selectedSymbol, selectedTimeframe } = get();
    if (!selectedSymbol) return;

    const enabledCount = indicators.filter((i) => i.enabled).length;

    const updated = indicators.map(async (ind) => {
      if (ind.def.name !== name) return ind;

      if (ind.enabled) {
        return { ...ind, enabled: false, data: undefined };
      }

      // Enforce max 3 visible on chart
      if (enabledCount >= get().MAX_VISIBLE_INDICATORS) {
        return ind;
      }

      const data = await api.fetchIndicator({
        symbol: selectedSymbol,
        timeframe: selectedTimeframe,
        indicator_name: name,
        params: ind.params,
      });

      return { ...ind, enabled: true, data, loading: false };
    });

    const resolved = await Promise.all(updated);
    set({ indicators: resolved });
  },

  updateIndicatorParams: async (name: string, params: Record<string, number>) => {
    const { indicators, selectedSymbol, selectedTimeframe } = get();

    const updated = indicators.map(async (ind) => {
      if (ind.def.name !== name) return ind;
      const merged = { ...ind.params, ...params };

      if (!ind.enabled) {
        return { ...ind, params: merged };
      }

      const data = await api.fetchIndicator({
        symbol: selectedSymbol!,
        timeframe: selectedTimeframe,
        indicator_name: name,
        params: merged,
        force_recompute: true,
      });

      return { ...ind, params: merged, data, loading: false };
    });

    const resolved = await Promise.all(updated);
    set({ indicators: resolved });
  },

  refreshResearch: async () => {
    const { selectedSymbol, selectedTimeframe } = get();
    if (!selectedSymbol) return;

    set({ researchLoading: true });
    const [entries, analysis] = await Promise.all([
      api.fetchResearch(selectedSymbol, 10),
      api.fetchTechnicalAnalysis(selectedSymbol, selectedTimeframe),
    ]);
    set({ researchEntries: entries, technicalAnalysis: analysis, researchLoading: false });
  },

  refreshPositions: async () => {
    const positions = await api.fetchPositions();
    set({ positions });
  },

  refreshPortfolio: async () => {
    const [portfolio, equityCurve] = await Promise.all([
      api.fetchPortfolio(),
      api.fetchEquityCurve(),
    ]);
    set({ portfolio, equityCurve });
  },

  runSignal: async (config: SignalConfig) => {
    const { selectedSymbol, selectedTimeframe } = get();
    if (!selectedSymbol) return;

    set({ signalLoading: true, signalError: null, signalConfig: config });
    const response = await api.fetchSignal(selectedSymbol, selectedTimeframe, config, 500);
    if (response) {
      set({ signalResult: response.signals, signalLoading: false });
    } else {
      set({ signalError: "Failed to compute signal", signalLoading: false, signalResult: null });
    }
  },

  clearSignal: () => {
    set({ signalResult: null, signalConfig: null, signalError: null });
  },
}));
