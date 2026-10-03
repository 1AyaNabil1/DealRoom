"""CLI agent path (Gemini Live API), exercised offline with fake sessions."""
import asyncio
import base64
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

from google import genai
from google.genai import live

import src.agent as agent
from src.context_merger import AUDIO_MIME_TYPE, merge_and_send
from src.negotiation_state import NegotiationState, load_state
from src.screen_capture import LatestFrame, frame_generator

FRAME = base64.b64encode(b"\xff\xd8\xff fake jpeg").decode()


def run(coro):
    return asyncio.run(coro)


def text_message(text, turn_complete=False):
    return SimpleNamespace(text=text, server_content=SimpleNamespace(turn_complete=turn_complete))


class FakeLiveSession:
    """Records what the agent sends; replays one scripted turn per request."""

    def __init__(self, *turns, hang=False):
        self.turns = list(turns)
        self.hang = hang
        self.realtime = []
        self.client_content = []

    async def send_realtime_input(self, **kwargs):
        self.realtime.append(kwargs)

    async def send_client_content(self, *, turns, turn_complete):
        self.client_content.append((turns, turn_complete))

    async def receive(self):
        if self.hang:
            await asyncio.sleep(3600)
        for message in self.turns.pop(0) if self.turns else [text_message("", True)]:
            yield message


# --- merge_and_send ----------------------------------------------------------

def test_sends_audio_frame_and_context_then_reads_the_whole_turn():
    session = FakeLiveSession([
        text_message('{"type":"TACTIC",'),
        text_message('"message":"Hold firm."}'),
        text_message(None, turn_complete=True),
    ])
    state = NegotiationState(session_id="s", opening_ask=150.0)

    reply = run(merge_and_send(session, b"\x00\x01", FRAME, state))

    assert reply == '{"type":"TACTIC","message":"Hold firm."}'
    audio, video = session.realtime
    assert audio["audio"].data == b"\x00\x01"
    assert audio["audio"].mime_type == AUDIO_MIME_TYPE
    assert video["video"].mime_type == "image/jpeg"
    assert video["video"].data == base64.b64decode(FRAME)
    (content, turn_complete), = session.client_content
    assert turn_complete is True
    assert "OPENING ASK: $150.0" in content.parts[0].text


def test_no_frame_means_no_video_message():
    session = FakeLiveSession([text_message('{"type":"SILENT"}', True)])
    run(merge_and_send(session, b"\x00", None, NegotiationState()))
    assert [list(m) for m in session.realtime] == [["audio"]]


def test_hung_live_session_times_out_with_none():
    session = FakeLiveSession(hang=True)
    assert run(merge_and_send(session, b"\x00", None, NegotiationState(), timeout_s=0.05)) is None


def test_session_errors_return_none():
    class Broken(FakeLiveSession):
        async def send_realtime_input(self, **kwargs):
            raise ConnectionError("socket closed")

    assert run(merge_and_send(Broken(), b"\x00", None, NegotiationState())) is None


def test_media_reaches_the_wire_through_the_real_sdk():
    # Regression: session.send(input=LiveClientRealtimeInput(audio=...)) only
    # serialised media_chunks, so audio and frames were sent as null.
    class FakeWebSocket:
        def __init__(self):
            self.sent = []
            self.incoming = [
                json.dumps({"serverContent": {"modelTurn": {"parts": [{"text": '{"type":"SIGNAL",'}]}}}),
                json.dumps({"serverContent": {"modelTurn": {"parts": [{"text": '"message":"ok"}'}]}}}),
                json.dumps({"serverContent": {"turnComplete": True}}),
            ]

        async def send(self, message):
            self.sent.append(json.loads(message))

        async def recv(self, decode=True):
            return self.incoming.pop(0)

    ws = FakeWebSocket()
    client = genai.Client(api_key="not-a-real-key")
    session = live.AsyncSession(api_client=client._api_client, websocket=ws)

    reply = run(merge_and_send(session, b"\x00\x01", FRAME, NegotiationState(session_id="w")))

    assert reply == '{"type":"SIGNAL","message":"ok"}'
    audio, video, context = ws.sent
    assert audio["realtime_input"]["audio"] == {"data": "AAE=", "mime_type": AUDIO_MIME_TYPE}
    # The SDK re-encodes bytes as URL-safe base64; the image itself is unchanged.
    assert base64.urlsafe_b64decode(video["realtime_input"]["video"]["data"]) == base64.b64decode(FRAME)
    assert "SESSION: w" in context["client_content"]["turns"][0]["parts"][0]["text"]


# --- screen frames -------------------------------------------------------------

def test_latest_frame_hands_out_each_frame_once():
    latest = LatestFrame()
    assert latest.take() is None
    latest.put("a")
    latest.put("b")
    assert latest.take() == "b"
    assert latest.take() is None


def test_frames_keep_flowing_while_the_agent_polls():
    # Regression: the agent used asyncio.wait_for(frame_iter.__anext__(), 0.1);
    # the first timeout cancelled and finalised the generator, so no frame was
    # ever sent after that.
    async def scenario():
        stop = asyncio.Event()
        counter = iter(range(1000))

        def slow_capture():
            import time
            time.sleep(0.02)
            return f"frame-{next(counter)}"

        latest = LatestFrame()
        task = asyncio.create_task(latest.fill_from(frame_generator(stop, interval_s=0.01, capture=slow_capture)))
        seen = []
        for _ in range(20):
            frame = latest.take()
            if frame:
                seen.append(frame)
            await asyncio.sleep(0.02)
        stop.set()
        task.cancel()
        return seen

    seen = run(scenario())
    assert len(set(seen)) >= 3


# --- full agent loop -------------------------------------------------------------

def test_agent_loop_records_only_valid_signals(monkeypatch):
    session = FakeLiveSession(
        [text_message('{"type":"TACTIC","message":"Anchor at 150.","confidence":"HIGH"}', True)],
        [text_message("I think you are doing great!", True)],  # prose: dropped
        [text_message('{"type":"RED_FLAG","message":"Competitor quote mentioned."}', True)],
    )

    class FakeLive:
        @asynccontextmanager
        async def connect(self, model, config):
            assert model == "test-live-model"
            yield session

    class FakeClient:
        def __init__(self, **kwargs):
            self.aio = SimpleNamespace(live=FakeLive())

    async def fake_microphone(stop_event):
        for _ in range(3):
            await asyncio.sleep(0.01)
            yield b"\x00\x00" * 8

    async def fake_frames(stop_event):
        yield FRAME
        await asyncio.sleep(3600)

    monkeypatch.setenv("GOOGLE_API_KEY", "not-a-real-key")
    monkeypatch.setenv("DEALROOM_LIVE_MODEL", "test-live-model")
    monkeypatch.setattr(agent.genai, "Client", FakeClient)
    monkeypatch.setattr(agent, "stream_microphone", fake_microphone)
    monkeypatch.setattr(agent, "frame_generator", fake_frames)
    monkeypatch.setattr(agent, "TURN_INTERVAL_S", 0)

    run(agent.run_dealroom_session("cli-1"))

    state = load_state("cli-1")
    assert state.key_moments == ["Anchor at 150."]
    assert state.red_flags == ["Competitor quote mentioned."]
    assert state.status == "completed"
    assert sum("video" in m for m in session.realtime) == 1  # the frame is sent once
