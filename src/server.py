# server.py
import os
import uuid
import logging
import asyncio
import json
import io
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
import uvicorn
from google import genai

try:
    from google.cloud import texttospeech
except Exception:
    texttospeech = None

try:
    from gtts import gTTS
except Exception:
    gTTS = None

# Import components from the DealRoom modules
from src.agent import get_live_config
from src.screen_capture import frame_generator
from src.negotiation_state import create_session, save_state, update_state, load_state, state_to_prompt_context
from src.context_merger import merge_and_send, parse_gemini_response

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dealroom_server")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    """
    print("DEALROOM SERVER STARTED")
    yield
    print("DEALROOM SERVER STOPPED")

app = FastAPI(lifespan=lifespan)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    import os
    overlay_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "overlay.html")
    with open(overlay_path, "r") as f:
        return f.read()

@app.get("/test_mic", response_class=HTMLResponse)
async def serve_test():
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "test_mic.html")) as f:
        return f.read()

@app.get("/health")
async def health_check():
    """
    Standard health check endpoint.
    """
    return JSONResponse(content={
        "status": "ok",
        "model": "gemini-2.0-flash-live-001",
        "version": "1.0.0"
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


def _gemini_generate_text(prompt: str, model: str = "gemini-2.5-flash") -> str:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not configured")

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(model=model, contents=prompt)

    text = getattr(response, "text", None)
    if text:
        return text.strip()

    # Fallback for SDK response variants where text is nested in candidates/parts.
    try:
        candidates = getattr(response, "candidates", []) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", []) if content else []
            for part in parts:
                part_text = getattr(part, "text", None)
                if part_text:
                    return part_text.strip()
    except Exception:
        pass

    raise RuntimeError("Gemini returned an empty response")


def _google_tts_synthesize(text: str, voice_name: str) -> bytes:
    if texttospeech is None:
        raise RuntimeError("google-cloud-texttospeech is not installed")

    gcp_project_id = os.environ["GCP_PROJECT_ID"]
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

@app.websocket("/stream")
async def websocket_endpoint(websocket: WebSocket, session_id: str = None):
    await websocket.accept()

    if not session_id:
        session_id = str(uuid.uuid4())

    logger.info(f"New WebSocket session: {session_id}")

    await websocket.send_json({
        "type": "SESSION_INIT",
        "session_id": session_id
    })

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        await websocket.send_json({"type": "ERROR", "message": "GOOGLE_API_KEY is not configured"})
        await websocket.close()
        return

    state = create_session(session_id)
    audio_chunks = []
    chunk_count = 0

    try:
        while True:
            # FIX 2: Handle both binary and text websocket payloads.
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=1.0)
                if message.get("type") == "websocket.receive":
                    if message.get("bytes"):
                        audio_chunks.append(message["bytes"])
                        chunk_count += 1
                    elif message.get("text"):
                        # Text message received, ignore for now
                        pass
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                break
            except Exception:
                break

            # Every 20 chunks (~10 seconds of audio), ask Gemini for tactical advice
            if chunk_count > 0 and chunk_count % 20 == 0:
                try:
                    prompt = f"""You are DealRoom, a real-time negotiation coach.
IMPORTANT: Always respond with TACTIC, SIGNAL, or RED_FLAG. Never use SILENT.
Always find coaching value even from silence — remind the user to anchor, listen, or prepare.

Return ONLY valid JSON, no other text:
{{"type":"TACTIC","message":"your advice in under 20 words","confidence":"HIGH","reasoning":"one sentence"}}

Valid types: TACTIC, SIGNAL, RED_FLAG
Current session context: {state_to_prompt_context(state)}"""

                    text = await asyncio.to_thread(
                        _gemini_generate_text,
                        prompt,
                        "gemini-2.5-flash",
                    )
                    # Strip markdown if present
                    if text.startswith("```"):
                        text = text.split("```")[1]
                        if text.startswith("json"):
                            text = text[4:]
                    text = text.strip()

                    try:
                        parsed = json.loads(text)
                    except json.JSONDecodeError:
                        parsed = {
                            "type": "SIGNAL",
                            "message": text[:100],
                            "confidence": "MEDIUM",
                            "reasoning": "raw response"
                        }

                    if parsed.get("type") != "SILENT":
                        # Update state based on response type
                        if parsed.get("type") == "RED_FLAG":
                            state.red_flags.append(parsed.get("message", ""))
                        else:
                            state.key_moments.append(parsed.get("message", ""))
                        save_state(state)
                        logger.info(f"WS state before send: {websocket.client_state}")
                        logger.info(f"Sending to overlay: {parsed}")
                        await websocket.send_json(parsed)

                except Exception as e:
                    logger.error(f"Gemini error: {e}")

    except WebSocketDisconnect:
        logger.info(f"Session disconnected: {session_id}")
    except Exception as e:
        logger.error(f"Session error: {e}")
    finally:
        update_state(state, {"status": "completed"})
        logger.info(f"Session closed: {session_id}")


@app.post("/debrief")
async def debrief(request: DebriefRequest):
    # FIX 1: Add /debrief endpoint for post-call summary generation.
    state = load_state(request.session_id)
    if not state:
        # Create a default debrief if no state found
        return JSONResponse({
            "debrief_text": "Session complete. No negotiation data recorded.",
            "session_id": request.session_id
        })

    api_key = os.environ.get("GOOGLE_API_KEY")

    prompt = f"""You are DealRoom. Generate a post-call debrief in under 60 words.
SESSION DATA:
{state_to_prompt_context(state)}
KEY MOMENTS: {", ".join(state.key_moments) or "none recorded"}
RED FLAGS: {", ".join(state.red_flags) or "none"}

Write exactly this format:
SUMMARY: one sentence about what happened
CLOSED AT: final offer amount or "not determined"
KEY LEVERAGE: what worked in our favor
FOLLOW UP: one specific next action"""

    try:
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY is not configured")
        debrief_text = await asyncio.to_thread(
            _gemini_generate_text,
            prompt,
            "gemini-2.5-flash",
        )
    except Exception:
        debrief_text = "Session complete. Review your notes for follow-up actions."

    update_state(state, {"status": "completed"})

    return JSONResponse({
        "debrief_text": debrief_text,
        "session_id": request.session_id
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
