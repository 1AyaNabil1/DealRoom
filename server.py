# server.py
import os
import uuid
import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from google import genai

# Import components from the DealRoom modules
from agent import get_live_config
from screen_capture import frame_generator
from negotiation_state import create_session, update_state, save_state
from context_merger import merge_and_send, parse_gemini_response

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

@app.websocket("/stream")
async def websocket_endpoint(websocket: WebSocket, session_id: str = None):
    """
    WebSocket endpoint that receives audio bytes and yields negotiation tactics.
    """
    await websocket.accept()
    
    # Handle session_id
    if not session_id:
        session_id = str(uuid.uuid4())
    
    state = create_session(session_id)
    logger.info(f"New WebSocket session: {session_id}")
    
    # Send initialization message to client
    await websocket.send_json({"type": "SESSION_INIT", "session_id": session_id})
    
    stop_event = asyncio.Event()
    api_key = os.environ.get("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key, http_options={'api_version': 'v1alpha'})
    
    try:
        async with client.aio.live.connect(model="gemini-2.0-flash-live-001", config=get_live_config()) as session:
            # Initialize generators
            frame_iter = frame_generator(stop_event).__aiter__()
            
            while not stop_event.is_set():
                try:
                    # 1. Receive audio from WebSocket
                    audio_bytes = await websocket.receive_bytes()
                    
                    # 2. Try to get frame from screen_capture
                    try:
                        frame_base64 = await asyncio.wait_for(frame_iter.__anext__(), timeout=0.1)
                    except (asyncio.TimeoutError, StopAsyncIteration):
                        frame_base64 = None
                    
                    # 3. Process multimodal input
                    response_json = await merge_and_send(session, audio_bytes, frame_base64, state)
                    
                    if response_json:
                        parsed = parse_gemini_response(response_json)
                        
                        # Forward parsed response to WebSocket client
                        await websocket.send_json(parsed)
                        
                        # Update state and save if not silent
                        if parsed["type"] != "SILENT":
                            if parsed["type"] == "RED_FLAG":
                                state.red_flags.append(parsed["message"])
                            else:
                                state.key_moments.append(parsed["message"])
                            save_state(state)
                    
                    # Rate limit protection
                    await asyncio.sleep(0.5)
                    
                except WebSocketDisconnect:
                    logger.info(f"WebSocket disconnected: {session_id}")
                    break
                except Exception as e:
                    logger.error(f"Error in stream loop: {e}")
                    break
                    
    except Exception as e:
        logger.error(f"Internal server error in /stream: {e}")
    finally:
        stop_event.set()
        update_state(state, {"status": "completed"})
        try:
            await websocket.close()
        except:
            pass
        logger.info(f"Session closed: {session_id}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
