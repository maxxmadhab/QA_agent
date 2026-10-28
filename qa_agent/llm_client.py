"""Lightweight LLM clients for Anthropic and OpenAI using Python's built-in urllib.

No third-party packages are required — all HTTP calls are made with ``urllib.request``
from the standard library.  Adding a new provider means implementing one class with a
single ``complete()`` method and registering it in ``create_llm_client``.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import Any, cast

# Ensure .env is populated into os.environ
try:
    from .env_loader import load_dotenv
    load_dotenv()
except Exception:
    pass


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OMNIKEY = "omnikey"


# Default model IDs used when the caller does not specify one
DEFAULT_MODELS: dict[LLMProvider, str] = {
    LLMProvider.ANTHROPIC: "claude-sonnet-4-6",
    LLMProvider.OPENAI: "gpt-4o",
    LLMProvider.OMNIKEY: "google/gemma-4-26b-a4b-it:free",
}


# Environment variable names for API keys
_KEY_ENV_VARS: dict[LLMProvider, str] = {
    LLMProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
    LLMProvider.OPENAI: "OPENAI_API_KEY",
    LLMProvider.OMNIKEY: "OMNIKEY_API_KEY",
}


@dataclass
class LLMResponse:
    """Normalized response from any LLM provider."""

    text: str
    provider: LLMProvider
    model: str



class LLMError(Exception):
    """Raised when an LLM API call fails."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


# ---------------------------------------------------------------------------
# Shared HTTP helper
# ---------------------------------------------------------------------------

def _http_post(url: str, headers: dict[str, str], body: dict, timeout: int) -> dict:
    """POST JSON to *url* and return the parsed response body.

    Raises :class:`LLMError` on HTTP errors, connection failures, or timeouts.
    The ``retryable`` flag is set for transient conditions (rate limits, server
    errors, connection problems) so callers can apply back-off retry logic.
    """
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return cast(dict[str, Any], json.loads(resp.read().decode("utf-8")))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        retryable = exc.code in (429, 500, 502, 503, 504, 529)
        raise LLMError(
            f"HTTP {exc.code}: {raw[:300]}",
            status_code=exc.code,
            retryable=retryable,
        ) from exc
    except urllib.error.URLError as exc:
        raise LLMError(str(exc), retryable=True) from exc
    except TimeoutError as exc:
        raise LLMError("Request timed out", retryable=True) from exc


