# server.py
import os
import uuid
import logging
import asyncio
import io
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
import uvicorn

try:
    from google.cloud import texttospeech
except Exception:
    texttospeech = None

try:
    from gtts import gTTS
except Exception:
    gTTS = None

# Import components from the DealRoom modules.
# The server deliberately does not import src.agent or src.screen_capture:
# those need PyAudio (PortAudio) and PyAutoGUI (a display), which a headless
# server or container does not have.
from src.config import get_settings
from src.context_merger import parse_gemini_response
from src.llm import LLMError, TextModel, gemini_model, generate_text
from src.negotiation_state import (
    NegotiationState,
    create_session,
    load_state,
    save_state,
    state_to_prompt_context,
    update_state,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dealroom_server")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
VERSION = "1.0.0"
DEBRIEF_FALLBACK = "Session complete. Review your notes for follow-up actions."

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    """
    settings = get_settings()
    if settings.llm_configured:
        logger.info("DEALROOM SERVER STARTED (model: %s)", settings.model)
    else:
        logger.warning("DEALROOM SERVER STARTED without GOOGLE_API_KEY: live coaching is disabled "
                       "and debriefs use a fixed fallback text")
    yield
    logger.info("DEALROOM SERVER STOPPED")

app = FastAPI(lifespan=lifespan)

# CORS configuration. No cookies or auth headers are used, so credentials
# stay disabled; restrict origins with DEALROOM_CORS_ORIGINS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_settings().cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_llm() -> TextModel | None:
    """FastAPI dependency: the configured text model, or None without an API key."""
    settings = get_settings()
    if not settings.google_api_key:
        return None
    return gemini_model(settings.google_api_key, settings.model, settings.llm_timeout_s)


LLM = Annotated[TextModel | None, Depends(get_llm)]

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """
    Root endpoint returning a simple HTML status page.
    """
    html_content = """
    <!DOCTYPE html>
    <html>
        <head>
            <title>DealRoom</title>
            <style>
                body { font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; background-color: #f0f2f5; }
                .container { background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; }
                h1 { color: #1a73e8; }
                .status { color: #34a853; font-weight: bold; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>DealRoom — Live Negotiation Intelligence</h1>
                <p class="status">Status: Online</p>
            </div>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.get("/overlay", response_class=HTMLResponse)
async def serve_overlay():
    return FileResponse(STATIC_DIR / "overlay.html", media_type="text/html")

@app.get("/test_mic", response_class=HTMLResponse)
async def serve_test():
    return FileResponse(STATIC_DIR / "test_mic.html", media_type="text/html")

@app.get("/health")
async def health_check():
    """
    Standard health check endpoint. Reports the model the server actually
    calls and whether an API key is configured (never the key itself).
    """
    settings = get_settings()
    return JSONResponse(content={
        "status": "ok",
        "model": settings.model,
        "llm_configured": settings.llm_configured,
        "version": VERSION,
    })

# === TTS SECTION START ===
class TTSRequest(BaseModel):
    text: str = Field(..., max_length=200)
    voice: str = "en-US-Neural2-D"

    @field_validator("text", mode="before")
    @classmethod
    def truncate_text(cls, value):
        return str(value)[:200]


class DebriefRequest(BaseModel):
    session_id: str


def _google_tts_synthesize(text: str, voice_name: str) -> bytes:
    if texttospeech is None:
        raise RuntimeError("google-cloud-texttospeech is not installed")

    gcp_project_id = os.environ.get("GCP_PROJECT_ID")
    if not gcp_project_id:
        raise RuntimeError("GCP_PROJECT_ID is not set; skipping Google Cloud TTS")
    logger.debug("Using Google Cloud TTS project: %s", gcp_project_id)

    client = texttospeech.TextToSpeechClient()
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(language_code="en-US", name=voice_name)
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=0.95,
        pitch=-2.0,
    )
    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config,
    )
    return response.audio_content


def _gtts_synthesize(text: str) -> bytes:
    # Try gTTS first
    try:
        if gTTS is None:
            raise RuntimeError("gTTS not installed")
        tts = gTTS(text=text, lang="en", slow=False)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    except Exception:
        pass

    # Fallback: macOS say command -> AIFF bytes
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as f:
        tmp_path = f.name

    try:
        subprocess.run(
            ["say", "-o", tmp_path, text],
            check=True,
            timeout=10,
            capture_output=True,
        )
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.post("/tts")
async def text_to_speech(request: TTSRequest):
    text = request.text[:200]

    try:
        google_audio = await asyncio.wait_for(
            asyncio.to_thread(_google_tts_synthesize, text, request.voice),
            timeout=5,
        )
        return Response(content=google_audio, media_type="audio/mpeg")
    except Exception as google_error:
        logger.warning("Google TTS failed, falling back to gTTS: %s", google_error)

    try:
        gtts_audio = await asyncio.wait_for(
            asyncio.to_thread(_gtts_synthesize, text),
            timeout=5,
        )
        media_type = "audio/aiff" if gtts_audio.startswith(b"FORM") and gtts_audio[8:12] == b"AIFF" else "audio/mpeg"
        return Response(content=gtts_audio, media_type=media_type)
    except Exception as gtts_error:
        logger.error("gTTS fallback failed: %s", gtts_error)

    return JSONResponse({"error": "TTS unavailable"}, status_code=503)


@app.get("/tts/health")
async def tts_health_check():
    test_text = "test"

    try:
        await asyncio.wait_for(
            asyncio.to_thread(_google_tts_synthesize, test_text, "en-US-Neural2-D"),
            timeout=5,
        )
        return JSONResponse({"tts": "google"})
    except Exception as google_error:
        logger.warning("Google TTS health check failed: %s", google_error)

    try:
        await asyncio.wait_for(asyncio.to_thread(_gtts_synthesize, test_text), timeout=5)
        return JSONResponse({"tts": "gtts"})
    except Exception as gtts_error:
        logger.warning("gTTS health check failed: %s", gtts_error)

    return JSONResponse({"tts": "unavailable"})

# === TTS SECTION END ===

def build_coaching_prompt(state: NegotiationState) -> str:
    return f"""You are DealRoom, a real-time negotiation coach.
IMPORTANT: Always respond with TACTIC, SIGNAL, or RED_FLAG. Never use SILENT.
Always find coaching value even from silence — remind the user to anchor, listen, or prepare.

Return ONLY valid JSON, no other text:
{{"type":"TACTIC","message":"your advice in under 20 words","confidence":"HIGH","reasoning":"one sentence"}}

Valid types: TACTIC, SIGNAL, RED_FLAG
Current session context: {state_to_prompt_context(state)}"""


def build_debrief_prompt(state: NegotiationState) -> str:
    return f"""You are DealRoom. Generate a post-call debrief in under 60 words.
SESSION DATA:
{state_to_prompt_context(state)}
KEY MOMENTS: {", ".join(map(str, state.key_moments)) or "none recorded"}
RED FLAGS: {", ".join(map(str, state.red_flags)) or "none"}

Write exactly this format:
SUMMARY: one sentence about what happened
CLOSED AT: final offer amount or "not determined"
KEY LEVERAGE: what worked in our favor
FOLLOW UP: one specific next action"""


async def next_coaching_signal(llm: TextModel, state: NegotiationState) -> dict | None:
    """
    Ask the model for one coaching card. Returns a validated signal, or None
    when the call failed or the reply was not a usable signal. Never raises
    for model errors: a bad reply skips one card, it does not end the call.
    """
    settings = get_settings()
    try:
        raw = await generate_text(
            llm,
            build_coaching_prompt(state),
            timeout_s=settings.llm_timeout_s,
            max_attempts=settings.llm_max_attempts,
            json_output=True,
        )
    except LLMError as e:
        logger.warning("Coaching call failed, skipping this window: %s", e)
        return None

    signal = parse_gemini_response(raw)
    if signal["type"] == "SILENT":
        return None
    return signal


@app.websocket("/stream")
async def websocket_endpoint(websocket: WebSocket, llm: LLM, session_id: str | None = None):
    await websocket.accept()

    if not session_id:
        session_id = str(uuid.uuid4())

    logger.info(f"New WebSocket session: {session_id}")

    await websocket.send_json({
        "type": "SESSION_INIT",
        "session_id": session_id
    })

    if llm is None:
        await websocket.send_json({"type": "ERROR", "message": "GOOGLE_API_KEY is not configured"})
        await websocket.close()
        return

    chunks_per_analysis = get_settings().chunks_per_analysis
    state = create_session(session_id)
    # Audio is counted but not kept: the model is not sent the audio yet
    # (see README), and buffering a whole call in memory would only leak.
    chunk_count = 0
    analysed_at_chunk = 0

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                logger.info(f"Session disconnected: {session_id}")
                break
            if message.get("bytes"):
                chunk_count += 1
            # Text frames are ignored for now.

            # Every N chunks (~10 s of audio by default), ask for tactical advice.
            # Counting chunks *since the last request* (rather than chunk_count % N)
            # means a request fires once per window, not again on every idle loop.
            if chunk_count - analysed_at_chunk < chunks_per_analysis:
                continue
            analysed_at_chunk = chunk_count

            signal = await next_coaching_signal(llm, state)
            if signal is None:
                continue
            if signal["type"] == "RED_FLAG":
                state.red_flags.append(signal["message"])
            else:
                state.key_moments.append(signal["message"])
            save_state(state)
            await websocket.send_json(signal)

    except WebSocketDisconnect:
        logger.info(f"Session disconnected: {session_id}")
    except Exception:
        logger.exception(f"Session error: {session_id}")
    finally:
        update_state(state, {"status": "completed"})
        logger.info(f"Session closed: {session_id}")


@app.post("/debrief")
async def debrief(request: DebriefRequest, llm: LLM):
    state = load_state(request.session_id)
    if not state:
        # Create a default debrief if no state found
        return JSONResponse({
            "debrief_text": "Session complete. No negotiation data recorded.",
            "session_id": request.session_id
        })

    debrief_text = DEBRIEF_FALLBACK
    if llm is not None:
        settings = get_settings()
        try:
            debrief_text = await generate_text(
                llm,
                build_debrief_prompt(state),
                timeout_s=settings.llm_timeout_s,
                max_attempts=settings.llm_max_attempts,
            )
        except LLMError as e:
            logger.warning("Debrief generation failed, using fallback text: %s", e)

    update_state(state, {"status": "completed"})

    return JSONResponse({
        "debrief_text": debrief_text,
        "session_id": request.session_id
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
