"""Institutional Readiness Scorecard & Capital Scaling Auditor for Crypto Trading.
Borrows the quantitative readiness scoring architecture from the Indian desk,
adapted strictly for Binance USDT Spot execution.

Graduation Criteria:
1. Capital Expectancy: Realized net profit positive in USDT.
2. Win Rate: >= 50% over a statistically meaningful trade sample.
3. Profit Factor: >= 1.30 (Gross Profit / Gross Loss).
4. Capital Preservation: Max historical drawdown <= 5.0%.
5. Statistical Sample Significance: >= 20 verified closed trades.
6. Continuous Self-Correction: Documented forensic autopsies and adaptive parameter mutations.
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

logger = logging.getLogger("CryptoReadinessScorecard")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
SCORECARD_FILE = os.path.join(DATA_DIR, "crypto_readiness_scorecard.json")
LEDGER_FILE = os.path.join(DATA_DIR, "crypto_paper_ledger.json")
HISTORY_FILE = os.path.join(DATA_DIR, "crypto_paper_history.json")
ADAPTIVE_FILE = os.path.join(DATA_DIR, "crypto_adaptive_hyperparams.json")
RETROS_DIR = os.path.join(DATA_DIR, "retros")


def _load_json_safe(path: str, default_val: Any) -> Any:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning("Error reading %s: %s", path, str(e))
    return default_val


class CryptoReadinessScorecardAuditor:
    """Evaluates crypto spot performance against institutional readiness hurdles."""

    def __init__(self, scorecard_path: str = SCORECARD_FILE):
        self.scorecard_path = scorecard_path

    def compute_scorecard(self) -> Dict[str, Any]:
        ledger = _load_json_safe(LEDGER_FILE, {})
        history = _load_json_safe(HISTORY_FILE, [])
        hyperparams = _load_json_safe(ADAPTIVE_FILE, {})

        total_trades = len(history)
        wins = sum(1 for t in history if float(t.get("net_pnl_usd", 0.0)) > 0)
        win_rate = round((wins / total_trades * 100.0), 2) if total_trades > 0 else 0.0
        net_pnl = round(float(ledger.get("realized_pnl_usdt", 0.0)), 2)
        drawdown = round(float(ledger.get("max_drawdown_pct", 0.0)), 2)
        profit_factor = round(float(ledger.get("profit_factor", 1.0)), 2)

        # Count completed retrospective autopsies
        retro_count = 0
        if os.path.exists(RETROS_DIR):
            retro_count = len([f for f in os.listdir(RETROS_DIR) if f.endswith(".md")])

        mutations_count = len(hyperparams.get("applied_mutations", []))

        hurdles: List[Dict[str, Any]] = []
        score = 0

        # Hurdle 1: Net Profitability (25 pts)
        if net_pnl > 0:
            score += 25
            hurdles.append({"criterion": "Net Capital Growth", "status": "PASSED", "weight": 25, "awarded": 25, "detail": f"Net realized PnL is +${net_pnl:.2f} USDT."})
        elif net_pnl == 0:
            score += 10
            hurdles.append({"criterion": "Net Capital Growth", "status": "NEUTRAL", "weight": 25, "awarded": 10, "detail": "Net PnL is flat ($0.00 USDT)."})
        else:
            hurdles.append({"criterion": "Net Capital Growth", "status": "FAILING", "weight": 25, "awarded": 0, "detail": f"Net realized PnL is negative (${net_pnl:.2f} USDT)."})

        # Hurdle 2: Win Rate Discipline (20 pts)
        if win_rate >= 50.0 and total_trades >= 10:
            score += 20
            hurdles.append({"criterion": "Win Rate Discipline", "status": "PASSED", "weight": 20, "awarded": 20, "detail": f"Win rate is {win_rate:.1f}% (target >= 50%)."})
        elif win_rate >= 40.0:
            score += 10
            hurdles.append({"criterion": "Win Rate Discipline", "status": "PROGRESSING", "weight": 20, "awarded": 10, "detail": f"Win rate is {win_rate:.1f}% (acceptable range 40-50%)."})
        else:
            hurdles.append({"criterion": "Win Rate Discipline", "status": "FAILING", "weight": 20, "awarded": 0, "detail": f"Win rate is {win_rate:.1f}% (< 40%)."})

        # Hurdle 3: Profit Factor (15 pts)
        if profit_factor >= 1.30:
            score += 15
            hurdles.append({"criterion": "Profit Factor", "status": "PASSED", "weight": 15, "awarded": 15, "detail": f"Profit factor is {profit_factor:.2f} (target >= 1.30)."})
        elif profit_factor >= 0.90:
            score += 8
            hurdles.append({"criterion": "Profit Factor", "status": "PROGRESSING", "weight": 15, "awarded": 8, "detail": f"Profit factor is {profit_factor:.2f} (target >= 1.30)."})
        else:
            hurdles.append({"criterion": "Profit Factor", "status": "FAILING", "weight": 15, "awarded": 0, "detail": f"Profit factor is {profit_factor:.2f} (gross losses exceed gross gains)."})

        # Hurdle 4: Capital Preservation & Drawdown Control (20 pts)
        if drawdown <= 4.0:
            score += 20
            hurdles.append({"criterion": "Capital Preservation", "status": "PASSED", "weight": 20, "awarded": 20, "detail": f"Max historical drawdown is {drawdown:.2f}% (limit <= 4.0%)."})
        elif drawdown <= 6.0:
            score += 10
            hurdles.append({"criterion": "Capital Preservation", "status": "PROGRESSING", "weight": 20, "awarded": 10, "detail": f"Max historical drawdown is {drawdown:.2f}% (limit <= 6.0%)."})
        else:
            hurdles.append({"criterion": "Capital Preservation", "status": "FAILING", "weight": 20, "awarded": 0, "detail": f"Max historical drawdown is {drawdown:.2f}% (> 6.0%)."})

        # Hurdle 5: Statistical Sample Significance (10 pts)
        if total_trades >= 30:
            score += 10
            hurdles.append({"criterion": "Sample Significance", "status": "PASSED", "weight": 10, "awarded": 10, "detail": f"Verified sample of {total_trades} closed trades."})
        elif total_trades >= 15:
            score += 5
            hurdles.append({"criterion": "Sample Significance", "status": "PROGRESSING", "weight": 10, "awarded": 5, "detail": f"Sample of {total_trades} closed trades (target >= 30)."})
        else:
            hurdles.append({"criterion": "Sample Significance", "status": "FAILING", "weight": 10, "awarded": 0, "detail": f"Sample of {total_trades} closed trades (< 15)."})

        # Hurdle 6: Self-Correction Track Record (10 pts)
        if retro_count >= 1 and mutations_count >= 1:
            score += 10
            hurdles.append({"criterion": "Self-Correction Track Record", "status": "PASSED", "weight": 10, "awarded": 10, "detail": f"{retro_count} retrospectives and {mutations_count} adaptive mutations applied."})
        else:
            hurdles.append({"criterion": "Self-Correction Track Record", "status": "PROGRESSING", "weight": 10, "awarded": 5, "detail": "Autopsy cycles initializing."})

        verdict = "CAPITAL_SCALE_READY" if score >= 85 else ("PROGRESSING" if score >= 50 else "EARLY_STAGE_DEVELOPMENT")

        payload = {
            "score": score,
            "max_score": 100,
            "verdict": verdict,
            "total_trades": total_trades,
            "wins": wins,
            "losses": total_trades - wins,
            "win_rate_pct": win_rate,
            "net_pnl_usdt": net_pnl,
            "profit_factor": profit_factor,
            "max_drawdown_pct": drawdown,
            "hurdles": hurdles,
            "last_audited": datetime.now(timezone.utc).isoformat(),
        }

        os.makedirs(DATA_DIR, exist_ok=True)
        try:
            with open(self.scorecard_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            logger.error("Error saving crypto readiness scorecard: %s", e)

        return payload


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    auditor = CryptoReadinessScorecardAuditor()
    res = auditor.compute_scorecard()
    print(json.dumps(res, indent=2))
