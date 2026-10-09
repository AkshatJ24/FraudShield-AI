"""Turn SHAP contributions into human-readable reasons (Phase 4).

Pure Python + numpy on purpose: the FastAPI service (Phase 5) copies this file as-is, so the
notebook and the API produce identical reasons.

A reason map (JSON) has:
  rules        feature name -> rule        (specific, human-written)
  group_rules  [{pattern, text, kind}]      (regex fallbacks, e.g. every V-column -> one 'anonymized' line)

Rule forms (checked in this order):
  {"values": {"1": "First time this device..."}}                  exact match on a flag value
  {"bins": [{"min":.., "max":.., "scale":.., "text": ".. {v:.0f} .."}]}  first bin whose range contains the value
  {"labels": {"0": "W"}, "text": ".. '{label}' ..", "text_nolabel": ".."}  categorical codes
  {"text": ".. {v} .."}                                           always applies
Optional on any rule: "transform": "expm1", "when_missing": "text", "kind": "specific" | "anonymized".
A rule that finds no matching text returns None, so neutral values never become 'reasons'.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np


def _is_missing(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


class ReasonMap:
    def __init__(self, spec: dict):
        self.spec = spec
        self.rules = spec.get("rules", {})
        self.group_rules = [(re.compile(g["pattern"]), g["text"], g.get("kind", "anonymized")) for g in spec.get("group_rules", [])]
        self.max_reasons = int(spec.get("max_reasons", 3))
        self.min_contribution = float(spec.get("min_contribution", 0.05))
        self.max_anonymized = int(spec.get("max_anonymized", 1))
        self.fallback = spec.get("fallback_reason", "Overall transaction pattern resembles past fraud")

    @classmethod
    def from_json(cls, path) -> "ReasonMap":
        return cls(json.loads(Path(path).read_text()))

    # -- one feature -> one sentence (or None) -------------------------------------------------
    def reason_for(self, feature: str, value):
        rule = self.rules.get(feature)
        if rule is not None:
            kind = rule.get("kind", "specific")
            if _is_missing(value):
                t = rule.get("when_missing")
                return (t, kind) if t else None
            v = float(value)
            if rule.get("transform") == "expm1":
                v = math.expm1(v)
            if "values" in rule:
                if math.isnan(v):
                    return None
                t = rule["values"].get(str(int(round(v))))
                return (t.format(v=v), kind) if t else None
            if "bins" in rule:
                for b in rule["bins"]:
                    if (b.get("min") is None or v >= b["min"]) and (b.get("max") is None or v <= b["max"]):
                        t = b.get("text")
                        return (t.format(v=v / b.get("scale", 1.0)), kind) if t else None
                return None
            if "labels" in rule:
                lab = rule["labels"].get(str(int(round(v))))
                if lab is not None:
                    return rule["text"].format(label=lab, v=v), kind
                t = rule.get("text_nolabel")
                return (t, kind) if t else None
            if "text" in rule:
                return rule["text"].format(v=v), kind
            return None
        for pat, text, kind in self.group_rules:
            if pat.match(feature):
                return text, kind
        return None

    # -- a whole transaction -------------------------------------------------------------------
    def explain(self, features, values, contribs, top_k: int | None = None) -> list[dict]:
        """features/values/contribs are aligned sequences (contribs = SHAP in log-odds, no bias term).
        Returns up to top_k reasons, strongest first. Reasons with the same text are merged (contributions add)."""
        top_k = top_k or self.max_reasons
        c = np.asarray(contribs, dtype="float64")
        order = np.argsort(-c)[:80]
        merged: dict[str, dict] = {}
        for idx in order:
            if c[idx] <= 0:
                break
            hit = self.reason_for(features[idx], values[idx])
            if hit is None:
                continue
            text, kind = hit
            m = merged.setdefault(text, {"text": text, "contribution": 0.0, "kind": kind, "features": []})
            m["contribution"] += float(c[idx])
            m["features"].append(features[idx])
        ranked = sorted(merged.values(), key=lambda m: -m["contribution"])
        out, n_anon = [], 0
        for m in ranked:
            if m["contribution"] < self.min_contribution:
                continue
            if m["kind"] == "anonymized":
                if n_anon >= self.max_anonymized:
                    continue
                n_anon += 1
            out.append(m)
            if len(out) == top_k:
                break
        if not out:
            out = [{"text": self.fallback, "contribution": float(c[order[0]]) if len(order) else 0.0, "kind": "fallback", "features": []}]
        return out
