# server.py
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Import the negotiation engine from agent.py
from agent import stream_negotiation

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dealroom")

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
        "model": "gemini-flash-latest",
        "version": "1.0.0"
    })

@app.websocket("/stream")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint that receives audio bytes and yields negotiation tactics.
    """
    await websocket.accept()
    logger.info("Client connected to /stream")

    async def audio_receiver():
        """
        Generator that receives binary frames from the WebSocket.
        """
        try:
            while True:
                data = await websocket.receive_bytes()
                yield data
        except WebSocketDisconnect:
            logger.info("Client disconnected from /stream")
        except Exception as e:
            logger.error(f"Error receiving audio: {e}")

    try:
        # Pipe the audio receiver generator into the Gemini negotiation engine
        async for tactic_text in stream_negotiation(audio_receiver()):
            # Parse response text into the required signal format
            # In a production scenario, you might add logic here to categorize the text.
            # For now, we wrap the model output as a TACTIC with HIGH confidence.
            payload = {
                "type": "TACTIC",
                "message": tactic_text,
                "confidence": "HIGH"
            }
            await websocket.send_json(payload)
            
    except Exception as e:
        logger.error(f"Internal server error in /stream: {e}")
    finally:
        try:
            await websocket.close()
        except:
            pass

if __name__ == "__main__":
    # Fetch port from environment variable, default to 8080 for Cloud Run
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
