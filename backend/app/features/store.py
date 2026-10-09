"""Stateful per-card history features (velocity, novelty, behaviour vs history).

DESIGN: one implementation for training AND serving.
Training replays transactions in time order through ``CardHistoryStore.process``;
the API calls the very same method for each incoming transaction. That removes
training/serving skew by construction.

LEAKAGE RULES (enforced by this design and by tests/test_features.py):
* Features for a transaction are computed BEFORE that transaction is added to history.
* Only earlier transactions are visible. Fraud labels are never used (in production
  labels arrive days later, so they cannot be features).
* Transactions must be fed in non-decreasing TransactionDT order (ties: by TransactionID).
"""
from __future__ import annotations

from collections import deque

from .keys import ADDR1_POS, CARD_COLS, make_keys, norm, norm_d1

NAN = float("nan")
WINDOW_24H, WINDOW_1H, WINDOW_10M = 86_400, 3_600, 600

# Key B = fine card identity. Key A = coarse card group.
B_FEATURES = [
    "b_hist_count", "b_hist_amt_mean",
    "b_txn_count_10m", "b_txn_count_1h", "b_txn_count_24h",
    "b_amt_sum_1h", "b_amt_sum_24h",
    "b_time_since_last", "amt_vs_b_mean",
    "new_device_flag", "new_email_flag", "new_addr_flag",
]
A_FEATURES = ["a_hist_count", "a_hist_amt_mean", "a_txn_count_1h", "a_txn_count_24h", "amt_vs_a_mean"]
STATEFUL_FEATURES = B_FEATURES + A_FEATURES


class _State:
    __slots__ = ("count", "amt_sum", "last_dt", "win", "devices", "emails", "addrs")

    def __init__(self):
        self.count = 0
        self.amt_sum = 0.0
        self.last_dt = None
        self.win = deque()          # (dt, amt) pairs, only the last 24h are kept
        self.devices = set()
        self.emails = set()
        self.addrs = set()


def _window(state, dt):
    """Counts and sums over the last 10 min / 1 h / 24 h (past transactions only)."""
    n10 = n1h = n24 = 0
    s1h = s24 = 0.0
    c24, c1h, c10 = dt - WINDOW_24H, dt - WINDOW_1H, dt - WINDOW_10M
    for t, a in reversed(state.win):
        if t < c24:
            break
        n24 += 1
        s24 += a
        if t >= c1h:
            n1h += 1
            s1h += a
            if t >= c10:
                n10 += 1
    return n10, n1h, n24, s1h, s24


def _ratio(amount, mean):
    return amount / mean if mean and mean > 0 else NAN


def _novelty(value, seen):
    """1.0 if value was never seen on this card, 0.0 if seen before, NaN if value missing."""
    return NAN if value is None else float(value not in seen)


class CardHistoryStore:
    """In-memory history for all cards. One instance lives in the FastAPI process."""

    def __init__(self):
        self._a = {}   # key_a -> _State
        self._b = {}   # key_b -> _State

    def __len__(self):
        return len(self._b)

    # ------------------------------------------------------------------ API
    def process(self, txn, update=True):
        """Compute stateful features for ``txn`` (dict of raw fields), then add it to history.

        Required keys: TransactionDT, TransactionAmt.
        Optional keys: card1..card6, addr1, addr2, D1, DeviceInfo, P_emaildomain
        (missing -> treated as unknown).

        update=False scores without remembering the transaction (what-if scoring).
        """
        dt = int(txn["TransactionDT"])
        amt = round(float(txn["TransactionAmt"]), 3)
        card_values = [norm(txn.get(c)) for c in CARD_COLS]
        key_a, key_b = make_keys(card_values, dt // 86_400, norm_d1(txn.get("D1")))

        device = norm(txn.get("DeviceInfo"))
        email = norm(txn.get("P_emaildomain"))
        addr = card_values[ADDR1_POS]

        state_a, state_b = self._a.get(key_a), self._b.get(key_b)
        out = self._b_features(state_b, dt, amt, device, email, addr)
        out.update(self._a_features(state_a, dt, amt))

        if update:
            self._add(self._a, key_a, dt, amt)
            state = self._add(self._b, key_b, dt, amt)
            if device is not None:
                state.devices.add(device)
            if email is not None:
                state.emails.add(email)
            if addr is not None:
                state.addrs.add(addr)
        return out

    # -------------------------------------------------------------- internals
    @staticmethod
    def _add(table, key, dt, amt):
        state = table.get(key)
        if state is None:
            state = table[key] = _State()
        win = state.win
        while win and win[0][0] < dt - WINDOW_24H:
            win.popleft()
        win.append((dt, amt))
        state.count += 1
        state.amt_sum += amt
        state.last_dt = dt
        return state

    @staticmethod
    def _b_features(state, dt, amt, device, email, addr):
        if state is None or state.count == 0:
            return {
                "b_hist_count": 0.0, "b_hist_amt_mean": NAN,
                "b_txn_count_10m": 0.0, "b_txn_count_1h": 0.0, "b_txn_count_24h": 0.0,
                "b_amt_sum_1h": 0.0, "b_amt_sum_24h": 0.0,
                "b_time_since_last": NAN, "amt_vs_b_mean": NAN,
                "new_device_flag": NAN, "new_email_flag": NAN, "new_addr_flag": NAN,
            }
        n10, n1h, n24, s1h, s24 = _window(state, dt)
        mean = state.amt_sum / state.count
        return {
            "b_hist_count": float(state.count), "b_hist_amt_mean": mean,
            "b_txn_count_10m": float(n10), "b_txn_count_1h": float(n1h), "b_txn_count_24h": float(n24),
            "b_amt_sum_1h": s1h, "b_amt_sum_24h": s24,
            "b_time_since_last": float(dt - state.last_dt), "amt_vs_b_mean": _ratio(amt, mean),
            "new_device_flag": _novelty(device, state.devices),
            "new_email_flag": _novelty(email, state.emails),
            "new_addr_flag": _novelty(addr, state.addrs),
        }

    @staticmethod
    def _a_features(state, dt, amt):
        if state is None or state.count == 0:
            return {"a_hist_count": 0.0, "a_hist_amt_mean": NAN,
                    "a_txn_count_1h": 0.0, "a_txn_count_24h": 0.0, "amt_vs_a_mean": NAN}
        _, n1h, n24, _, _ = _window(state, dt)
        mean = state.amt_sum / state.count
        return {"a_hist_count": float(state.count), "a_hist_amt_mean": mean,
                "a_txn_count_1h": float(n1h), "a_txn_count_24h": float(n24),
                "amt_vs_a_mean": _ratio(amt, mean)}
