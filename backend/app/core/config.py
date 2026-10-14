"""
ReceiptLedger – Application Configuration
==========================================
All configuration values are loaded from environment variables (or .env file).
Access via the singleton `settings` object imported throughout the app.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings, loaded from .env file or environment."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Server ──────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    environment: str = "development"

    # ── CORS ────────────────────────────────────────────────────────────────
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:5173", "http://localhost:4173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            v_stripped = v.strip()
            if v_stripped.startswith("[") and v_stripped.endswith("]"):
                try:
                    return json.loads(v_stripped)
                except Exception:
                    pass
            return [origin.strip() for origin in v_stripped.split(",") if origin.strip()]
        elif isinstance(v, list):
            return v
        return ["http://localhost:3000", "http://localhost:5173", "http://localhost:4173"]

    # ── Google Cloud Vision ──────────────────────────────────────────────────
    google_application_credentials: str = ""
    # Maximum Cloud Vision calls before automatic fallback to Tesseract
    vision_api_monthly_quota: int = 950

    # ── Google Gemini (AI Studio) ────────────────────────────────────────────
    # Get from https://aistudio.google.com/app/apikey
    gemini_api_key: str = ""
    # Model to use for receipt parsing (gemini-3.5-flash-lite is fast, reliable, and high quota)
    gemini_model: str = "gemini-3.5-flash-lite"

    # ── Supabase / PostgreSQL ────────────────────────────────────────────────
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # ── Pipeline Tuning ──────────────────────────────────────────────────────
    # Confidence threshold below which items are flagged for review
    review_confidence_threshold: float = 0.85
    # pHash Hamming distance at or below which images are considered duplicates
    phash_hamming_threshold: int = 4
    # Levenshtein similarity ratio required for dictionary normalisation
    fuzzy_match_threshold: float = 0.80
    # Max concurrent heavy OCR tasks (EasyOCR is memory-intensive)
    max_concurrent_ocr: int = 2
    # Max uploaded file size in bytes (10 MB)
    max_upload_bytes: int = 10 * 1024 * 1024
    # Auto-seed sample receipts and review items in development for easy dashboard testing
    seed_demo_data_on_startup: bool = True

    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"

    @property
    def cloud_vision_enabled(self) -> bool:
        return bool(self.google_application_credentials)

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def supabase_enabled(self) -> bool:
        return bool(self.supabase_url) and bool(self.supabase_anon_key)


# Module-level singleton — import `settings` everywhere in the codebase.
settings = Settings()
