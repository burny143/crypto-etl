import { useState, useEffect } from "react";
import { useTradeStore } from "@/stores/tradeStore";
import { TopBar } from "@/components/layout/TopBar";
import { LandingPage } from "@/components/layout/LandingPage";
import { CandlestickChart } from "@/components/chart/CandlestickChart";
import { ResearchPanel } from "@/components/research/ResearchPanel";
import { IndicatorControls } from "@/components/indicators/IndicatorControls";
import { SignalPanel } from "@/components/indicators/SignalPanel";
import { OrderForm } from "@/components/trading/OrderForm";
import { PositionsTable } from "@/components/trading/PositionsTable";

export default function App() {
  const { init, loadingSymbols } = useTradeStore();
  const [landing, setLanding] = useState(true);

  useEffect(() => {
    init();
  }, [init]);

  if (landing) {
    return <LandingPage onLaunch={() => setLanding(false)} />;
  }

  if (loadingSymbols) {
    return (
      <div className="flex h-screen items-center justify-center bg-surface">
        <div className="text-center space-y-3">
          <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-text-muted text-sm">Connecting to database…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-surface overflow-hidden">
      <TopBar />
      <div className="flex-1 flex overflow-hidden">
        <div className="w-64 border-r border-surface-border flex flex-col overflow-hidden shrink-0">
          <IndicatorControls />
          <div className="border-t border-surface-border" />
          <div className="flex-1 overflow-y-auto">
            <SignalPanel />
          </div>
        </div>
        <div className="flex-1 flex flex-col overflow-hidden min-w-0">
          <div className="flex-1 p-2">
            <CandlestickChart />
          </div>
        </div>
        <div className="w-80 border-l border-surface-border flex flex-col overflow-hidden shrink-0">
          <ResearchPanel />
          <div className="border-t border-surface-border" />
          <OrderForm />
          <div className="flex-1 overflow-y-auto border-t border-surface-border">
            <PositionsTable />
          </div>
        </div>
      </div>
    </div>
  );
}
