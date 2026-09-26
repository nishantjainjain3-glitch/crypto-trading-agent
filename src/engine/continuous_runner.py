import os
import time
import logging
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()
from src.exchanges.ccxt_client import CryptoExchangeClient
from src.analysis.crypto_scanner import CryptoScanner, DEFAULT_WATCHLIST
from src.engine.position_sizer import PositionSizer
from src.engine.crypto_gatekeeper import CryptoTradeGatekeeper
from src.engine.crypto_paper_trader import CryptoPaperTrader
from src.engine.counterfactual_tracker import CounterfactualTracker
from src.notifications.telegram import TelegramNotifier

logger = logging.getLogger(__name__)

class ContinuousCryptoRunner:
    """Orchestrates 24/7 crypto scanning, gatekeeper validation, and execution."""

    def __init__(
        self,
        watchlist: Optional[List[str]] = None,
        data_dir: str = "data",
    ):
        self.watchlist = watchlist or DEFAULT_WATCHLIST
        self.client = CryptoExchangeClient()
        self.scanner = CryptoScanner(exchange_client=self.client, watchlist=self.watchlist)
        self.paper_trader = CryptoPaperTrader(data_dir=data_dir)
        self.gatekeeper = CryptoTradeGatekeeper()
        self.counterfactual_tracker = CounterfactualTracker(
            ledger_path=os.path.join(data_dir, "counterfactual_ledger.json"),
            attribution_path=os.path.join(data_dir, "gatekeeper_attribution.json"),
        )
        self.position_sizer = PositionSizer()
        self.notifier = TelegramNotifier()
        self.is_live = os.getenv("LIVE_EXECUTION_ENABLED", "false").lower() == "true"
        if self.is_live and self.client.exchange:
            try:
                bal = self.client.fetch_balance()
                live_cash = bal.get("free", {}).get("USDT", 0.0)
                if len(self.paper_trader.positions) == 0:
                    self.paper_trader.ledger["virtual_cash_usdt"] = live_cash
                    if self.paper_trader.ledger.get("initial_capital_usdt", 0) <= 1.0:
                        self.paper_trader.ledger["initial_capital_usdt"] = live_cash
                    self.paper_trader._save_ledger()
                    logger.info(f"Synchronized ledger with Binance free cash: ${live_cash:.2f} USDT")
            except Exception as e:
                logger.error(f"Failed syncing live cash to ledger: {e}")

    def run_single_iteration(self) -> Dict[str, Any]:
        """Execute a single complete scan, management, and execution cycle."""
        iteration_log = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "closed_trades": [],
            "new_trades": [],
            "vetoed_candidates": [],
        }

        # Step 1: Fetch current market prices for active positions and watchlist
        active_symbols = list(self.paper_trader.positions.keys())
        symbols_to_price = list(set(self.watchlist + active_symbols))
        current_prices = {}

        for sym in symbols_to_price:
            try:
                t = self.client.fetch_ticker(sym)
                if t.get("last_price", 0) > 0:
                    current_prices[sym] = t["last_price"]
            except Exception as e:
                logger.error(f"Error fetching ticker for {sym}: {e}")

        # Step 2: Update existing positions (trailing stop, targets, stops)
        closed = self.paper_trader.update_positions(current_prices)
        iteration_log["closed_trades"] = closed
        for trade in closed:
            if self.is_live and trade.get("direction") == "BUY":
                try:
                    base_currency = trade["symbol"].split("/")[0]
                    bal = self.client.fetch_balance()
                    avail = bal.get("free", {}).get(base_currency, 0.0)
                    sell_qty = min(trade["quantity"], avail)
                    formatted_qty = self.client.exchange.amount_to_precision(trade["symbol"], sell_qty)
                    logger.info(f"Placing LIVE Binance Market Sell to close {trade['symbol']} for {formatted_qty}")
                    sell_order = self.client.create_market_sell(trade["symbol"], float(formatted_qty))
                    logger.info(f"Binance exit order filled! Order ID: {sell_order.get('id')}")
                except Exception as e:
                    logger.error(f"Failed to execute live exit on Binance for {trade['symbol']}: {e}")

            msg = (
                f"🚨 *Crypto Trade Closed*\n"
                f"Symbol: `{trade['symbol']}`\n"
                f"Exit Price: `${trade['exit_price']}`\n"
                f"Net PnL: `${trade['net_pnl_usd']}` ({trade['pnl_pct']}%)\n"
                f"Reason: {trade['exit_reason']}"
            )
            self.notifier.send_message(msg)

        # Step 2b: Update open counterfactual shadow trades with current market prices
        resolved_cf = self.counterfactual_tracker.evaluate_open_counterfactuals(current_prices)
        if resolved_cf:
            iteration_log["resolved_counterfactuals"] = resolved_cf

        # Step 3: Run full scanner on watchlist
        candidates = self.scanner.scan_all()

        # Step 4: Evaluate candidates through gatekeeper
        ledger_summary = self.paper_trader.get_portfolio_summary(current_prices)
        current_equity = ledger_summary["total_equity_usdt"]
        daily_pnl = ledger_summary["realized_pnl_usdt"]

        for cand in candidates:
            symbol = cand["symbol"]
            score = cand["conviction_score"]
            technicals = cand.get("technicals", {})
            sweep = cand.get("liquidity_sweep")

            # Only consider high conviction setups (Score >= 70 or confirmed sweep)
            if score < 70 and not sweep:
                continue

            direction = "BUY"
            if sweep and sweep.get("direction") == "SELL":
                direction = "SELL"

            # Spot trading only allows opening BUY positions
            if self.is_live and direction != "BUY":
                logger.debug(f"Skipping short setup {symbol} because Binance spot cannot short.")
                continue

            entry_price = cand["last_price"]
            atr = technicals.get("atr", entry_price * 0.02)
            
            if sweep:
                stop_loss = sweep["stop_loss"]
                target_price = sweep["target_price"]
            else:
                stop_loss = round(entry_price - (1.5 * atr), 4) if direction == "BUY" else round(entry_price + (1.5 * atr), 4)
                target_price = round(entry_price + (3.0 * atr), 4) if direction == "BUY" else round(entry_price - (3.0 * atr), 4)

            # Pass through gatekeeper
            peak_equity = self.paper_trader.ledger.get("peak_equity_usdt", current_equity)
            passed, verdict, veto_reasons = self.gatekeeper.evaluate_candidate(
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                stop_loss=stop_loss,
                target_price=target_price,
                technicals=technicals,
                active_positions=self.paper_trader.positions,
                daily_pnl_usd=daily_pnl,
                is_liquidity_sweep=(sweep is not None),
                current_equity=current_equity,
                peak_equity=peak_equity,
                order_book_analysis=cand.get("order_book"),
            )

            if not passed:
                iteration_log["vetoed_candidates"].append({
                    "symbol": symbol,
                    "reasons": veto_reasons,
                })
                self.counterfactual_tracker.record_declined_setup(
                    symbol=symbol,
                    direction=direction,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    target_price=target_price,
                    atr=atr,
                    veto_reasons=veto_reasons,
                    score=score,
                )
                continue

            # Compute position size
            size_info = self.position_sizer.calculate_size(
                symbol=symbol,
                entry_price=entry_price,
                stop_loss=stop_loss,
                atr=atr,
                current_equity=current_equity,
            )

            if self.is_live:
                try:
                    bal = self.client.fetch_balance()
                    live_cash = bal.get("free", {}).get("USDT", 0.0)
                    if live_cash < 5.0:
                        logger.warning(f"Live cash ${live_cash:.2f} is below $5.00 minNotional. Skipping live buy.")
                        continue
                    # For small accounts, allocate 92% of available cash to leave buffer for fees and slippage
                    alloc = min(live_cash * 0.92, size_info.get("allocated_capital_usd", live_cash * 0.92))
                    if alloc < 5.05:
                        alloc = 5.05
                    raw_qty = alloc / entry_price
                    formatted_qty = self.client.exchange.amount_to_precision(symbol, raw_qty)
                    qty = float(formatted_qty)
                    if (qty * entry_price) < 5.0:
                        logger.warning(f"Calculated notional ${(qty * entry_price):.2f} below $5.00 minNotional. Skipping.")
                        continue
                except Exception as e:
                    logger.error(f"Error sizing live order: {e}")
                    qty = size_info["quantity"]
            else:
                qty = size_info["quantity"]

            try:
                # Live order execution on Binance
                if self.is_live:
                    logger.info(f"Placing LIVE Binance Market Buy on {symbol} for {qty}")
                    live_order = self.client.create_market_buy(symbol, qty)
                    logger.info(f"Binance order filled! Order ID: {live_order.get('id')}")

                pos = self.paper_trader.open_position(
                    symbol=symbol,
                    direction=direction,
                    entry_price=entry_price,
                    quantity=qty,
                    stop_loss=stop_loss,
                    target_price=target_price,
                    atr=atr,
                    rationale=f"Score {score}/100 | {'LIVE BROKER' if self.is_live else 'PAPER'} | {cand['verdict']}",
                )
                iteration_log["new_trades"].append(pos)

                msg = (
                    f"⚡ *New Crypto Position Opened ({'LIVE' if self.is_live else 'PAPER'})*\n"
                    f"Pair: `{symbol}` ({direction})\n"
                    f"Entry: `${entry_price}`\n"
                    f"Stop Loss: `${stop_loss}`\n"
                    f"Target: `${target_price}`\n"
                    f"Quantity: `{qty}`\n"
                    f"Conviction: {score}/100"
                )
                self.notifier.send_message(msg)
            except Exception as e:
                logger.error(f"Failed opening position for {symbol}: {e}")

        return iteration_log
