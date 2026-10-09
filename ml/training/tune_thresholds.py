"""Cost model + threshold search for FraudShield (Phase 4).

Three outcomes per transaction: APPROVE (score < t_review), REVIEW (t_review <= score < t_block),
BLOCK (score >= t_block). Thresholds are chosen on VALIDATION by minimizing realized money cost,
then applied unchanged to the holdout.

    cd ml/training
    python tune_thresholds.py             # reads data/processed/val_predictions.parquet
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

APPROVE, REVIEW, BLOCK = 0, 1, 2
ACTION_NAMES = {APPROVE: "APPROVE", REVIEW: "REVIEW", BLOCK: "BLOCK"}


@dataclass
class CostModel:
    """All money assumptions in one place. Every number is a documented ASSUMPTION, not a fact."""
    fraud_loss_rate: float = 1.00      # share of the amount lost when a fraudulent txn is approved
    chargeback_fee: float = 15.0       # fixed fee per approved fraud (processor chargeback fee)
    block_margin_rate: float = 0.08    # share of the amount lost (margin) when a legit txn is blocked
    block_friction: float = 5.0        # fixed cost per wrongly blocked customer (support contact, churn)
    analyst_cost: float = 3.0          # analyst time per case sent to review
    review_accuracy: float = 0.95      # chance the analyst resolves a case correctly
    review_delay_cost: float = 0.5     # small cost for a legit customer who has to wait

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CostModel":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def _clean_amount(amount) -> np.ndarray:
    a = np.asarray(amount, dtype="float64")
    return np.where(np.isfinite(a), a, np.nanmedian(a))


def cost_arrays(cm: CostModel, amount, y_or_p):
    """Per-transaction cost of each action. `y_or_p` is the label (realized cost) or a fraud
    probability (expected cost): the formulas are linear in it, so one function serves both.
    Returns (approve_cost, review_cost, block_cost)."""
    amt = _clean_amount(amount)
    y = np.asarray(y_or_p, dtype="float64")
    missed = amt * cm.fraud_loss_rate + cm.chargeback_fee          # cost if this txn is fraud and slips through
    blocked_legit = amt * cm.block_margin_rate + cm.block_friction  # cost if this txn is legit and gets declined
    approve = y * missed
    block = (1 - y) * blocked_legit
    review = (cm.analyst_cost
              + y * (1 - cm.review_accuracy) * missed
              + (1 - y) * (cm.review_delay_cost + (1 - cm.review_accuracy) * blocked_legit))
    return approve, review, block


def decide(scores, t_review: float, t_block: float) -> np.ndarray:
    s = np.asarray(scores, dtype="float64")
    return np.where(s >= t_block, BLOCK, np.where(s >= t_review, REVIEW, APPROVE))


def policy_costs(cm: CostModel, amount, y, actions) -> np.ndarray:
    """Realized cost of each transaction under the given actions."""
    a, r, b = cost_arrays(cm, amount, y)
    act = np.asarray(actions)
    return np.where(act == APPROVE, a, np.where(act == REVIEW, r, b))


def bayes_actions(cm: CostModel, amount, p) -> np.ndarray:
    """Reference policy (NOT shipped): per-transaction cheapest action given calibrated probability p.
    Amount-aware, so it cannot be expressed as two score thresholds. Useful as an upper bound."""
    a, r, b = cost_arrays(cm, amount, p)
    return np.argmin(np.vstack([a, r, b]), axis=0)


def _cut_value(sorted_scores: np.ndarray, k_top: int) -> float:
    """Score threshold that flags exactly the k_top highest scores (midpoint between neighbours)."""
    n = len(sorted_scores)
    if k_top <= 0:
        return float("inf")
    if k_top >= n:
        return float("-inf")
    return float(0.5 * (sorted_scores[n - k_top - 1] + sorted_scores[n - k_top]))


def search_thresholds(cm: CostModel, amount, y, scores, review_cap: float = 0.05,
                      grid: int = 400, top_share: float = 0.20) -> dict:
    """Exhaustive search over (t_review, t_block) pairs on a grid of 'top-k' cut points.

    Uses prefix sums, so every pair costs O(1). Constraint: review share <= review_cap.
    Also returns the best single-threshold (no review band) policy and the full cost grid.
    """
    s_all = np.asarray(scores, dtype="float64")
    order = np.argsort(s_all, kind="mergesort")
    s = s_all[order]
    a, r, b = (x[order] for x in cost_arrays(cm, amount, y))
    n = len(s)
    CA, CR, CB = (np.concatenate([[0.0], np.cumsum(x)]) for x in (a, r, b))

    ks = np.unique(np.round(np.linspace(0, top_share * n, grid)).astype(int))   # counts taken from the top
    KF, KB = np.meshgrid(ks, ks, indexing="ij")           # KF = flagged (review+block), KB = blocked
    I, J = n - KF, n - KB                                  # approve below I, block from J
    total = CA[I] + (CR[J] - CR[I]) + (CB[n] - CB[J])
    valid = (KB <= KF) & ((KF - KB) / n <= review_cap + 1e-12)
    total_masked = np.where(valid, total, np.inf)

    i, j = np.unravel_index(np.argmin(total_masked), total.shape)
    kf, kb = int(ks[i]), int(ks[j])
    diag = np.where(KB == KF, total, np.inf)
    bi, bj = np.unravel_index(np.argmin(diag), total.shape)
    kbin = int(ks[bi])

    approve_all = float(CA[n])
    return {
        "n": n,
        "review_cap": review_cap,
        "t_review": _cut_value(s, kf), "t_block": _cut_value(s, kb),
        "k_flagged": kf, "k_blocked": kb,
        "cost": float(total[i, j]),
        "binary": {"threshold": _cut_value(s, kbin), "k_flagged": kbin, "cost": float(total[bi, bj])},
        "approve_all_cost": approve_all,
        "block_all_cost": float(CB[n]),
        "ks": ks, "grid_cost": np.where(valid, total, np.nan),
    }


def evaluate_policy(cm: CostModel, amount, y, scores, t_review: float, t_block: float) -> dict:
    """Decision mix, fraud caught, money breakdown and savings vs 'approve everything'."""
    y = np.asarray(y).astype(int)
    amt = _clean_amount(amount)
    act = decide(scores, t_review, t_block)
    cost = policy_costs(cm, amt, y, act)
    base = policy_costs(cm, amt, y, np.full(len(y), APPROVE))
    n, frauds = len(y), int(y.sum())
    out = {"n": n, "fraud_count": frauds, "fraud_rate": float(y.mean()), "bands": {}}
    for code, name in ACTION_NAMES.items():
        m = act == code
        out["bands"][name] = {
            "count": int(m.sum()), "share": float(m.mean()),
            "fraud_rate": float(y[m].mean()) if m.any() else float("nan"),
            "fraud_caught": int(y[m].sum()),
        }
    flagged = act != APPROVE
    a, r, b = cost_arrays(cm, amt, y)
    out.update({
        "recall_review_or_block": float(y[flagged].sum() / max(frauds, 1)),
        "recall_block_only": float(y[act == BLOCK].sum() / max(frauds, 1)),
        "cost_total": float(cost.sum()),
        "cost_approve_all": float(base.sum()),
        "savings": float(base.sum() - cost.sum()),
        "savings_pct": float((base.sum() - cost.sum()) / base.sum()) if base.sum() > 0 else float("nan"),
        "savings_per_100k_txns": float((base.sum() - cost.sum()) / n * 100_000),
        "breakdown": {
            "missed_fraud_cost": float(a[act == APPROVE].sum()),
            "blocked_legit_cost": float(b[act == BLOCK].sum()),
            "review_cost_total": float(r[act == REVIEW].sum()),
        },
        "fraud_dollars_total": float(amt[y == 1].sum()),
        "fraud_dollars_in_approved": float(amt[(y == 1) & (act == APPROVE)].sum()),
    })
    return out


def bootstrap_savings(per_txn_cost, per_txn_baseline, day_ids, n_boot: int = 1000, seed: int = 42) -> dict:
    """Resample whole DAYS (fraud arrives in bursts, so resampling single rows would be too optimistic)."""
    df = pd.DataFrame({"d": np.asarray(day_ids), "c": per_txn_cost, "b": per_txn_baseline})
    g = df.groupby("d").agg(c=("c", "sum"), b=("b", "sum")).to_numpy()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(g), size=(n_boot, len(g)))
    c, b = g[idx, 0].sum(axis=1), g[idx, 1].sum(axis=1)
    pct = (b - c) / b
    q = lambda x: [float(np.percentile(x, 5)), float(np.percentile(x, 95))]
    return {"n_days": int(len(g)), "savings_pct_90ci": q(pct), "savings_90ci": q(b - c)}


def threshold_curve(cm: CostModel, amount, y, scores, points: int = 200, max_share: float = 0.20) -> pd.DataFrame:
    """Single-threshold (approve/block only) curve for the dashboard's cost slider."""
    s = np.asarray(scores, dtype="float64")
    order = np.argsort(-s, kind="mergesort")
    ss, yy = s[order], np.asarray(y)[order]
    a, _, b = (x[order] for x in cost_arrays(cm, amount, y))
    n = len(ss)
    ks = np.unique(np.round(np.linspace(0, max_share * n, points)).astype(int))
    cum_block_legit = np.concatenate([[0.0], np.cumsum(b)])          # blocking the top k
    cum_missed_tail = np.concatenate([[0.0], np.cumsum(a[::-1])])[::-1]  # approving everything below the top k
    cum_fraud = np.concatenate([[0], np.cumsum(yy)])
    rows = []
    base = float(cum_missed_tail[0])
    for k in ks:
        cost = float(cum_block_legit[k] + cum_missed_tail[k])
        rows.append({"k_flagged": int(k), "flagged_share": k / n,
                     "threshold": _cut_value(ss[::-1], int(k)),
                     "recall": float(cum_fraud[k] / max(yy.sum(), 1)),
                     "precision": float(cum_fraud[k] / k) if k else float("nan"),
                     "cost": cost, "savings": base - cost})
    return pd.DataFrame(rows)


