"""Market screener scanning liquid crypto pairs for actionable setups."""

import os
import json
import logging
from typing import List, Dict, Any, Optional
from src.exchanges.ccxt_client import CryptoExchangeClient
from src.analysis.technical_indicators import compute_all_technicals
from src.analysis.liquidity_sweep import detect_liquidity_sweep

logger = logging.getLogger(__name__)

DEFAULT_WATCHLIST = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "BNB/USDT",
    "XRP/USDT",
    "DOGE/USDT",
    "ADA/USDT",
    "AVAX/USDT",
    "LINK/USDT",
    "SUI/USDT",
]

class CryptoScanner:
    """Scans crypto universe and outputs actionable ranked opportunities."""

    def __init__(
        self,
        exchange_client: Optional[CryptoExchangeClient] = None,
        watchlist: Optional[List[str]] = None,
    ):
        self.client = exchange_client or CryptoExchangeClient()
        self.watchlist = watchlist or DEFAULT_WATCHLIST

    def scan_symbol(self, symbol: str, timeframe: str = "15m") -> Dict[str, Any]:
        """Perform comprehensive technical and liquidity scan for a single symbol."""
        ticker = self.client.fetch_ticker(symbol)
        df = self.client.fetch_ohlcv(symbol, timeframe=timeframe, limit=100)
        
        technicals = compute_all_technicals(df) if not df.empty else {}
        sweep_signal = detect_liquidity_sweep(df) if not df.empty else None
        
        # Calculate conviction score (0-100)
        score = 50
        bullish_factors = []
        bearish_factors = []
        
        if technicals:
            if technicals.get("above_20_ema") and technicals.get("above_50_ema"):
                score += 15
                bullish_factors.append("Price above 20 & 50 EMA (Momentum Uptrend)")
            elif not technicals.get("above_20_ema") and not technicals.get("above_50_ema"):
                score -= 15
                bearish_factors.append("Price below 20 & 50 EMA (Downtrend)")

            rsi = technicals.get("rsi", 50)
            if 40 <= rsi <= 60:
                score += 5
                bullish_factors.append("RSI in healthy consolidation zone (40-60)")
            elif rsi > 70:
                score -= 10
                bearish_factors.append(f"RSI overbought ({rsi:.1f})")
            elif rsi < 30:
                bullish_factors.append(f"RSI oversold rebound territory ({rsi:.1f})")
                score += 5

            rvol = technicals.get("rvol", 1.0)
            if rvol >= 1.5:
                score += 10
                bullish_factors.append(f"High relative volume surge ({rvol:.1f}x)")
            elif rvol < 0.6:
                score -= 5
                bearish_factors.append(f"Low trading interest (RVOL {rvol:.1f}x)")

        if sweep_signal:
            if sweep_signal["direction"] == "BUY":
                score += 20
                bullish_factors.append(sweep_signal["rationale"])
            elif sweep_signal["direction"] == "SELL":
                score -= 20
                bearish_factors.append(sweep_signal["rationale"])

        score = max(5, min(95, score))
        verdict = "STRONG_BUY" if score >= 75 else ("BUY" if score >= 60 else ("STRONG_SELL" if score <= 25 else ("SELL" if score <= 40 else "NEUTRAL")))

        return {
            "symbol": symbol,
            "last_price": ticker.get("last_price", 0.0),
            "change_24h_pct": ticker.get("change_24h_pct", 0.0),
            "volume_24h": ticker.get("volume_24h", 0.0),
            "quote_volume_24h": ticker.get("quote_volume_24h", 0.0),
            "conviction_score": score,
            "verdict": verdict,
            "technicals": technicals,
            "liquidity_sweep": sweep_signal,
            "bullish_factors": bullish_factors,
            "bearish_factors": bearish_factors,
        }

    def scan_all(self, timeframe: str = "15m", output_file: Optional[str] = None) -> List[Dict[str, Any]]:
        """Scan all symbols in the watchlist and sort by conviction score."""
        results = []
        for symbol in self.watchlist:
            try:
                res = self.scan_symbol(symbol, timeframe=timeframe)
                results.append(res)
            except Exception as e:
                logger.error(f"Error scanning {symbol}: {e}")
                
        results.sort(key=lambda x: x["conviction_score"], reverse=True)

        if output_file:
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            with open(output_file, "w") as f:
                json.dump(results, f, indent=2)

        return results
