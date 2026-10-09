"""Evaluation helpers for FraudShield (Phase 3).

Accuracy is deliberately absent: with ~3.5% fraud, "approve everything" is already ~96.5% accurate.
Headline metrics: PR-AUC, ROC-AUC, recall at a fixed false-positive rate, precision at that point.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score, roc_curve


def recall_at_fpr(y_true, scores, fpr_target: float = 0.01):
    """Best recall reachable while keeping the false-positive rate <= fpr_target.

    Returns (recall, threshold, achieved_fpr). Flag a transaction when score >= threshold.
    """
    y = np.asarray(y_true)
    s = np.asarray(scores, dtype="float64")
    fpr, tpr, thr = roc_curve(y, s)
    i = int(np.searchsorted(fpr, fpr_target, side="right") - 1)  # last point with fpr <= target
    return float(tpr[i]), float(thr[i]), float(fpr[i])


def operating_point(y_true, scores, threshold: float) -> dict:
    """Confusion-matrix based metrics when flagging every transaction with score >= threshold."""
    y = np.asarray(y_true).astype(bool)
    flagged = np.asarray(scores, dtype="float64") >= threshold
    tp = int((flagged & y).sum())
    fp = int((flagged & ~y).sum())
    fn = int((~flagged & y).sum())
    tn = int((~flagged & ~y).sum())
    return {
        "recall": tp / (tp + fn) if (tp + fn) else float("nan"),
        "precision": tp / (tp + fp) if (tp + fp) else float("nan"),
        "fpr": fp / (fp + tn) if (fp + tn) else float("nan"),
        "flagged_share": float(flagged.mean()),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }


def evaluate(y_true, scores, fpr_target: float = 0.01, threshold: float | None = None) -> dict:
    """Headline metrics for one set of scores.

    - pr_auc / roc_auc: ranking quality (threshold-free).
    - recall_at_fpr / threshold_at_fpr / precision_at_fpr: the *oracle* operating point on THIS data.
    - If `threshold` is given (e.g. picked on validation), also report what that fixed threshold
      really achieves here: recall_at_thr, precision_at_thr, fpr_at_thr, flagged_share_at_thr.
      This is the honest number for a holdout: thresholds must never be tuned on the holdout itself.
    """
    y = np.asarray(y_true).astype(int)
    s = np.asarray(scores, dtype="float64")
    out = {"n": int(len(y)), "fraud_rate": float(y.mean()) if len(y) else float("nan")}
    if len(y) == 0 or y.sum() == 0 or y.sum() == len(y):
        out.update({k: float("nan") for k in ["pr_auc", "roc_auc", "recall_at_fpr", "threshold_at_fpr", "precision_at_fpr"]})
        return out
    rec, thr, _ = recall_at_fpr(y, s, fpr_target)
    op = operating_point(y, s, thr)
    out.update({
        "pr_auc": float(average_precision_score(y, s)),
        "roc_auc": float(roc_auc_score(y, s)),
        "recall_at_fpr": rec,
        "threshold_at_fpr": thr,
        "precision_at_fpr": op["precision"],
    })
    if threshold is not None:
        fixed = operating_point(y, s, threshold)
        out.update({
            "recall_at_thr": fixed["recall"],
            "precision_at_thr": fixed["precision"],
            "fpr_at_thr": fixed["fpr"],
            "flagged_share_at_thr": fixed["flagged_share"],
        })
    return out


def slice_report(y_true, scores, masks: dict, fpr_target: float = 0.01) -> pd.DataFrame:
    """Metrics per named boolean mask (e.g. cold-start cards vs cards with history)."""
    y = np.asarray(y_true)
    s = np.asarray(scores)
    rows = {}
    for name, m in masks.items():
        m = np.asarray(m).astype(bool)
        r = evaluate(y[m], s[m], fpr_target)
        rows[name] = {k: r[k] for k in ["n", "fraud_rate", "pr_auc", "roc_auc", "recall_at_fpr", "precision_at_fpr"]}
    return pd.DataFrame(rows).T


# ---- calibration ---------------------------------------------------------------------------
def reliability_table(y_true, probs, n_bins: int = 10) -> pd.DataFrame:
    """Quantile-binned reliability table: mean predicted vs observed fraud rate per bin."""
    y = np.asarray(y_true, dtype="float64")
    p = np.asarray(probs, dtype="float64")
    edges = np.unique(np.quantile(p, np.linspace(0, 1, n_bins + 1)))
    if len(edges) < 3:
        return pd.DataFrame({"mean_pred": [p.mean()], "frac_pos": [y.mean()], "count": [len(y)]})
    b = np.clip(np.digitize(p, edges[1:-1], right=True), 0, len(edges) - 2)
    df = pd.DataFrame({"b": b, "p": p, "y": y}).groupby("b").agg(mean_pred=("p", "mean"), frac_pos=("y", "mean"), count=("y", "size"))
    return df.reset_index(drop=True)


def expected_calibration_error(y_true, probs, n_bins: int = 10) -> float:
    t = reliability_table(y_true, probs, n_bins)
    w = t["count"] / t["count"].sum()
    return float((w * (t["mean_pred"] - t["frac_pos"]).abs()).sum())


def calibration_report(y_true, probs) -> dict:
    y = np.asarray(y_true)
    p = np.clip(np.asarray(probs, dtype="float64"), 1e-7, 1 - 1e-7)
    return {
        "brier": float(brier_score_loss(y, p)),
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "ece": expected_calibration_error(y, p),
        "mean_pred": float(p.mean()),
        "observed_rate": float(y.mean()),
    }
