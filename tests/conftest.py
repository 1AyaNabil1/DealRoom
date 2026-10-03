"""Shared fixtures. The suite runs offline: no test talks to Google APIs."""
import pytest


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Give every test its own session store and no real credentials."""
    monkeypatch.setenv("DEALROOM_SESSION_FILE", str(tmp_path / "sessions.json"))
    for name in ("GOOGLE_API_KEY", "GCP_PROJECT_ID", "DEALROOM_MODEL", "DEALROOM_LIVE_MODEL",
                 "DEALROOM_LLM_TIMEOUT_S", "DEALROOM_LLM_MAX_ATTEMPTS",
                 "DEALROOM_CHUNKS_PER_ANALYSIS", "DEALROOM_CORS_ORIGINS"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path
