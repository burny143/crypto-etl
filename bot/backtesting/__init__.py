"""Backtesting engine for the paper-trading bot.

Reuses the same Strategy, RiskManager, PaperExecutor, and PortfolioService
components as the forward engine — so strategies are tested with exactly
the same code that runs live.
"""

from bot.backtesting.backtester import BacktestEngine, BacktestResult, BacktestTrade
from bot.backtesting.metrics import BacktestMetrics, compute_metrics

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "BacktestTrade",
    "BacktestMetrics",
    "compute_metrics",
]
