"""API and WebSocket behaviour, with Gemini replaced by FakeLLM."""
import pytest
from fastapi.testclient import TestClient

import src.server as server
from src.negotiation_state import create_session, load_state, update_state
from tests.fakes import FakeLLM

TACTIC = '{"type":"TACTIC","message":"Anchor high.","confidence":"HIGH","reasoning":"r"}'
RED_FLAG = '{"type":"RED_FLAG","message":"Budget freeze mentioned.","confidence":"MEDIUM","reasoning":"r"}'
CHUNKS = 3  # audio chunks per coaching request in these tests


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DEALROOM_CHUNKS_PER_ANALYSIS", str(CHUNKS))
    with TestClient(server.app) as c:
        yield c
    server.app.dependency_overrides.clear()


def use_llm(llm):
    server.app.dependency_overrides[server.get_llm] = lambda: llm
    return llm


def send_window(ws, n=CHUNKS):
    for _ in range(n):
        ws.send_bytes(b"\x1a\x45\xdf\xa3")


# --- health and static pages ---------------------------------------------

def test_health_without_api_key(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["llm_configured"] is False
    assert body["model"] == "gemini-2.5-flash"


def test_health_with_api_key_never_echoes_it(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "secret-value")
    response = client.get("/health")
    assert response.json()["llm_configured"] is True
    assert "secret-value" not in response.text


@pytest.mark.parametrize("path", ["/", "/overlay", "/test_mic"])
def test_pages_are_served(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


# --- /stream ---------------------------------------------------------------

def test_stream_without_api_key_reports_error_and_closes(client):
    with client.websocket_connect("/stream") as ws:
        assert ws.receive_json()["type"] == "SESSION_INIT"
        error = ws.receive_json()
        assert error == {"type": "ERROR", "message": "GOOGLE_API_KEY is not configured"}
        assert ws.receive()["type"] == "websocket.close"


def test_stream_sends_validated_card_after_each_audio_window(client):
    llm = use_llm(FakeLLM(TACTIC))
    with client.websocket_connect("/stream?session_id=s1") as ws:
        assert ws.receive_json() == {"type": "SESSION_INIT", "session_id": "s1"}
        send_window(ws)
        card = ws.receive_json()

    assert card == {"type": "TACTIC", "message": "Anchor high.", "confidence": "HIGH", "reasoning": "r"}
    assert llm.calls == 1
    assert llm.json_flags == [True]
    assert "SESSION: s1" in llm.prompts[0]

    state = load_state("s1")
    assert state.key_moments == ["Anchor high."]
    assert state.status == "completed"


def test_red_flags_are_recorded_separately(client):
    use_llm(FakeLLM(RED_FLAG))
    with client.websocket_connect("/stream?session_id=s2") as ws:
        ws.receive_json()
        send_window(ws)
        assert ws.receive_json()["type"] == "RED_FLAG"

    state = load_state("s2")
    assert state.red_flags == ["Budget freeze mentioned."]
    assert state.key_moments == []


def test_no_extra_model_calls_without_new_audio(client):
    # Regression: the old loop checked chunk_count % 20 == 0 on every
    # iteration, so after a window it called the model again on every idle
    # poll and every text frame until new audio arrived.
    llm = use_llm(FakeLLM(TACTIC))
    with client.websocket_connect("/stream") as ws:
        ws.receive_json()
        send_window(ws)
        ws.receive_json()
        for _ in range(5):
            ws.send_text("ping")
        send_window(ws)
        ws.receive_json()
    assert llm.calls == 2


@pytest.mark.parametrize("bad_reply", [
    '{"type":"RED_FLAG","message":null}',
    "Sure! Here is some advice: anchor high.",
    '{"type":"SILENT"}',
    ValueError("model exploded"),
])
def test_bad_model_output_is_dropped_and_session_continues(client, bad_reply):
    llm = use_llm(FakeLLM(bad_reply, TACTIC))
    with client.websocket_connect("/stream?session_id=s3") as ws:
        ws.receive_json()
        send_window(ws)  # bad reply: nothing is sent
        send_window(ws)  # good reply
        card = ws.receive_json()

    assert card["message"] == "Anchor high."
    assert llm.calls == 2
    state = load_state("s3")
    assert state.red_flags == []
    assert state.key_moments == ["Anchor high."]


# --- /debrief --------------------------------------------------------------

def test_debrief_for_unknown_session(client):
    body = client.post("/debrief", json={"session_id": "nope"}).json()
    assert body == {"debrief_text": "Session complete. No negotiation data recorded.", "session_id": "nope"}


def test_debrief_without_api_key_uses_fallback(client):
    create_session("d1")
    body = client.post("/debrief", json={"session_id": "d1"}).json()
    assert body["debrief_text"] == server.DEBRIEF_FALLBACK
    assert load_state("d1").status == "completed"


def test_debrief_uses_session_history(client):
    state = create_session("d2")
    update_state(state, {"key_moments": ["Anchor high."], "red_flags": ["Budget freeze."]})
    llm = use_llm(FakeLLM("SUMMARY: Good call."))

    body = client.post("/debrief", json={"session_id": "d2"}).json()

    assert body["debrief_text"] == "SUMMARY: Good call."
    assert "KEY MOMENTS: Anchor high." in llm.prompts[0]
    assert "RED FLAGS: Budget freeze." in llm.prompts[0]
    assert llm.json_flags == [False]


def test_debrief_falls_back_when_model_fails(client):
    create_session("d3")
    use_llm(FakeLLM(ValueError("quota")))
    body = client.post("/debrief", json={"session_id": "d3"}).json()
    assert body["debrief_text"] == server.DEBRIEF_FALLBACK


# --- /tts ------------------------------------------------------------------

def test_tts_returns_503_when_every_engine_fails(client, monkeypatch):
    def fail(*args):
        raise RuntimeError("offline")

    monkeypatch.setattr(server, "_google_tts_synthesize", fail)
    monkeypatch.setattr(server, "_gtts_synthesize", fail)
    response = client.post("/tts", json={"text": "hello"})
    assert response.status_code == 503


def test_tts_uses_fallback_engine(client, monkeypatch):
    def fail(*args):
        raise RuntimeError("no gcp")

    monkeypatch.setattr(server, "_google_tts_synthesize", fail)
    monkeypatch.setattr(server, "_gtts_synthesize", lambda text: b"ID3fake-mp3")
    response = client.post("/tts", json={"text": "x" * 500})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"


def test_google_tts_is_skipped_without_project_id():
    with pytest.raises(RuntimeError, match="GCP_PROJECT_ID"):
        server._google_tts_synthesize("hi", "en-US-Neural2-D")
