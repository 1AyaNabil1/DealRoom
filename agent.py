# agent.py
import asyncio
import os
import sys
import traceback
import uuid
import argparse
from typing import AsyncGenerator
import pyaudio
from google import genai
from google.genai import types

# Import from other DealRoom modules
from screen_capture import frame_generator
from negotiation_state import NegotiationState, create_session, update_state, save_state
from context_merger import merge_and_send, parse_gemini_response

# Audio Configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024

# Global stop event
stop_event = asyncio.Event()

def get_live_config():
    from google.genai import types
    return types.LiveConnectConfig(
        response_modalities=["TEXT"],
        system_instruction=types.Content(
            parts=[types.Part(text="""You are DealRoom, a silent real-time negotiation 
intelligence agent. Respond only when you have genuine tactical value. 
Keep every response under 25 words. Return valid JSON only in this format:
{"type":"TACTIC","message":"text","confidence":"HIGH","reasoning":"one sentence"}
Valid types: TACTIC, SIGNAL, RED_FLAG, DEBRIEF, SILENT
If nothing useful to say return {"type":"SILENT"}""")],
            role="user"
        )
    )

async def stream_microphone() -> AsyncGenerator[bytes, None]:
    """
    Opens a PyAudio stream and yields CHUNK-sized byte buffers continuously.
    """
    pa = pyaudio.PyAudio()
    stream = None
    try:
        stream = pa.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK
        )
    except pyaudio.PyAudioException as e:
        print(f"PyAudio Exception: {e}")
        print("\nAvailable input devices:")
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info.get('maxInputChannels') > 0:
                print(f"Device {i}: {info.get('name')}")
        pa.terminate()
        raise

    try:
        while not stop_event.is_set():
            data = stream.read(CHUNK, exception_on_overflow=False)
            yield data
            await asyncio.sleep(0)
    finally:
        if stream:
            stream.stop_stream()
            stream.close()
        pa.terminate()

async def run_dealroom_session(session_id: str = None) -> None:
    """
    Runs the complete DealRoom multimodal pipeline.
    """
    if session_id is None:
        session_id = str(uuid.uuid4())
    
    state = create_session(session_id)
    print(f"SESSION STARTED: {session_id}")
    
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable is not set.")

    client = genai.Client(api_key=api_key, http_options={'api_version': 'v1alpha'})
    
    try:
        async with client.aio.live.connect(model="gemini-2.0-flash-live-001", config=get_live_config()) as session:
            frame_iter = frame_generator(stop_event).__aiter__()
            audio_iter = stream_microphone().__aiter__()
            
            while not stop_event.is_set():
                try:
                    # Fetch next audio chunk
                    audio_bytes = await audio_iter.__anext__()
                    
                    # Try to get frame with 0.1s timeout
                    try:
                        frame_base64 = await asyncio.wait_for(frame_iter.__anext__(), timeout=0.1)
                    except (asyncio.TimeoutError, StopAsyncIteration):
                        frame_base64 = None
                    
                    # Merge and send to Gemini
                    response_json = await merge_and_send(session, audio_bytes, frame_base64, state)
                    
                    if response_json:
                        parsed = parse_gemini_response(response_json)
                        if parsed["type"] != "SILENT":
                            print(f"[{parsed['type']}] {parsed['message']} ({parsed['confidence']})")
                            
                            # Update state lists based on response type
                            if parsed["type"] == "RED_FLAG":
                                state.red_flags.append(parsed["message"])
                            else:
                                state.key_moments.append(parsed["message"])
                            
                            save_state(state)
                    
                    # Rate limit protection
                    await asyncio.sleep(0.5)
                    
                except StopAsyncIteration:
                    break
                except Exception as e:
                    print(f"LOOP ERROR: {e}")
                    await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("\nSESSION ENDED")
    except Exception as e:
        print(f"SESSION FATAL ERROR: {e}")
    finally:
        stop_event.set()
        update_state(state, {"status": "completed"})
        print(f"SESSION {session_id} CLOSED")

async def connect_and_test() -> str:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not set")
    client = genai.Client(api_key=api_key, http_options={'api_version': 'v1alpha'})
    model = "gemini-2.0-flash-live-001"
    async with client.aio.live.connect(model=model, config=get_live_config()) as session:
        await session.send(input="Hello, confirm you are connected.", end_of_turn=True)
        async for message in session.receive():
            if getattr(message, "text", None):
                return message.text
            if getattr(message, "server_content", None):
                model_turn = getattr(message.server_content, "model_turn", None)
                if model_turn:
                    for part in getattr(model_turn, "parts", []):
                        if getattr(part, "text", None):
                            return part.text
                if getattr(message.server_content, "turn_complete", False):
                    break
    return "CONNECTED"

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DealRoom Multimodal Agent")
    parser.add_argument("--session-id", type=str, help="Optional session ID to resume or use")
    args = parser.parse_args()

    try:
        asyncio.run(run_dealroom_session(session_id=args.session_id))
    except KeyboardInterrupt:
        print("\nGoodbye")
        sys.exit(0)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
