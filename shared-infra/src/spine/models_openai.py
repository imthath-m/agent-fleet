"""API-key OpenAI adapter implementing ``ModelClient`` over plain ``httpx``.

No OpenAI SDK: one POST to ``/v1/chat/completions``. ``httpx`` keeps its default
``trust_env`` (proxy settings) and TLS verification. The key is whatever
``OPENAI_API_KEY`` holds; its format is not checked.
"""

from __future__ import annotations

import os
import re
from dataclasses import replace

import httpx

from spine.models import ModelConfig, ModelResponse, TransientModelError
from spine.models_anthropic import MissingApiKeyError

__all__ = [
    "OPENAI_DEFAULT_CONFIG",
    "PRICES",
    "MissingApiKeyError",
    "OpenAIModelClient",
    "config_for_model",
    "cost_usd",
]

# USD per 1K tokens (input, output) = published $/1M divided by 1000, standard
# tier, short-context rates. Source: https://developers.openai.com/api/docs/pricing
# (fetched 2026-11-14). Only models listed there are priced; anything else gives
# cost None. Re-check before trusting a figure.
PRICES: dict[str, tuple[float, float]] = {
    "gpt-6-astra": (0.010, 0.050),
    "gpt-6.1-sol": (0.002, 0.010),
    "gpt-6.1-terra": (0.001, 0.005),
    "gpt-6-sol": (0.002, 0.010),
    "gpt-6-luna": (0.0001, 0.0005),
    "gpt-5.6-sol": (0.004, 0.020),
    "gpt-5.6-terra": (0.002, 0.012),
    "gpt-5.6-luna": (0.0002, 0.0012),
    "gpt-5.4-mini": (0.00075, 0.0045),
    "gpt-5.4-nano": (0.0002, 0.00125),
    "gpt-5-mini": (0.00025, 0.002),
    "gpt-5-nano": (0.00005, 0.0004),
    "gpt-4.1": (0.002, 0.008),
    "gpt-4.1-mini": (0.0004, 0.0016),
    "gpt-4o-mini": (0.00015, 0.0006),
}

# https://developers.openai.com/api/docs/models lists gpt-6-luna as a current model
# ("most efficient ... high-volume"); it is also the cheapest text model there.
OPENAI_DEFAULT_CONFIG = ModelConfig(
    model="gpt-6-luna",
    temperature=0.0,
    max_output_tokens=1024,
    timeout_s=60.0,
    max_retries=2,
    input_cost_per_1k=PRICES["gpt-6-luna"][0],
    output_cost_per_1k=PRICES["gpt-6-luna"][1],
)

_DATED = re.compile(r"-\d{4}-\d{2}-\d{2}$")  # API echoes e.g. "gpt-5-nano-2025-08-07"


def _override() -> tuple[float, float] | None:
    """User-supplied $/1M prices (both env vars required); applies to every model."""
    in_, out = os.environ.get("SPINE_LIVE_INPUT_COST_PER_1M"), os.environ.get(
        "SPINE_LIVE_OUTPUT_COST_PER_1M"
    )
    if in_ and out:
        return float(in_) / 1000, float(out) / 1000
    return None


def _price(model: str) -> tuple[float, float] | None:
    return _override() or PRICES.get(model) or PRICES.get(_DATED.sub("", model))


def config_for_model(model: str) -> ModelConfig:
    """The default config pointed at ``model``; prices are 0.0 if unknown (use
    :func:`cost_usd` for an honest None)."""
    in_, out = _price(model) or (0.0, 0.0)
    return replace(
        OPENAI_DEFAULT_CONFIG, model=model, input_cost_per_1k=in_, output_cost_per_1k=out
    )


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """USD cost of a call, or None when ``model`` has no known price."""
    price = _price(model)
    if price is None:
        return None
    return input_tokens / 1000 * price[0] + output_tokens / 1000 * price[1]


class OpenAIModelClient:
    """``ModelClient`` backed by the OpenAI Chat Completions API (API-key auth)."""

    def __init__(
        self,
        api_key: str | None = None,
        config: ModelConfig | None = None,
        base_url: str = "https://api.openai.com",
        *,
        client: httpx.Client | None = None,
    ) -> None:
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise MissingApiKeyError("OPENAI_API_KEY is not set; pass api_key= or export it")
        self._api_key = key
        self.config = config or OPENAI_DEFAULT_CONFIG
        self._url = base_url.rstrip("/") + "/v1/chat/completions"
        self._http = client or httpx.Client(timeout=self.config.timeout_s)
        self._send_temperature = True  # cleared once the API rejects it

    def _post(self, body: dict[str, object]) -> httpx.Response:
        try:
            return self._http.post(
                self._url, json=body, headers={"Authorization": f"Bearer {self._api_key}"}
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise TransientModelError(f"{type(exc).__name__}: {exc}") from exc

    def generate(self, prompt: str, **params: object) -> ModelResponse:
        model = self.config.model
        body: dict[str, object] = {
            "model": model,
            "max_completion_tokens": int(
                params.get("max_output_tokens", self.config.max_output_tokens)
            ),
            "messages": [{"role": "user", "content": prompt}],
        }
        if effort := os.environ.get("SPINE_LIVE_REASONING_EFFORT"):
            body["reasoning_effort"] = effort
        if self._send_temperature:
            body["temperature"] = float(params.get("temperature", self.config.temperature))

        resp = self._post(body)
        if resp.status_code == 400 and "temperature" in body:
            msg = _error_message(resp).lower()
            if "temperature" in msg or "unsupported" in msg:
                self._send_temperature = False
                del body["temperature"]
                resp = self._post(body)

        if resp.status_code == 429 or resp.status_code >= 500:
            raise TransientModelError(f"OpenAI API {resp.status_code}: {_error_message(resp)}")
        if resp.status_code >= 400:
            raise RuntimeError(f"OpenAI API error {resp.status_code}: {_error_message(resp)}")

        try:
            data = resp.json()
            choice = data["choices"][0]
            text = choice["message"].get("content") or ""
            usage = data.get("usage", {})
            result = ModelResponse(
                text=text,
                input_tokens=int(usage.get("prompt_tokens", 0)),
                output_tokens=int(usage.get("completion_tokens", 0)),
                model=str(data.get("model", model)),
            )
            finish = choice.get("finish_reason")
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise RuntimeError(f"unparseable OpenAI API response: {resp.text[:200]!r}") from exc
        if not text and finish == "length":
            raise RuntimeError(
                f"{model} returned empty text with finish_reason=length: the output cap "
                "was likely consumed by hidden reasoning; raise max_output_tokens or lower "
                "SPINE_LIVE_REASONING_EFFORT"
            )
        return result


def _error_message(resp: httpx.Response) -> str:
    try:
        return str(resp.json()["error"]["message"])
    except (ValueError, KeyError, TypeError):
        return resp.text[:200]
