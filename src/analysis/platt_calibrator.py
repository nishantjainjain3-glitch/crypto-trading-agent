"""Platt Calibration and Brier Skill Scoring Engine.

Ported from OpenThomas: Converts heuristic technical conviction scores into
statistically calibrated win probabilities using logistic regression (Platt scaling)
and evaluates calibration accuracy using Brier skill scores.
"""

from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import json
import os


class PlattCalibrator:
    """Fits and applies Platt sigmoid scaling to convert raw scores to true win probabilities."""

    def __init__(self, data_path: str = "data/platt_calibration.json"):
        self.data_path = data_path
        self.param_a = -4.0   # Baseline slope: higher score = higher win probability
        self.param_b = 2.0    # Baseline intercept: maps score 50 to 50%
        self.sample_count = 0
        self.brier_score = 0.25
        self.brier_skill_score = 0.0
        self._load_parameters()

    def _load_parameters(self) -> None:
        """Load fitted parameters from disk if available."""
        if os.path.exists(self.data_path):
            try:
                with open(self.data_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.param_a = float(data.get("param_a", self.param_a))
                    self.param_b = float(data.get("param_b", self.param_b))
                    self.sample_count = int(data.get("sample_count", 0))
                    self.brier_score = float(data.get("brier_score", 0.25))
                    self.brier_skill_score = float(data.get("brier_skill_score", 0.0))
            except Exception:
                pass

    def _save_parameters(self) -> None:
        """Save fitted parameters to disk."""
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
        with open(self.data_path, "w", encoding="utf-8") as f:
            json.dump({
                "param_a": round(self.param_a, 6),
                "param_b": round(self.param_b, 6),
                "sample_count": self.sample_count,
                "brier_score": round(self.brier_score, 4),
                "brier_skill_score": round(self.brier_skill_score, 4),
            }, f, indent=2)

    def calibrate_probability(self, raw_score: float) -> float:
        """Apply fitted sigmoid scaling: P(Win | Score) = 1 / (1 + exp(A * (Score / 100) + B))."""
        # Normalize score to 0.0 - 1.0 range
        norm_score = float(raw_score) / 100.0
        z = self.param_a * norm_score + self.param_b
        # Numerical stability clamp
        z = max(-15.0, min(15.0, z))
        prob = 1.0 / (1.0 + np.exp(z))
        # Hard clamp between 10% and 90% (prevent overconfident betting)
        return round(float(np.clip(prob, 0.10, 0.90)), 3)

    def compute_brier_metrics(self, probabilities: List[float], outcomes: List[int]) -> Dict[str, float]:
        """Compute Brier Score and Brier Skill Score against an uncalibrated 50/50 baseline."""
        if not probabilities or not outcomes or len(probabilities) != len(outcomes):
            return {"brier_score": 0.25, "brier_skill_score": 0.0}

        p = np.array(probabilities)
        y = np.array(outcomes)

        brier = float(np.mean((p - y) ** 2))

        # Reference baseline: predicting overall base rate
        base_rate = float(np.mean(y)) if len(y) > 0 else 0.50
        brier_ref = float(np.mean((base_rate - y) ** 2)) if brier > 0 else 0.25
        brier_ref = max(0.001, brier_ref)

        # BSS = 1 - (Brier / Brier_ref). Positive = skill, Negative = worse than base rate
        bss = 1.0 - (brier / brier_ref)

        return {
            "brier_score": round(brier, 4),
            "brier_skill_score": round(bss, 4),
        }

    def fit_from_trade_history(self, history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Fit Platt scaling parameters A and B from closed trade history."""
        valid_pairs = []
        for t in history:
            # Extract conviction score recorded at entry
            score = t.get("entry_score")
            if score is None:
                # Infer from rationale if possible (e.g. "Score 95/100")
                rat = t.get("rationale", "")
                if "Score " in rat:
                    try:
                        score = float(rat.split("Score ")[1].split("/")[0])
                    except Exception:
                        score = 70.0
                else:
                    score = 70.0

            # Win outcome (1 for profit, 0 for loss)
            pnl = t.get("net_pnl_usd", t.get("pnl_usd", 0.0))
            outcome = 1 if pnl > 0 else 0
            valid_pairs.append((score, outcome))

        if len(valid_pairs) < 5:
            return {
                "status": "INSUFFICIENT_SAMPLES",
                "sample_count": len(valid_pairs),
                "param_a": self.param_a,
                "param_b": self.param_b,
            }

        scores = np.array([p[0] for p in valid_pairs])
        outcomes = np.array([p[1] for p in valid_pairs])
        norm_scores = scores / 100.0

        # Initialize reasonable baseline: negative slope a = -2.0 (higher score increases win rate)
        a = -2.0
        b = 1.0
        lr = 0.05

        for _ in range(300):
            z = np.clip(a * norm_scores + b, -15.0, 15.0)
            preds = 1.0 / (1.0 + np.exp(z))
            grad_a = np.mean((preds - outcomes) * norm_scores)
            grad_b = np.mean(preds - outcomes)
            a -= lr * grad_a
            b -= lr * grad_b

        self.param_a = float(a)
        self.param_b = float(b)
        self.sample_count = len(valid_pairs)

        probs = [self.calibrate_probability(s) for s in scores]
        brier_res = self.compute_brier_metrics(probs, outcomes.tolist())
        self.brier_score = brier_res["brier_score"]
        self.brier_skill_score = brier_res["brier_skill_score"]
        self._save_parameters()

        return {
            "status": "FITTED",
            "sample_count": self.sample_count,
            "param_a": round(self.param_a, 6),
            "param_b": round(self.param_b, 6),
            "brier_score": self.brier_score,
            "brier_skill_score": self.brier_skill_score,
        }
