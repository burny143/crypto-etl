import { useEffect, useRef, useMemo, useCallback } from "react";
import { createChart, type IChartApi, type ISeriesApi, type Time, ColorType, LineStyle } from "lightweight-charts";
import { useTradeStore } from "@/stores/tradeStore";
import type { OHLCVBar, SignalPoint } from "@/types";

function toChartTime(datetime: string, timeframe: string): Time {
  if (["1m", "5m", "15m", "30m", "1h", "4h"].includes(timeframe)) {
    return Math.floor(new Date(datetime).getTime() / 1000) as Time;
  }
  return datetime.split("T")[0] as Time;
}

function toMarker(signal: SignalPoint, timeframe: string): { time: Time; position: "aboveBar" | "belowBar"; shape: "arrowDown" | "arrowUp"; color: string; text?: string } | null {
  if (signal.signal === 1) {
    return {
      time: toChartTime(signal.datetime, timeframe),
      position: "belowBar",
      shape: "arrowUp",
      color: "#22c55e",
      text: "BUY",
    };
  }
  if (signal.signal === -1) {
    return {
      time: toChartTime(signal.datetime, timeframe),
      position: "aboveBar",
      shape: "arrowDown",
      color: "#ef4444",
      text: "SELL",
    };
  }
  return null;
}

