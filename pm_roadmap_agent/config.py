"""Runtime configuration, read from environment variables.

Every setting has a sane default so the demo and tests run with zero
configuration. Only LLM-backed runs need real secrets (ANTHROPIC_API_KEY
or OPENAI_API_KEY, depending on LLM_PROVIDER).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


@dataclass
class Config:
    """All knobs for the pipeline. Prefer environment variables in production."""

    # --- LLM ---
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "anthropic").lower())
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL", ""))
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    openai_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY"))
    llm_temperature: float = field(default_factory=lambda: _env_float("LLM_TEMPERATURE", 0.2))
    llm_max_tokens: int = field(default_factory=lambda: _env_int("LLM_MAX_TOKENS", 2000))

    # --- Storage ---
    db_path: str = field(default_factory=lambda: _env("DB_PATH", "pm_roadmap_agent.db"))
    briefs_dir: str = field(default_factory=lambda: _env("BRIEFS_DIR", "briefs"))

    # --- Pipeline tuning ---
    cluster_batch_size: int = field(default_factory=lambda: _env_int("CLUSTER_BATCH_SIZE", 40))
    max_feedback_per_run: int = field(default_factory=lambda: _env_int("MAX_FEEDBACK_PER_RUN", 500))
    trend_min_count: int = field(default_factory=lambda: _env_int("TREND_MIN_COUNT", 3))
    trend_growth_factor: float = field(default_factory=lambda: _env_float("TREND_GROWTH_FACTOR", 2.0))

    # --- Weekly digest email (optional; printing is the default) ---
    smtp_host: str = field(default_factory=lambda: _env("SMTP_HOST"))
    smtp_port: int = field(default_factory=lambda: _env_int("SMTP_PORT", 587))
    smtp_user: str = field(default_factory=lambda: _env("SMTP_USER"))
    smtp_password: str = field(default_factory=lambda: _env("SMTP_PASSWORD"))
    digest_from: str = field(default_factory=lambda: _env("DIGEST_FROM"))
    digest_to: str = field(default_factory=lambda: _env("DIGEST_TO"))

    # --- App Store ingestion ---
    appstore_country: str = field(default_factory=lambda: _env("APPSTORE_COUNTRY", "us"))
    appstore_max_pages: int = field(default_factory=lambda: _env_int("APPSTORE_MAX_PAGES", 5))

    @property
    def default_model(self) -> str:
        """Provider default model when LLM_MODEL is unset."""
        if self.llm_model:
            return self.llm_model
        if self.llm_provider == "openai":
            return "gpt-4o-mini"
        return "claude-haiku-4-5"

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.digest_to)
