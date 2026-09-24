"""Institutional quantitative risk measurement: Cornish-Fisher VaR, CVaR, Sortino, and Drawdown analysis."""

import math
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional


def _approx_norm_ppf(p: float) -> float:
    """Accurate rational approximation for standard normal inverse CDF (Wichura / Abramowitz & Stegun)."""
    if p <= 0.0 or p >= 1.0:
        raise ValueError("Probability p must be in (0, 1)")
    # Rational approximation constants
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]

    q = min(p, 1.0 - p)
    if q > 0.02425:
        r = q - 0.5
        r2 = r * r
        num = (((((a[0] * r2 + a[1]) * r2 + a[2]) * r2 + a[3]) * r2 + a[4]) * r2 + a[5]) * r
        den = ((((b[0] * r2 + b[1]) * r2 + b[2]) * r2 + b[3]) * r2 + b[4]) * r2 + 1.0
        val = num / den
    else:
        r = math.sqrt(-2.0 * math.log(q))
        num = ((((c[0] * r + c[1]) * r + c[2]) * r + c[3]) * r + c[4]) * r + c[5]
        den = (((d[0] * r + d[1]) * r + d[2]) * r + d[3]) * r + 1.0
        val = num / den

    if p == 0.5:
        return 0.0
    return abs(val) if p > 0.5 else -abs(val)


class PortfolioRiskEngine:
    """Calculates VaR, CVaR (Expected Shortfall), Sortino, Sharpe, and Drawdown metrics."""

    def __init__(self, returns: pd.Series, annual_factor: float = 365.0):
        self.returns = returns.dropna().astype(float)
        self.annual_factor = annual_factor

    def compute_all_metrics(self, confidence: float = 0.95) -> Dict[str, Any]:
        """Compute complete institutional risk profile."""
        if len(self.returns) < 5:
            return {
                "sample_size": len(self.returns),
                "var_historical_pct": 0.0,
                "var_cornish_fisher_pct": 0.0,
                "cvar_pct": 0.0,
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "max_drawdown_pct": 0.0,
                "status": "INSUFFICIENT_DATA",
            }

        ret = self.returns
        mean_ret = float(ret.mean())
        std_ret = float(ret.std())
        if std_ret <= 1e-8:
            std_ret = 1e-6

        # Skewness & Excess Kurtosis
        n = len(ret)
        diff = ret - mean_ret
        skewness = float(((diff ** 3).mean()) / (std_ret ** 3))
        kurtosis = float(((diff ** 4).mean()) / (std_ret ** 4) - 3.0)

        # 1. Historical VaR
        hist_var = float(-np.percentile(ret, (1.0 - confidence) * 100.0))

        # 2. Cornish-Fisher VaR (Adjusts for fat tails & negative skew in crypto)
        z = _approx_norm_ppf(confidence)
        z_cf = (
            z
            + (z ** 2 - 1.0) * skewness / 6.0
            + (z ** 3 - 3.0 * z) * kurtosis / 24.0
            - (2.0 * z ** 3 - 5.0 * z) * (skewness ** 2) / 36.0
        )
        cf_var = float(-(mean_ret - z_cf * std_ret))

        # 3. Conditional VaR (Expected Shortfall / Average tail loss beyond VaR)
        tail_losses = ret[ret <= -hist_var]
        cvar = float(-tail_losses.mean()) if len(tail_losses) > 0 else hist_var

        # 4. Downside Deviation & Sortino Ratio
        downside = ret[ret < 0.0]
        downside_std = float(downside.std()) if len(downside) > 1 else std_ret
        if downside_std <= 1e-8:
            downside_std = 1e-6

        sharpe = round((mean_ret / std_ret) * math.sqrt(self.annual_factor), 2)
        sortino = round((mean_ret / downside_std) * math.sqrt(self.annual_factor), 2)

        # 5. Drawdown
        cum_ret = (1.0 + ret).cumprod()
        peak = cum_ret.cummax()
        drawdowns = (cum_ret - peak) / peak
        max_dd = float(abs(drawdowns.min())) * 100.0

        return {
            "sample_size": n,
            "mean_return_pct": round(mean_ret * 100.0, 3),
            "volatility_daily_pct": round(std_ret * 100.0, 3),
            "skewness": round(skewness, 2),
            "kurtosis": round(kurtosis, 2),
            "var_historical_pct": round(hist_var * 100.0, 2),
            "var_cornish_fisher_pct": round(cf_var * 100.0, 2),
            "cvar_expected_shortfall_pct": round(cvar * 100.0, 2),
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "max_drawdown_pct": round(max_dd, 2),
            "status": "OK",
        }
