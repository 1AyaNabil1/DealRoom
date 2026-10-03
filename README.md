<div align="center">

# DEALROOM
## Real-Time Negotiation Intelligence Agent
### Your silent AI copilot for every sales call

Gemini Live Agent Challenge | March 2026

[![test](https://github.com/1AyaNabil1/DealRoom/actions/workflows/test.yml/badge.svg)](https://github.com/1AyaNabil1/DealRoom/actions/workflows/test.yml)

![DealRoom overlay during a session](demo.gif)

</div>

DealRoom is a negotiation copilot built on Google Gemini. A small floating
overlay sits on screen during a sales call and shows short coaching cards,
labelled **TACTIC**, **SIGNAL** or **RED_FLAG**. TACTIC and RED_FLAG cards are
read aloud. When the call ends, DealRoom writes a short debrief from the cards
it recorded.

It was built for the Gemini Live Agent Challenge. Because it runs an LLM
during a live call, it treats model output as untrusted: every reply is
validated before it is shown or stored, model calls have timeouts and bounded
retries, and the app behaves predictably without an API key.

> **Current status.** The browser overlay streams microphone audio to the
> server, but the server **does not send that audio to the model yet**. About
> every 10 seconds of audio it asks Gemini for one card based on the session
> state, so the cards are general negotiation advice, not reactions to what
> was said on the call. The standalone CLI agent (`src/agent.py`) does stream
> microphone audio and screenshots to the Gemini Live API.

## How it works

There are two entry points: the web overlay with its API server, which is what
the demo shows, and a standalone command-line agent.

### Web overlay and API server (`src/server.py`)

```
Browser overlay (static/overlay.html, or the Chrome extension in extension/)
  │  microphone chunks (MediaRecorder, one every 500 ms) over WebSocket /stream
  ▼
FastAPI server
  1. counts audio chunks; every DEALROOM_CHUNKS_PER_ANALYSIS chunks (20, about 10 s)
     it asks Gemini (gemini-2.5-flash) for one coaching card
  2. src/llm.py            runs the call off the event loop, with a timeout and bounded retries
  3. src/context_merger.py validates the reply (CoachingSignal schema); invalid replies are dropped
  4. src/negotiation_state.py records the card (key moment or red flag) in a JSON session store
  ▼
Overlay shows the card and reads TACTIC/RED_FLAG cards aloud via POST /tts.
"End session" calls POST /debrief, which asks Gemini to summarise the recorded cards.
```

### CLI agent (`src/agent.py`)

This agent captures the local microphone (PyAudio, 16 kHz PCM) and a
screenshot every 2 seconds (PyAutoGUI), and sends them to a Gemini Live API
session together with the negotiation context. It prints each card in the
terminal. It uses the same validation and session store as the server.

### How model output is handled

- **Every reply is untrusted.** `parse_gemini_response()` finds the first JSON
  object in the reply, so code fences and extra prose are tolerated. It then
  validates the object against a strict schema: type, non-empty message,
  confidence and reasoning, with long text clipped. Anything invalid becomes
  `SILENT` and is logged. It is never shown to the user or saved to the
  session.
- Coaching calls ask Gemini for JSON output, and the reply is still validated.
- **Timeouts and retries.** Each call has a time limit
  (`DEALROOM_LLM_TIMEOUT_S`) and is tried at most `DEALROOM_LLM_MAX_ATTEMPTS`
  times, with exponential backoff. Only timeouts, HTTP 429, 5xx and network
  errors are retried; errors such as an invalid key fail at once.
- **Graceful degradation.** A failed coaching call skips one card and the
  call carries on. A failed debrief returns a fixed fallback text. A corrupt
  session store is moved aside to `<file>.corrupt`, and writes are atomic.
- The overlays display model text as plain text and never insert it as HTML.
- **Without `GOOGLE_API_KEY`** the server still starts and logs a warning:
  - `/health` reports `"llm_configured": false`;
  - `/stream` sends an `ERROR` message and closes, and the overlay shows the
    message instead of reconnecting;
  - `/debrief` returns the fallback text.

## Quick start

Requires Python 3.11 or newer (CI runs 3.11 and 3.13).

```bash
git clone https://github.com/1AyaNabil1/DealRoom.git
cd DealRoom
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then set GOOGLE_API_KEY (Google AI Studio key)
uvicorn src.server:app --host 127.0.0.1 --port 8080 --env-file .env
```

Open <http://localhost:8080/overlay> and allow microphone access. Use
<http://localhost:8080/health> to see which model is configured and whether a
key was found.

**Chrome extension (optional):** open `chrome://extensions`, enable Developer
mode, choose *Load unpacked* and select the `extension/` folder. The popup
connects to `http://127.0.0.1:8080` by default; you can change this in the
popup. See [extension/README.md](extension/README.md).

**CLI agent (optional):** PyAudio needs the PortAudio library.

```bash
brew install portaudio            # macOS; on Debian/Ubuntu: sudo apt-get install portaudio19-dev
pip install -r requirements-agent.txt
python -m src.agent               # needs GOOGLE_API_KEY in the environment
```

On macOS, the terminal also needs Microphone and Screen Recording
permissions.

## Configuration

All settings are environment variables; [.env.example](.env.example)
documents each one.

| Variable | Default | Purpose |
|---|---|---|
| `GOOGLE_API_KEY` | (none) | Gemini API key. Without it coaching is disabled (see above). |
| `DEALROOM_MODEL` | `gemini-2.5-flash` | Model for coaching cards and debriefs. |
| `DEALROOM_LIVE_MODEL` | `gemini-2.0-flash-live-001` | Live API model for the CLI agent. Live model names change; list yours with `python -m scripts.list_models`. |
| `DEALROOM_LLM_TIMEOUT_S` | `15` | Time limit per model call attempt, in seconds. |
| `DEALROOM_LLM_MAX_ATTEMPTS` | `2` | Total attempts per model call. |
| `DEALROOM_CHUNKS_PER_ANALYSIS` | `20` | Audio chunks (500 ms each) between coaching requests. |
| `DEALROOM_SESSION_FILE` | `session_store.json` | Path of the JSON session store. |
| `DEALROOM_CORS_ORIGINS` | `*` | Comma-separated allowed browser origins. |
| `GCP_PROJECT_ID` | (none) | Enables Google Cloud Text-to-Speech (also needs Application Default Credentials). |
| `GCP_LOCATION`, `VERTEX_ENDPOINT_ID` | `us-central1`, (none) | Only used by `src/gcp_vertex_demo.py`. |

## API

| Endpoint | Description |
|---|---|
| `GET /overlay` | The overlay UI. |
| `GET /health` | `status`, configured `model`, `llm_configured`, `version`. |
| `WS /stream?session_id=` | Binary audio chunks in; `SESSION_INIT`, `ERROR` and coaching cards (`{type, message, confidence, reasoning}`) out. |
| `POST /debrief` | `{"session_id": ...}` returns `{"debrief_text", "session_id"}`. |
| `POST /tts` | `{"text": ..., "voice": ...}` returns audio. Tries Google Cloud TTS, then gTTS, then macOS `say`; returns 503 if all fail. |
| `GET /tts/health` | Which TTS engine is working. |
| `GET /test_mic` | A minimal page for testing the microphone and WebSocket. |

## Tests

```bash
pip install -r requirements-dev.txt
ruff check .
pytest
```

The tests run offline. A `FakeLLM` replaces Gemini, through FastAPI
dependency overrides, and fake Live sessions stand in for the Live API. No
API keys or network access are needed, and CI (`.github/workflows/test.yml`)
runs the same commands on every push. The tests cover:

- **Output validation:** fenced or chatty JSON, null or non-string messages,
  unknown types, clipping.
- **Model calls:** timeout, retry and give-up behaviour, the retry policy per
  error type, and the Gemini adapter with a stubbed transport.
- **WebSocket loop:** one card per audio window; bad replies are dropped and
  the session continues; no extra model calls without new audio. Also covers
  debrief fallbacks and TTS fallbacks.
- **CLI agent:** what it sends to the Live API, including a check through the
  real `google-genai` session over a fake websocket that audio and frames
  reach the wire; screen frames keep flowing; only valid cards are stored.
- **Session store:** round-trips, recovery from a corrupt file, atomic writes.

`scripts/` also contains **manual** checks that call the real APIs and use
quota: `live_integration_check.py`, `verify_setup.py`, `list_models.py` and
`try_models.py`. Run them with `python -m scripts.<name>`.

## Deploying to Google Cloud

The repository includes deployment code for Cloud Run:

- `Dockerfile`: the API server image (no system packages needed).
- `scripts/setup_gcp.sh`: creates the project and enables the required APIs.
- `scripts/deploy.sh`: builds with Cloud Build and deploys to Cloud Run,
  reading `GOOGLE_API_KEY` from the Secret Manager secret `dealroom-api-key`.
- `scripts/verify_deployment.sh`: checks `/health` on the deployed service.
- `infra/main.tf`: Terraform for the APIs, the Cloud Run service and a
  Firestore database.

The scripts read `GCP_PROJECT_ID`, `GCP_REGION` and `SERVICE_NAME`; Terraform
takes `project_id`, `region` and `image` variables (or `TF_VAR_*`). Both
default to the original `dealroom-hackathon` project in `us-central1`.

## Limitations

- **The server does not analyse call audio** (see *Current status*). The
  offer fields in the session state (opening ask, current offer, clauses,
  leverage) are never filled in, so the coaching prompt always contains the
  same empty context. This is why the cards are generic.
- **The session store is a local JSON file.** It is rewritten on every save,
  is not shared between Cloud Run instances, and is lost when a container
  restarts, so a debrief can miss a session that ran on another instance.
  Terraform creates a Firestore database, but the code does not use it.
- **No authentication.** The deploy scripts make the Cloud Run service
  public (`--allow-unauthenticated`) and CORS allows every origin by default,
  so anyone with the URL can spend the API key's quota.
- **The live paths are tested offline only.** No real Gemini responses or
  Live API sessions are exercised by the test suite. The default Live model
  may be retired by Google; set `DEALROOM_LIVE_MODEL` if so.
- **TTS fallbacks have limits.** gTTS calls Google Translate's
  text-to-speech service over the internet, and the last fallback, `say`, only
  exists on macOS.
- **The Vertex AI demo is not part of the app.** `src/gcp_vertex_demo.py`
  shows a Vertex AI endpoint call for the hackathon's Google Cloud
  requirement; the app does not call it.

## Hackathon requirements

| Requirement | Where |
|---|---|
| Uses a Gemini model through the Google GenAI SDK | [src/llm.py](src/llm.py) and [src/server.py](src/server.py) (`generate_content`); [src/agent.py](src/agent.py) and [src/context_merger.py](src/context_merger.py) (Live API) |
| Uses a Google Cloud service | Cloud Text-to-Speech in [src/server.py](src/server.py); Vertex AI endpoint call in [src/gcp_vertex_demo.py](https://github.com/1AyaNabil1/DealRoom/blob/main/src/gcp_vertex_demo.py) |
| Deployment code | [Dockerfile](Dockerfile), [scripts/deploy.sh](scripts/deploy.sh), [infra/main.tf](infra/main.tf) |
| Reproducible spin-up | [Quick start](#quick-start) |

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md). Released under the [MIT License](LICENSE).

---
Built for the Gemini Live Agent Challenge.
