"""Classifier stage: a ticket in, a schema-guarded `Classification` out.

Mirrors the span/log/metric shape of `spine.reference_agent.ReferenceAgent.run`
for one step: input guardrails -> a wrapped model call inside a `model_call`
span -> JSON parse -> `SchemaGuard` validation.

Two guardrail outcomes are deliberately different in kind:

* the injection guard returning `Decision.BLOCK` is an *input* problem — the
  caller gets `(None, report)` and the pipeline short-circuits;
* `SchemaGuard` returning `Decision.BLOCK` is a *model* problem (bad JSON, not
  an ambiguous ticket) so it raises `ClassificationError` — a hard failure, not
  an escalation.

PII never blocks: support tickets legitimately carry emails and phone numbers.
`PiiGuard(block_on_detect=False)` still redacts, and the redacted text is what
reaches the model; `Classification.pii_flag` records that PII was present.
"""

from __future__ import annotations

import logging

from spine.eval.runner import parse_json_prediction
from spine.guardrails import (
    AgentOutput,
    Decision,
    GuardrailReport,
    PiiGuard,
    PromptInjectionGuard,
    SchemaGuard,
    run_guardrails,
)
from spine.logging import log_event
from spine.models import ModelClient, WrappedModelClient
from spine.tracing import StepType, record_metrics, span

from triage import config
from triage.schemas import INTENTS, PRIORITIES, PRODUCT_AREAS, SENTIMENTS, Classification, Ticket

# The four model-decided fields; `pii_flag` comes from the guard, not the model.
CLASSIFIED_FIELDS = ("intent", "priority", "product_area", "sentiment")

_USER_MARKER = "User:"

_PROMPT_TEMPLATE = """You are a support ticket classifier for an Ubuntu support desk.

Classify the ticket below and reply with a JSON object with exactly these keys:
  "intent": one of {intents}
  "priority": one of {priorities}
  "product_area": one of {product_areas}
  "sentiment": one of {sentiments}

{user_marker} {subject}. {text}"""


class ClassificationError(RuntimeError):
    """The model returned output that failed `SchemaGuard`. Hard failure."""


def build_prompt(ticket: Ticket, text: str) -> str:
    """Prompt for one ticket. `text` is the (possibly redacted) ticket body.

    The ticket lands after a `User:` marker, in the same shape
    `spine.reference_agent._build_prompt` uses, so prompt-parsing fakes can
    read the ticket without also reading the enum vocabularies listed above it.
    """
    return _PROMPT_TEMPLATE.format(
        intents=", ".join(INTENTS),
        priorities=", ".join(PRIORITIES),
        product_areas=", ".join(PRODUCT_AREAS),
        sentiments=", ".join(SENTIMENTS),
        user_marker=_USER_MARKER,
        subject=ticket.subject,
        text=text,
    )


def classify(
    ticket: Ticket,
    *,
    model: ModelClient,
    logger: logging.Logger,
) -> tuple[Classification | None, GuardrailReport]:
    """Classify one ticket. Returns `(None, report)` when the input is blocked.

    Raises `ClassificationError` when the model's output fails `SchemaGuard`.
    """
    guards = [PromptInjectionGuard(), PiiGuard(block_on_detect=False)]

    with span("input_guardrail", step=StepType.GUARDRAIL) as gsp:
        report = run_guardrails(guards, ticket.text, span=gsp)
    _log(logger, ticket, "input guardrails", step=StepType.GUARDRAIL, decision=report.decision)

    if report.decision == Decision.BLOCK:
        return None, report

    pii = next(r for r in report.results if r.name == "pii")
    pii_flag = bool(pii.detail.get("found"))
    text = pii.redacted_text if pii.redacted_text is not None else ticket.text

    wrapped = (
        model
        if isinstance(model, WrappedModelClient)
        else WrappedModelClient(model, config.MODEL_CONFIG)
    )
    with span("classify", step=StepType.MODEL_CALL) as msp:
        response = wrapped.generate(
            build_prompt(ticket, text),
            temperature=config.MODEL_CONFIG.temperature,
            max_output_tokens=config.MODEL_CONFIG.max_output_tokens,
        )
        cost = _cost(response.input_tokens, response.output_tokens)
        record_metrics(msp, tokens=response.total_tokens, cost=cost)
    _log(
        logger,
        ticket,
        "classify model call",
        step=StepType.MODEL_CALL,
        tokens=response.total_tokens,
        cost=cost,
    )

    parsed = parse_json_prediction(response.text).output
    schema = SchemaGuard(
        required_fields=list(CLASSIFIED_FIELDS),
        types=dict.fromkeys(CLASSIFIED_FIELDS, str),
    )
    schema_result = schema.check(AgentOutput(data=parsed))
    if schema_result.decision == Decision.BLOCK:
        _log(
            logger,
            ticket,
            "classification failed schema validation",
            step=StepType.GUARDRAIL,
            decision=schema_result.decision,
            outcome="error",
        )
        raise ClassificationError(f"{schema_result.reason}: {schema_result.detail}")

    classification = Classification(
        intent=parsed["intent"],
        priority=parsed["priority"],
        product_area=parsed["product_area"],
        sentiment=parsed["sentiment"],
        pii_flag=pii_flag,
    )
    return classification, report


def _cost(input_tokens: int, output_tokens: int) -> float:
    c = config.MODEL_CONFIG
    return input_tokens / 1000 * c.input_cost_per_1k + output_tokens / 1000 * c.output_cost_per_1k


def _log(logger: logging.Logger, ticket: Ticket, message: str, *, decision=None, **fields) -> None:
    log_event(
        logger,
        message,
        request_id=ticket.ticket_id,
        agent=config.AGENT_ID,
        guardrail_decision=decision,
        **fields,
    )
