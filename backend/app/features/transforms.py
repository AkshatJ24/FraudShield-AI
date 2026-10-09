"""Stateless row-level features (no history needed).

Works on a DataFrame, so training passes the whole dataset and serving passes a
one-row DataFrame. Same function, same output.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

D_COLS = [f"D{i}" for i in range(1, 16)]
ID_NUM_COLS = [f"id_{i:02d}" for i in range(1, 12)]

STATELESS_FEATURES = [
    "amt_log", "amt_cents", "hour_rel", "dow_rel", "email_match",
    "has_identity", "addr_missing", "r_email_present", "n_null_D", "n_null_id",
]


def add_stateless_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame (same index as df) with the STATELESS_FEATURES columns."""
    out = pd.DataFrame(index=df.index)

    amt = pd.to_numeric(df["TransactionAmt"], errors="coerce").astype("float64").round(3)
    dt = pd.to_numeric(df["TransactionDT"], errors="coerce").astype("int64")

    out["amt_log"] = np.log1p(amt)
    out["amt_cents"] = (amt - np.floor(amt)).round(3)           # fraud often uses distinctive cents
    # TransactionDT has no known start date: these are RELATIVE hour / weekday, not clock times.
    out["hour_rel"] = (dt // 3600) % 24
    out["dow_rel"] = (dt // 86_400) % 7

    p = df["P_emaildomain"].astype("object") if "P_emaildomain" in df else pd.Series(None, index=df.index, dtype="object")
    r = df["R_emaildomain"].astype("object") if "R_emaildomain" in df else pd.Series(None, index=df.index, dtype="object")
    both = (p.notna() & r.notna()).to_numpy()
    same = (p.astype(str) == r.astype(str)).to_numpy()
    out["email_match"] = np.where(both, same.astype("float64"), np.nan)   # 1 match, 0 mismatch, NaN unknown

    out["has_identity"] = df["has_identity"].astype("int8") if "has_identity" in df else 0
    out["addr_missing"] = (df["addr1"].isna().astype("int8") if "addr1" in df else 1)
    out["r_email_present"] = r.notna().astype("int8")
    out["n_null_D"] = df.reindex(columns=D_COLS).isna().sum(axis=1)
    out["n_null_id"] = df.reindex(columns=ID_NUM_COLS).isna().sum(axis=1)
    return out[STATELESS_FEATURES]
