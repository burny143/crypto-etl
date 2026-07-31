# Trader's Lab

## Product Lane
Product — a crypto research and trading terminal for individual traders and analysts.

## Audience
Self-directed crypto traders who need technical charting, strategy research, and paper trading in a single interface. Users are technically literate but time-constrained — they want fast access to price action, indicators, and signal data without configuration overhead.

## Core Job
Enable a trader to go from "what's happening in the market?" to "I have a thesis and a paper position" in under 30 seconds.

## Surface Hierarchy

| Surface | Mode | Purpose |
|---------|------|---------|
| Landing (`index.html`) | Persuade | Quick entry to terminal or research dashboard |
| Charts (`charts.html`) | Operate | Primary trading surface: OHLCV chart, indicators, signals, paper trading, backtest review |
| Research (`research.html`) | Operate | Cross-pair sentiment consensus, strategy leaderboard, historical research |

## Design Principles

1. **Dark-first, not dark-only.** The terminal lives in a dark environment (traders work at night). All surfaces assume dark mode as default. Light mode is not in scope.
2. **Information density with clarity.** Traders scan, not read. Dense data needs clear hierarchy, not whitespace theater. Every pixel justifies its existence.
3. **Precise over playful.** Financial data demands accuracy. Animation is purposeful (state transitions, not decoration). Color is semantic (green = up, red = down), not decorative.
4. **Console sensibility.** Monospaced numbers, keyboard shortcuts where practical, minimal chrome. The chart is the hero.
5. **Offline-capable core.** Indicators and signals compute client-side. The UI works with stale data; it never blocks on a remote response.

## Competitive Landscape
TradingView is the incumbent but targets retail traders broadly. This terminal differentiates by focusing on cross-pair research consensus and strategy-backtest traceability — fewer features, tighter research workflow.

## Tone & Voice
- Professional but not corporate. Direct, data-driven, no marketing fluff.
- Error messages explain what happened *and* what the user can do next.
- Success states are understated (a subtle flash, not confetti).
