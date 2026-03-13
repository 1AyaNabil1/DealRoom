# context_merger.py
import json
import logging
from typing import Optional
from google.genai import types
from src.negotiation_state import NegotiationState, state_to_prompt_context

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("context_merger")

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

        if not response_text:
            return None
            
        # Validate if it's JSON
        try:
            json.loads(response_text)
            return response_text
        except json.JSONDecodeError:
            # Wrap non-JSON response as required
            wrapped = {
                "type": "SIGNAL",
                "message": response_text[:100],
                "confidence": "MEDIUM",
                "reasoning": response_text
            }
            return json.dumps(wrapped)
            
    except Exception as e:
        print(f"MERGE ERROR: {e}")
        return None

def parse_gemini_response(response_text: str) -> dict:
    """
    Parses and validates the JSON response from Gemini.
    """
    default_error = {"type": "SILENT", "message": "", "confidence": "LOW", "reasoning": "parse error"}
    
    try:
        data = json.loads(response_text)
        
        # Validate schema
        if not isinstance(data, dict) or "type" not in data or "message" not in data:
            return default_error
            
        # Validate type
        valid_types = ["TACTIC", "SIGNAL", "RED_FLAG", "DEBRIEF", "SILENT"]
        if data["type"] not in valid_types:
            data["type"] = "SIGNAL"
            
        return data
        
    except json.JSONDecodeError:
        return default_error
    except Exception:
        return default_error

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
