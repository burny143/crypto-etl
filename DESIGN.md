# Trader's Lab — Design System

## Visual Identity

### Personality
Precise, data-dense, calm. The terminal feels like a professional instrument — every element is there for a reason. Nothing decorative, nothing half-implemented. Dark backgrounds make the data (and the green/red of price movement) the primary source of visual energy.

### Brand Color
Deep indigo-blue (`oklch(0.55 0.16 260)`) used sparingly for interactive elements. The brand is the data, not the chrome.

---

## Typography

### Font Stack
- **UI:** `DM Sans` (Google Fonts) — clean, warm geometric with strong legibility at small sizes
- **Monospace:** `JetBrains Mono` (Google Fonts) — all numeric data, prices, quantities, timestamps
- **Fallback:** `-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`

### Type Scale

| Token | Size | Weight | Usage |
|-------|------|--------|-------|
| `--text-xs` | 11px / 0.688rem | 400 | Secondary labels, order history, timestamps |
| `--text-sm` | 12px / 0.75rem | 400, 600 | Panel headers, trade items, badges |
| `--text-base` | 13px / 0.813rem | 400 | Body text, table cells, signals |
| `--text-lg` | 14px / 0.875rem | 400, 500 | Filter bar, pair select, button labels |
| `--text-xl` | 16px / 1rem | 500, 600 | Sub-headings, metric values |
| `--text-2xl` | 18px / 1.125rem | 600, 700 | Section titles, price display |
| `--text-3xl` | 20px / 1.25rem | 700 | Chart header, brand wordmark |
| `--text-4xl` | 42px / 2.625rem | 700 | Landing page hero |

Monospace overrides: All numeric data in the trading panel, prices, quantities, returns, timestamps use `--font-mono` via `.num` class.

---

## Color System (OKLCH)

### Surface Colors — Tinted Neutrals
Never pure black, never pure gray. All surfaces have a subtle blue hue that ties the interface together.

| Token | Value | Usage |
|-------|-------|-------|
| `--color-surface-base` | `oklch(0.135 0.012 265)` | Page background (deepest) |
| `--color-surface-raised` | `oklch(0.165 0.014 265)` | Panels, sidebars |
| `--color-surface-overlay` | `oklch(0.195 0.015 265)` | Dropdowns, tooltips |
| `--color-surface-hover` | `oklch(0.225 0.016 265)` | Hovered items |

### Border Colors

| Token | Value | Usage |
|-------|-------|-------|
| `--color-border` | `oklch(0.235 0.014 265)` | Default borders |
| `--color-border-hover` | `oklch(0.35 0.025 265)` | Hovered/focused borders |

### Text Colors

| Token | Value | Usage |
|-------|-------|-------|
| `--color-text-primary` | `oklch(0.83 0.012 265)` | Primary content |
| `--color-text-secondary` | `oklch(0.55 0.02 265)` | Secondary, muted labels |
| `--color-text-brand` | `oklch(0.95 0.01 265)` | Brand wordmark |

### Semantic Colors

| Token | Value | Usage |
|-------|-------|-------|
| `--color-accent` | `oklch(0.55 0.16 260)` | Interactive elements, links |
| `--color-up` | `oklch(0.62 0.14 155)` | Up/green candles, bullish, positive P&L |
| `--color-down` | `oklch(0.55 0.18 25)` | Down/red candles, bearish, negative P&L |
| `--color-warning` | `oklch(0.75 0.15 75)` | Warnings, caution states |
| `--color-neutral` | `oklch(0.55 0.02 265)` | Neutral sentiment, inactive |

---

## Spacing Scale

4px base. All spacing values are `--space-{n}` tokens.

| Token | Value | Typical Usage |
|-------|-------|---------------|
| `--space-1` | 4px | Tight padding, separators |
| `--space-2` | 8px | Small gap, inner padding |
| `--space-3` | 12px | Panel padding, section gap |
| `--space-4` | 16px | Card padding, standard gap |
| `--space-5` | 24px | Section spacing |
| `--space-6` | 32px | Major section spacing |
| `--space-7` | 48px | Page section separation |
| `--space-8` | 64px | Page margins |

---

## Component Architecture

### Component Conventions
- All interactive elements have `:hover`, `:focus-visible`, `:disabled` states
- Loading states use a spinning indicator (`.loading` with `::after` pseudo-element)
- Empty states are explicit: "No open positions.", "No orders yet.", "Select a pair…"
- Error states use `--color-down` text color
- Badges/pills for sentiment, strategy quality, status labels

### Key Components

**SignalDot** — `6px` circle for sentiment/status
**Badge** — Pill-shaped label for sentiment, quality tier
**PanelHeader** — Section header with title + optional action button
**StratCard** — Strategy result item with name, sharpe, metrics
**TradeForm** — Paper trading entry form
**TradeRow** — Position display with P&L
**MetricTile** — 2×2 grid tile for backtest metrics
**ConsensusBar** — 3-segment bar for bullish/neutral/bearish ratio

---

## Anti-Patterns (not doing)

- Purple-to-blue gradients (fixed in this revision — landing page heading changed to accent-only)
- System font stacks without intentional choice
- Pure black (`#000`) or pure gray backgrounds — all surfaces use tinted OKLCH
- Cards nested inside cards
- Bounce/elastic easing on animations
- Gray text on colored backgrounds (badges use tinted backgrounds + semantic color text)
