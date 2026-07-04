"""Input/output guardrails: deterministic checks that run around an Agent's
model calls.

Input guards inspect raw user text before it reaches the model (PII, prompt
injection, allow/deny topics). Output guards inspect the model's structured
response before it reaches the caller (schema validation, citation/grounding
checks, confidence gating). Every guard returns a structured
:class:`GuardrailResult`; :func:`run_guardrails` composes any number of guards
into one aggregate :class:`GuardrailReport` and (optionally) records the
decision as the standard ``spine.decision`` span attribute, mirroring
``spine.tracing.record_metrics``.

Detection here is deliberately deterministic (regex/keyword based) rather than
model-based, so it runs with no model calls, no GCP creds, and no network.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from opentelemetry.trace import Span

from spine.tracing import record_metrics


class Decision:
    """Canonical guardrail decisions. Severity order: BLOCK > ESCALATE > PASS."""

    PASS = "pass"
    ESCALATE = "escalate"
    BLOCK = "block"


_SEVERITY = {Decision.PASS: 0, Decision.ESCALATE: 1, Decision.BLOCK: 2}


@dataclass
class GuardrailResult:
    """Outcome of one guard's check."""

    name: str
    decision: str
    reason: str = ""
    detail: dict[str, Any] = field(default_factory=dict)
    redacted_text: str | None = None

    @property
    def passed(self) -> bool:
        return self.decision == Decision.PASS


@runtime_checkable
class InputGuard(Protocol):
    """A guard that checks raw input text."""

    name: str

    def check(self, text: str) -> GuardrailResult: ...


@dataclass
class AgentOutput:
    """The shape output guards inspect: structured data, free text, an
    optional confidence score, and any citations the agent produced."""

    data: dict[str, Any] = field(default_factory=dict)
    text: str = ""
    confidence: float | None = None
    citations: Sequence[str] = ()


@runtime_checkable
class OutputGuard(Protocol):
    """A guard that checks an agent's output."""

    name: str

    def check(self, output: AgentOutput) -> GuardrailResult: ...


# --------------------------------------------------------------------------- #
# Input guards
# --------------------------------------------------------------------------- #

_PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone": re.compile(r"\b(?:\+?1[ -]?)?\(?\d{3}\)?[ -]?\d{3}[ -]?\d{4}\b"),
}

# Order matters: credit_card/ssn are more specific than phone and must be
# matched (and redacted) first so a card number isn't also flagged as a phone.
_PII_ORDER = ("email", "credit_card", "ssn", "phone")


@dataclass
class PiiGuard:
    """Flags emails, phone numbers, credit-card-like, and SSN-like numbers.

    Always computes a redacted version of the text (each match replaced with
    ``[REDACTED_<TYPE>]``) so callers can choose to continue with the redacted
    text instead of hard-blocking. ``block_on_detect`` (default ``True``)
    controls whether detection also yields a ``BLOCK`` decision.
    """

    block_on_detect: bool = True
    name: str = "pii"

    def check(self, text: str) -> GuardrailResult:
        found: dict[str, list[str]] = {}
        redacted = text
        for kind in _PII_ORDER:
            pattern = _PII_PATTERNS[kind]
            matches = pattern.findall(redacted)
            if matches:
                found[kind] = matches
                redacted = pattern.sub(f"[REDACTED_{kind.upper()}]", redacted)

        if not found:
            return GuardrailResult(name=self.name, decision=Decision.PASS)

        decision = Decision.BLOCK if self.block_on_detect else Decision.PASS
        kinds = ", ".join(sorted(found))
        return GuardrailResult(
            name=self.name,
            decision=decision,
            reason=f"PII detected: {kinds}",
            detail={"found": found},
            redacted_text=redacted,
        )


_INJECTION_PATTERNS = [
    re.compile(r"ignore (?:all )?(?:previous|prior|above) instructions", re.IGNORECASE),
    re.compile(r"disregard (?:all )?(?:previous|prior|above)", re.IGNORECASE),
    re.compile(r"reveal (?:your |the )?(?:system prompt|instructions)", re.IGNORECASE),
    re.compile(r"you are now (?:in )?dan\b", re.IGNORECASE),
    re.compile(r"act as if you have no (?:rules|restrictions|guardrails)", re.IGNORECASE),
    re.compile(r"pretend (?:you are|to be) (?:an? )?(?:unfiltered|jailbroken)", re.IGNORECASE),
]


@dataclass
class PromptInjectionGuard:
    """Keyword/pattern heuristic for common prompt-injection attempts."""

    name: str = "prompt_injection"

    def check(self, text: str) -> GuardrailResult:
        for pattern in _INJECTION_PATTERNS:
            match = pattern.search(text)
            if match:
                return GuardrailResult(
                    name=self.name,
                    decision=Decision.BLOCK,
                    reason=f"prompt injection pattern matched: {match.group(0)!r}",
                    detail={"matched": match.group(0)},
                )
        return GuardrailResult(name=self.name, decision=Decision.PASS)


