import pytest

from spine.models import (
    DEFAULT_CONFIG,
    FakeModelClient,
    ModelClient,
    ModelConfig,
    ModelResponse,
    TimeoutExceeded,
    TransientModelError,
    WrappedModelClient,
)


def test_fake_client_is_a_model_client():
    assert isinstance(FakeModelClient(), ModelClient)


def test_fake_client_canned_reply_and_queue():
    fake = FakeModelClient(reply="fallback", replies=["a", "b"])
    assert fake.generate("x").text == "a"
    assert fake.generate("y").text == "b"
    assert fake.generate("z").text == "fallback"  # queue exhausted


def test_fake_client_responder():
    fake = FakeModelClient(responder=lambda p: p.upper())
    assert fake.generate("hi").text == "HI"


def test_response_token_totals():
    resp = ModelResponse(text="x", input_tokens=3, output_tokens=4)
    assert resp.total_tokens == 7


def test_wrapper_cost_accounting():
    config = ModelConfig(input_cost_per_1k=1.0, output_cost_per_1k=2.0)
    fake = FakeModelClient(responder=lambda p: "abcdefgh")  # 8 chars -> 2 tokens
    wrapped = WrappedModelClient(fake, config)

    wrapped.generate("abcd")  # 4 chars -> 1 input token

    u = wrapped.usage
    assert u.calls == 1
    assert u.input_tokens == 1
    assert u.output_tokens == 2
    # 1/1000*1.0 + 2/1000*2.0
    assert u.cost_usd == pytest.approx(0.001 + 0.004)


def test_wrapper_retries_then_succeeds():
    fake = FakeModelClient(reply="ok", fail_times=2)
    config = ModelConfig(max_retries=2)
    wrapped = WrappedModelClient(fake, config, sleep=lambda _s: None)

    resp = wrapped.generate("go")

    assert resp.text == "ok"
    assert wrapped.usage.retries == 2
    assert wrapped.usage.calls == 1


def test_wrapper_gives_up_after_max_retries():
    fake = FakeModelClient(fail_times=5)
    config = ModelConfig(max_retries=1)
    wrapped = WrappedModelClient(fake, config, sleep=lambda _s: None)

    with pytest.raises(TransientModelError):
        wrapped.generate("go")

    assert wrapped.usage.retries == 1


def test_wrapper_timeout_guard():
    ticks = iter([0.0, 100.0])  # start, end -> 100s elapsed
    fake = FakeModelClient(reply="ok")
    config = ModelConfig(timeout_s=5.0)
    wrapped = WrappedModelClient(fake, config, clock=lambda: next(ticks))

    with pytest.raises(TimeoutExceeded):
        wrapped.generate("go")


def test_default_config_present():
    assert isinstance(DEFAULT_CONFIG, ModelConfig)
    assert DEFAULT_CONFIG.model
