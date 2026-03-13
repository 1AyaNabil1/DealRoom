import asyncio
import base64
import io
import os
import sys
import json
import logging
from PIL import Image

# Import DealRoom components
try:
    from screen_capture import frame_generator
    from negotiation_state import create_session, load_state, update_state, NegotiationState
    from context_merger import build_audio_part, build_vision_part, parse_gemini_response, merge_and_send
    from agent import connect_and_test, get_live_config
    from google import genai
except ImportError as e:
    print(f"IMPORT ERROR: {e}")
    sys.exit(1)

# Configure logging to be quiet during tests
logging.basicConfig(level=logging.ERROR)

async def run_tests():
    results = []

    # TEST 1 — SCREEN_CAPTURE
    print("RUNNING TEST 1: SCREEN_CAPTURE...")
    try:
        stop_event = asyncio.Event()
        frames = []
        
        async def capture_task():
            async for frame in frame_generator(stop_event):
                frames.append(frame)
                if len(frames) >= 3:
                    stop_event.set()
                    break
        
        # Run with timeout to prevent hanging if generator fails
        try:
            await asyncio.wait_for(capture_task(), timeout=10.0)
        except asyncio.TimeoutError:
            stop_event.set()

        assert len(frames) > 0, "No frames captured"
        for i, frame in enumerate(frames):
            assert isinstance(frame, str) and len(frame) > 0, f"Frame {i} is empty or not a string"
            decoded = base64.b64decode(frame)
            assert decoded.startswith(b'\xff\xd8\xff'), f"Frame {i} does not start with JPEG magic bytes"
        
        print("  PASS")
        results.append(("SCREEN_CAPTURE", True))
    except Exception as e:
        print(f"  FAIL")
        print(f"  REASON: {e}")
        results.append(("SCREEN_CAPTURE", False))

    # TEST 2 — NEGOTIATION_STATE
    print("RUNNING TEST 2: NEGOTIATION_STATE...")
    try:
        # Ensure GCP_PROJECT_ID is set for testing
        if "GCP_PROJECT_ID" not in os.environ:
            os.environ["GCP_PROJECT_ID"] = "dealroom-hackathon"
            
        session_id = "integration-test-001"
        create_session(session_id)
        update_state(NegotiationState(session_id=session_id), {"opening_ask": 200.0, "current_offer": 150.0})
        
        loaded = load_state(session_id)
        assert loaded is not None, "Failed to load state"
        assert loaded.opening_ask == 200.0, f"Expected opening_ask 200.0, got {loaded.opening_ask}"
        assert loaded.current_offer == 150.0, f"Expected current_offer 150.0, got {loaded.current_offer}"
        
        print("  PASS")
        results.append(("NEGOTIATION_STATE", True))
    except Exception as e:
        print(f"  FAIL")
        print(f"  REASON: {e}")
        results.append(("NEGOTIATION_STATE", False))

    # TEST 3 — CONTEXT_MERGER
    print("RUNNING TEST 3: CONTEXT_MERGER...")
    try:
        audio_input = build_audio_part(b"test")
        assert hasattr(audio_input, 'audio'), "audio_input should have audio"
        assert audio_input.audio.mime_type == "audio/pcm"
        
        vision_input = build_vision_part("abc")
        assert hasattr(vision_input, 'video'), "vision_input should have video"
        assert vision_input.video.mime_type == "image/jpeg"
        
        assert build_vision_part(None) is None
        assert build_vision_part("") is None
        
        tactic_json = '{"type":"TACTIC","message":"test","confidence":"HIGH","reasoning":"x"}'
        res1 = parse_gemini_response(tactic_json)
        assert res1["type"] == "TACTIC"
        
        res2 = parse_gemini_response("not json at all")
        assert res2["type"] == "SILENT"
        
        print("  PASS")
        results.append(("CONTEXT_MERGER", True))
    except Exception as e:
        print(f"  FAIL")
        print(f"  REASON: {e}")
        results.append(("CONTEXT_MERGER", False))

    # TEST 4 — GEMINI_LIVE_CONNECTION
    print("RUNNING TEST 4: GEMINI_LIVE_CONNECTION...")
    try:
        response = await connect_and_test()
        assert isinstance(response, str) and len(response) > 0, "Empty response from Gemini"
        print(f"  PASS: {response[:80]}")
        results.append(("GEMINI_LIVE_CONNECTION", True))
    except Exception as e:
        print(f"  FAIL")
        print(f"  REASON: {e}")
        results.append(("GEMINI_LIVE_CONNECTION", False))

    # TEST 5 — FULL_PIPELINE_MOCK
    print("RUNNING TEST 5: FULL_PIPELINE_MOCK...")
    try:
        # 1. Generate 1x1 white JPEG
        img = Image.new('RGB', (1, 1), color='white')
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        frame_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        
        # 2. Mock state
        mock_state = NegotiationState(session_id="mock-pipeline-test")
        
        # 3. Real Gemini Session
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not set")
            
        client = genai.Client(api_key=api_key, http_options={'api_version': 'v1beta'})
        
        async with client.aio.live.connect(model="gemini-2.0-flash-exp", config=get_live_config()) as session:
            # 4. Merge and Send
            result = await merge_and_send(session, b'\x00\x01' * 512, frame_base64, mock_state)
            assert result is not None, "Pipeline returned None"
            
            # 5. Parse and Assert
            parsed = parse_gemini_response(result)
            valid_types = ["TACTIC", "SIGNAL", "RED_FLAG", "DEBRIEF", "SILENT"]
            assert parsed["type"] in valid_types, f"Invalid response type: {parsed['type']}"
            
            print(f"  PASS: {json.dumps(parsed)}")
            results.append(("FULL_PIPELINE_MOCK", True))
            
    except Exception as e:
        print(f"  FAIL")
        print(f"  REASON: {e}")
        results.append(("FULL_PIPELINE_MOCK", False))

    # SUMMARY TABLE
    print("\nSUMMARY TABLE:")
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name:<30} | {status}")

    # Exit logic
    if all(r[1] for r in results):
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_tests())
