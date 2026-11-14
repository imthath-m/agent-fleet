import json

import httpx
import pytest

from spine.models import ModelClient, TransientModelError
from spine.models_openai import (
    OPENAI_DEFAULT_CONFIG,
    MissingApiKeyError,
    OpenAIModelClient,
    cost_usd,
)


def _client(handler, **kw):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAIModelClient(api_key="sk-test", client=http, **kw)


def _ok(request, text="hello", finish="stop"):
    return httpx.Response(
        200,
        json={
            "model": "gpt-6-luna-2026-01-01",
            "choices": [{"message": {"content": text}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3},
        },
    )


def test_success_parses_text_usage_and_sends_contract(monkeypatch):
    monkeypatch.delenv("SPINE_LIVE_REASONING_EFFORT", raising=False)
    seen = {}

    def handler(request):
        seen["req"] = request
        return _ok(request)

    resp = _client(handler).generate("hi", max_output_tokens=50, temperature=0.3)

    assert isinstance(_client(handler), ModelClient)
    assert (resp.text, resp.input_tokens, resp.output_tokens) == ("hello", 7, 3)
    req = seen["req"]
    assert req.url == "https://api.openai.com/v1/chat/completions"
    assert req.headers["authorization"] == "Bearer sk-test"
    body = json.loads(req.content)
    assert body["max_completion_tokens"] == 50
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    assert body["temperature"] == 0.3
    assert "reasoning_effort" not in body


def test_reasoning_effort_from_env(monkeypatch):
    monkeypatch.setenv("SPINE_LIVE_REASONING_EFFORT", "low")
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return _ok(request)

    _client(handler).generate("hi")
    assert seen["body"]["reasoning_effort"] == "low"


@pytest.mark.parametrize("status", [429, 500, 503])
def test_retryable_statuses_raise_transient(status):
    with pytest.raises(TransientModelError):
        _client(lambda r: httpx.Response(status, json={"error": {"message": "busy"}})).generate("x")


def test_timeout_is_transient():
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(TransientModelError):
        _client(timeout).generate("x")


def test_400_raises_runtime_error_with_api_message():
    handler = lambda r: httpx.Response(400, json={"error": {"message": "bad model"}})  # noqa: E731
    with pytest.raises(RuntimeError, match="bad model") as exc:
        _client(handler).generate("x")
    assert not isinstance(exc.value, TransientModelError)


def test_temperature_rejected_retries_once_and_is_remembered():
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if "temperature" in body:
            msg = "Unsupported value: 'temperature' does not support 0.0 with this model."
            return httpx.Response(400, json={"error": {"message": msg}})
        return _ok(request)

    client = _client(handler)
    assert client.generate("a").text == "hello"
    assert client.generate("b").text == "hello"
    assert ["temperature" in b for b in bodies] == [True, False, False]


def test_empty_text_with_length_is_an_error():
    with pytest.raises(RuntimeError, match="finish_reason=length"):
        _client(lambda r: _ok(r, text="", finish="length")).generate("x")


def test_missing_key_raises_clear_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(MissingApiKeyError, match="OPENAI_API_KEY"):
        OpenAIModelClient()


def test_key_defaults_from_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "anything")
    assert OpenAIModelClient()._api_key == "anything"


def test_cost_known_dated_unknown_and_override(monkeypatch):
    monkeypatch.delenv("SPINE_LIVE_INPUT_COST_PER_1M", raising=False)
    monkeypatch.delenv("SPINE_LIVE_OUTPUT_COST_PER_1M", raising=False)
    assert OPENAI_DEFAULT_CONFIG.model == "gpt-6-luna"
    assert cost_usd("gpt-6-luna", 1_000_000, 1_000_000) == pytest.approx(0.60)
    assert cost_usd("gpt-6-luna-2026-01-01", 1_000_000, 0) == pytest.approx(0.10)
    assert cost_usd("some-new-model", 10, 10) is None
    monkeypatch.setenv("SPINE_LIVE_INPUT_COST_PER_1M", "1")
    assert cost_usd("some-new-model", 10, 10) is None  # needs both
    monkeypatch.setenv("SPINE_LIVE_OUTPUT_COST_PER_1M", "2")
    assert cost_usd("some-new-model", 1_000_000, 1_000_000) == pytest.approx(3.0)
