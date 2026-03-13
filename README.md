<div align="center">

# DealRoom
**Real-time AI negotiation copilot powered by Gemini 2.5 Flash**

![DealRoom Demo](demo.gif)
*The DealRoom overlay in action.*

</div>

## Overview
DealRoom is an unintrusive, real-time sales and negotiation assistant. It listens to your live calls, surfaces tactical advice, detects red flags, and delivers post-call debriefs—all within a clean, floating overlay that stays out of your way.

## Features
- **Real-time Tactical Advice**: Instant suggestions on what to say next to close the deal.
- **Red Flag Detection**: Automatic alerts for warning signs in the conversation (e.g., budget hesitation, competitor mentions).
- **Post-call Debriefs**: Comprehensive summaries and action items generated immediately after the call.
- **Unintrusive Floating UI**: A vanilla JS overlay that floats above your workspace without interrupting your flow.

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Create a `.env` file and add your Google Gemini API key:
```bash
echo 'GOOGLE_API_KEY=your_key' > .env
```

### 3. Run the Server
```bash
uvicorn server:app --host 0.0.0.0 --port 8080
```

### 4. Open the Overlay
Navigate to `http://localhost:8080/overlay` in your browser.

## Tech Stack
- **Backend**: FastAPI + WebSockets (`server.py`)
- **AI Brain**: Gemini 2.5 Flash
- **Frontend**: Vanilla JS floating overlay
- **Audio Fallback**: macOS TTS

## Judge Evidence (Google Cloud API Usage)
To make technical validation fast for judges, here are direct code links that demonstrate Google Cloud service/API usage:

- **Vertex AI endpoint call example**: https://github.com/1AyaNabil1/DealRoom/blob/main/src/gcp_vertex_demo.py
- **Google Cloud Text-to-Speech integration in backend**: https://github.com/1AyaNabil1/DealRoom/blob/main/src/server.py

The Vertex example includes a full endpoint prediction call path via `PredictionServiceClient`, request payload assembly, and endpoint resource formatting.

---
<div align="center">
  <p>Built for the Google Gemini Live Agent Challenge — March 2026</p>
  <p><em>Built by AyaNexus 🦢</em></p>
</div>
