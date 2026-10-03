# context_merger.py
import asyncio
import json
import logging
from typing import Literal

from google.genai import types
from pydantic import BaseModel, ValidationError, field_validator

from src.negotiation_state import NegotiationState, state_to_prompt_context

logger = logging.getLogger("context_merger")

SIGNAL_TYPES = ("TACTIC", "SIGNAL", "RED_FLAG", "DEBRIEF", "SILENT")
CONFIDENCE_LEVELS = ("HIGH", "MEDIUM", "LOW")
MAX_MESSAGE_CHARS = 300
MAX_REASONING_CHARS = 500
# Model replies are short; never scan an unbounded string for JSON.
MAX_RESPONSE_CHARS = 20_000
# The CLI agent records 16 kHz, 16-bit mono PCM (see src/agent.py).
AUDIO_MIME_TYPE = "audio/pcm;rate=16000"

def build_audio_part(audio_bytes: bytes) -> types.Blob:
    """
    Returns the raw PCM audio chunk as a Blob for send_realtime_input(audio=...).
    """
    return types.Blob(mime_type=AUDIO_MIME_TYPE, data=audio_bytes)

def build_vision_part(base64_frame: str | None) -> types.Blob | None:
    """
    Returns the base64 JPEG frame as a Blob for send_realtime_input(video=...),
    or None if there is no frame.
    """
    if not base64_frame:
        return None
    # The SDK decodes a base64 string into bytes for Blob.data.
    return types.Blob(mime_type="image/jpeg", data=base64_frame)

def build_context_message(state: NegotiationState) -> str:
    """
    Constructs the structured context message for Gemini.
    """
    context_str = state_to_prompt_context(state)
    return (
        f"CURRENT NEGOTIATION CONTEXT:\n"
        f"{context_str}\n\n"
        f"Analyze the audio and screen above. Respond only if you have genuine "
        f"tactical value. Return valid JSON only, no other text."
    )

async def _collect_turn_text(session) -> str:
    """Reads the model's whole turn: text can arrive split over several messages."""
    response_text = ""
    async for message in session.receive():
        text = getattr(message, "text", None)
        if text:
            response_text += text
        server_content = getattr(message, "server_content", None)
        if server_content is not None and getattr(server_content, "turn_complete", False):
            break
    return response_text

async def merge_and_send(session, audio_bytes: bytes, frame_base64: str | None, state: NegotiationState,
                         timeout_s: float = 15.0) -> str | None:
    """
    Sends one audio chunk, an optional screen frame and the negotiation context
    to a Gemini Live session and returns the model's raw reply text.

    Returns None on any error or timeout, so one bad turn never ends the call.
    """
    try:
        # Media must go through send_realtime_input(). The deprecated
        # session.send(input=LiveClientRealtimeInput(audio=..., video=...))
        # only forwards the media_chunks field, so the audio and screen frames
        # were silently dropped and the model only ever saw the text context.
        await session.send_realtime_input(audio=build_audio_part(audio_bytes))

        vision_part = build_vision_part(frame_base64)
        if vision_part is not None:
            await session.send_realtime_input(video=vision_part)

        await session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text=build_context_message(state))]),
            turn_complete=True,
        )

        # Previously the first text fragment ended the read, which truncated
        # multi-part JSON replies and left the rest of the turn to be misread
        # as the answer to the next one.
        response_text = await asyncio.wait_for(_collect_turn_text(session), timeout=timeout_s)

        # Validation happens in parse_gemini_response(); non-JSON replies are
        # dropped there rather than shown to the user as a SIGNAL.
        return response_text or None

    except (TimeoutError, asyncio.TimeoutError):
        logger.warning("No complete reply from the Live API within %.0fs", timeout_s)
        return None
    except Exception as e:
        logger.error("MERGE ERROR: %s", e)
        return None

class CoachingSignal(BaseModel):
    """The only shape of model output that is allowed to reach the user."""

    type: Literal["TACTIC", "SIGNAL", "RED_FLAG", "DEBRIEF", "SILENT"]
    message: str = ""
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    reasoning: str = ""

    @field_validator("type", mode="before")
    @classmethod
    def _normalise_type(cls, value):
        if not isinstance(value, str):
            raise ValueError("type must be a string")
        value = value.strip().upper()
        # Unknown labels are still advice; show them as a generic SIGNAL.
        return value if value in SIGNAL_TYPES else "SIGNAL"

    @field_validator("confidence", mode="before")
    @classmethod
    def _normalise_confidence(cls, value):
        value = value.strip().upper() if isinstance(value, str) else ""
        return value if value in CONFIDENCE_LEVELS else "MEDIUM"

    @field_validator("message", mode="before")
    @classmethod
    def _clip_message(cls, value):
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError("message must be a string")
        return value.strip()[:MAX_MESSAGE_CHARS]

    @field_validator("reasoning", mode="before")
    @classmethod
    def _clip_reasoning(cls, value):
        return value.strip()[:MAX_REASONING_CHARS] if isinstance(value, str) else ""


def _silent(reason: str) -> dict:
    return {"type": "SILENT", "message": "", "confidence": "LOW", "reasoning": reason}


def extract_json_object(text: str) -> dict | None:
    """
    Returns the first JSON object in a model reply, or None.

    Models often wrap JSON in ```json fences or add a sentence before or
    after it, so this scans for the first decodable object instead of
    requiring the whole reply to be JSON.
    """
    text = text.strip()[:MAX_RESPONSE_CHARS]
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            obj, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict):
            return obj
        start = text.find("{", start + 1)
    return None


def parse_gemini_response(response_text: str) -> dict:
    """
    Parses and validates a model reply into a coaching signal.

    Always returns a dict with exactly the keys type, message, confidence
    and reasoning. Anything that is not a valid signal (prose, malformed
    JSON, missing or non-string message, ...) becomes SILENT, so raw or
    malformed model output is never shown to the user and never stored in
    the negotiation state.
    """
    if not isinstance(response_text, str) or not response_text.strip():
        return _silent("empty response")

    data = extract_json_object(response_text)
    if data is None:
        logger.warning("Model reply contained no JSON object: %.120r", response_text)
        return _silent("parse error")

    try:
        signal = CoachingSignal.model_validate(data)
    except ValidationError as e:
        logger.warning("Model reply failed validation (%s errors): %.120r", e.error_count(), response_text)
        return _silent("parse error")

    if signal.type == "SILENT":
        return _silent("")
    if not signal.message:
        logger.warning("Model reply had an empty message: %.120r", response_text)
        return _silent("parse error")
    return signal.model_dump()

if __name__ == "__main__":
    # Test block
    mock_state = NegotiationState(
        session_id="test",
        opening_ask=150.0,
        current_offer=105.0
    )
    
    # 1. Test build_context_message
    context = build_context_message(mock_state)
    print("--- CONTEXT MESSAGE ---")
    print(context)
    
    # 2. Test parse_gemini_response (Valid)
    valid_json = '{"type": "TACTIC", "message": "Push for a bulk discount.", "confidence": "HIGH"}'
    parsed_valid = parse_gemini_response(valid_json)
    assert parsed_valid["type"] == "TACTIC"
    print("\nValid JSON parsed successfully.")
    
    # 3. Test parse_gemini_response (Invalid)
    invalid_json = "This is not JSON at all."
    parsed_invalid = parse_gemini_response(invalid_json)
    assert parsed_invalid["type"] == "SILENT"
    print("Invalid JSON handled correctly (SILENT).")
    
    print("\nTEST PASSED")
