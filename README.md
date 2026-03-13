# DealRoom 🎯
> Real-time negotiation intelligence agent powered by Gemini AI

DealRoom is a live AI copilot that listens to your sales calls and surfaces 
tactical advice, detects red flags, and delivers post-call debriefs — all 
in a floating overlay that stays out of your way.

## Demo
[Insert ngrok URL here]

## Features
- 🎙️ Real-time audio analysis via WebSocket
- 🧠 Gemini AI tactical coaching (TACTIC, SIGNAL, RED_FLAG alerts)  
- 🔊 Text-to-speech delivery of key insights
- 📋 Automated post-call debrief generation
- 🪟 Floating overlay UI — works over any video call

## Quick Start
```bash
git clone https://github.com/ayanabil/DealRoom
cd DealRoom
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
echo 'GOOGLE_API_KEY=your_key_here' > .env
uvicorn src.server:app --host 0.0.0.0 --port 8080
```

Open http://localhost:8080/overlay in your browser during any call.

## Architecture
- **Frontend**: Vanilla JS overlay (`static/overlay.html`) — captures mic, displays signals
- **Backend**: FastAPI + WebSocket server (`src/server.py`)
- **AI**: Google Gemini 2.0 Flash via generate_content API
- **TTS**: Google Cloud TTS with gTTS + macOS fallback
- **State**: Local JSON session store (session_store.json)

## Built For
Google Gemini Live Agent Challenge — March 2026
