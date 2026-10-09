"""Batch feature building for training (replays the stream through CardHistoryStore)."""
from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd

from .encoders import FeatureEncoders
from .keys import CARD_COLS
from .store import STATEFUL_FEATURES, CardHistoryStore
from .transforms import ID_NUM_COLS, add_stateless_features

PASSTHROUGH_BASE = ["TransactionAmt", "card1", "card2", "card3", "card5",
                    "addr1", "addr2", "dist1", "dist2"]

# Columns the history store reads from each transaction.
STORE_INPUT_COLS = ["TransactionDT", "TransactionAmt"] + CARD_COLS + ["D1", "DeviceInfo", "P_emaildomain"]


def _py_list(series: pd.Series) -> list:
    """Series -> list of plain Python values (missing -> None, text -> str, numbers -> float)."""
    if isinstance(series.dtype, pd.CategoricalDtype) or series.dtype == object \
            or pd.api.types.is_string_dtype(series.dtype):
        return [None if (v is None or v is pd.NA or (isinstance(v, float) and math.isnan(v))) else str(v)
                for v in series.astype(object).tolist()]
    return [None if v != v else float(v) for v in series.astype("float64").tolist()]


def passthrough_columns(columns) -> list:
    cols = [c for c in PASSTHROUGH_BASE if c in columns]
    cd_v = [c for c in columns if re.match(r"^(C|D|V)\d+$", c)]
    cols += sorted(cd_v, key=lambda c: (c[0], int(c[1:])))
    cols += [c for c in ID_NUM_COLS if c in columns]
    return cols


def replay(df: pd.DataFrame, store: CardHistoryStore | None = None):
    """Run every transaction through the history store in time order.

    Returns (stateful_features_df aligned to df.index, store).
    Pass an existing ``store`` to continue from a warmed-up state.
    """
    store = store if store is not None else CardHistoryStore()
    n = len(df)
    order = np.lexsort((df["TransactionID"].to_numpy(), df["TransactionDT"].to_numpy()))

    cols = {c: _py_list(df[c]) if c in df else [None] * n for c in STORE_INPUT_COLS}
    rows = [None] * n
    for pos in order:
        rows[pos] = store.process({c: cols[c][pos] for c in STORE_INPUT_COLS})
    return pd.DataFrame(rows, index=df.index, columns=STATEFUL_FEATURES), store


def build_feature_frame(df: pd.DataFrame, encoders: FeatureEncoders,
                        store: CardHistoryStore | None = None) -> pd.DataFrame:
    """Full model-input frame: passthrough + stateless + encoded + stateful (all float32)."""
    stateful, _ = replay(df, store)
    parts = [
        df[passthrough_columns(df.columns)].astype("float32"),
        add_stateless_features(df),
        encoders.transform(df),
        stateful,
    ]
    return pd.concat(parts, axis=1).astype("float32")
