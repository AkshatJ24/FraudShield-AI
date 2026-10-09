"""Feature tests. Run from the backend/ folder:  pytest -q

These protect the two things that quietly ruin fraud models:
  1. leakage        - a feature must never see the future
  2. train/serve skew - training and the API must produce identical features
"""
import numpy as np
import pandas as pd
import pytest

from app.features import (CARD_COLS, STATEFUL_FEATURES, CardHistoryStore,
                          FeatureEncoders, add_stateless_features, build_feature_frame, replay)


def make_df(n=600, seed=0):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "TransactionID": np.arange(1, n + 1),
        "TransactionDT": np.sort(rng.integers(86_400, 86_400 * 20, n)),
        "TransactionAmt": np.round(np.exp(rng.normal(4, 1, n)), 2),
        "card1": rng.integers(1000, 1010, n),
        "card2": rng.choice([100.0, 200.0, np.nan], n),
        "card3": 150.0, "card5": 226.0,
        "card4": rng.choice(["visa", "mastercard"], n),
        "card6": rng.choice(["debit", "credit"], n),
        "addr1": rng.choice([300.0, 310.0, np.nan], n),
        "addr2": 87.0,
        "D1": rng.choice([0.0, 5.0, 40.0, np.nan], n),
        "DeviceInfo": rng.choice(["Windows", "iOS", None], n),
        "P_emaildomain": rng.choice(["gmail.com", "yahoo.com", None], n),
        "R_emaildomain": rng.choice(["gmail.com", None], n),
    })
    # realistic dtypes: category + float32, like the notebook's reduce_mem()
    for c in ["card4", "card6", "DeviceInfo", "P_emaildomain", "R_emaildomain"]:
        df[c] = df[c].astype("category")
    for c in ["TransactionAmt", "card2", "card3", "card5", "addr1", "addr2", "D1"]:
        df[c] = df[c].astype("float32")
    return df


def test_window_counts_by_hand():
    store = CardHistoryStore()
    base = dict(card1=1, card2=1, card3=1, card4="visa", card5=1, card6="debit", addr1=1, addr2=1)
    times = [100_000, 100_300, 103_000, 190_000]        # +0, +5min, +~48min, +25h
    outs = [store.process({**base, "TransactionDT": t, "TransactionAmt": 10.0}) for t in times]

    assert outs[0]["b_hist_count"] == 0 and np.isnan(outs[0]["b_time_since_last"])
    assert outs[1]["b_txn_count_10m"] == 1 and outs[1]["b_time_since_last"] == 300
    # third txn: first is 3000s old (inside 1h, outside 10m), second is 2700s old
    assert outs[2]["b_txn_count_10m"] == 0 and outs[2]["b_txn_count_1h"] == 2
    assert outs[2]["b_amt_sum_1h"] == pytest.approx(20.0)
    # fourth txn: everything older than 24h -> windows empty, but history count is kept
    assert outs[3]["b_txn_count_24h"] == 0 and outs[3]["b_hist_count"] == 3


def test_first_transaction_has_no_history_and_amount_ratio_uses_past_only():
    store = CardHistoryStore()
    base = dict(card1=1, card2=1, card3=1, card4="visa", card5=1, card6="debit", addr1=1, addr2=1)
    first = store.process({**base, "TransactionDT": 100, "TransactionAmt": 50.0})
    second = store.process({**base, "TransactionDT": 200, "TransactionAmt": 100.0})
    assert np.isnan(first["amt_vs_b_mean"])
    assert second["amt_vs_b_mean"] == pytest.approx(2.0)      # 100 / mean(past = [50])


def test_no_future_leakage():
    """Changing FUTURE transactions must not change features of earlier ones."""
    df = make_df()
    feats, _ = replay(df)

    cut = 300
    future = df.copy()
    rng = np.random.default_rng(1)
    future.loc[cut:, "TransactionAmt"] = (rng.random(len(df) - cut) * 5000).astype("float32")
    future.loc[cut:, "card1"] = rng.integers(2000, 2005, len(df) - cut)
    future["DeviceInfo"] = future["DeviceInfo"].astype(object)
    future.loc[cut:, "DeviceInfo"] = "Linux"
    feats_future, _ = replay(future)

    pd.testing.assert_frame_equal(feats.iloc[:cut], feats_future.iloc[:cut])


def test_serving_row_matches_training_replay():
    """Feeding plain-Python dicts (as the API would) must equal the pandas batch result."""
    df = make_df(300)
    batch, _ = replay(df)

    store = CardHistoryStore()
    order = np.lexsort((df["TransactionID"].to_numpy(), df["TransactionDT"].to_numpy()))
    for pos in order:
        row = df.iloc[pos]
        raw = {}
        for col in ["TransactionDT", "TransactionAmt", "D1", *CARD_COLS, "DeviceInfo", "P_emaildomain"]:
            v = row[col]
            raw[col] = None if pd.isna(v) else (str(v) if isinstance(v, str) else v.item() if hasattr(v, "item") else v)
        # JSON-style types: ints stay ints, floats stay floats
        got = store.process(raw)
        want = batch.iloc[pos]
        np.testing.assert_allclose([got[c] for c in STATEFUL_FEATURES], want.to_numpy(dtype="float64"),
                                   rtol=1e-6, equal_nan=True)


def test_stateless_serving_single_row_matches_batch():
    df = make_df(100)
    df["has_identity"] = 1
    batch = add_stateless_features(df)
    one = add_stateless_features(df.iloc[[7]])
    pd.testing.assert_frame_equal(batch.iloc[[7]], one)


def test_encoders_fit_on_train_only_and_handle_unseen():
    train = pd.DataFrame({"ProductCD": ["W"] * 10 + ["C"] * 10, "P_emaildomain": ["gmail.com"] * 20})
    enc = FeatureEncoders().fit(train)
    test = pd.DataFrame({"ProductCD": ["W", "H", None], "P_emaildomain": ["gmail.com", "new.com", None]})
    out = enc.transform(test)
    assert out["ProductCD_code"].tolist()[:2] == [1.0, -1.0] and np.isnan(out["ProductCD_code"].iloc[2])
    assert out["P_emaildomain_freq"].tolist()[:2] == [1.0, 0.0] and np.isnan(out["P_emaildomain_freq"].iloc[2])


def test_build_feature_frame_shape_and_dtype():
    df = make_df(200)
    df["has_identity"] = 0
    enc = FeatureEncoders().fit(df)
    feats = build_feature_frame(df, enc)
    assert len(feats) == len(df)
    assert set(feats.dtypes.astype(str)) == {"float32"}
    assert not np.isinf(feats.to_numpy()).any()
