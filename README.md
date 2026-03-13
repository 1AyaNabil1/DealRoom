# DealRoom
> Real-time AI negotiation copilot powered by Gemini

## What it does
DealRoom listens to your live sales calls and surfaces tactical advice,
detects red flags, and delivers post-call debriefs, all in a floating 
overlay that stays out of your way.

## Quick Start
```python
pip install -r requirements.txt
echo 'GOOGLE_API_KEY=your_key' > .env
uvicorn server:app --host 0.0.0.0 --port 8080
Open: http://localhost:8080/overlay
```
## Stack
- FastAPI + WebSocket (server.py)
- Gemini 2.5 Flash (AI tactics)
- Vanilla JS floating overlay
- macOS TTS fallback

## Built for
Google Gemini Live Agent Challenge — March 2026



<div align="center">
  <p><em>Build by AyaNexus 🦢</em></p>
</div>
