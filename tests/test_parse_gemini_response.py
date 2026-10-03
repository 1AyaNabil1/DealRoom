"""Model output is untrusted: every reply must become a valid signal or SILENT."""
import pytest

from src.context_merger import MAX_MESSAGE_CHARS, extract_json_object, parse_gemini_response

KEYS = {"type", "message", "confidence", "reasoning"}


def test_valid_signal_passes_through():
    raw = '{"type":"TACTIC","message":"Anchor high.","confidence":"HIGH","reasoning":"They asked first."}'
    assert parse_gemini_response(raw) == {
        "type": "TACTIC",
        "message": "Anchor high.",
        "confidence": "HIGH",
        "reasoning": "They asked first.",
    }


@pytest.mark.parametrize("raw", [
    '```json\n{"type":"RED_FLAG","message":"Budget freeze mentioned"}\n```',
    'Here is my advice: {"type":"RED_FLAG","message":"Budget freeze mentioned"} Hope it helps!',
    '{bad json} {"type":"RED_FLAG","message":"Budget freeze mentioned"}',
])
def test_json_is_found_inside_fences_and_prose(raw):
    parsed = parse_gemini_response(raw)
    assert parsed["type"] == "RED_FLAG"
    assert parsed["message"] == "Budget freeze mentioned"


@pytest.mark.parametrize("raw", [
    None,
    "",
    "   ",
    "This is not JSON at all.",
    '{"type": "TACTIC", "message": "unterminated',
    "[1, 2, 3]",
    '"just a string"',
    '{"message": "no type"}',
    '{"type": "TACTIC"}',
    '{"type": "TACTIC", "message": ""}',
    '{"type": "TACTIC", "message": "   "}',
    '{"type": "TACTIC", "message": null}',
    '{"type": "TACTIC", "message": 42}',
    '{"type": "TACTIC", "message": ["a", "b"]}',
    '{"type": 7, "message": "x"}',
])
def test_invalid_output_becomes_silent(raw):
    parsed = parse_gemini_response(raw)
    assert set(parsed) == KEYS
    assert parsed["type"] == "SILENT"
    assert parsed["message"] == ""


def test_explicit_silent_is_respected():
    parsed = parse_gemini_response('{"type": "SILENT"}')
    assert parsed["type"] == "SILENT"


def test_unknown_type_is_shown_as_generic_signal():
    assert parse_gemini_response('{"type": "ADVICE", "message": "x"}')["type"] == "SIGNAL"


def test_type_and_confidence_are_normalised():
    parsed = parse_gemini_response('{"type": " red_flag ", "message": "x", "confidence": "high"}')
    assert parsed["type"] == "RED_FLAG"
    assert parsed["confidence"] == "HIGH"


@pytest.mark.parametrize("confidence", [None, "", "certain", 0.9])
def test_bad_confidence_defaults_to_medium(confidence):
    import json
    raw = json.dumps({"type": "TACTIC", "message": "x", "confidence": confidence})
    assert parse_gemini_response(raw)["confidence"] == "MEDIUM"


def test_extra_keys_are_dropped_and_missing_ones_filled():
    parsed = parse_gemini_response('{"type": "SIGNAL", "message": "x", "html": "<script>"}')
    assert set(parsed) == KEYS
    assert parsed["reasoning"] == ""


def test_overlong_message_is_clipped():
    raw = '{"type": "TACTIC", "message": "%s"}' % ("a" * 5000)
    assert len(parse_gemini_response(raw)["message"]) == MAX_MESSAGE_CHARS


def test_non_string_reasoning_is_discarded():
    parsed = parse_gemini_response('{"type": "TACTIC", "message": "x", "reasoning": {"a": 1}}')
    assert parsed["reasoning"] == ""


def test_extract_json_object_returns_none_without_object():
    assert extract_json_object("no braces here") is None
    assert extract_json_object("{ not json }") is None
