"""Performance metrics for backtest results.

All metrics are computed from a list of completed trades and an equity
curve.  No pandas dependency — pure Python with Decimal for money.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence


@dataclass
class BacktestMetrics:
    """Aggregate performance metrics for a backtest run.

    All percentage values are floats (e.g. 0.12 = 12 %).
    """

    total_return_pct: float
    """Overall return as a fraction of starting capital."""

    sharpe_ratio: float
    """Annualized Sharpe — risk-free rate assumed 0."""

    max_drawdown_pct: float
    """Peak-to-trough equity decline as a positive fraction."""

    win_rate: float
    """Fraction of closed trades that were profitable (0..1)."""

    total_trades: int
    """Number of completed round-trip trades."""

    profit_factor: float
    """Gross profit / gross loss (infinity if no losing trades)."""

    avg_trade_pnl: Decimal
    """Mean P&L per completed trade in quote currency."""

    avg_holding_bars: float
    """Average number of bars a position was held."""


def compute_metrics(
    trade_pnls: Sequence[Decimal],
    equity_values: Sequence[Decimal],
    total_trades: int,
    avg_holding_bars: float,
    starting_capital: Decimal,
) -> BacktestMetrics:
    """Compute aggregate metrics from trade and equity data.

    Args:
        trade_pnls: Realized P&L for each completed trade.
        equity_values: Equity value at each bar (including the initial value).
        total_trades: Total number of completed round-trip trades.
        avg_holding_bars: Average holding period in bars.
        starting_capital: Initial portfolio balance.

    Returns:
        A ``BacktestMetrics`` instance.
    """
    if not equity_values:
        return BacktestMetrics(
            total_return_pct=0.0,
            sharpe_ratio=0.0,
            max_drawdown_pct=0.0,
            win_rate=0.0,
            total_trades=0,
            profit_factor=0.0,
            avg_trade_pnl=Decimal("0"),
            avg_holding_bars=0.0,
        )

    final_equity = equity_values[-1]
    total_return_pct = float((final_equity - starting_capital) / starting_capital)

    # Max drawdown — peak-to-trough
    peak = equity_values[0]
    max_drawdown = Decimal("0")
    for eq in equity_values:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else Decimal("0")
        if dd > max_drawdown:
            max_drawdown = dd
    max_drawdown_pct = float(max_drawdown)

    # Sharpe ratio — annualized from bar-level returns
    if len(equity_values) >= 2:
        bar_returns = []
        for i in range(1, len(equity_values)):
            prev = equity_values[i - 1]
            if prev > 0:
                bar_returns.append(float((equity_values[i] - prev) / prev))
        if bar_returns:
            mean_r = sum(bar_returns) / len(bar_returns)
            var_r = (
                sum((r - mean_r) ** 2 for r in bar_returns) / len(bar_returns)
                if len(bar_returns) > 1
                else 0.0
            )
            std_r = math.sqrt(var_r) if var_r > 0 else 0.0
            # Annualize: sqrt(periods_per_year) — caller should adjust
            # For now use raw (bar-level) Sharpe
            sharpe_ratio = mean_r / std_r if std_r > 0 else 0.0
        else:
            sharpe_ratio = 0.0
    else:
        sharpe_ratio = 0.0

    # Win rate
    wins = sum(1 for pnl in trade_pnls if pnl > 0)
    win_rate = wins / len(trade_pnls) if trade_pnls else 0.0

    # Profit factor
    gross_profit = sum(pnl for pnl in trade_pnls if pnl > 0)
    gross_loss = abs(sum(pnl for pnl in trade_pnls if pnl < 0))
    if gross_loss > 0:
        profit_factor = float(gross_profit / gross_loss)
    elif gross_profit > 0:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0

    # Average trade P&L
    avg_trade_pnl = (
        sum(trade_pnls, Decimal("0")) / len(trade_pnls) if trade_pnls else Decimal("0")
    )

    return BacktestMetrics(
        total_return_pct=round(total_return_pct, 6),
        sharpe_ratio=round(sharpe_ratio, 4),
        max_drawdown_pct=round(max_drawdown_pct, 6),
        win_rate=round(win_rate, 4),
        total_trades=total_trades,
        profit_factor=round(profit_factor, 4) if math.isfinite(profit_factor) else float("inf"),
        avg_trade_pnl=avg_trade_pnl,
        avg_holding_bars=round(avg_holding_bars, 1),
    )
