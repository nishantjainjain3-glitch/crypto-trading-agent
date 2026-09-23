"""Backtesting runner for quantitative crypto strategies with full risk metrics."""

import argparse
import logging
from typing import Dict, Any
import pandas as pd
import numpy as np
import yfinance as yf

logger = logging.getLogger(__name__)

class CryptoBacktester:
    """Simulates trading strategies on historical crypto data and calculates risk metrics."""

    def __init__(self, initial_capital: float = 10000.0, commission_pct: float = 0.075):
        self.initial_capital = initial_capital
        self.commission_pct = commission_pct

    def fetch_historical_data(self, symbol: str = "BTC-USD", period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        """Download OHLCV data."""
        yf_sym = symbol.replace("/", "-")
        if not yf_sym.endswith("-USD"):
            yf_sym = f"{yf_sym.split('-')[0]}-USD"

        df = yf.download(yf_sym, period=period, interval=interval, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0].lower() for col in df.columns]
        else:
            df.columns = [col.lower() for col in df.columns]

        return df.dropna()

    def backtest_ema_crossover(
        self,
        df: pd.DataFrame,
        fast_period: int = 20,
        slow_period: int = 50,
    ) -> Dict[str, Any]:
        """Backtest an EMA trend following strategy."""
        if len(df) < slow_period + 10:
            return {"error": "Insufficient historical data"}

        data = df.copy()
        data["fast_ema"] = data["close"].ewm(span=fast_period, adjust=False).mean()
        data["slow_ema"] = data["close"].ewm(span=slow_period, adjust=False).mean()

        data["signal"] = 0
        data.loc[data["fast_ema"] > data["slow_ema"], "signal"] = 1
        data["position"] = data["signal"].shift(1).fillna(0)

        # Calculate daily asset and strategy returns
        data["asset_return"] = data["close"].pct_change().fillna(0)
        data["strategy_return"] = data["position"] * data["asset_return"]

        # Deduct commission on trade flips
        data["trades"] = data["position"].diff().abs().fillna(0)
        data["strategy_net_return"] = data["strategy_return"] - (data["trades"] * (self.commission_pct / 100.0))

        # Cumulative equity curve
        data["equity_curve"] = self.initial_capital * (1.0 + data["strategy_net_return"]).cumprod()

        return self._compute_performance_metrics(data, strategy_name="EMA_CROSSOVER")

    def _compute_performance_metrics(self, data: pd.DataFrame, strategy_name: str) -> Dict[str, Any]:
        """Calculate Sharpe, Sortino, VaR, CVaR, and max drawdown."""
        net_returns = data["strategy_net_return"]
        equity = data["equity_curve"]

        total_return_pct = round(((equity.iloc[-1] - self.initial_capital) / self.initial_capital) * 100, 2)
        
        # Annualized metrics assuming daily candles (365 trading days in crypto)
        mean_ret = net_returns.mean()
        std_ret = net_returns.std()
        
        sharpe = round((mean_ret / (std_ret + 1e-9)) * np.sqrt(365), 2)
        
        downside_returns = net_returns[net_returns < 0]
        downside_std = downside_returns.std()
        sortino = round((mean_ret / (downside_std + 1e-9)) * np.sqrt(365), 2)

        # Max Drawdown
        rolling_max = equity.cummax()
        drawdown = (equity - rolling_max) / rolling_max
        max_drawdown_pct = round(abs(drawdown.min()) * 100, 2)

        # Value at Risk (VaR 95%) & Conditional VaR (CVaR 95%)
        var_95 = round(abs(np.percentile(net_returns, 5)) * 100, 2)
        cvar_returns = net_returns[net_returns <= - (var_95 / 100.0)]
        cvar_95 = round(abs(cvar_returns.mean()) * 100, 2) if not cvar_returns.empty else var_95

        # Trade stats
        trade_count = int(data["trades"].sum())
        winning_days = int((net_returns > 0).sum())
        total_trading_days = int((data["position"] > 0).sum())
        win_rate = round((winning_days / total_trading_days * 100), 2) if total_trading_days else 0.0

        return {
            "strategy": strategy_name,
            "initial_capital": self.initial_capital,
            "final_equity": round(float(equity.iloc[-1]), 2),
            "total_return_pct": total_return_pct,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "max_drawdown_pct": max_drawdown_pct,
            "var_95_pct": var_95,
            "cvar_95_pct": cvar_95,
            "total_flips": trade_count,
            "active_days": total_trading_days,
            "win_rate_pct": win_rate,
        }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run crypto backtest")
    parser.add_argument("--symbol", default="BTC-USD", help="Symbol e.g. BTC-USD")
    parser.add_argument("--period", default="1y", help="Historical period e.g. 6mo, 1y")
    args = parser.parse_args()

    backtester = CryptoBacktester()
    df = backtester.fetch_historical_data(args.symbol, period=args.period)
    res = backtester.backtest_ema_crossover(df)
    print(f"\n=== BACKTEST RESULTS FOR {args.symbol} ({args.period}) ===")
    for k, v in res.items():
        print(f"  {k}: {v}")
