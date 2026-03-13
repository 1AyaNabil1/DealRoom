# agent.py
import asyncio
import os
import sys
import traceback
from typing import AsyncGenerator
import pyaudio
from google import genai
from google.genai import types

# Audio Configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024

# Global stop event for the microphone stream
stop_event = asyncio.Event()

def get_live_config() -> types.LiveConnectConfig:
    """
    Returns a fully configured LiveConnectConfig object for the DealRoom agent.
    """
    system_instruction = (
        "You are DealRoom, a silent real-time negotiation intelligence agent. "
        "Respond only when you have genuine tactical value. Keep every response under 25 words. "
        "Never hallucinate numbers — only reference what you have heard or seen in this session."
    )
    
    return types.LiveConnectConfig(
        system_instruction=types.Content(
            parts=[types.Part(text=system_instruction)]
        ),
        generation_config=types.GenerationConfig(
            response_modalities=["TEXT"]
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
            # Read audio data from the microphone.
            # exception_on_overflow=False handles minor buffering delays.
            data = stream.read(CHUNK, exception_on_overflow=False)
            yield data
            # Yield control back to the event loop.
            await asyncio.sleep(0)
    finally:
        if stream:
            stream.stop_stream()
            stream.close()
        pa.terminate()

async def stream_negotiation(audio_stream: AsyncGenerator) -> AsyncGenerator[str, None]:
    """
    Manages a Gemini Live API session, piping audio in and yielding text out.
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable is not set.")

    client = genai.Client(api_key=api_key, http_options={'api_version': 'v1alpha'})
    config = get_live_config()
    model_id = "gemini-flash-latest"

    try:
        async with client.aio.live.connect(model=model_id, config=config) as session:
            # We use a concurrent task to iterate over the audio_stream
            # and send chunks using await session.send().
            async def sender():
                try:
                    async for chunk in audio_stream:
                        await session.send(input={"data": chunk, "mime_type": "audio/pcm"})
                except Exception as e:
                    print(f"Audio sender error: {e}")

            sender_task = asyncio.create_task(sender())

            try:
                # Await session.receive() stream to extract response text.
                async for message in session.receive():
                    if message.server_content and message.server_content.model_turn:
                        parts = message.server_content.model_turn.parts
                        if parts:
                            for part in parts:
                                if part.text:
                                    yield part.text
            except Exception as e:
                print(f"Session disconnected or failed: {e}")
            finally:
                # Cleanup the sender task.
                sender_task.cancel()
                try:
                    await sender_task
                except asyncio.CancelledError:
                    pass
    except Exception as e:
        print(f"Gemini Live API connection error: {e}")

async def run_audio_test(duration_seconds: int = 10):
    """
    Pipes microphone audio to Gemini and prints responses for a set duration.
    """
    async def process():
        async for text in stream_negotiation(stream_microphone()):
            print(f"GEMINI: {text}", end="", flush=True)

    try:
        print(f"Streaming negotiation for {duration_seconds} seconds...")
        await asyncio.wait_for(process(), timeout=duration_seconds)
    except asyncio.TimeoutError:
        print(f"\nTime limit reached ({duration_seconds}s). Stopping...")
    finally:
        stop_event.set()

async def connect_and_test() -> str:
    """
    Legacy test function for connection check.
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable is not set.")

    client = genai.Client(api_key=api_key, http_options={'api_version': 'v1alpha'})
    config = get_live_config()
    model_id = "gemini-flash-latest"
    response_text = ""

    try:
        async with client.aio.live.connect(model=model_id, config=config) as session:
            await session.send("Hello, confirm connection and readiness.", end_of_turn=True)
            async for message in session.receive():
                if message.server_content and message.server_content.model_turn:
                    parts = message.server_content.model_turn.parts
                    if parts:
                        for part in parts:
                            if part.text:
                                response_text += part.text
                    if message.server_content.turn_complete:
                        break
    except Exception as e:
        print(f"Exception during Live API session: {type(e).__name__}: {str(e)}")
        raise

    return response_text

if __name__ == "__main__":
    try:
        # Running the real-time audio test
        asyncio.run(run_audio_test(10))
    except KeyboardInterrupt:
        print("\nStreaming stopped.")
        sys.exit(0)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
