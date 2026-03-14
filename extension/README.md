# DealRoom Chrome Extension

## Files
- `manifest.json`: Chrome Extension (MV3) manifest.
- `overlay.html`: Popup UI.
- `overlay.js`: WebSocket, mic capture, signal rendering, TTS queue, and debrief logic.

## Load in Chrome (Unpacked)
1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select this folder: `extension/`.

## Connect to backend
- Default backend is `http://127.0.0.1:8080`.
- In the popup, edit the backend URL field and click **Save**.
- Keep your FastAPI server running before opening the popup.

## Notes
- Popup lifecycle: closing the popup will close the WebSocket and mic stream.
- Host permissions include localhost and common HTTPS/WSS targets; tighten in production.