export function CandlestickChart() {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const indicatorSeriesRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const isFirstLoad = useRef(true);
  const paginationCb = useRef<((from: number, to: number) => void) | null>(null);

  const {
    ohlcvData, ohlcvLoading, selectedSymbol, selectedTimeframe,
    indicators, showVolume,
    earliestDate, hasMoreHistory, loadingMore, loadMoreHistory,
    signalResult,
  } = useTradeStore();

  const chartData = useMemo(() => {
    return ohlcvData.map((bar: OHLCVBar) => ({
      time: toChartTime(bar.datetime, selectedTimeframe),
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
    }));
  }, [ohlcvData, selectedTimeframe]);

  const volumeData = useMemo(() => {
    return ohlcvData.map((bar: OHLCVBar) => ({
      time: toChartTime(bar.datetime, selectedTimeframe),
      value: bar.volume,
      color: bar.close >= bar.open ? "rgba(34,197,94,0.3)" : "rgba(239,68,68,0.3)",
    }));
  }, [ohlcvData, selectedTimeframe]);

  // Pagination check — always keep the latest version in a ref
  const checkPagination = useCallback(() => {
    const chart = chartRef.current;
    if (!chart || !earliestDate || !hasMoreHistory || loadingMore) return;

    const logical = chart.timeScale().getVisibleLogicalRange();
    if (!logical) return;

    // If within ~15 bars of the earliest loaded bar, fetch the next page
    // Use a larger threshold when there's very little data
    const threshold = ohlcvData.length < 100 ? 30 : 15;
    if (logical.from < threshold) {
      loadMoreHistory();
    }
  }, [earliestDate, hasMoreHistory, loadingMore, ohlcvData.length, loadMoreHistory]);
  const checkPaginationRef = useRef(checkPagination);
  checkPaginationRef.current = checkPagination;

  // ── Chart creation ──
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#0f172a" },
        textColor: "#94a3b8",
        fontSize: 11,
        fontFamily: "JetBrains Mono, monospace",
      },
      grid: {
        vertLines: { color: "#1e293b" },
        horzLines: { color: "#1e293b" },
      },
      crosshair: {
        mode: 0,
        vertLine: {
          color: "#64748b",
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: "#334155",
        },
        horzLine: {
          color: "#64748b",
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: "#334155",
        },
      },
      timeScale: {
        borderColor: "#334155",
        timeVisible: false,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: "#334155",
      },
      handleScroll: { vertTouchDrag: false },
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });

    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
      visible: false,
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;
    isFirstLoad.current = true;

    // Subscribe to visible range changes for pagination (once, stable handler via ref)
    const handler = () => checkPaginationRef.current();
    chart.timeScale().subscribeVisibleTimeRangeChange(handler);

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      chart.timeScale().unsubscribeVisibleTimeRangeChange(handler);
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      indicatorSeriesRef.current.clear();
    };
    // Intentionally runs once; checkPagination stays current via ref
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Set data on candle + volume series ──
  useEffect(() => {
    if (candleSeriesRef.current && chartData.length > 0) {
      candleSeriesRef.current.setData(chartData);
    }
    if (volumeSeriesRef.current) {
      if (showVolume && volumeData.length > 0) {
        volumeSeriesRef.current.setData(volumeData);
      } else {
        volumeSeriesRef.current.setData([]);
      }
    }
    // Fit content only on the very first data load (not pagination)
    if (chartRef.current && chartData.length > 0 && isFirstLoad.current) {
      chartRef.current.timeScale().fitContent();
      isFirstLoad.current = false;
    }
  }, [chartData, volumeData, showVolume]);

  // Reset first-load flag when symbol or timeframe changes
  useEffect(() => {
    isFirstLoad.current = true;
  }, [selectedSymbol, selectedTimeframe]);

  // Adjust volume pane size based on visibility
  useEffect(() => {
    if (!chartRef.current) return;
    chartRef.current.priceScale("volume").applyOptions({
      scaleMargins: showVolume
        ? { top: 0.85, bottom: 0 }
        : { top: 1, bottom: 0 },
    });
  }, [showVolume]);

  // ── Indicator series ──
  useEffect(() => {
    if (!chartRef.current) return;

    const chart = chartRef.current;
    const activeSeries = new Set<string>();

    indicators.forEach((ind) => {
      if (!ind.enabled || !ind.data || ind.data.length === 0) return;

      const key = `${ind.def.name}-${JSON.stringify(ind.params)}`;
      activeSeries.add(key);

      let series = indicatorSeriesRef.current.get(key);
      if (!series) {
        series = chart.addLineSeries({
          color: getIndicatorColor(ind.def.name),
          lineWidth: 1,
          priceFormat: { type: "price" },
          lastValueVisible: false,
          priceLineVisible: false,
        });
        indicatorSeriesRef.current.set(key, series);
      }

      const lineData = ind.data
        .filter((p) => p.value != null)
        .map((p) => ({
          time: toChartTime(p.datetime, selectedTimeframe),
          value: p.value!,
        }));

      if (lineData.length > 0) {
        series.setData(lineData);
      }
    });

    indicatorSeriesRef.current.forEach((series, key) => {
      if (!activeSeries.has(key)) {
        chart.removeSeries(series);
        indicatorSeriesRef.current.delete(key);
      }
    });
  }, [indicators, selectedTimeframe]);

  // ── Signal markers ──
  useEffect(() => {
    if (!candleSeriesRef.current || !signalResult) return;

    const markers = signalResult
      .map((s) => toMarker(s, selectedTimeframe))
      .filter((m): m is NonNullable<typeof m> => m !== null);

    candleSeriesRef.current.setMarkers(markers);
  }, [signalResult, selectedTimeframe]);

  // ── Pagination loading indicator ──
  const showLoadingOverlay = ohlcvLoading || (loadingMore && chartData.length === 0);

  return (
    <div className="h-full w-full relative card overflow-hidden">
      {showLoadingOverlay && (
        <div className="absolute inset-0 bg-surface/60 flex items-center justify-center z-10">
          <div className="flex items-center gap-2 text-text-muted text-sm">
            <div className="w-4 h-4 border-2 border-accent border-t-transparent rounded-full animate-spin" />
            Loading {selectedSymbol} [{selectedTimeframe}]…
          </div>
        </div>
      )}

      {!showLoadingOverlay && chartData.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center z-10">
          <div className="text-center text-text-muted">
            <p className="text-sm">No data available</p>
            <p className="text-xs mt-1">
              Run the ETL pipeline to load {selectedSymbol} [{selectedTimeframe}] data
            </p>
          </div>
        </div>
      )}

      {/* Subtle edge-loading indicator */}
      {loadingMore && chartData.length > 0 && (
        <div className="absolute top-2 left-2 z-10 flex items-center gap-1.5 bg-surface-alt/80 rounded px-2 py-1 text-[10px] text-text-muted">
          <div className="w-2.5 h-2.5 border border-accent border-t-transparent rounded-full animate-spin" />
          Loading more…
        </div>
      )}

      {!hasMoreHistory && chartData.length > 0 && (
        <div className="absolute bottom-2 left-1/2 -translate-x-1/2 z-10 text-[9px] text-text-muted bg-surface-alt/60 rounded px-2 py-0.5">
          All historical data loaded
        </div>
      )}

      <div ref={containerRef} className="h-full w-full" />
    </div>
  );
}

function getIndicatorColor(name: string): string {
  const colors: Record<string, string> = {
    sma: "#f59e0b",
    ema: "#8b5cf6",
    rsi: "#06b6d4",
    macd: "#3b82f6",
    bb: "#ec4899",
    vwap: "#14b8a6",
    adx: "#f97316",
    atr: "#a78bfa",
    obv: "#22d3ee",
    stoch_rsi: "#e879f9",
    vol_ratio: "#34d399",
    kc: "#fb923c",
  };
  return colors[name] ?? "#94a3b8";
}