@dataclass
class TopicGuard:
    """Allow/deny topic check by keyword matching (case-insensitive).

    ``denied`` keywords always block. When ``allowed`` is set, input that
    matches none of those keywords is blocked as out of scope.
    """

    allowed: Sequence[str] | None = None
    denied: Sequence[str] = ()
    name: str = "topic"

    def check(self, text: str) -> GuardrailResult:
        lowered = text.lower()

        for topic in self.denied:
            if topic.lower() in lowered:
                return GuardrailResult(
                    name=self.name,
                    decision=Decision.BLOCK,
                    reason=f"denied topic matched: {topic!r}",
                    detail={"matched": topic},
                )

        if self.allowed is not None and not any(t.lower() in lowered for t in self.allowed):
            return GuardrailResult(
                name=self.name,
                decision=Decision.BLOCK,
                reason="no allowed topic matched",
                detail={"allowed": list(self.allowed)},
            )

        return GuardrailResult(name=self.name, decision=Decision.PASS)


# --------------------------------------------------------------------------- #
# Output guards
# --------------------------------------------------------------------------- #


@dataclass
class SchemaGuard:
    """Validates ``output.data`` has every required field with the right type.

    Mirrors ``spine.eval.metrics.SchemaPassRate`` but as a pass/block guard.
    """

    required_fields: Sequence[str]
    types: dict[str, type] | None = None
    name: str = "schema"

    def check(self, output: AgentOutput) -> GuardrailResult:
        missing = [f for f in self.required_fields if f not in output.data]
        bad_types: dict[str, str] = {}
        if self.types:
            for f, typ in self.types.items():
                if f in output.data and not isinstance(output.data[f], typ):
                    bad_types[f] = type(output.data[f]).__name__

        if not missing and not bad_types:
            return GuardrailResult(name=self.name, decision=Decision.PASS)

        return GuardrailResult(
            name=self.name,
            decision=Decision.BLOCK,
            reason="output failed schema validation",
            detail={"missing": missing, "bad_types": bad_types},
        )


@dataclass
class CitationGuard:
    """Requires at least ``min_citations`` citations when ``required`` is set."""

    required: bool = True
    min_citations: int = 1
    name: str = "citation"

    def check(self, output: AgentOutput) -> GuardrailResult:
        if not self.required:
            return GuardrailResult(name=self.name, decision=Decision.PASS)
        n = len(output.citations)
        if n >= self.min_citations:
            return GuardrailResult(name=self.name, decision=Decision.PASS)
        return GuardrailResult(
            name=self.name,
            decision=Decision.BLOCK,
            reason=f"expected >= {self.min_citations} citation(s), got {n}",
            detail={"citations": list(output.citations)},
        )


@dataclass
class ConfidenceGuard:
    """Gates on ``output.confidence``: below ``threshold`` yields ``on_low``
    (``ESCALATE`` by default, so low-confidence answers route to a human
    instead of being hard-blocked). Missing confidence passes — there's
    nothing to gate on.
    """

    threshold: float = 0.5
    on_low: str = Decision.ESCALATE
    name: str = "confidence"

    def check(self, output: AgentOutput) -> GuardrailResult:
        if output.confidence is None:
            return GuardrailResult(name=self.name, decision=Decision.PASS)
        if output.confidence >= self.threshold:
            return GuardrailResult(name=self.name, decision=Decision.PASS)
        return GuardrailResult(
            name=self.name,
            decision=self.on_low,
            reason=f"confidence {output.confidence:.2f} < threshold {self.threshold:.2f}",
            detail={"confidence": output.confidence, "threshold": self.threshold},
        )


# --------------------------------------------------------------------------- #
# Composition
# --------------------------------------------------------------------------- #


@dataclass
class GuardrailReport:
    """Aggregate outcome of running a set of guards over one input/output."""

    decision: str
    results: list[GuardrailResult]

    @property
    def passed(self) -> bool:
        return self.decision == Decision.PASS

    @property
    def blocked(self) -> list[GuardrailResult]:
        return [r for r in self.results if r.decision == Decision.BLOCK]

    @property
    def escalated(self) -> list[GuardrailResult]:
        return [r for r in self.results if r.decision == Decision.ESCALATE]


def run_guardrails(
    guards: Sequence[InputGuard] | Sequence[OutputGuard],
    value: Any,
    *,
    span: Span | None = None,
) -> GuardrailReport:
    """Run every guard over ``value`` and aggregate to the worst decision.

    ``value`` is a ``str`` for input guards or an :class:`AgentOutput` for
    output guards — each guard's ``check`` decides what it accepts. When
    ``span`` is given, the aggregate decision is recorded on it via
    ``spine.tracing.record_metrics`` (the standard ``spine.decision`` attribute).
    """
    results = [g.check(value) for g in guards]
    decision = Decision.PASS
    for r in results:
        if _SEVERITY[r.decision] > _SEVERITY[decision]:
            decision = r.decision

    if span is not None:
        record_metrics(span, decision=decision)

    return GuardrailReport(decision=decision, results=results)
