"""Quantitative Alpha Researcher and Strategy Sandbox.

Automates the translation of academic quantitative strategies (breakouts,
mean-reversion, trend-following) into executable backtests and produces
institutional scorecards (Sharpe, Sortino, Drawdown, Profit Factor).
"""

from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd


class QuantitativeAlphaResearcher:
    """Backtests and scores quantitative trading strategies on historical price data."""

    def __init__(self, risk_free_rate: float = 0.04):
        self.risk_free_rate = risk_free_rate
        self.registered_strategies = {
            "MOMENTUM_IMPULSE": self.strategy_momentum_impulse,
            "DONCHIAN_BREAKOUT": self.strategy_donchian_breakout,
            "BOLLINGER_MEAN_REVERSION": self.strategy_bollinger_reversion,
        }

    def compute_performance_metrics(self, trade_pnls_pct: List[float], dates: Optional[List[Any]] = None) -> Dict[str, Any]:
        """Compute institutional scorecard metrics from a sequence of trade returns."""
        if not trade_pnls_pct:
            return {
                "total_trades": 0,
                "win_rate_pct": 0.0,
                "profit_factor": 0.0,
                "total_return_pct": 0.0,
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "max_drawdown_pct": 0.0,
                "institutional_score": 0.0,
                "qualification": "DISQUALIFIED_NO_TRADES",
            }

        pnls = np.array(trade_pnls_pct) / 100.0  # convert to decimal returns
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]

        win_rate = len(wins) / len(pnls) if len(pnls) > 0 else 0.0
        gross_profit = float(np.sum(wins)) if len(wins) > 0 else 0.0
        gross_loss = float(abs(np.sum(losses))) if len(losses) > 0 else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        # Cumulative equity curve
        equity_curve = np.cumprod(1.0 + pnls)
        peaks = np.maximum.accumulate(equity_curve)
        drawdowns = (peaks - equity_curve) / peaks
        max_drawdown = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

        # Annualized Sharpe & Sortino (assuming 365 periods for crypto)
        mean_ret = float(np.mean(pnls))
        std_ret = float(np.std(pnls)) if len(pnls) > 1 else 1e-6
        downside_std = float(np.std(losses)) if len(losses) > 1 else 1e-6

        daily_rf = self.risk_free_rate / 365.0
        sharpe = float((mean_ret - daily_rf) / std_ret * np.sqrt(365)) if std_ret > 0 else 0.0
        sortino = float((mean_ret - daily_rf) / downside_std * np.sqrt(365)) if downside_std > 0 else 0.0

        total_return = float((equity_curve[-1] - 1.0) * 100.0) if len(equity_curve) > 0 else 0.0

        # Institutional Score (0 to 100)
        score = 0.0
        if sharpe >= 1.5:
            score += 25.0
        elif sharpe >= 1.0:
            score += 15.0

        if profit_factor >= 1.5:
            score += 25.0
        elif profit_factor >= 1.2:
            score += 15.0

        if max_drawdown <= 0.08:
            score += 25.0
        elif max_drawdown <= 0.15:
            score += 15.0

        if win_rate >= 0.50:
            score += 25.0
        elif win_rate >= 0.40:
            score += 15.0

        qualification = (
            "INSTITUTIONAL_READY"
            if score >= 75.0
            else ("CANDIDATE" if score >= 50.0 else "UNQUALIFIED")
        )

        return {
            "total_trades": len(trade_pnls_pct),
            "win_rate_pct": round(win_rate * 100.0, 2),
            "profit_factor": round(min(profit_factor, 99.0), 2),
            "total_return_pct": round(total_return, 2),
            "sharpe_ratio": round(sharpe, 2),
            "sortino_ratio": round(sortino, 2),
            "max_drawdown_pct": round(max_drawdown * 100.0, 2),
            "institutional_score": round(score, 1),
            "qualification": qualification,
        }

    def strategy_momentum_impulse(self, df: pd.DataFrame) -> List[float]:
        """Simulate momentum impulse breakout: 20 EMA > 50 EMA with volume expansion."""
        if len(df) < 55:
            return []

        close = df["close"].values
        high = df["high"].values
        low = df["low"].values
        vol = df["volume"].values

        ema20 = df["close"].ewm(span=20, adjust=False).mean().values
        ema50 = df["close"].ewm(span=50, adjust=False).mean().values
        vol_ma = df["volume"].rolling(20).mean().values

        trade_pnls = []
        in_pos = False
        entry_price = 0.0
        stop_price = 0.0
        target_price = 0.0

        for i in range(50, len(df)):
            if not in_pos:
                # Entry condition: EMA 20 > EMA 50, Close > EMA 20, RVOL >= 1.5
                rvol = vol[i] / vol_ma[i] if vol_ma[i] > 0 else 1.0
                if ema20[i] > ema50[i] and close[i] > ema20[i] and rvol >= 1.5:
                    in_pos = True
                    entry_price = close[i]
                    atr_approx = np.mean(high[i-14:i] - low[i-14:i])
                    stop_price = entry_price - (1.5 * atr_approx)
                    target_price = entry_price + (3.5 * atr_approx)
            else:
                # Check exit
                if low[i] <= stop_price:
                    pnl_pct = (stop_price - entry_price) / entry_price * 100.0
                    trade_pnls.append(pnl_pct)
                    in_pos = False
                elif high[i] >= target_price:
                    pnl_pct = (target_price - entry_price) / entry_price * 100.0
                    trade_pnls.append(pnl_pct)
                    in_pos = False

        return trade_pnls

    def strategy_donchian_breakout(self, df: pd.DataFrame, window: int = 20) -> List[float]:
        """Simulate classic Donchian channel 20-bar high breakout with 10-bar low exit."""
        if len(df) < window + 10:
            return []

        high = df["high"].values
        low = df["low"].values
        close = df["close"].values

        upper_channel = df["high"].shift(1).rolling(window).max().values
        lower_channel = df["low"].shift(1).rolling(window // 2).min().values

        trade_pnls = []
        in_pos = False
        entry_price = 0.0

        for i in range(window, len(df)):
            if not in_pos:
                if close[i] > upper_channel[i]:
                    in_pos = True
                    entry_price = close[i]
            else:
                if close[i] < lower_channel[i]:
                    pnl_pct = (close[i] - entry_price) / entry_price * 100.0
                    trade_pnls.append(pnl_pct)
                    in_pos = False

        return trade_pnls

    def strategy_bollinger_reversion(self, df: pd.DataFrame, window: int = 20, num_std: float = 2.0) -> List[float]:
        """Simulate Bollinger mean reversion: buy under lower band and exit at middle SMA."""
        if len(df) < window + 10:
            return []

        close = df["close"].values
        sma = df["close"].rolling(window).mean().values
        std = df["close"].rolling(window).std().values
        lower_band = sma - (num_std * std)

        trade_pnls = []
        in_pos = False
        entry_price = 0.0
        stop_price = 0.0

        for i in range(window, len(df)):
            if not in_pos:
                if close[i] < lower_band[i]:
                    in_pos = True
                    entry_price = close[i]
                    stop_price = entry_price * 0.97  # 3% stop
            else:
                if close[i] <= stop_price:
                    pnl_pct = (stop_price - entry_price) / entry_price * 100.0
                    trade_pnls.append(pnl_pct)
                    in_pos = False
                elif close[i] >= sma[i]:
                    pnl_pct = (sma[i] - entry_price) / entry_price * 100.0
                    trade_pnls.append(pnl_pct)
                    in_pos = False

        return trade_pnls

    def evaluate_strategy_on_ohlcv(self, strategy_name: str, df: pd.DataFrame) -> Dict[str, Any]:
        """Evaluate a named strategy against an OHLCV dataset."""
        if strategy_name not in self.registered_strategies:
            return {"error": f"Strategy {strategy_name} is not registered"}

        func = self.registered_strategies[strategy_name]
        trade_pnls = func(df)
        scorecard = self.compute_performance_metrics(trade_pnls)
        scorecard["strategy_name"] = strategy_name
        return scorecard
