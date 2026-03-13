<div align="center">

# DEALROOM
## Real-Time Negotiation Intelligence Agent
### Your silent AI copilot for every sales call

Gemini Live Agent Challenge | March 2026

![DealRoom Demo](demo.gif)

</div>

## Project Overview
- Project: DealRoom
- Tagline: Your silent AI copilot for every sales call
- Challenge: Gemini Live Agent Challenge
- Repository: https://github.com/1AyaNabil1/DealRoom

## Hackathon Requirement Coverage (Judge Checklist)
This section maps each mandatory requirement to concrete evidence in this repository.

1. Leverages a Gemini model
- Evidence: Google GenAI SDK usage in [src/agent.py](src/agent.py) and [src/context_merger.py](src/context_merger.py)
- Evidence: Gemini model usage with live session connect in [src/agent.py](src/agent.py)

2. Built with Google GenAI SDK or ADK
- Evidence: Google GenAI SDK imports and client/session usage in [src/agent.py](src/agent.py) and [src/context_merger.py](src/context_merger.py)

3. Uses at least one Google Cloud service
- Evidence: Google Cloud Text-to-Speech API integration in [src/server.py](src/server.py)
- Evidence: Vertex AI endpoint API call example in [src/gcp_vertex_demo.py](src/gcp_vertex_demo.py)
- Direct GitHub link (requirement option 2 proof): https://github.com/1AyaNabil1/DealRoom/blob/main/src/gcp_vertex_demo.py

4. Public code repository with reproducible spin-up instructions
- Evidence: This README Quick Start section

5. Google Cloud deployment proof
- Evidence (infrastructure and deployment code): [infra/main.tf](infra/main.tf), [Dockerfile](Dockerfile), [scripts/deploy.sh](scripts/deploy.sh)
- Requirement-compatible proof link to Google Cloud API usage code: https://github.com/1AyaNabil1/DealRoom/blob/main/src/gcp_vertex_demo.py

6. Architecture diagram
- Evidence: Architecture/data flow section below (and diagram image should be uploaded in Devpost media carousel)

## Text Description
DealRoom is a real-time negotiation copilot that runs as a floating overlay during sales calls. It captures microphone audio in short windows, sends context to an AI agent, classifies live signals (TACTIC, SIGNAL, RED_FLAG), and returns concise coaching cards. At session end, it generates a structured debrief and can read critical guidance aloud.

## Core Features
- Real-time tactical coaching cards over WebSocket
- Red-flag detection for risk moments
- Post-call debrief generation
- Text-to-speech playback with layered fallback
- Floating overlay UI that stays visible but non-blocking

## Technologies Used
- Backend: FastAPI + WebSocket + asyncio
- AI SDK: Google GenAI SDK
- Google Cloud APIs: Text-to-Speech, Vertex AI endpoint example
- Frontend: Vanilla JavaScript + MediaRecorder
- Deployment assets: Dockerfile + Terraform

## Quick Start (Spin-Up Instructions)
### 1. Install dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cat > .env << 'EOF'
GOOGLE_API_KEY=your_google_ai_studio_key
# Optional for Google Cloud TTS
GCP_PROJECT_ID=your_gcp_project_id
# Optional for Vertex endpoint demo
GCP_LOCATION=us-central1
VERTEX_ENDPOINT_ID=your_vertex_endpoint_id
EOF
```

### 3. Run backend
```bash
uvicorn src.server:app --host 0.0.0.0 --port 8080 --env-file .env
```

### 4. Open overlay
Go to http://localhost:8080/overlay and allow microphone access.

## Google Cloud API Proof (Code Links)
- Vertex AI endpoint call demo file: [src/gcp_vertex_demo.py](src/gcp_vertex_demo.py)
- Google Cloud TTS request flow: [src/server.py](src/server.py)
- Terraform enabling GCP services including Vertex AI and Cloud Run: [infra/main.tf](infra/main.tf)

## Architecture Summary
1. Browser overlay captures microphone chunks.
2. Chunks stream to FastAPI over WebSocket.
3. Backend sends contextual prompts to the AI engine and parses structured JSON responses.
4. Overlay renders TACTIC/SIGNAL/RED_FLAG cards.
5. TTS endpoint synthesizes key messages via Google Cloud TTS (with fallback path).
6. Debrief endpoint returns a compact post-session summary.

## Bonus Criteria Coverage
- Infrastructure as code: [infra/main.tf](infra/main.tf)
- Containerized deployment path: [Dockerfile](Dockerfile)
- Deployment script: [scripts/deploy.sh](scripts/deploy.sh)

---
Built for the Gemini Live Agent Challenge.