def _http_get(url: str, headers: dict[str, str], timeout: int) -> dict:
    """GET JSON from *url* and return the parsed response body."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return cast(dict[str, Any], json.loads(resp.read().decode("utf-8")))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        retryable = exc.code in (429, 500, 502, 503, 504, 529)
        raise LLMError(
            f"HTTP {exc.code}: {raw[:300]}",
            status_code=exc.code,
            retryable=retryable,
        ) from exc
    except urllib.error.URLError as exc:
        raise LLMError(str(exc), retryable=True) from exc
    except TimeoutError as exc:
        raise LLMError("Request timed out", retryable=True) from exc


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

class AnthropicClient:
    """Calls the Anthropic Messages API (``POST /v1/messages``) using urllib."""

    _API_URL = "https://api.anthropic.com/v1/messages"
    _API_VERSION = "2023-06-01"

    def __init__(self, model: str, api_key: str | None = None) -> None:
        self.model = model
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise LLMError(
                "Anthropic API key not found. "
                "Set the ANTHROPIC_API_KEY environment variable."
            )
        self._api_key = key

    def complete(self, system: str, user: str, max_tokens: int, timeout: int) -> LLMResponse:
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": self._API_VERSION,
            "content-type": "application/json",
        }
        body: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        data = _http_post(self._API_URL, headers, body, timeout)
        content = data.get("content", [])
        text = next((b["text"] for b in content if b.get("type") == "text"), None)
        if not text:
            raise LLMError("Anthropic API returned no text content.")
        return LLMResponse(text=text, provider=LLMProvider.ANTHROPIC, model=self.model)


class OpenAIClient:
    """Calls the OpenAI Chat Completions API (``POST /v1/chat/completions``) using urllib."""

    _API_URL = "https://api.openai.com/v1/chat/completions"

    # OpenAI reasoning models use max_completion_tokens instead of max_tokens.
    # Match o1, o1-mini, o1-preview, o3, o3-mini, etc.
    _REASONING_MODEL_PREFIX = ("o1", "o3")

    def __init__(self, model: str, api_key: str | None = None) -> None:
        self.model = model
        key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise LLMError(
                "OpenAI API key not found. "
                "Set the OPENAI_API_KEY environment variable."
            )
        self._api_key = key

    def _tokens_param(self, max_tokens: int) -> dict:
        """Return the correct token-limit parameter for this model.

        Reasoning models (o1*, o3*) require ``max_completion_tokens``; all
        other models use the standard ``max_tokens``.
        """
        key = (
            "max_completion_tokens"
            if any(self.model.startswith(p) for p in self._REASONING_MODEL_PREFIX)
            else "max_tokens"
        )
        return {key: max_tokens}

    def complete(self, system: str, user: str, max_tokens: int, timeout: int) -> LLMResponse:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body: dict = {
            "model": self.model,
            **self._tokens_param(max_tokens),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        data = _http_post(self._API_URL, headers, body, timeout)
        choices = data.get("choices", [])
        if not choices:
            raise LLMError("OpenAI API returned no choices.")
        text = choices[0].get("message", {}).get("content", "")
        if not text:
            raise LLMError("OpenAI API returned no text content.")
        return LLMResponse(text=text, provider=LLMProvider.OPENAI, model=self.model)


class OmniKeyClient:
    """Calls the OmniKey AI OpenAI-compatible API (POST /chat/completions, GET /models) using urllib."""

    _DEFAULT_BASE_URL = "https://omnikey-ai-unified-key-manager.onrender.com/v1"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("OMNIKEY_BASE_URL") or self._DEFAULT_BASE_URL).rstrip("/")
        env_model = os.environ.get("OMNIKEY_MODEL")
        self.model = model or env_model or "auto"
        key = api_key or os.environ.get("OMNIKEY_API_KEY", "")
        if not key:
            raise LLMError(
                "OmniKey API key not found. "
                "Set the OMNIKEY_API_KEY environment variable or define it in .env."
            )
        self._api_key = key

    def get_models(self, timeout: int = 30) -> list[str]:
        """Fetch available models from GET /models."""
        url = f"{self.base_url}/models"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        data = _http_get(url, headers, timeout)
        models_data = data.get("data", [])
        if isinstance(models_data, list):
            return [m["id"] for m in models_data if isinstance(m, dict) and "id" in m]
        return []

    def verify_connectivity(self, timeout: int = 30) -> dict:
        """Test API connectivity and key validity without leaking raw credentials."""
        try:
            models = self.get_models(timeout=timeout)
            return {
                "status": "ok",
                "provider": "omnikey",
                "base_url": self.base_url,
                "configured_model": self.model,
                "available_models_count": len(models),
                "available_models_sample": models[:5],
                "authenticated": True,
            }
        except Exception as exc:
            return {
                "status": "error",
                "provider": "omnikey",
                "base_url": self.base_url,
                "configured_model": self.model,
                "error": str(exc),
                "authenticated": False,
            }

    def complete(self, system: str, user: str, max_tokens: int, timeout: int) -> LLMResponse:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        chosen_model = self.model
        if not chosen_model or chosen_model == "auto":
            chosen_model = os.environ.get("OMNIKEY_MODEL") or "google/gemma-4-26b-a4b-it:free"
            if chosen_model == "auto":
                chosen_model = "google/gemma-4-26b-a4b-it:free"


        body: dict = {
            "model": chosen_model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        data = _http_post(url, headers, body, timeout)
        choices = data.get("choices", [])
        if not choices:
            raise LLMError("OmniKey API returned no choices.")
        text = choices[0].get("message", {}).get("content", "")
        if not text:
            raise LLMError("OmniKey API returned no text content.")
        return LLMResponse(text=text, provider=LLMProvider.OMNIKEY, model=chosen_model)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_llm_client(
    provider: LLMProvider,
    model: str | None = None,
    api_key: str | None = None,
) -> AnthropicClient | OpenAIClient | OmniKeyClient:
    """Create an LLM client for *provider*, using *model* (or the provider default).

    Raises :class:`LLMError` if the required API key is absent.
    """
    if provider == LLMProvider.ANTHROPIC:
        resolved_model = model or DEFAULT_MODELS[provider]
        return AnthropicClient(model=resolved_model, api_key=api_key)
    if provider == LLMProvider.OPENAI:
        resolved_model = model or DEFAULT_MODELS[provider]
        return OpenAIClient(model=resolved_model, api_key=api_key)
    if provider == LLMProvider.OMNIKEY:
        return OmniKeyClient(model=model, api_key=api_key)
    raise ValueError(f"Unknown LLM provider: {provider!r}")

