"""Categorical encoders. FIT ON TRAIN ONLY, then reused unchanged for validation,
holdout and serving. Saved as JSON so the API loads exactly what training used.

* Low-cardinality columns  -> integer codes (unseen value -> -1, missing -> NaN)
* High-cardinality columns -> frequency (share of train rows; unseen -> 0.0, missing -> NaN)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

LOWCARD_COLS = ["ProductCD", "card4", "card6", "DeviceType"] + [f"M{i}" for i in range(1, 10)]
FREQ_COLS = ["P_emaildomain", "R_emaildomain", "DeviceInfo", "id_30", "id_31", "id_33"]
MIN_COUNT_FOR_FREQ = 5          # values rarer than this are treated as unseen (keeps the JSON small)


def encoded_feature_names():
    return [f"{c}_code" for c in LOWCARD_COLS] + [f"{c}_freq" for c in FREQ_COLS]


class FeatureEncoders:
    def __init__(self):
        self.categories = {}     # col -> sorted list of train values
        self.freqs = {}          # col -> {value: share of train rows}
        self.n_train = None

    # ----------------------------------------------------------------- fit
    def fit(self, train_df: pd.DataFrame) -> "FeatureEncoders":
        self.n_train = int(len(train_df))
        for col in LOWCARD_COLS:
            if col in train_df:
                values = train_df[col].dropna().astype(str).unique().tolist()
                self.categories[col] = sorted(values)
        for col in FREQ_COLS:
            if col in train_df:
                vc = train_df[col].dropna().astype(str).value_counts()
                vc = vc[vc >= MIN_COUNT_FOR_FREQ]
                self.freqs[col] = (vc / self.n_train).to_dict()
        return self

    # ----------------------------------------------------------- transform
    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame(index=df.index)
        for col in LOWCARD_COLS:
            mapping = {v: i for i, v in enumerate(self.categories.get(col, []))}
            out[f"{col}_code"] = self._map(df, col, mapping, unseen=-1.0)
        for col in FREQ_COLS:
            out[f"{col}_freq"] = self._map(df, col, self.freqs.get(col, {}), unseen=0.0)
        return out[encoded_feature_names()]

    @staticmethod
    def _map(df, col, mapping, unseen):
        result = pd.Series(np.nan, index=df.index, dtype="float64")
        if col not in df:
            return result
        s = df[col].astype("object")
        present = s.notna()
        result[present] = s[present].astype(str).map(mapping).fillna(unseen).astype("float64")
        return result

    # --------------------------------------------------------------- save
    def to_json(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(
            {"n_train": self.n_train, "categories": self.categories, "freqs": self.freqs}))

    @classmethod
    def from_json(cls, path) -> "FeatureEncoders":
        data = json.loads(Path(path).read_text())
        enc = cls()
        enc.n_train = data["n_train"]
        enc.categories = data["categories"]
        enc.freqs = data["freqs"]
        return enc
