"""Card identity keys used for per-card history features.

IEEE-CIS has no card ID, so we build pseudo-IDs from card/address columns:

* Key A (coarse "card group"): card1..card6 + addr1 + addr2
* Key B (fine "card"):         Key A + anchor day, where anchor = floor(day - D1)

D1 behaves like "days since this card's first activity", so (day - D1) is roughly
constant for one card. This is a heuristic found in EDA, not ground truth.

All values are normalised (NaN -> None, numbers -> float, text -> str) so that the
SAME key is produced in training (pandas, mixed dtypes) and in serving (JSON values).
"""
from __future__ import annotations

import math

CARD_COLS = ["card1", "card2", "card3", "card4", "card5", "card6", "addr1", "addr2"]
ADDR1_POS = CARD_COLS.index("addr1")


def norm(value):
    """Normalise a raw value: missing -> None, numeric -> float, anything else -> str."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return None if math.isnan(number) else number


def norm_d1(value):
    """Normalise D1 (rounded so float32 vs float64 inputs give the same anchor)."""
    number = norm(value)
    return None if number is None or isinstance(number, str) else round(number, 3)


def make_keys(card_values, day, d1):
    """Return (key_a, key_b) for one transaction.

    card_values: values for CARD_COLS, in order (already normalised or raw)
    day:         TransactionDT // 86400
    d1:          normalised D1 or None
    """
    key_a = tuple(norm(v) for v in card_values)
    anchor = None if d1 is None else float(math.floor(day - d1))
    return key_a, key_a + (anchor,)
