"""Training helpers + CLI for FraudShield (Phase 3).

Single source of truth for how models are built, fit, calibrated and saved. The notebook
(03_Modeling.ipynb) imports these functions; `python train.py` reproduces the final artifacts.

    cd ml/training
    python train.py                       # uses ml/artifacts/best_params.json written by the notebook
    python train.py --model lightgbm --calibration isotonic

The holdout split is NEVER loaded here. It is read once, in the notebook's final-evaluation section.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

META_COLS = ["TransactionID", "TransactionDT", "isFraud", "split"]
RANDOM_STATE = 42
EARLY_STOPPING_ROUNDS = 100

# `spw_mult` scales scale_pos_weight (neg/pos ratio). 1.0 = fully balanced, smaller = gentler.
XGB_DEFAULTS = dict(n_estimators=3000, learning_rate=0.05, max_depth=7, min_child_weight=1,
                    subsample=0.8, colsample_bytree=0.5, reg_lambda=1.0, reg_alpha=0.0, gamma=0.0, spw_mult=1.0)
LGBM_DEFAULTS = dict(n_estimators=3000, learning_rate=0.05, num_leaves=127, min_child_samples=50,
                     subsample=0.8, colsample_bytree=0.5, reg_lambda=1.0, reg_alpha=0.0, spw_mult=1.0)


# ---- data ----------------------------------------------------------------------------------
def load_features(path, features, splits):
    """Load feature rows for the requested splits, sorted by time. Returns (meta, X)."""
    path = Path(path)
    cols = META_COLS + list(features)
    if path.suffix == ".parquet":
        df = pd.read_parquet(path, columns=cols, filters=[("split", "in", list(splits))])
    else:
        df = pd.read_pickle(path)
        df = df.loc[df["split"].isin(splits), cols]
    df = df.sort_values(["TransactionDT", "TransactionID"]).reset_index(drop=True)
    meta = df[META_COLS].copy()
    X = df[list(features)]
    return meta, X


def pos_weight_ratio(y) -> float:
    y = np.asarray(y)
    return float((len(y) - y.sum()) / max(y.sum(), 1))


# ---- models --------------------------------------------------------------------------------
def make_baseline(max_iter: int = 300):
    """Logistic regression baseline: median impute -> quantile-to-normal -> class-weighted LR."""
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import QuantileTransformer

    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", QuantileTransformer(n_quantiles=200, output_distribution="normal", subsample=200_000, random_state=RANDOM_STATE)),
        ("lr", LogisticRegression(C=0.1, class_weight="balanced", max_iter=max_iter, solver="lbfgs")),
    ])


def make_model(name: str, params: dict | None = None, pos_ratio: float = 1.0,
               early_stopping_rounds: int = EARLY_STOPPING_ROUNDS, n_jobs: int = -1):
    """Build an (unfitted) XGBoost or LightGBM classifier."""
    p = dict(XGB_DEFAULTS if name == "xgboost" else LGBM_DEFAULTS)
    p.update(params or {})
    spw = float(pos_ratio) * float(p.pop("spw_mult"))
    if name == "xgboost":
        import xgboost as xgb
        return xgb.XGBClassifier(tree_method="hist", eval_metric="aucpr", early_stopping_rounds=early_stopping_rounds,
                                 scale_pos_weight=spw, n_jobs=n_jobs, random_state=RANDOM_STATE, **p)
    if name == "lightgbm":
        import lightgbm as lgb
        return lgb.LGBMClassifier(objective="binary", metric="average_precision", scale_pos_weight=spw,
                                  subsample_freq=1, n_jobs=n_jobs, random_state=RANDOM_STATE, verbose=-1, **p)
    raise ValueError(f"unknown model {name!r}")


def fit_model(name: str, model, X_tr, y_tr, X_va, y_va, early_stopping_rounds: int = EARLY_STOPPING_ROUNDS) -> float:
    """Fit with early stopping on the validation set (PR-AUC). Returns fit time in seconds."""
    t0 = time.time()
    if name == "xgboost":
        model.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
    else:
        import lightgbm as lgb
        model.fit(X_tr, y_tr, eval_set=[(X_va, y_va)],
                  callbacks=[lgb.early_stopping(early_stopping_rounds, first_metric_only=True, verbose=False)])
    return time.time() - t0


def best_iteration(name: str, model) -> int:
    """Number of trees actually used after early stopping."""
    if name == "xgboost":
        return int(model.best_iteration) + 1
    return int(model.best_iteration_)


def predict_scores(model, X) -> np.ndarray:
    return model.predict_proba(X)[:, 1]


def feature_importance(name: str, model, features) -> pd.Series:
    """Gain-based importance (sum of loss reduction), sorted descending."""
    if name == "xgboost":
        s = pd.Series(model.get_booster().get_score(importance_type="gain"))
    else:
        b = model.booster_
        s = pd.Series(b.feature_importance("gain"), index=b.feature_name())
    return s.reindex(list(features)).fillna(0.0).sort_values(ascending=False)


# ---- calibration (JSON-serialisable, so the API needs no pickle and no sklearn) -------------
class Calibrator:
    """Maps a raw model score to a probability. method: 'none' | 'sigmoid' (Platt) | 'isotonic'."""

    def __init__(self, method: str, **params):
        self.method, self.params = method, params

    @classmethod
    def fit(cls, method: str, raw, y):
        raw = np.clip(np.asarray(raw, dtype="float64"), 1e-7, 1 - 1e-7)
        y = np.asarray(y)
        if method == "none":
            return cls("none")
        if method == "isotonic":
            from sklearn.isotonic import IsotonicRegression
            ir = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(raw, y)
            return cls("isotonic", x=ir.X_thresholds_.tolist(), y=ir.y_thresholds_.tolist())
        if method == "sigmoid":
            from sklearn.linear_model import LogisticRegression
            z = np.log(raw / (1 - raw)).reshape(-1, 1)
            lr = LogisticRegression(C=1e6, solver="lbfgs", max_iter=1000).fit(z, y)
            return cls("sigmoid", a=float(lr.coef_[0, 0]), b=float(lr.intercept_[0]))
        raise ValueError(method)

    def predict(self, raw) -> np.ndarray:
        raw = np.clip(np.asarray(raw, dtype="float64"), 1e-7, 1 - 1e-7)
        if self.method == "none":
            return raw
        if self.method == "isotonic":
            return np.interp(raw, self.params["x"], self.params["y"])
        z = np.log(raw / (1 - raw))
        return 1.0 / (1.0 + np.exp(-(self.params["a"] * z + self.params["b"])))

    def to_json(self, path):
        Path(path).write_text(json.dumps({"method": self.method, **self.params}))

    @classmethod
    def from_json(cls, path):
        d = json.loads(Path(path).read_text())
        return cls(d.pop("method"), **d)


# ---- artifacts -----------------------------------------------------------------------------
def save_artifacts(out_dir, name: str, model, calibrator: Calibrator, params: dict, n_trees: int,
                   features, metrics: dict | None = None, extra: dict | None = None) -> dict:
    """Write model, calibrator.json and model_meta.json into out_dir (ml/artifacts)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if name == "xgboost":
        model_file = "model.xgb.json"
        model.get_booster()[:n_trees].save_model(str(out / model_file))   # keep only the early-stopped trees
    else:
        model_file = "model.lgb.txt"
        model.booster_.save_model(str(out / model_file), num_iteration=n_trees)
    calibrator.to_json(out / "calibrator.json")
    order_hash = hashlib.sha256(json.dumps(list(features)).encode()).hexdigest()
    now = datetime.now(timezone.utc)
    meta = {
        "version": f"{name}-{now:%Y%m%d-%H%M%S}-{order_hash[:8]}",
        "trained_at_utc": now.isoformat(timespec="seconds"),
        "model_type": name,
        "model_file": model_file,
        "calibrator_file": "calibrator.json",
        "calibration_method": calibrator.method,
        "n_trees": int(n_trees),
        "n_features": len(list(features)),
        "feature_order_sha256": order_hash,
        "params": params,
        "metrics": metrics or {},
        **(extra or {}),
    }
    (out / "model_meta.json").write_text(json.dumps(meta, indent=2, default=float))
    return meta


