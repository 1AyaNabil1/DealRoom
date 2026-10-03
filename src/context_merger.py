# context_merger.py
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

def build_audio_part(audio_bytes: bytes) -> types.LiveClientRealtimeInput:
    """
    Returns the audio LiveClientRealtimeInput for Gemini Live API.
    """
    audio_blob = types.Blob(mime_type="audio/pcm", data=audio_bytes)
    return types.LiveClientRealtimeInput(audio=audio_blob)

def build_vision_part(base64_frame: str | None) -> types.LiveClientRealtimeInput | None:
    """
    Returns the vision LiveClientRealtimeInput if a frame is provided.
    """
    if not base64_frame:
        return None
    vision_blob = types.Blob(mime_type="image/jpeg", data=base64_frame)
    return types.LiveClientRealtimeInput(video=vision_blob)

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

async def merge_and_send(session, audio_bytes: bytes, frame_base64: str | None, state: NegotiationState) -> str | None:
    """
    Sends multimodal context to Gemini and returns the processed response text.
    """
    try:
        # 1. Send Audio
        await session.send(input=build_audio_part(audio_bytes))
        
        # 2. Send Vision (if available)
        vision_part = build_vision_part(frame_base64)
        if vision_part:
            await session.send(input=vision_part)
            
        # 3. Send Context Text with end_of_turn=True
        context_text = build_context_message(state)
        await session.send(input=context_text, end_of_turn=True)
        
        # 4. Receive Response
        response_text = ""
        async for message in session.receive():
            # Try direct text first
            if getattr(message, "text", None):
                response_text += message.text
                break
            # Try server_content path
            if getattr(message, "server_content", None):
                model_turn = getattr(message.server_content, "model_turn", None)
                if model_turn:
                    for part in getattr(model_turn, "parts", []):
                        if getattr(part, "text", None):
                            response_text += part.text
                # Stop reading when turn is complete
                if getattr(message.server_content, "turn_complete", False):
                    break

        # Validation happens in parse_gemini_response(); non-JSON replies are
        # dropped there rather than shown to the user as a SIGNAL.
        return response_text or None
            
    except Exception as e:
        print(f"MERGE ERROR: {e}")
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
