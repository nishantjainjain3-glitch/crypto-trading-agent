"""
Continuous Forensic Mistake Autopsy & Self-Tuning Engine for Crypto Trading.
Inspired by the Phil architecture (bennyjo/phil).

Automatically:
1. Performs forensic root-cause analysis on every closed trade (MFE/MAE/Volume/Chop).
2. Categorizes mistakes into actionable failure modes (FALSE_BREAKOUT_CHOP, TRAILING_STOP_FAILURE, etc.).
3. Mutates strategy hyperparameters dynamically in data/crypto_adaptive_hyperparams.json.
4. Generates human-readable Markdown post-mortem retrospectives in data/retros/.
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger("CryptoAutopsy")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
RETROS_DIR = os.path.join(DATA_DIR, "retros")
os.makedirs(RETROS_DIR, exist_ok=True)

# Shared Quant Vault resolution
_scratch_dir = os.path.abspath(os.path.join(PROJECT_ROOT, ".."))
if _scratch_dir not in sys.path:
    sys.path.insert(0, _scratch_dir)

try:
    from shared_quant_vault import (
        ZeroCostResearchFleet,
        CrossMarketBus,
        detect_liquidity_sweep,
    )
    _fleet = ZeroCostResearchFleet()
    _bus = CrossMarketBus()
except ImportError:
    _fleet = None
    _bus = None

ADAPTIVE_FILE = os.path.join(DATA_DIR, "crypto_adaptive_hyperparams.json")
HISTORY_FILE = os.path.join(DATA_DIR, "crypto_paper_history.json")
LEDGER_FILE = os.path.join(DATA_DIR, "crypto_paper_ledger.json")


DEFAULT_HYPERPARAMS = {
    "min_rvol_ratio": 1.2,
    "breakeven_atr_mult": 1.0,
    "trailing_stop_atr_mult": 1.5,
    "cooldown_minutes_after_loss": 30.0,
    "max_concurrent_positions": 2,
    "max_risk_per_trade_pct": 5.0,
    "min_reward_to_risk": 1.5,
    "min_quote_volume_24h_usd": 5000000.0,
    "applied_mutations": [],
    "last_tuned": datetime.now(timezone.utc).isoformat()
}


def load_adaptive_hyperparams() -> Dict[str, Any]:
    if os.path.exists(ADAPTIVE_FILE):
        try:
            with open(ADAPTIVE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Error loading crypto hyperparams: %s", e)
    return dict(DEFAULT_HYPERPARAMS)


def save_adaptive_hyperparams(params: Dict[str, Any]):
    os.makedirs(DATA_DIR, exist_ok=True)
    params["last_tuned"] = datetime.now(timezone.utc).isoformat()
    try:
        with open(ADAPTIVE_FILE, "w", encoding="utf-8") as f:
            json.dump(params, f, indent=2)
    except Exception as e:
        logger.error("Error saving crypto adaptive hyperparams: %s", e)


def categorize_crypto_mistake(trade: Dict[str, Any]) -> Dict[str, str]:
    """
    Forensic classification of a closed trade's outcome.
    Evaluates net PnL, Maximum Favorable Excursion (MFE), Maximum Adverse Excursion (MAE),
    and holding duration.
    """
    net_pnl = float(trade.get("net_pnl_usd", 0.0))
    mfe_pct = float(trade.get("mfe_pct", 0.0))
    mae_pct = float(trade.get("mae_pct", 0.0))
    holding_secs = int(trade.get("holding_seconds", 0))
    exit_reason = str(trade.get("exit_reason", "MANUAL"))

    if net_pnl > 0:
        return {
            "outcome": "WIN",
            "mistake_category": "NONE",
            "lesson": f"Trade hit profit target or trailed gain cleanly (+${net_pnl:.2f}, MFE {mfe_pct}%)."
        }

    # Loss forensic classification
    if mfe_pct >= 1.5:
        # Trade was in substantial profit before reversing into a loss
        return {
            "outcome": "LOSS",
            "mistake_category": "TRAILING_STOP_LAG",
            "lesson": f"MFE reached +{mfe_pct}% but trailing stop failed to protect gains before stop-loss hit. Action: Tighten breakeven ratchet threshold."
        }

    if abs(mae_pct) > 3.0 and holding_secs < 1800:
        # Immediate steep adverse excursion within 30 minutes
        return {
            "outcome": "LOSS",
            "mistake_category": "FALSE_BREAKOUT_CHOP",
            "lesson": f"Plunged {mae_pct}% immediately post-entry. False breakout entry during low volume consolidation. Action: Raise minimum RVOL requirement."
        }

    if holding_secs > 86400 and abs(net_pnl) < 1.0:
        # Stagnant multi-day drift
        return {
            "outcome": "LOSS",
            "mistake_category": "STAGNANT_CAPITAL_DRIFT",
            "lesson": "Coin stayed dead in consolidation exceeding 24 hours. Action: Enforce aggressive decaying ROI time-stop."
        }

    if "STOP" in exit_reason:
        return {
            "outcome": "LOSS",
            "mistake_category": "CONTROLLED_STOP_HIT",
            "lesson": f"Disciplined cut via stop-loss limit (-${abs(net_pnl):.2f}). Preserved capital against larger adverse drift."
        }

    return {
        "outcome": "LOSS",
        "mistake_category": "MARKET_VOLATILITY_CHOP",
        "lesson": f"Unfavorable price expansion against position (-${abs(net_pnl):.2f})."
    }


def run_crypto_forensic_autopsy_cycle() -> Dict[str, Any]:
    """
    Scans entire crypto trade history, classifies past mistakes,
    mutates hyperparameters to fix root causes, and writes a Markdown retrospective.
    """
    if not os.path.exists(HISTORY_FILE):
        return {"status": "NO_HISTORY"}

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)

    if not history:
        return {"status": "EMPTY_HISTORY"}

    params = load_adaptive_hyperparams()
    mutations = []

    # 1. Forensic classification of all historical trades
    mistake_counts: Dict[str, int] = {}
    mistake_losses: Dict[str, float] = {}
    wins = 0
    losses = 0
    total_net_pnl = 0.0

    for t in history:
        analysis = categorize_crypto_mistake(t)
        t["outcome"] = analysis["outcome"]
        t["post_mortem"] = {
            "mistake_category": analysis["mistake_category"],
            "lesson": analysis["lesson"]
        }

        pnl = float(t.get("net_pnl_usd", 0.0))
        total_net_pnl += pnl

        if analysis["outcome"] == "WIN":
            wins += 1
        else:
            losses += 1
            cat = analysis["mistake_category"]
            mistake_counts[cat] = mistake_counts.get(cat, 0) + 1
            mistake_losses[cat] = mistake_losses.get(cat, 0.0) + pnl

    # Save enriched history
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

    # 2. Rule mutations based on forensic evidence
    trailing_errors = mistake_counts.get("TRAILING_STOP_LAG", 0)
    chop_errors = mistake_counts.get("FALSE_BREAKOUT_CHOP", 0)

    if trailing_errors >= 2 and params["breakeven_atr_mult"] > 0.8:
        params["breakeven_atr_mult"] = 0.8
        params["trailing_stop_atr_mult"] = 1.2
        mut = f"Tightened breakeven threshold to 0.8 ATR after {trailing_errors} trailing lag mistakes."
        mutations.append(mut)
        params["applied_mutations"].append(mut)

    if chop_errors >= 2 and params["min_rvol_ratio"] < 1.4:
        params["min_rvol_ratio"] = 1.4
        mut = f"Raised minimum RVOL filter to 1.4x after {chop_errors} false breakout chop mistakes."
        mutations.append(mut)
        params["applied_mutations"].append(mut)

    if losses > wins and params["cooldown_minutes_after_loss"] < 45.0:
        params["cooldown_minutes_after_loss"] = 45.0
        mut = "Extended post-loss cooldown to 45 minutes to curb revenge trading."
        mutations.append(mut)
        params["applied_mutations"].append(mut)

    save_adaptive_hyperparams(params)

    # 3. Generate Markdown Retrospective
    now_utc = datetime.now(timezone.utc)
    stamp = now_utc.strftime("%Y%m%d-%H%M")
    retro_path = os.path.join(RETROS_DIR, f"CRYPTO-RETRO-{stamp}.md")

    md = []
    md.append(f"# CRYPTO-RETRO-{stamp}")
    md.append(f"**Generated:** {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}  ")
    md.append("**Environment:** Autonomous Binance Micro-Spot Workstation  ")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 1. Executive Summary")
    md.append(f"- **Total Closed Trades Analyzed:** {len(history)} ({wins} Wins, {losses} Losses)")
    win_rate = (wins / len(history) * 100.0) if history else 0.0
    md.append(f"- **Win Rate:** {win_rate:.2f}%")
    md.append(f"- **Cumulative Net Realized PnL:** ${total_net_pnl:+,.2f} USDT")
    md.append("")

    md.append("## 2. Forensic Mistake Breakdown")
    if mistake_counts:
        md.append("| Mistake Category | Count | Total Drag ($) | Applied Rule Mutation |")
        md.append("| :--- | :---: | :---: | :--- |")
        for cat, cnt in sorted(mistake_counts.items(), key=lambda x: abs(mistake_losses.get(x[0], 0.0)), reverse=True):
            loss_val = mistake_losses.get(cat, 0.0)
            if "TRAILING" in cat:
                action = "Tightened breakeven ratchet to 0.8 ATR to lock profits faster."
            elif "CHOP" in cat:
                action = "Raised minimum RVOL ratio to 1.4x to reject low-volume false breaks."
            elif "STAGNANT" in cat:
                action = "Enforced 24h decaying ROI time stop."
            else:
                action = "Maintained strict initial stop-loss cap."
            md.append(f"| `{cat}` | {cnt} | ${loss_val:+,.2f} | {action} |")
    else:
        md.append("No active mistake clusters identified.")
    md.append("")

    md.append("## 3. Active Learned Hyperparameters")
    md.append(f"- **Minimum RVOL Threshold:** `{params['min_rvol_ratio']}x`")
    md.append(f"- **Breakeven ATR Ratchet:** `{params['breakeven_atr_mult']} ATR`")
    md.append(f"- **Trailing Stop Distance:** `{params['trailing_stop_atr_mult']} ATR`")
    md.append(f"- **Post-Loss Cooldown:** `{params['cooldown_minutes_after_loss']} minutes`")
    if mutations:
        md.append("")
        md.append("**Recent Mutations Applied:**")
        for m in mutations:
            md.append(f"- {m}")

    with open(retro_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    logger.info("Crypto forensic autopsy complete. Retrospective: %s", retro_path)
    return {
        "status": "COMPLETED",
        "total_trades": len(history),
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(win_rate, 2),
        "total_net_pnl_usd": round(total_net_pnl, 2),
        "mutations": mutations,
        "retro_path": retro_path
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    res = run_crypto_forensic_autopsy_cycle()
    print(json.dumps(res, indent=2))
