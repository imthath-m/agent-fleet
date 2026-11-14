import json

import httpx
import pytest

from spine.models import ModelClient, TransientModelError
from spine.models_anthropic import (
    ANTHROPIC_DEFAULT_CONFIG,
    AnthropicModelClient,
    MissingApiKeyError,
    config_for_model,
    cost_usd,
)


def _client(handler, **kw):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return AnthropicModelClient(api_key="sk-test", client=http, **kw)


def _ok(request):
    return httpx.Response(
        200,
        json={
            "model": "claude-haiku-5-5",
            "content": [{"type": "text", "text": "hel"}, {"type": "text", "text": "lo"}],
            "usage": {"input_tokens": 7, "output_tokens": 3},
        },
    )


def test_is_a_model_client():
    assert isinstance(_client(_ok), ModelClient)


def test_success_parses_text_usage_and_sends_contract():
    seen = {}

    def handler(request):
        seen["req"] = request
        return _ok(request)

    resp = _client(handler).generate("hi", max_output_tokens=50, temperature=0.9)

    assert (resp.text, resp.input_tokens, resp.output_tokens) == ("hello", 7, 3)
    req = seen["req"]
    assert req.url == "https://api.anthropic.com/v1/messages"
    assert req.headers["x-api-key"] == "sk-test"
    assert req.headers["anthropic-version"] == "2023-06-01"
    body = json.loads(req.content)
    assert body["max_tokens"] == 50
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    assert "temperature" not in body  # haiku-5-5 rejects non-default sampling


def test_temperature_sent_for_models_that_accept_it():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return _ok(request)

    _client(handler, config=config_for_model("claude-haiku-4-5")).generate("hi", temperature=0.3)
    assert seen["body"]["temperature"] == 0.3


@pytest.mark.parametrize("status", [429, 500, 529])
def test_retryable_statuses_raise_transient(status):
    with pytest.raises(TransientModelError):
        _client(lambda r: httpx.Response(status, json={"error": {"message": "busy"}})).generate("x")


def test_timeout_and_connect_errors_are_transient():
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request):
        raise httpx.ConnectError("nope", request=request)

    for handler in (timeout, refused):
        with pytest.raises(TransientModelError):
            _client(handler).generate("x")


def test_400_raises_runtime_error_with_api_message():
    handler = lambda r: httpx.Response(400, json={"error": {"message": "bad model"}})  # noqa: E731
    with pytest.raises(RuntimeError, match="bad model") as exc:
        _client(handler).generate("x")
    assert not isinstance(exc.value, TransientModelError)


def test_missing_key_raises_clear_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(MissingApiKeyError, match="ANTHROPIC_API_KEY"):
        AnthropicModelClient()


def test_key_defaults_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
    assert AnthropicModelClient()._api_key == "sk-env"


def test_cost_known_and_unknown():
    assert ANTHROPIC_DEFAULT_CONFIG.model == "claude-haiku-5-5"
    assert cost_usd("claude-haiku-5-5", 1_000_000, 1_000_000) == pytest.approx(0.60)
    assert cost_usd("claude-sonnet-5-5", 1_000_000, 1_000_000) == pytest.approx(12.0)
    assert cost_usd("some-new-model", 10, 10) is None
