"""Text-model access for the server: timeouts, bounded retries, clear errors.

The server only needs "prompt in, text out". Keeping that behind the small
TextModel interface gives one place for reliability policy and lets the
tests use a fake model instead of calling Gemini.
"""
from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import Protocol

logger = logging.getLogger("dealroom.llm")

# Rate limits and server-side failures are worth retrying; 4xx errors such
# as an invalid key or unknown model are not.
RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})
# asyncio.TimeoutError only became an alias of TimeoutError in Python 3.11.
_TIMEOUT_ERRORS = (TimeoutError, asyncio.TimeoutError)


class LLMError(RuntimeError):
    """The model could not produce a usable reply."""


class TextModel(Protocol):
    name: str

    def generate(self, prompt: str, *, json_output: bool = False) -> str:
        """Blocking call that returns the model's text reply."""
        ...


def extract_text(response) -> str:
    """Return the text of a generate_content response, or "" if there is none."""
    text = getattr(response, "text", None)
    if text:
        return text.strip()

    # Fallback for SDK response variants where text is nested in candidates/parts.
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            part_text = getattr(part, "text", None)
            if part_text:
                return part_text.strip()
    return ""


class GeminiTextModel:
    """Gemini via the google-genai SDK, with a per-request HTTP timeout."""

    def __init__(self, api_key: str, model: str, timeout_s: float):
        from google import genai
        from google.genai import types

        self.name = model
        self._types = types
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(timeout_s * 1000)),
        )

    def generate(self, prompt: str, *, json_output: bool = False) -> str:
        config = None
        if json_output:
            # Ask Gemini for JSON directly; the reply is still validated.
            config = self._types.GenerateContentConfig(response_mime_type="application/json")
        response = self._client.models.generate_content(model=self.name, contents=prompt, config=config)
        text = extract_text(response)
        if not text:
            raise LLMError("Gemini returned an empty response")
        return text


@lru_cache(maxsize=4)
def gemini_model(api_key: str, model: str, timeout_s: float) -> GeminiTextModel:
    """Reuse one client (and its connection pool) per configuration."""
    return GeminiTextModel(api_key, model, timeout_s)


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, _TIMEOUT_ERRORS):
        return True
    try:
        from google.genai import errors
    except ImportError:  # pragma: no cover - google-genai is a hard dependency
        errors = None
    if errors is not None and isinstance(exc, errors.APIError):
        return exc.code in RETRYABLE_STATUS_CODES
    try:
        import httpx
    except ImportError:  # pragma: no cover
        return False
    return isinstance(exc, httpx.TransportError)


async def generate_text(
    model: TextModel,
    prompt: str,
    *,
    timeout_s: float,
    max_attempts: int = 2,
    backoff_s: float = 0.5,
    json_output: bool = False,
) -> str:
    """
    Run model.generate() off the event loop with a timeout and bounded retries.

    Raises LLMError when every attempt failed or the error is not retryable.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(model.generate, prompt, json_output=json_output),
                timeout=timeout_s,
            )
        except Exception as exc:
            reason = "timed out" if isinstance(exc, _TIMEOUT_ERRORS) else f"{type(exc).__name__}: {exc}"
            if attempt >= max_attempts or not is_retryable(exc):
                raise LLMError(f"{model.name} failed after {attempt} attempt(s): {reason}") from exc
            delay = backoff_s * 2 ** (attempt - 1)
            logger.warning("%s call %s; retrying in %.1fs (attempt %d/%d)",
                           model.name, reason, delay, attempt, max_attempts)
            await asyncio.sleep(delay)
