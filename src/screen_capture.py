# screen_capture.py
import asyncio
import base64
import io
import logging
import sys
from typing import AsyncGenerator
import pyautogui
from PIL import Image

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("screen_capture")

def capture_frame() -> str | None:
    """
    Takes a screenshot, resizes it to 1280x720, and encodes it as a base64 JPEG string.
    """
    try:
        # Capture screenshot
        screenshot = pyautogui.screenshot()
        
        # Convert to RGB (in case of RGBA) and resize
        resized_img = screenshot.convert("RGB").resize((1280, 720), Image.Resampling.LANCZOS)
        
        # Save to BytesIO buffer as JPEG
        buffer = io.BytesIO()
        resized_img.save(buffer, format="JPEG", quality=75)
        
        # Get byte data and encode to base64
        byte_data = buffer.getvalue()
        base64_str = base64.b64encode(byte_data).decode("utf-8")
        
        return base64_str
    except Exception as e:
        print(f"CAPTURE ERROR: {e}")
        return None

async def frame_generator(stop_event: asyncio.Event) -> AsyncGenerator[str, None]:
    """
    Asynchronously yields base64-encoded screenshots every 2 seconds.
    """
    loop = asyncio.get_event_loop()
    
    while not stop_event.is_set():
        # Execute synchronous pyautogui call in a separate thread to avoid blocking
        frame = await loop.run_in_executor(None, capture_frame)
        
        if not stop_event.is_set() and frame is not None:
            yield frame
        
        # Check stop event before waiting
        if stop_event.is_set():
            break
            
        await asyncio.sleep(2)

if __name__ == "__main__":
    async def main():
        stop_event = asyncio.Event()
        count = 0
        
        print("Starting screen capture for 10 seconds...")
        
        # Set a timer to stop the generator after 10 seconds
        async def stopper():
            await asyncio.sleep(10)
            stop_event.set()
        
        asyncio.create_task(stopper())
        
        try:
            async for frame in frame_generator(stop_event):
                count += 1
                # Print first 80 characters of the frame
                print(f"FRAME: {frame[:80]}...")
                if count >= 5: # Limit to 5 frames as per requirements
                    stop_event.set()
                    break
        except Exception as e:
            print(f"Error during execution: {e}")
        finally:
            print(f"TOTAL FRAMES: {count}")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nCapture stopped by user.")
        sys.exit(0)
