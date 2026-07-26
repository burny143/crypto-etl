import { BarChart3, TrendingUp, Brain, Shield } from "lucide-react";

interface LandingPageProps {
  onLaunch: () => void;
}

const features = [
  {
    icon: BarChart3,
    title: "Professional Charts",
    desc: "TradingView-quality candlestick charts with zoom, crosshair, and full history scrolling across 30 pairs.",
  },
  {
    icon: TrendingUp,
    title: "Indicator Lab",
    desc: "Test SMA, EMA, RSI, MACD, Bollinger Bands, VWAP and more. Max 3 on chart — clutter-free research.",
  },
  {
    icon: Brain,
    title: "AI Research",
    desc: "Technical analysis summaries and research entries generated per pair to surface edge faster.",
  },
  {
    icon: Shield,
    title: "Paper Trading",
    desc: "Simulate long/short positions with persistent P&L tracking. Foundation for future automation.",
  },
];

export function LandingPage({ onLaunch }: LandingPageProps) {
  return (
    <div className="h-screen flex flex-col bg-surface overflow-hidden">
      {/* Nav bar */}
      <header className="h-12 border-b border-surface-border bg-surface-alt flex items-center px-6 shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-full bg-accent flex items-center justify-center">
            <span className="text-white text-xs font-bold">C</span>
          </div>
          <span className="text-sm font-semibold text-text-primary">Crypto Terminal</span>
        </div>
      </header>

      {/* Hero */}
      <div className="flex-1 flex flex-col items-center justify-center px-6">
        <div className="max-w-2xl mx-auto text-center">
          <div className="w-16 h-16 rounded-2xl bg-accent/10 border border-accent/20 flex items-center justify-center mx-auto mb-6">
            <BarChart3 className="w-8 h-8 text-accent" />
          </div>

          <h1 className="text-4xl font-bold text-text-primary mb-3 tracking-tight">
            Crypto Research Terminal
          </h1>

          <p className="text-lg text-text-secondary leading-relaxed mb-8 max-w-lg mx-auto">
            A research laboratory for finding edge in crypto markets —
            combine historical price data, technical indicators, and AI analysis
            in one focused workspace.
          </p>

          <button
            onClick={onLaunch}
            className="inline-flex items-center gap-2 px-8 py-3 bg-accent text-white rounded-lg text-base font-semibold hover:bg-blue-600 transition-colors shadow-lg shadow-accent/20"
          >
            <TrendingUp className="w-5 h-5" />
            Launch Terminal
          </button>
        </div>

        {/* Features grid */}
        <div className="grid grid-cols-2 gap-4 max-w-2xl mx-auto mt-12 w-full">
          {features.map((f) => (
            <div
              key={f.title}
              className="bg-surface-alt border border-surface-border rounded-lg p-4 text-left"
            >
              <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center mb-2">
                <f.icon className="w-4 h-4 text-accent" />
              </div>
              <h3 className="text-sm font-semibold text-text-primary mb-1">{f.title}</h3>
              <p className="text-xs text-text-secondary leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="mt-auto pb-6 text-[11px] text-text-muted">
          Powered by Supabase · 30 pairs · 8 timeframes
        </div>
      </div>
    </div>
  );
}
