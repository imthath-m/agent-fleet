"""Domain schemas for the triage pipeline.

Frozen dataclasses, deliberately shaped like `spine.reference_agent.ReferenceResult`
so the same round-trip and equality assertions transfer. Each carries a plain
`dataclasses.asdict`-based `to_dict()`/`from_dict()` pair so golden JSONL rows
and the API response share one serialization path.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any

from spine.hitl import EscalationItem
from spine.obs import MetricRecord

# --------------------------------------------------------------------------- #
# Enum vocabularies (Q1, resolved) — small closed sets. Widen only with a
# dataset version bump; never re-litigate silently.
# --------------------------------------------------------------------------- #

INTENTS = ("billing", "technical", "account", "how_to", "complaint", "other")  # ticket topic
PRIORITIES = ("low", "normal", "high", "urgent")  # urgency, drives escalation rule 4
PRODUCT_AREAS = (
    "install",
    "networking",
    "packaging",
    "users_permissions",
    "hardware",
    "other",
)  # mirrors the Ubuntu KB page groups Phase 1 fetches
SENTIMENTS = ("neutral", "frustrated", "angry", "positive")  # tone, drives escalation rule 5

# --------------------------------------------------------------------------- #
# Ticket
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Ticket:
    """An incoming support ticket."""

    ticket_id: str
    text: str
    channel: str
    customer_id: str
    subject: str
    received_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Ticket:
        return cls(**d)


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Classification:
    """Classifier output. Exactly 5 fields per Q1: no free-text `reason`, no
    self-reported `confidence` — retrieval score is the confidence signal fed
    to `ConfidenceGuard`, exactly as `spine.reference_agent.ReferenceAgent` does."""

    intent: str
    priority: str
    product_area: str
    sentiment: str
    pii_flag: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Classification:
        return cls(**d)


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Resolution:
    """Resolver output: a grounded, cited answer (or the lack of one)."""

    answer: str
    citations: list[str]
    grounded: bool
    retrieval_score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Resolution:
        return cls(**d)


# --------------------------------------------------------------------------- #
# ProposedAction
# --------------------------------------------------------------------------- #


def idempotency_key(*parts: object) -> str:
    """`sha256` over the pipe-joined parts — the same call always keys the same.

    Lives here rather than in `triage.tools` because it is how a
    `ProposedAction` is keyed, and because the tools package imports this
    module (the reverse would be a cycle).
    """
    return sha256("|".join(str(p) for p in parts).encode()).hexdigest()


@dataclass(frozen=True)
class ProposedAction:
    """A tool call proposed by the action agent — never auto-executed for
    high-risk tools; see `config.HIGH_RISK_TOOLS`."""

    tool: str
    args: dict[str, Any]
    idempotency_key: str
    risk: str
    executed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProposedAction:
        return cls(**d)


# --------------------------------------------------------------------------- #
# TriageResult
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TriageResult:
    """Everything one pipeline run produced, for callers, the API, and tests."""

    request_id: str
    trace_id: str | None
    ticket: Ticket
    classification: Classification | None
    resolution: Resolution | None
    proposed_actions: list[ProposedAction]
    escalation: EscalationItem | None
    withheld: bool
    metric: MetricRecord | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TriageResult:
        data = dict(d)
        data["ticket"] = Ticket.from_dict(data["ticket"])
        if data["classification"] is not None:
            data["classification"] = Classification.from_dict(data["classification"])
        if data["resolution"] is not None:
            data["resolution"] = Resolution.from_dict(data["resolution"])
        data["proposed_actions"] = [ProposedAction.from_dict(a) for a in data["proposed_actions"]]
        if data["escalation"] is not None:
            data["escalation"] = EscalationItem(**data["escalation"])
        if data["metric"] is not None:
            data["metric"] = MetricRecord(**data["metric"])
        return cls(**data)
