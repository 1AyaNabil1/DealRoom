"""Runtime configuration read from environment variables.

Every setting has a safe default so the server starts with no configuration
at all; without GOOGLE_API_KEY it runs but reports that the model is not
configured. See .env.example for the full list.

Settings are read on each call to get_settings() (it is cheap), so tests and
long-running processes pick up changes without restarting.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass

logger = logging.getLogger("dealroom.config")

DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_LIVE_MODEL = "gemini-2.0-flash-live-001"
DEFAULT_SESSION_FILE = "session_store.json"


@dataclass(frozen=True)
class Settings:
    google_api_key: str | None
    model: str
    live_model: str
    llm_timeout_s: float
    llm_max_attempts: int
    chunks_per_analysis: int
    session_file: str
    cors_origins: tuple[str, ...]

    @property
    def llm_configured(self) -> bool:
        return bool(self.google_api_key)


def _number(env: Mapping[str, str], name: str, default, cast, minimum):
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = cast(raw)
    except ValueError:
        logger.warning("Ignoring invalid %s=%r; using default %r", name, raw, default)
        return default
    if value < minimum:
        logger.warning("Ignoring %s=%r (must be >= %r); using default %r", name, raw, minimum, default)
        return default
    return value


def get_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    origins = env.get("DEALROOM_CORS_ORIGINS", "*")
    return Settings(
        google_api_key=(env.get("GOOGLE_API_KEY") or "").strip() or None,
        model=env.get("DEALROOM_MODEL") or DEFAULT_MODEL,
        live_model=env.get("DEALROOM_LIVE_MODEL") or DEFAULT_LIVE_MODEL,
        llm_timeout_s=_number(env, "DEALROOM_LLM_TIMEOUT_S", 15.0, float, 1.0),
        llm_max_attempts=_number(env, "DEALROOM_LLM_MAX_ATTEMPTS", 2, int, 1),
        chunks_per_analysis=_number(env, "DEALROOM_CHUNKS_PER_ANALYSIS", 20, int, 1),
        session_file=env.get("DEALROOM_SESSION_FILE") or DEFAULT_SESSION_FILE,
        cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()) or ("*",),
    )
