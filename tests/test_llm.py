import asyncio
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors

from src.llm import GeminiTextModel, LLMError, extract_text, generate_text, is_retryable
from tests.fakes import FakeLLM


def run(coro):
    return asyncio.run(coro)


def test_returns_model_text():
    llm = FakeLLM("hello")
    assert run(generate_text(llm, "p", timeout_s=1, json_output=True)) == "hello"
    assert llm.prompts == ["p"]
    assert llm.json_flags == [True]


def test_retries_a_transient_failure_then_succeeds():
    llm = FakeLLM(httpx.ConnectError("reset"), "ok")
    assert run(generate_text(llm, "p", timeout_s=1, max_attempts=2, backoff_s=0)) == "ok"
    assert llm.calls == 2


def test_hung_call_times_out_and_is_retried_then_gives_up():
    llm = FakeLLM("too late", delay_s=0.3)
    with pytest.raises(LLMError, match="timed out"):
        run(generate_text(llm, "p", timeout_s=0.05, max_attempts=2, backoff_s=0))
    assert llm.calls == 2


def test_non_retryable_error_fails_fast():
    llm = FakeLLM(ValueError("bad request"), "never reached")
    with pytest.raises(LLMError, match="after 1 attempt"):
        run(generate_text(llm, "p", timeout_s=1, max_attempts=3, backoff_s=0))
    assert llm.calls == 1


def test_gives_up_after_max_attempts():
    llm = FakeLLM(errors.ServerError(503, {"error": {"message": "overloaded"}}))
    with pytest.raises(LLMError, match="after 3 attempt"):
        run(generate_text(llm, "p", timeout_s=1, max_attempts=3, backoff_s=0))
    assert llm.calls == 3


@pytest.mark.parametrize("exc, expected", [
    (TimeoutError(), True),
    (asyncio.TimeoutError(), True),
    (httpx.ReadTimeout("slow"), True),
    (errors.ClientError(429, {"error": {"message": "quota"}}), True),
    (errors.ServerError(500, {"error": {"message": "boom"}}), True),
    (errors.ClientError(400, {"error": {"message": "bad"}}), False),
    (errors.ClientError(403, {"error": {"message": "bad key"}}), False),
    (LLMError("empty"), False),
    (ValueError("x"), False),
])
def test_retry_policy(exc, expected):
    assert is_retryable(exc) is expected


def test_extract_text_handles_sdk_response_shapes():
    assert extract_text(SimpleNamespace(text="  hi  ")) == "hi"
    nested = SimpleNamespace(text=None, candidates=[
        SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(text=None), SimpleNamespace(text="deep")]))
    ])
    assert extract_text(nested) == "deep"
    assert extract_text(SimpleNamespace(text=None, candidates=None)) == ""


def _gemini_with_fake_transport(reply):
    """The real adapter, constructed offline, with the HTTP call replaced."""
    model = GeminiTextModel(api_key="not-a-real-key", model="gemini-test", timeout_s=2)
    calls = []

    def generate_content(**kwargs):
        calls.append(kwargs)
        return reply

    model._client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    return model, calls


def test_gemini_adapter_requests_json_when_asked():
    model, calls = _gemini_with_fake_transport(SimpleNamespace(text='{"type":"TACTIC"}'))
    assert model.generate("p", json_output=True) == '{"type":"TACTIC"}'
    assert calls[0]["model"] == "gemini-test"
    assert calls[0]["config"].response_mime_type == "application/json"

    model.generate("p")
    assert calls[1]["config"] is None


def test_gemini_adapter_rejects_empty_reply():
    model, _ = _gemini_with_fake_transport(SimpleNamespace(text="", candidates=[]))
    with pytest.raises(LLMError, match="empty"):
        model.generate("p")
