"""Virtual paper trading execution engine and persistent ledger for crypto."""

import os
import json
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from src.engine.protections import CryptoProtectionManager
from src.engine.exit_manager import evaluate_minimal_roi_exit

logger = logging.getLogger(__name__)

class CryptoPaperTrader:
    """
    Simulates crypto spot/futures orders with exchange fee modeling (0.075% taker fee)
    and realistic slippage (0.02%).
    """

    def __init__(
        self,
        data_dir: str = "data",
        initial_capital_usdt: Optional[float] = None,
        taker_fee_pct: float = 0.075,
        slippage_pct: float = 0.02,
        protection_manager: Optional[CryptoProtectionManager] = None,
    ):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.protections = protection_manager or CryptoProtectionManager()
        if initial_capital_usdt is None:
            initial_capital_usdt = float(os.getenv("PAPER_CAPITAL_USDT", "9.27"))
        self.initial_capital = float(initial_capital_usdt)
        self.taker_fee_pct = float(taker_fee_pct)
        self.slippage_pct = float(slippage_pct)

        self.ledger_file = os.path.join(self.data_dir, "crypto_paper_ledger.json")
        self.positions_file = os.path.join(self.data_dir, "crypto_paper_positions.json")
        self.history_file = os.path.join(self.data_dir, "crypto_paper_history.json")

        self.ledger = self._load_ledger()
        self.positions = self._load_positions()
        self.history = self._load_history()

        if not os.path.exists(self.ledger_file):
            self._save_ledger()
        if not os.path.exists(self.positions_file):
            self._save_positions()
        if not os.path.exists(self.history_file):
            self._save_history()

    def _load_ledger(self) -> Dict[str, Any]:
        if os.path.exists(self.ledger_file):
            try:
                with open(self.ledger_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed loading ledger: {e}")
        return {
            "initial_capital_usdt": self.initial_capital,
            "virtual_cash_usdt": self.initial_capital,
            "realized_pnl_usdt": 0.0,
            "total_fees_usdt": 0.0,
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "peak_equity_usdt": self.initial_capital,
            "max_drawdown_pct": 0.0,
            "last_updated": datetime.now().isoformat(),
        }

    def _save_ledger(self):
        with open(self.ledger_file, "w") as f:
            json.dump(self.ledger, f, indent=2)

    def _load_positions(self) -> Dict[str, Any]:
        if os.path.exists(self.positions_file):
            try:
                with open(self.positions_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_positions(self):
        with open(self.positions_file, "w") as f:
            json.dump(self.positions, f, indent=2)

    def _load_history(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_history(self):
        with open(self.history_file, "w") as f:
            json.dump(self.history, f, indent=2)

    def open_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        quantity: float,
        stop_loss: float,
        target_price: float,
        atr: float,
        rationale: str = "",
    ) -> Dict[str, Any]:
        """Open a new simulated position with slippage and fees."""
        # Add slippage: Buy slightly higher, Sell slightly lower
        slip_mult = 1.0 + (self.slippage_pct / 100.0) if direction.upper() == "BUY" else 1.0 - (self.slippage_pct / 100.0)
        executed_price = round(entry_price * slip_mult, 4)
        
        gross_cost = executed_price * quantity
        fee = round(gross_cost * (self.taker_fee_pct / 100.0), 4)

        if self.ledger["virtual_cash_usdt"] < (gross_cost + fee):
            raise ValueError(f"Insufficient cash ${self.ledger['virtual_cash_usdt']:.2f} to cover ${gross_cost + fee:.2f}")

        self.ledger["virtual_cash_usdt"] -= (gross_cost + fee)
        self.ledger["total_fees_usdt"] += fee
        self._save_ledger()

        pos_data = {
            "symbol": symbol,
            "direction": direction.upper(),
            "entry_price": executed_price,
            "quantity": quantity,
            "allocated_usd": round(gross_cost, 2),
            "stop_loss": stop_loss,
            "initial_stop_loss": stop_loss,
            "target_price": target_price,
            "atr": atr,
            "highest_price": executed_price,
            "lowest_price": executed_price,
            "breakeven_triggered": False,
            "trailing_stop_triggered": False,
            "entry_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "entry_fee_usd": fee,
            "rationale": rationale,
        }
        self.positions[symbol] = pos_data
        self._save_positions()
        logger.info(f"Opened simulated {direction} in {symbol} at ${executed_price} (Qty: {quantity})")
        return pos_data

    def update_positions(self, market_prices: Dict[str, float]) -> List[Dict[str, Any]]:
        """Update live unrealized PnL, check trailing stops, and trigger exits."""
        closed_trades = []
        for symbol, pos in list(self.positions.items()):
            current_price = market_prices.get(symbol)
            if not current_price or current_price <= 0:
                continue

            entry_p = pos["entry_price"]
            qty = pos["quantity"]
            atr = pos.get("atr", entry_p * 0.02)
            direction = pos.get("direction", "BUY")

            if direction == "BUY":
                pos["highest_price"] = max(pos.get("highest_price", entry_p), current_price)
                pos["lowest_price"] = min(pos.get("lowest_price", entry_p), current_price)
                unrealized_pnl = (current_price - entry_p) * qty

                # Dynamic Breakeven Rule: at +0.5x ATR move stop to breakeven + buffer
                if not pos["breakeven_triggered"] and (current_price - entry_p) >= (0.5 * atr):
                    pos["stop_loss"] = round(entry_p * 1.0008, 4)
                    pos["breakeven_triggered"] = True
                    logger.info(f"{symbol}: Dynamic breakeven activated at ${pos['stop_loss']}")

                # Trailing Stop Rule: at +1.75x ATR trail at 1.0x ATR behind peak
                if (current_price - entry_p) >= (1.75 * atr):
                    trail_level = round(pos["highest_price"] - (1.0 * atr), 4)
                    if trail_level > pos["stop_loss"]:
                        pos["stop_loss"] = trail_level
                        pos["trailing_stop_triggered"] = True

                # Check Decaying Minimal ROI Target Hit
                entry_time_str = pos.get("entry_time")
                holding_hours = 0.0
                if entry_time_str:
                    try:
                        clean_time = entry_time_str.replace(" UTC", "")
                        dt_entry = datetime.fromisoformat(clean_time)
                        if dt_entry.tzinfo is None:
                            dt_entry = dt_entry.replace(tzinfo=timezone.utc)
                        holding_hours = max(0.0, (datetime.now(timezone.utc) - dt_entry).total_seconds() / 3600.0)
                    except Exception:
                        pass

                roi_eval = evaluate_minimal_roi_exit(entry_p, current_price, holding_hours)
                if roi_eval.get("should_exit", False):
                    closed = self.close_position(symbol, current_price, "DECAYING_ROI_TARGET_REACHED")
                    closed_trades.append(closed)
                # Check Stop Loss Hit
                elif current_price <= pos["stop_loss"]:
                    closed = self.close_position(symbol, current_price, "STOP_LOSS_HIT")
                    closed_trades.append(closed)
                # Check Target Hit
                elif current_price >= pos["target_price"]:
                    closed = self.close_position(symbol, current_price, "TARGET_PRICE_REACHED")
                    closed_trades.append(closed)

            elif direction == "SELL":
                pos["lowest_price"] = min(pos.get("lowest_price", entry_p), current_price)
                pos["highest_price"] = max(pos.get("highest_price", entry_p), current_price)
                unrealized_pnl = (entry_p - current_price) * qty

                if not pos["breakeven_triggered"] and (entry_p - current_price) >= (0.5 * atr):
                    pos["stop_loss"] = round(entry_p * 0.9992, 4)
                    pos["breakeven_triggered"] = True

                if (entry_p - current_price) >= (1.75 * atr):
                    trail_level = round(pos["lowest_price"] + (1.0 * atr), 4)
                    if trail_level < pos["stop_loss"]:
                        pos["stop_loss"] = trail_level
                        pos["trailing_stop_triggered"] = True

                if current_price >= pos["stop_loss"]:
                    closed = self.close_position(symbol, current_price, "STOP_LOSS_HIT")
                    closed_trades.append(closed)
                elif current_price <= pos["target_price"]:
                    closed = self.close_position(symbol, current_price, "TARGET_PRICE_REACHED")
                    closed_trades.append(closed)

        self._save_positions()
        return closed_trades

    def close_position(self, symbol: str, exit_price: float, reason: str) -> Dict[str, Any]:
        """Close an open position and update performance metrics."""
        if symbol not in self.positions:
            raise ValueError(f"No open position found for {symbol}")

        pos = self.positions.pop(symbol)
        qty = pos["quantity"]
        entry_p = pos["entry_price"]
        direction = pos.get("direction", "BUY")

        # Slippage on exit
        slip_mult = 1.0 - (self.slippage_pct / 100.0) if direction == "BUY" else 1.0 + (self.slippage_pct / 100.0)
        actual_exit_p = round(exit_price * slip_mult, 4)
        
        gross_proceeds = actual_exit_p * qty
        exit_fee = round(gross_proceeds * (self.taker_fee_pct / 100.0), 4)
        total_trade_fees = pos.get("entry_fee_usd", 0.0) + exit_fee

        if direction == "BUY":
            raw_pnl = (actual_exit_p - entry_p) * qty
        else:
            raw_pnl = (entry_p - actual_exit_p) * qty

        net_pnl = round(raw_pnl - total_trade_fees, 2)
        pnl_pct = round((net_pnl / pos["allocated_usd"]) * 100, 2)

        # Return capital to ledger
        self.ledger["virtual_cash_usdt"] += (gross_proceeds - exit_fee)
        self.ledger["realized_pnl_usdt"] = round(self.ledger["realized_pnl_usdt"] + net_pnl, 2)
        self.ledger["total_fees_usdt"] = round(self.ledger["total_fees_usdt"] + exit_fee, 2)
        self.ledger["total_trades"] += 1

        if net_pnl > 0:
            self.ledger["winning_trades"] += 1
        else:
            self.ledger["losing_trades"] += 1

        if reason == "STOP_LOSS_HIT":
            self.protections.record_stoploss_hit(symbol, actual_exit_p, pnl_pct)

        total_t = self.ledger["total_trades"]
        self.ledger["win_rate_pct"] = round((self.ledger["winning_trades"] / total_t) * 100, 2) if total_t else 0.0

        highest_seen = pos.get("highest_price", entry_p)
        lowest_seen = pos.get("lowest_price", entry_p)
        if direction == "BUY":
            mfe_pct = round(((highest_seen - entry_p) / entry_p) * 100, 2)
            mae_pct = round(((lowest_seen - entry_p) / entry_p) * 100, 2)
        else:
            mfe_pct = round(((entry_p - lowest_seen) / entry_p) * 100, 2)
            mae_pct = round(((entry_p - highest_seen) / entry_p) * 100, 2)

        holding_seconds = 0
        try:
            entry_clean = pos["entry_time"].replace(" UTC", "")
            dt_ent = datetime.fromisoformat(entry_clean).replace(tzinfo=timezone.utc)
            holding_seconds = int((datetime.now(timezone.utc) - dt_ent).total_seconds())
        except Exception:
            pass

        trade_record = {
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry_p,
            "exit_price": actual_exit_p,
            "quantity": qty,
            "allocated_usd": pos["allocated_usd"],
            "net_pnl_usd": net_pnl,
            "pnl_pct": pnl_pct,
            "mfe_pct": mfe_pct,
            "mae_pct": mae_pct,
            "holding_seconds": holding_seconds,
            "exit_reason": reason,
            "entry_time": pos["entry_time"],
            "exit_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "total_fees_usd": total_trade_fees,
        }
        self.history.append(trade_record)
        
        self._recalculate_performance()
        self._save_ledger()
        self._save_positions()
        self._save_history()

        logger.info(f"Closed {symbol} trade: PnL ${net_pnl:.2f} ({pnl_pct}%) - Reason: {reason}")
        return trade_record

    def _recalculate_performance(self):
        """Update drawdown and profit factor from trade history."""
        gross_profit = sum(t["net_pnl_usd"] for t in self.history if t["net_pnl_usd"] > 0)
        gross_loss = abs(sum(t["net_pnl_usd"] for t in self.history if t["net_pnl_usd"] < 0))
        self.ledger["profit_factor"] = round(gross_profit / (gross_loss + 1e-9), 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        # Drawdown tracking
        current_equity = self.ledger["virtual_cash_usdt"]
        if current_equity > self.ledger["peak_equity_usdt"]:
            self.ledger["peak_equity_usdt"] = round(current_equity, 2)
        
        peak = self.ledger["peak_equity_usdt"]
        dd = ((peak - current_equity) / peak) * 100 if peak > 0 else 0.0
        self.ledger["max_drawdown_pct"] = max(self.ledger["max_drawdown_pct"], round(dd, 2))
        self.ledger["last_updated"] = datetime.now().isoformat()

    def get_portfolio_summary(self, current_prices: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """Generate high-level portfolio overview including unrealized gains."""
        prices = current_prices or {}
        unrealized_pnl = 0.0
        positions_summary = []

        for symbol, pos in self.positions.items():
            curr_p = prices.get(symbol, pos["entry_price"])
            qty = pos["quantity"]
            direction = pos.get("direction", "BUY")
            pnl = (curr_p - pos["entry_price"]) * qty if direction == "BUY" else (pos["entry_price"] - curr_p) * qty
            unrealized_pnl += pnl
            positions_summary.append({
                "symbol": symbol,
                "direction": direction,
                "entry_price": pos["entry_price"],
                "current_price": curr_p,
                "quantity": qty,
                "allocated_usd": pos["allocated_usd"],
                "stop_loss": pos["stop_loss"],
                "target_price": pos["target_price"],
                "unrealized_pnl_usd": round(pnl, 2),
                "unrealized_pnl_pct": round((pnl / pos["allocated_usd"]) * 100, 2),
            })

        total_equity = self.ledger["virtual_cash_usdt"] + sum(p["allocated_usd"] for p in self.positions.values()) + unrealized_pnl

        today_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        baseline = float(self.ledger.get("current_investment_baseline_usdt") or self.ledger.get("initial_capital_usdt", total_equity))
        session_date = self.ledger.get("session_start_date")

        # Roll over baseline daily at 00:00 UTC so current balance becomes the new investment baseline
        if session_date != today_date:
            baseline = round(total_equity, 2)
            self.ledger["current_investment_baseline_usdt"] = baseline
            self.ledger["session_start_date"] = today_date
            self._save_ledger()

        today_pnl = round(total_equity - baseline, 2)
        today_return_pct = round((today_pnl / baseline) * 100, 2) if baseline > 0 else 0.0

        return {
            "total_equity_usdt": round(total_equity, 2),
            "current_investment_usdt": baseline,
            "today_pnl_usdt": today_pnl,
            "today_return_pct": today_return_pct,
            "cash_usdt": round(self.ledger["virtual_cash_usdt"], 2),
            "realized_pnl_usdt": self.ledger["realized_pnl_usdt"],
            "unrealized_pnl_usdt": round(unrealized_pnl, 2),
            "win_rate_pct": self.ledger["win_rate_pct"],
            "profit_factor": self.ledger["profit_factor"],
            "max_drawdown_pct": self.ledger["max_drawdown_pct"],
            "open_positions_count": len(self.positions),
            "open_positions": positions_summary,
            "total_trades": self.ledger["total_trades"],
        }
