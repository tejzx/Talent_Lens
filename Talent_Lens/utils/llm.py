"""Resilient Groq client shared by the screening agents."""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv

log = logging.getLogger(__name__)

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env", override=False)

MODEL_NAME = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


class LLMUnavailable(RuntimeError):
    """Raised when the Groq API is unavailable or not configured."""


def api_key() -> str | None:
    """Return the Groq key, if it has been supplied via environment or .env."""
    return os.getenv("GROQ_API_KEY")


def is_configured() -> bool:
    return bool(api_key())


def _client():
    key = api_key()
    if not key:
        raise LLMUnavailable("GROQ_API_KEY is not set")
    try:
        from groq import Groq
    except ImportError as exc:  # pragma: no cover - installation concern
        raise LLMUnavailable("The 'groq' package is not installed") from exc
    return Groq(api_key=key)


def generate(
    system_prompt: str,
    user_prompt: str,
    *,
    json_mode: bool = False,
    temperature: float = 0.2,
    retries: int = 3,
) -> str:
    """Call Groq Chat Completions and return the message text."""
    client = _client()
    request = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": 4096,
    }
    if json_mode:
        request["response_format"] = {"type": "json_object"}

    last: Exception | None = None
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(**request)
            content = response.choices[0].message.content
            if content:
                return content.strip()
            raise LLMUnavailable("Groq returned an empty response")
        except Exception as exc:  # rate limits / transient 5xx / network errors
            last = exc
            log.warning("Groq call failed (attempt %s/%s): %s", attempt + 1, retries, exc)
            if attempt < retries - 1:
                time.sleep(1.5 * (2**attempt))
    raise LLMUnavailable(str(last))


def generate_json(system_prompt: str, user_prompt: str, **kwargs) -> dict:
    return parse_json(generate(system_prompt, user_prompt, json_mode=True, **kwargs))


def parse_json(raw: str) -> dict:
    """Parse model output that may be fenced or padded with prose."""
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    raise ValueError("Model did not return valid JSON")
