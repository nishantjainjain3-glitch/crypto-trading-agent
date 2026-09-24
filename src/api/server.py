"""FastAPI server for crypto workstation dashboard and API endpoints."""

import os
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.exchanges.ccxt_client import CryptoExchangeClient
from src.analysis.crypto_scanner import CryptoScanner
from src.analysis.backtest_runner import CryptoBacktester
from src.analysis.regime_service import get_current_regime
from src.engine.crypto_paper_trader import CryptoPaperTrader
from src.engine.continuous_runner import ContinuousCryptoRunner

app = FastAPI(title="Crypto Trade Agent API", version="1.0.0")

# Global instances
exchange_client = CryptoExchangeClient()
scanner = CryptoScanner(exchange_client=exchange_client)
paper_trader = CryptoPaperTrader()
runner = ContinuousCryptoRunner()
backtester = CryptoBacktester()

static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def get_dashboard():
    """Serve web dashboard index page."""
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Crypto Trade Agent API running. Dashboard UI loading."}

@app.get("/api/portfolio")
def get_portfolio():
    """Fetch current portfolio, ledger metrics, and open positions."""
    # Fetch live prices for open positions
    open_syms = list(paper_trader.positions.keys())
    prices = {}
    for s in open_syms:
        t = exchange_client.fetch_ticker(s)
        if t.get("last_price"):
            prices[s] = t["last_price"]

    summary = paper_trader.get_portfolio_summary(prices)
    summary["live_execution_enabled"] = os.getenv("LIVE_EXECUTION_ENABLED", "false").lower() == "true"
    summary["exchange_id"] = exchange_client.exchange_id
    return summary

@app.get("/api/screener")
def get_screener_results():
    """Fetch real-time scanner analysis across the watchlist."""
    results = scanner.scan_all()
    return {"count": len(results), "candidates": results}

@app.get("/api/regime")
def get_market_regime():
    """Fetch current macro crypto market regime health score and indicators."""
    return get_current_regime()

@app.get("/api/history")
def get_trade_history():
    """Fetch closed paper trading history."""
    return {"count": len(paper_trader.history), "history": paper_trader.history}

class BacktestRequest(BaseModel):
    symbol: str = "BTC-USD"
    period: str = "1y"
    fast_period: int = 20
    slow_period: int = 50

@app.post("/api/backtest")
def run_backtest(req: BacktestRequest):
    """Run historical backtest with quantitative risk metrics."""
    try:
        df = backtester.fetch_historical_data(req.symbol, period=req.period)
        if df.empty:
            raise HTTPException(status_code=400, detail="Could not download data for symbol")
        metrics = backtester.backtest_ema_crossover(df, req.fast_period, req.slow_period)
        return metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/runner/step")
def trigger_runner_step():
    """Run a single scanning and position management iteration."""
    log = runner.run_single_iteration()
    return {"status": "SUCCESS", "log": log}

import asyncio
import logging

logger = logging.getLogger(__name__)

async def background_runner_loop():
    """Autonomous 24/7 background loop running market scans and position checks."""
    while True:
        try:
            runner.run_single_iteration()
        except Exception as e:
            logger.error(f"Error in background runner: {e}")
        await asyncio.sleep(60)

@app.on_event("startup")
async def start_autonomous_runner():
    asyncio.create_task(background_runner_loop())
