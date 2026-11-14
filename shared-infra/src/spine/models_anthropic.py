"""API-key Claude adapter implementing ``ModelClient`` over plain ``httpx``.

No Anthropic SDK: one POST to ``/v1/messages``. ``httpx`` keeps its default
``trust_env`` (proxy settings) and TLS verification. Prices and the model list
below were taken from the claude-api skill's model table (cached 2026-11-03);
re-check them before trusting a cost figure for a new model.
"""

from __future__ import annotations

import os
from dataclasses import replace

import httpx

from spine.models import ModelConfig, ModelResponse, TransientModelError

ANTHROPIC_VERSION = "2023-06-01"

# USD per 1K tokens (input, output) = published $/1M divided by 1000.
# claude-haiku-5-5 is $0.10/$0.50 per 1M for prompts up to 100K tokens only
# ($0.50/$2.50 beyond); eval prompts are far below that.
PRICES: dict[str, tuple[float, float]] = {
    "claude-fable-5-2": (0.008, 0.040),
    "claude-mythos-5-2": (0.008, 0.040),
    "claude-fable-5-1": (0.010, 0.050),
    "claude-mythos-5-1": (0.010, 0.050),
    "claude-fable-5": (0.010, 0.050),
    "claude-opus-5-5": (0.004, 0.020),
    "claude-opus-5": (0.005, 0.025),
    "claude-opus-4-8": (0.005, 0.025),
    "claude-opus-4-7": (0.005, 0.025),
    "claude-opus-4-6": (0.005, 0.025),
    "claude-sonnet-5-5": (0.002, 0.010),
    "claude-sonnet-5": (0.002, 0.010),
    "claude-sonnet-4-6": (0.003, 0.015),
    "claude-haiku-5-5": (0.0001, 0.0005),
    "claude-haiku-4-5": (0.001, 0.005),
}

# Only these accept a non-default ``temperature``; newer models 400 on it, so it
# is left out of the request for every other model.
_ACCEPTS_TEMPERATURE = frozenset({"claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"})

_IN, _OUT = PRICES["claude-haiku-5-5"]
ANTHROPIC_DEFAULT_CONFIG = ModelConfig(
    model="claude-haiku-5-5",
    temperature=0.0,
    max_output_tokens=1024,
    timeout_s=60.0,
    max_retries=2,
    input_cost_per_1k=_IN,
    output_cost_per_1k=_OUT,
)


class MissingApiKeyError(RuntimeError):
    """``ANTHROPIC_API_KEY`` is not set and no ``api_key`` was passed."""


def config_for_model(model: str) -> ModelConfig:
    """The default config pointed at ``model``; prices are 0.0 if the model is
    not in the table (use :func:`cost_usd` for an honest None)."""
    in_, out = PRICES.get(model, (0.0, 0.0))
    return replace(
        ANTHROPIC_DEFAULT_CONFIG, model=model, input_cost_per_1k=in_, output_cost_per_1k=out
    )


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """USD cost of a call, or None when ``model`` has no known price."""
    if model not in PRICES:
        return None
    in_, out = PRICES[model]
    return input_tokens / 1000 * in_ + output_tokens / 1000 * out


class AnthropicModelClient:
    """``ModelClient`` backed by the Anthropic Messages API (API-key auth)."""

    def __init__(
        self,
        api_key: str | None = None,
        config: ModelConfig | None = None,
        base_url: str = "https://api.anthropic.com",
        *,
        client: httpx.Client | None = None,
    ) -> None:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise MissingApiKeyError(
                "ANTHROPIC_API_KEY is not set; pass api_key= or export the variable"
            )
        self._api_key = key
        self.config = config or ANTHROPIC_DEFAULT_CONFIG
        self._url = base_url.rstrip("/") + "/v1/messages"
        self._http = client or httpx.Client(timeout=self.config.timeout_s)

    def generate(self, prompt: str, **params: object) -> ModelResponse:
        model = self.config.model
        body: dict[str, object] = {
            "model": model,
            "max_tokens": int(params.get("max_output_tokens", self.config.max_output_tokens)),
            "messages": [{"role": "user", "content": prompt}],
        }
        if model in _ACCEPTS_TEMPERATURE:
            body["temperature"] = float(params.get("temperature", self.config.temperature))

        try:
            resp = self._http.post(
                self._url,
                json=body,
                headers={"x-api-key": self._api_key, "anthropic-version": ANTHROPIC_VERSION},
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise TransientModelError(f"{type(exc).__name__}: {exc}") from exc

        if resp.status_code == 429 or resp.status_code >= 500:  # incl. 529 overloaded
            raise TransientModelError(f"Anthropic API {resp.status_code}: {_error_message(resp)}")
        if resp.status_code >= 400:
            raise RuntimeError(f"Anthropic API error {resp.status_code}: {_error_message(resp)}")

        try:
            data = resp.json()
            text = "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
            usage = data.get("usage", {})
            return ModelResponse(
                text=text,
                input_tokens=int(usage.get("input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
                model=str(data.get("model", model)),
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise RuntimeError(f"unparseable Anthropic API response: {resp.text[:200]!r}") from exc


def _error_message(resp: httpx.Response) -> str:
    try:
        return str(resp.json()["error"]["message"])
    except (ValueError, KeyError, TypeError):
        return resp.text[:200]
