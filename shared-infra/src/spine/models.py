"""Model access: centralized config, a client interface, an in-memory fake,
and a thin wrapper adding retry, timeout, and cost accounting.

This module is SDK-free. The real Vertex/Gemini adapter lives in
``spine.models_vertex`` and imports its SDK lazily.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ModelConfig:
    """Centralized model + generation params shared by every agent.

    Costs are USD per 1K tokens, kept here so pricing lives in one place.
    """

    model: str = "gemini-2.0-flash"
    temperature: float = 0.2
    max_output_tokens: int = 1024
    timeout_s: float = 30.0
    max_retries: int = 2
    input_cost_per_1k: float = 0.00015
    output_cost_per_1k: float = 0.0006


DEFAULT_CONFIG = ModelConfig()


# --------------------------------------------------------------------------- #
# Response + interface
# --------------------------------------------------------------------------- #


@dataclass
class ModelResponse:
    """A single model generation result."""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@runtime_checkable
class ModelClient(Protocol):
    """Minimal interface every model backend implements."""

    def generate(self, prompt: str, **params: object) -> ModelResponse: ...


# --------------------------------------------------------------------------- #
# Fake client (deterministic, for tests + local dev)
# --------------------------------------------------------------------------- #


class TransientModelError(RuntimeError):
    """A retryable error (timeout, 429, transient 5xx)."""


class FakeModelClient:
    """Deterministic in-memory ``ModelClient`` for tests and local runs.

    Configure canned responses either as a fixed reply, a queue of replies, or
    a callable mapping the prompt to text. Optionally raise transient errors on
    the first ``fail_times`` calls to exercise retry logic.
    """

    def __init__(
        self,
        *,
        reply: str = "hello",
        replies: Iterable[str] | None = None,
        responder: Callable[[str], str] | None = None,
        fail_times: int = 0,
        config: ModelConfig = DEFAULT_CONFIG,
    ) -> None:
        self._reply = reply
        self._queue = list(replies) if replies is not None else None
        self._responder = responder
        self._fail_times = fail_times
        self._config = config
        self.calls: list[str] = []

    def generate(self, prompt: str, **params: object) -> ModelResponse:
        self.calls.append(prompt)
        if self._fail_times > 0:
            self._fail_times -= 1
            raise TransientModelError("simulated transient failure")

        if self._responder is not None:
            text = self._responder(prompt)
        elif self._queue is not None:
            text = self._queue.pop(0) if self._queue else self._reply
        else:
            text = self._reply

        return ModelResponse(
            text=text,
            input_tokens=_estimate_tokens(prompt),
            output_tokens=_estimate_tokens(text),
            model=self._config.model,
        )


# --------------------------------------------------------------------------- #
# Wrapper: retry + timeout + cost accounting
# --------------------------------------------------------------------------- #


@dataclass
class UsageStats:
    """Running totals across every call made through a wrapper."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    retries: int = 0


class TimeoutExceeded(RuntimeError):
    """Raised when a call takes longer than the configured timeout."""


class WrappedModelClient:
    """Wraps any ``ModelClient`` adding bounded retry, a timeout guard, and
    cost accounting. Retries only on ``TransientModelError``.
    """

    def __init__(
        self,
        client: ModelClient,
        config: ModelConfig = DEFAULT_CONFIG,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._config = config
        self._clock = clock
        self._sleep = sleep
        self.usage = UsageStats()

    def generate(self, prompt: str, **params: object) -> ModelResponse:
        attempts = self._config.max_retries + 1
        last_exc: Exception | None = None

        for attempt in range(attempts):
            start = self._clock()
            try:
                response = self._client.generate(prompt, **params)
            except TransientModelError as exc:
                last_exc = exc
                if attempt < attempts - 1:
                    self.usage.retries += 1
                    self._sleep(_backoff(attempt))
                    continue
                raise

            elapsed = self._clock() - start
            if elapsed > self._config.timeout_s:
                raise TimeoutExceeded(
                    f"call took {elapsed:.2f}s > {self._config.timeout_s:.2f}s"
                )

            self._record(response)
            return response

        # Unreachable: loop either returns or raises. Guard for type-checkers.
        raise last_exc if last_exc else RuntimeError("no attempts made")

    def _record(self, response: ModelResponse) -> None:
        u = self.usage
        u.calls += 1
        u.input_tokens += response.input_tokens
        u.output_tokens += response.output_tokens
        u.cost_usd += self._cost(response)

    def _cost(self, response: ModelResponse) -> float:
        c = self._config
        return (
            response.input_tokens / 1000 * c.input_cost_per_1k
            + response.output_tokens / 1000 * c.output_cost_per_1k
        )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _backoff(attempt: int) -> float:
    """Simple bounded exponential backoff in seconds."""
    return min(0.5 * (2**attempt), 5.0)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token). Good enough for fake accounting."""
    return max(1, len(text) // 4)
