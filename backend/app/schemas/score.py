"""Pydantic request and response schemas for the /score endpoint.

Design notes
------------
* Request fields mirror the IEEE-CIS dataset columns that analysts understand.
* Every field is Optional so the manual "Try a Transaction" form can omit columns.
  Missing fields get model-friendly defaults (None → NaN in the feature builder).
* The response carries only what is needed for the dashboard: score (0-100),
  decision, human-readable reasons, latency, and a stable transaction ID.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class ScoreRequest(BaseModel):
    """Input for POST /score.  All fields are optional to support partial input."""

    # ── identifiers (not used as model features, forwarded to the response) ─
    transaction_id: Optional[str] = Field(
        default=None,
        description="Caller-supplied transaction ID.  If omitted, the API generates one."
    )

    # ── core transaction fields ──────────────────────────────────────────────
    TransactionAmt: float = Field(
        ...,
        gt=0,
        description="Transaction amount in USD",
        examples=[912.50]
    )
    TransactionDT: Optional[int] = Field(
        default=None,
        description=(
            "Seconds offset from an unknown reference epoch (same unit as the "
            "training dataset).  If omitted, the current UNIX timestamp is used "
            "as a reasonable substitute for velocity features."
        )
    )
    ProductCD: Optional[str] = Field(
        default=None,
        description="Product code: W, H, C, S, or R",
        examples=["W"]
    )

    # ── card fields ──────────────────────────────────────────────────────────
    card1: Optional[float] = Field(default=None, description="Payment card attribute 1")
    card2: Optional[float] = Field(default=None, description="Payment card attribute 2")
    card3: Optional[float] = Field(default=None, description="Payment card attribute 3")
    card4: Optional[str] = Field(
        default=None,
        description="Card network: visa, mastercard, american express, discover",
        examples=["visa"]
    )
    card5: Optional[float] = Field(default=None, description="Payment card attribute 5")
    card6: Optional[str] = Field(
        default=None,
        description="Card type: debit or credit",
        examples=["credit"]
    )

    # ── address ──────────────────────────────────────────────────────────────
    addr1: Optional[float] = Field(default=None, description="Billing address code")
    addr2: Optional[float] = Field(default=None, description="Country code")

    # ── distance ─────────────────────────────────────────────────────────────
    dist1: Optional[float] = Field(default=None, description="Distance from home address")
    dist2: Optional[float] = Field(default=None, description="Distance from work address")

    # ── email ────────────────────────────────────────────────────────────────
    P_emaildomain: Optional[str] = Field(
        default=None,
        description="Purchaser email domain",
        examples=["protonmail.com"]
    )
    R_emaildomain: Optional[str] = Field(
        default=None,
        description="Recipient email domain"
    )

    # ── device ───────────────────────────────────────────────────────────────
    DeviceType: Optional[str] = Field(
        default=None,
        description="Device type: desktop or mobile",
        examples=["mobile"]
    )
    DeviceInfo: Optional[str] = Field(
        default=None,
        description="Device model/OS string"
    )

    # ── D-columns (card history timing, partially anonymised) ────────────────
    D1: Optional[float] = Field(default=None, description="Days since first transaction on card")

    # ── identity / match flags ───────────────────────────────────────────────
    # M1-M9 are match flags (T/F/nan in the raw data)
    M1: Optional[str] = Field(default=None)
    M2: Optional[str] = Field(default=None)
    M3: Optional[str] = Field(default=None)
    M4: Optional[str] = Field(default=None)
    M5: Optional[str] = Field(default=None)
    M6: Optional[str] = Field(default=None)
    M7: Optional[str] = Field(default=None)
    M8: Optional[str] = Field(default=None)
    M9: Optional[str] = Field(default=None)

    # ── identity table columns ───────────────────────────────────────────────
    id_30: Optional[str] = Field(default=None, description="Operating system")
    id_31: Optional[str] = Field(default=None, description="Browser")
    id_33: Optional[str] = Field(default=None, description="Screen resolution")

    # ── what-if flag ─────────────────────────────────────────────────────────
    what_if: bool = Field(
        default=False,
        description=(
            "If true, score the transaction WITHOUT recording it in card history. "
            "Use for the 'Try a Transaction' form so analysts can explore without "
            "corrupting the velocity store."
        )
    )

    @model_validator(mode="before")
    @classmethod
    def _set_defaults(cls, data: Any) -> Any:
        """Apply sensible defaults so partial requests don't crash."""
        import time as _time
        if isinstance(data, dict):
            if data.get("TransactionDT") is None:
                data["TransactionDT"] = int(_time.time())
        return data

    model_config = {"json_schema_extra": {
        "examples": [{
            "TransactionAmt": 912.50,
            "ProductCD": "W",
            "card4": "visa",
            "card6": "credit",
            "addr1": 315,
            "P_emaildomain": "protonmail.com",
            "DeviceType": "mobile",
        }]
    }}


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------

class Reason(BaseModel):
    """One human-readable reason driving the decision."""
    text: str
    contribution: float = Field(description="SHAP contribution in log-odds space")
    kind: Literal["specific", "anonymized", "fallback"] = "specific"


class ScoreResponse(BaseModel):
    """Response from POST /score."""
    transaction_id: str = Field(description="Stable ID for this scored transaction")
    score: int = Field(ge=0, le=100, description="Risk score 0 (safe) – 100 (high risk)")
    decision: Literal["APPROVE", "REVIEW", "BLOCK"]
    reasons: list[Reason] = Field(description="Top SHAP-driven explanations")
    calibrated_prob: float = Field(description="Calibrated fraud probability (0–1)")
    raw_score: float = Field(description="Raw model output before calibration")
    latency_ms: float = Field(description="End-to-end scoring latency in milliseconds")
    what_if: bool = Field(description="True if this score did NOT update card history")


# ---------------------------------------------------------------------------
# Health / Info
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"] = "ok"
    model_loaded: bool
    model_version: str
    n_trees: int
    n_features: int
    card_store_size: int = Field(description="Number of unique card identities in the in-memory store")
