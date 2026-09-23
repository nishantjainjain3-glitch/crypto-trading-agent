"""Entrypoint runner for the Crypto Trading Agent."""

import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

def main():
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    live_enabled = os.getenv("LIVE_EXECUTION_ENABLED", "false").lower() == "true"
    capital = os.getenv("PAPER_CAPITAL_USDT", "10000.0")

    print("\n" + "=" * 65)
    print("           ⚡ CRYPTO TRADE AGENT — 24/7 WORKSTATION ⚡")
    print("=" * 65)
    print(f" • Mode:                  {'LIVE BROKER EXECUTION' if live_enabled else 'VIRTUAL PAPER TRADING (SAFE)'}")
    print(f" • Starting Paper Ledger: ${capital} USDT")
    print(f" • Risk Model:            1% ATR Volatility Sizing (Ray Fu)")
    print(f" • Strategy:              Institutional Liquidity Sweeps & CPR Surfing")
    print(f" • Web Dashboard:         http://localhost:{port}")
    print("=" * 65 + "\n")

    uvicorn.run("src.api.server:app", host=host, port=port, reload=False)

if __name__ == "__main__":
    main()
