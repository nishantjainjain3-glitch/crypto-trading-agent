# Crypto Trade Agent (24/7 Autonomous Workstation)

An autonomous cryptocurrency research, backtesting, and paper trading workstation with real-time exchange data feeds via CCXT, institutional liquidity sweep detection, 1% ATR volatility position sizing, deterministic adversarial gatekeeping, and a dark-mode web dashboard.

---

## Architecture & Features

- **24/7 Market Surveillance:** Continuous scanning across liquid crypto pairs (BTC, ETH, SOL, BNB, XRP, DOGE, ADA, AVAX, LINK, SUI).
- **Institutional Liquidity Sweeps:** Identifies sell-side liquidity (SSL) and buy-side liquidity (BSL) stop-hunts where retail stops are swept before strong volume reversal.
- **Ray Fu 1% ATR Volatility Sizing:** Position sizes strictly limited to risking 1.0% of portfolio equity per trade, adjusted for crypto's wider volatility swings.
- **Deterministic Adversarial Gatekeeper:**
  - Enforces minimum 1.5:1 reward-to-risk ratio.
  - Requires relative volume (RVOL >= 1.2x).
  - Trend surfing above 20 EMA for longs.
  - Overbought RSI protection (> 78.0 filter).
  - Maximum concurrent positions cap (3 concurrent positions).
  - Daily loss circuit breaker ($500 USD daily stop).
- **Virtual Paper Trading Ledger:** $10,000 USDT virtual bankroll modeling 0.075% exchange taker fees and 0.02% slippage. Dynamic breakeven (+1.0x ATR) and trailing stop (+1.75x ATR).
- **Quantitative Strategy Backtesting:** Built-in engine computing Sharpe, Sortino, Value at Risk (VaR 95%), CVaR, and maximum drawdown over historical periods.
- **Web Terminal:** Fast responsive web dashboard with live portfolio metrics, open paper positions, ranked conviction screener, and interactive backtesting widget.
- **Telegram Phone Alerts:** Instant push notifications on entries, exits, trailing stops, and daily wraps.

---

## Directory Structure

```
crypto-trading-agent/
├── data/                             # Persistent ledger and position files
│   ├── crypto_paper_ledger.json
│   ├── crypto_paper_positions.json
│   └── crypto_paper_history.json
├── src/
│   ├── exchanges/
│   │   └── ccxt_client.py           # CCXT Binance/Bybit client with yfinance fallback
│   ├── analysis/
│   │   ├── technical_indicators.py  # ATR, RSI, EMAs, Bollinger Bands, CPR pivots
│   │   ├── liquidity_sweep.py       # SSL / BSL stop-hunt detection
│   │   ├── crypto_scanner.py        # Multi-pair conviction screener
│   │   └── backtest_runner.py       # Historical backtester with risk metrics
│   ├── engine/
│   │   ├── position_sizer.py        # 1% ATR volatility sizer
│   │   ├── crypto_gatekeeper.py     # Deterministic safety gatekeeper
│   │   ├── crypto_paper_trader.py   # Paper trader, trailing stops, taker fees
│   │   └── continuous_runner.py     # 24/7 scanning and execution loop
│   ├── notifications/
│   │   └── telegram.py              # Telegram alert dispatcher
│   └── api/
│       └── server.py                # FastAPI endpoints & dashboard backend
├── static/
│   └── index.html                   # Dark-mode dashboard frontend
├── tests/
│   └── test_crypto_pipeline.py      # Unit test suite
├── .env.example                     # Environment template
├── .env                             # Active configuration (safety locked by default)
├── pytest.ini                       # Pytest configuration
├── requirements.txt                 # Python dependencies
└── run.py                           # Workstation launcher
```

---

## Quickstart

### 1. Set Active Workspace
Open `C:\Users\HP\.gemini\antigravity\scratch\crypto-trading-agent` in your IDE.

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run Unit Tests
```bash
pytest -v
```

### 4. Run Quantitative Backtest
```bash
python -m src.analysis.backtest_runner --symbol BTC-USD --period 1y
```

### 5. Launch Web Dashboard
```bash
python run.py
```
Open `http://localhost:8000` in your web browser.

---

## Safety & Execution Locks

The workstation starts in **Safe Paper Trading Mode** (`LIVE_EXECUTION_ENABLED=false`). Live API execution remains locked until you complete a minimum verification period and verify that risk rules and profit targets are met.
