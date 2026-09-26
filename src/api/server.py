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
from src.engine.ip_monitor import IPMonitor, load_whitelisted_ips, save_whitelisted_ips

app = FastAPI(title="Crypto Trade Agent API", version="1.0.0")

# Global instances
exchange_client = CryptoExchangeClient()
scanner = CryptoScanner(exchange_client=exchange_client)
runner = ContinuousCryptoRunner()
paper_trader = runner.paper_trader
backtester = CryptoBacktester()
ip_monitor = IPMonitor()

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
    paper_trader.positions = paper_trader._load_positions()
    paper_trader.ledger = paper_trader._load_ledger()
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

@app.get("/api/status")
def get_system_status():
    """Fetch live system health, connection status, and balance."""
    live_enabled = os.getenv("LIVE_EXECUTION_ENABLED", "false").lower() == "true"
    bal_usdt = 0.0
    conn_ok = False
    if exchange_client.exchange:
        try:
            b = exchange_client.fetch_balance()
            bal_usdt = b.get("free", {}).get("USDT", 0.0)
            conn_ok = True
        except Exception:
            conn_ok = False

    ip_info = ip_monitor.check_ip()
    return {
        "status": "ONLINE",
        "live_execution_enabled": live_enabled,
        "exchange": exchange_client.exchange_id,
        "exchange_connected": conn_ok,
        "free_usdt": bal_usdt,
        "open_positions": len(paper_trader.positions),
        "total_trades": len(paper_trader.history),
        "ip_status": ip_info,
    }

@app.get("/api/ip")
def get_ip_status():
    """Fetch current public IP and Binance whitelist status."""
    return ip_monitor.check_ip()

@app.post("/api/ip/whitelist")
def add_ip_to_whitelist(ip: str = Query(...)):
    """Add a new IP address to the local whitelist cache."""
    ips = load_whitelisted_ips()
    if ip not in ips:
        ips.append(ip)
        save_whitelisted_ips(ips)
    return {"status": "SUCCESS", "whitelisted_ips": ips}

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

@app.get("/api/risk")
def get_portfolio_risk():
    """Fetch institutional risk analytics: Cornish-Fisher VaR, CVaR, Sortino, Drawdown."""
    import pandas as pd
    from src.analysis.risk_metrics import PortfolioRiskEngine
    history = paper_trader.history
    if not history:
        return {"status": "NO_CLOSED_TRADES_YET", "var_historical_pct": 0.0, "cvar_pct": 0.0}
    returns = pd.Series([t.get("pnl_pct", 0.0) / 100.0 for t in history])
    engine = PortfolioRiskEngine(returns)
    return engine.compute_all_metrics()

@app.get("/api/smart-money")
def get_smart_money_signals(chain: str = "56"):
    """Fetch Binance Web3 live smart-money wallet signals and top inflows."""
    from src.analysis.smart_money_signals import fetch_smart_money_signals, fetch_smart_money_inflows
    signals = fetch_smart_money_signals(chain_id=chain, page_size=20)
    inflows = fetch_smart_money_inflows(chain_id=chain, period="24h")
    return {
        "chain_id": chain,
        "signals_count": len(signals),
        "signals": signals[:10],
        "top_inflows": inflows[:10],
    }

@app.get("/api/counterfactuals")
def get_counterfactuals():
    """Fetch all recorded counterfactual shadow trades and filter attribution metrics."""
    return {
        "summary": runner.counterfactual_tracker.get_summary(),
        "attribution": runner.counterfactual_tracker.recompute_attribution(),
        "recent_entries": runner.counterfactual_tracker.entries[-30:],
    }

@app.get("/api/token-audit")
def get_token_audit(contract: str, chain: str = "56"):
    """Audit token contract for honeypots, rug pulls, and hidden taxes via Binance Web3 Security."""
    from src.analysis.token_security import audit_token_contract
    return audit_token_contract(contract_address=contract, chain_id=chain)

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

@app.get("/api/logs")
def get_logs(limit: int = 100):
    """Fetch recent execution log lines."""
    log_file = "data/trading_agent.log"
    if not os.path.exists(log_file):
        return {"lines": []}
    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            return {"lines": lines[-limit:]}
    except Exception as e:
        return {"error": str(e), "lines": []}

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
            logger.info("Autonomous scan heartbeat: evaluating watchlist order books and positions...")
            log = await asyncio.to_thread(runner.run_single_iteration)
            closed_cnt = len(log.get("closed_trades", []))
            new_cnt = len(log.get("new_trades", []))
            veto_cnt = len(log.get("vetoed_candidates", []))
            logger.info(f"Scan cycle complete: {new_cnt} entries, {closed_cnt} exits, {veto_cnt} filtered setups.")
        except Exception as e:
            logger.error(f"Error in background runner: {e}")
        await asyncio.sleep(60)

@app.on_event("startup")
async def start_autonomous_runner():
    asyncio.create_task(background_runner_loop())
