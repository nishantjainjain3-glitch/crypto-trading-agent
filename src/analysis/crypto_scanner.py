"""Market screener scanning liquid crypto pairs for actionable setups."""

import os
import json
import logging
from typing import List, Dict, Any, Optional
from src.exchanges.ccxt_client import CryptoExchangeClient
from src.analysis.technical_indicators import compute_all_technicals
from src.analysis.liquidity_sweep import detect_liquidity_sweep
from src.analysis.order_flow import analyze_order_flow
from src.analysis.order_book_depth import analyze_order_book_depth
from src.analysis.smart_money_signals import analyze_smart_money_backing

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
    """Scans crypto universe with EMAs, RSI, RVOL, Liquidity Sweeps, Wyckoff VSA, CVD, and L2 Order Book Depth."""

    def __init__(
        self,
        exchange_client: Optional[CryptoExchangeClient] = None,
        watchlist: Optional[List[str]] = None,
    ):
        self.client = exchange_client or CryptoExchangeClient()
        self.watchlist = watchlist or DEFAULT_WATCHLIST

    def scan_symbol(self, symbol: str, timeframe: str = "15m") -> Dict[str, Any]:
        """Perform comprehensive technical, order flow, and order book scan for a single symbol."""
        ticker = self.client.fetch_ticker(symbol)
        df = self.client.fetch_ohlcv(symbol, timeframe=timeframe, limit=100)

        technicals = compute_all_technicals(df) if not df.empty else {}
        sweep_signal = detect_liquidity_sweep(df) if not df.empty else None
        order_flow = analyze_order_flow(df) if not df.empty else {}
        order_book = analyze_order_book_depth(self.client, symbol, limit=20)

        # Base conviction score (0-100)
        score = 50
        bullish_factors = []
        bearish_factors = []

        if technicals:
            if technicals.get("above_20_ema") and technicals.get("above_50_ema"):
                score += 10
                bullish_factors.append("Price above 20 & 50 EMA (Momentum Uptrend)")
            elif not technicals.get("above_20_ema") and not technicals.get("above_50_ema"):
                score -= 10
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
                score += 15
                bullish_factors.append(sweep_signal["rationale"])
            elif sweep_signal["direction"] == "SELL":
                score -= 15
                bearish_factors.append(sweep_signal["rationale"])

        # Order Flow & Smart Money Confluence
        if order_flow:
            of_verdict = order_flow.get("verdict", "NEUTRAL")
            if of_verdict in ["STRONG_ACCUMULATION", "ACCUMULATION"]:
                score += 10
                bullish_factors.append(f"Smart Money Order Flow: {of_verdict} (Score: {order_flow.get('order_flow_score')})")
            elif of_verdict in ["STRONG_DISTRIBUTION", "DISTRIBUTION"]:
                score -= 10
                bearish_factors.append(f"Smart Money Order Flow: {of_verdict} (Score: {order_flow.get('order_flow_score')})")

        # L2 Order Book Depth Confluence
        if order_book and order_book.get("available", False):
            imb = order_book.get("imbalance_ratio", 1.0)
            if imb >= 1.5:
                score += 5
                bullish_factors.append(f"Order book bid absorption (Imbalance: {imb:.2f})")
            elif imb < 0.67:
                score -= 5
                bearish_factors.append(f"Order book ask resistance (Imbalance: {imb:.2f})")

            for v in order_book.get("violations", []):
                score -= 10
                bearish_factors.append(f"Order book depth warning: {v}")

        # Binance Web3 On-Chain Smart Money Confluence
        smart_money = analyze_smart_money_backing(symbol)
        if smart_money.get("is_accumulating"):
            score += 15
            bullish_factors.append(smart_money["rationale"])
        elif smart_money.get("direction") == "SELL" or smart_money.get("exit_rate_pct", 0) > 80.0:
            score -= 10
            bearish_factors.append(f"Smart Money exit risk: {smart_money.get('exit_rate_pct')}% of tracked whales exited")

        score = max(5, min(95, score))
        verdict = (
            "STRONG_BUY"
            if score >= 75
            else ("BUY" if score >= 60 else ("STRONG_SELL" if score <= 25 else ("SELL" if score <= 40 else "NEUTRAL")))
        )

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
            "order_flow": order_flow,
            "order_book": order_book,
            "smart_money": smart_money,
            "bullish_factors": bullish_factors,
            "bearish_factors": bearish_factors,
        }

    def scan_watchlist(self, timeframe: str = "15m") -> List[Dict[str, Any]]:
        """Scan entire watchlist and return opportunities sorted by conviction."""
        results = []
        for symbol in self.watchlist:
            try:
                res = self.scan_symbol(symbol, timeframe=timeframe)
                results.append(res)
            except Exception as e:
                logger.error(f"Error scanning {symbol}: {e}")
        results.sort(key=lambda x: x["conviction_score"], reverse=True)
        return results

    def scan_all(self, timeframe: str = "15m") -> List[Dict[str, Any]]:
        """Alias for scan_watchlist for backwards compatibility."""
        return self.scan_watchlist(timeframe=timeframe)
