"""Unified CCXT exchange client for crypto market data and order simulation."""

import os
import time
import logging
from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

class CryptoExchangeClient:
    """Wrapper around CCXT and fallback data providers for crypto assets."""

    def __init__(
        self,
        exchange_id: str = "binance",
        api_key: Optional[str] = None,
        secret: Optional[str] = None,
        testnet: bool = False,
    ):
        self.exchange_id = exchange_id.lower()
        self.api_key = api_key or os.getenv("EXCHANGE_API_KEY", "")
        self.secret = secret or os.getenv("EXCHANGE_SECRET", "")
        self.testnet = testnet or os.getenv("EXCHANGE_TESTNET", "false").lower() == "true"
        self.exchange = None
        self._init_exchange()

    def _init_exchange(self):
        """Initialise CCXT exchange instance with rate limiting."""
        try:
            import ccxt
            exchange_class = getattr(ccxt, self.exchange_id, None)
            if exchange_class is None:
                logger.warning(f"Exchange {self.exchange_id} not found in ccxt, falling back to binance")
                exchange_class = ccxt.binance

            config = {
                "enableRateLimit": True,
                "timeout": 15000,
            }
            if self.api_key and self.secret:
                config["apiKey"] = self.api_key
                config["secret"] = self.secret

            self.exchange = exchange_class(config)
            if self.testnet and hasattr(self.exchange, "set_sandbox_mode"):
                self.exchange.set_sandbox_mode(True)
            logger.info(f"Initialized {self.exchange_id} exchange client")
        except Exception as e:
            logger.warning(f"Could not initialize ccxt {self.exchange_id}: {e}. Running in offline/fallback mode.")
            self.exchange = None

    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch current ticker price and 24h stats."""
        # Normalize symbol: e.g. BTC/USDT or BTC-USD
        clean_symbol = symbol.replace("-", "/").upper()
        if not clean_symbol.endswith("/USDT") and "/" not in clean_symbol:
            clean_symbol = f"{clean_symbol}/USDT"

        if self.exchange:
            try:
                ticker = self.exchange.fetch_ticker(clean_symbol)
                return {
                    "symbol": clean_symbol,
                    "last_price": float(ticker.get("last") or ticker.get("close") or 0.0),
                    "bid": float(ticker.get("bid") or ticker.get("last") or 0.0),
                    "ask": float(ticker.get("ask") or ticker.get("last") or 0.0),
                    "high_24h": float(ticker.get("high") or 0.0),
                    "low_24h": float(ticker.get("low") or 0.0),
                    "volume_24h": float(ticker.get("baseVolume") or 0.0),
                    "quote_volume_24h": float(ticker.get("quoteVolume") or 0.0),
                    "change_24h_pct": float(ticker.get("percentage") or 0.0),
                    "timestamp": ticker.get("timestamp") or int(time.time() * 1000),
                }
            except Exception as e:
                logger.debug(f"CCXT fetch_ticker error for {clean_symbol}: {e}")

        # Fallback using yfinance if CCXT fails or network restriction
        return self._fetch_yfinance_ticker(clean_symbol)

    def _fetch_yfinance_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fallback ticker lookup using yfinance."""
        import yfinance as yf
        base = symbol.split("/")[0]
        yf_symbol = f"{base}-USD"
        try:
            ticker_obj = yf.Ticker(yf_symbol)
            fast_info = ticker_obj.fast_info
            last_price = float(fast_info.last_price or 0.0)
            prev_close = float(fast_info.previous_close or last_price)
            pct = round(((last_price - prev_close) / prev_close) * 100, 2) if prev_close else 0.0
            return {
                "symbol": symbol,
                "last_price": last_price,
                "bid": last_price,
                "ask": last_price,
                "high_24h": float(fast_info.day_high or last_price),
                "low_24h": float(fast_info.day_low or last_price),
                "volume_24h": float(fast_info.last_volume or 0.0),
                "quote_volume_24h": float(fast_info.last_volume or 0.0) * last_price,
                "change_24h_pct": pct,
                "timestamp": int(time.time() * 1000),
            }
        except Exception as e:
            logger.error(f"Fallback yfinance ticker failed for {yf_symbol}: {e}")
            return {
                "symbol": symbol,
                "last_price": 0.0,
                "bid": 0.0,
                "ask": 0.0,
                "high_24h": 0.0,
                "low_24h": 0.0,
                "volume_24h": 0.0,
                "quote_volume_24h": 0.0,
                "change_24h_pct": 0.0,
                "timestamp": int(time.time() * 1000),
            }

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
    ) -> pd.DataFrame:
        """Fetch OHLCV candlestick data into a pandas DataFrame."""
        clean_symbol = symbol.replace("-", "/").upper()
        if "/" not in clean_symbol:
            clean_symbol = f"{clean_symbol}/USDT"

        if self.exchange:
            try:
                ohlcv = self.exchange.fetch_ohlcv(clean_symbol, timeframe=timeframe, limit=limit)
                if ohlcv and len(ohlcv) > 0:
                    df = pd.DataFrame(
                        ohlcv,
                        columns=["timestamp", "open", "high", "low", "close", "volume"],
                    )
                    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
                    df.set_index("datetime", inplace=True)
                    return df
            except Exception as e:
                logger.debug(f"CCXT fetch_ohlcv failed for {clean_symbol} {timeframe}: {e}")

        # Fallback to yfinance
        return self._fetch_yfinance_ohlcv(clean_symbol, timeframe=timeframe, limit=limit)

    def _fetch_yfinance_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
    ) -> pd.DataFrame:
        """Fallback OHLCV fetch via yfinance."""
        import yfinance as yf
        base = symbol.split("/")[0]
        yf_symbol = f"{base}-USD"
        
        tf_map = {
            "15m": ("15m", "5d"),
            "1h": ("1h", "1mo"),
            "4h": ("1h", "3mo"),  # yf doesn't have 4h, resample 1h
            "1d": ("1d", "1y"),
        }
        interval, period = tf_map.get(timeframe, ("1h", "1mo"))

        try:
            df = yf.download(yf_symbol, period=period, interval=interval, progress=False)
            if df.empty:
                return pd.DataFrame()
            
            # Flatten MultiIndex columns if present
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [col[0].lower() for col in df.columns]
            else:
                df.columns = [col.lower() for col in df.columns]

            if timeframe == "4h":
                df = df.resample("4h").agg({
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }).dropna()

            df = df.tail(limit).copy()
            df["timestamp"] = (df.index.astype(np.int64) // 10**6).astype(int)
            return df
        except Exception as e:
            logger.error(f"Fallback yfinance OHLCV failed for {yf_symbol}: {e}")
            return pd.DataFrame()

    def fetch_order_book(self, symbol: str, limit: int = 10) -> Dict[str, Any]:
        """Fetch current order book depth and spread."""
        clean_symbol = symbol.replace("-", "/").upper()
        if "/" not in clean_symbol:
            clean_symbol = f"{clean_symbol}/USDT"

        if self.exchange:
            try:
                ob = self.exchange.fetch_order_book(clean_symbol, limit=limit)
                bids = ob.get("bids", [])[:limit]
                asks = ob.get("asks", [])[:limit]
                best_bid = bids[0][0] if bids else 0.0
                best_ask = asks[0][0] if asks else 0.0
                spread = best_ask - best_bid if best_ask and best_bid else 0.0
                spread_bps = (spread / best_bid * 10000) if best_bid else 0.0
                return {
                    "symbol": clean_symbol,
                    "bids": bids,
                    "asks": asks,
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "spread": round(spread, 4),
                    "spread_bps": round(spread_bps, 2),
                }
            except Exception as e:
                logger.debug(f"CCXT fetch_order_book failed: {e}")

        # Synthetic book from ticker
        t = self.fetch_ticker(clean_symbol)
        p = t["last_price"]
        return {
            "symbol": clean_symbol,
            "bids": [[p * 0.9995, 1.5], [p * 0.999, 3.2]],
            "asks": [[p * 1.0005, 1.5], [p * 1.001, 3.2]],
            "best_bid": p * 0.9995,
            "best_ask": p * 1.0005,
            "spread": round(p * 0.001, 4),
            "spread_bps": 10.0,
        }
