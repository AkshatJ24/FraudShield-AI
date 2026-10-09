"""Application configuration — loaded once at import time from .env / environment variables."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root: backend/app/core/config.py  →  ../../.. = repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ARTIFACTS = _REPO_ROOT / "ml" / "artifacts"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── app ───────────────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    APP_TITLE: str = "FraudShield API"
    APP_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    # ── security (optional for MVP) ───────────────────────────────────────────
    SECRET_KEY: str = "change_this_to_a_secure_secret_key_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ── database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/fraudshield"

    # ── ML artifact paths ─────────────────────────────────────────────────────
    MODEL_PATH: Path = _ARTIFACTS / "model.lgb.txt"
    CALIBRATOR_PATH: Path = _ARTIFACTS / "calibrator.json"
    ENCODERS_PATH: Path = _ARTIFACTS / "encoders.json"
    FEATURE_SCHEMA_PATH: Path = _ARTIFACTS / "feature_schema.json"
    THRESHOLDS_PATH: Path = _ARTIFACTS / "thresholds.json"
    REASON_MAP_PATH: Path = _ARTIFACTS / "reason_map.json"
    MODEL_META_PATH: Path = _ARTIFACTS / "model_meta.json"

    # ── scoring behaviour ────────────────────────────────────────────────────
    # Maximum SHAP reasons to return per request.
    MAX_REASONS: int = 3
    # Whether to update the in-memory card history store for "what-if" calls.
    WHAT_IF_UPDATE_STORE: bool = False


settings = Settings()