def main(argv=None):
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description="Re-run the threshold search on validation predictions")
    ap.add_argument("--processed", default=str(here.parent.parent / "data" / "processed"))
    ap.add_argument("--artifacts", default=str(here.parent / "artifacts"))
    ap.add_argument("--review-cap", type=float, default=0.05)
    args = ap.parse_args(argv)

    proc, art = Path(args.processed), Path(args.artifacts)
    path = proc / "val_predictions.parquet"
    val = pd.read_parquet(path) if path.exists() else pd.read_pickle(proc / "val_predictions.pkl")
    cm_path = art / "cost_model.json"
    cm = CostModel.from_dict(json.loads(cm_path.read_text())) if cm_path.exists() else CostModel()
    res = search_thresholds(cm, val["TransactionAmt"], val["isFraud"], val["raw_score"], args.review_cap)
    ev = evaluate_policy(cm, val["TransactionAmt"], val["isFraud"], val["raw_score"], res["t_review"], res["t_block"])
    print(json.dumps({"t_review": res["t_review"], "t_block": res["t_block"],
                      "review_share": ev["bands"]["REVIEW"]["share"], "block_share": ev["bands"]["BLOCK"]["share"],
                      "savings_pct_validation": ev["savings_pct"]}, indent=2))


if __name__ == "__main__":
    main()