# ---- CLI -----------------------------------------------------------------------------------
def main(argv=None):
    import evaluate as ev

    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description="Retrain the final FraudShield model from best_params.json")
    ap.add_argument("--artifacts", default=str(here.parent / "artifacts"))
    ap.add_argument("--features", default=str(here.parent.parent / "data" / "processed" / "features.parquet"))
    ap.add_argument("--params", default=None, help="JSON with {'model':..., 'params':{...}} (default: <artifacts>/best_params.json)")
    ap.add_argument("--model", choices=["xgboost", "lightgbm"], default=None)
    ap.add_argument("--calibration", choices=["none", "sigmoid", "isotonic"], default="isotonic")
    args = ap.parse_args(argv)

    art = Path(args.artifacts)
    cfg = json.loads(Path(args.params or art / "best_params.json").read_text())
    name = args.model or cfg["model"]
    params = cfg.get("params", {})
    features = json.loads((art / "feature_schema.json").read_text())["feature_order"]

    meta, X = load_features(args.features, features, splits=("train", "validation"))
    is_tr = (meta["split"] == "train").to_numpy()
    X_tr, y_tr = X.loc[is_tr], meta.loc[is_tr, "isFraud"].to_numpy()
    X_va, y_va = X.loc[~is_tr], meta.loc[~is_tr, "isFraud"].to_numpy()

    model = make_model(name, params, pos_weight_ratio(y_tr))
    secs = fit_model(name, model, X_tr, y_tr, X_va, y_va)
    n_trees = best_iteration(name, model)
    raw = predict_scores(model, X_va)
    cal = Calibrator.fit(args.calibration, raw, y_va)
    metrics = {"validation": ev.evaluate(y_va, raw)}
    info = save_artifacts(art, name, model, cal, params, n_trees, features, metrics, {"fit_seconds": round(secs, 1)})
    print(json.dumps({k: info[k] for k in ["version", "model_type", "n_trees", "calibration_method"]}, indent=2))
    print("validation PR-AUC:", round(metrics["validation"]["pr_auc"], 4))


if __name__ == "__main__":
    main()
