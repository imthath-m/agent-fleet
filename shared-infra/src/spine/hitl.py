"""Human-in-the-loop escalation queue.

When a guardrail decision is ``ESCALATE`` (low confidence) or an action is
high-risk, the agent pauses and routes the case to a human queue instead of
returning a response. :class:`EscalationStore` is the interface —
:class:`InMemoryEscalationStore` is the local, SDK-free default used in tests
and local dev; :class:`FirestoreEscalationStore` is a lazy-import adapter
behind the same interface for production (mirrors ``spine.eval.sink``).
:class:`HumanQueue` wraps a store with enqueue/pending/resolve operations and
an optional notification hook (a plain callable — no real GCP).
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from spine.guardrails import Decision, GuardrailReport

# --------------------------------------------------------------------------- #
# Item
# --------------------------------------------------------------------------- #

STATUS_PENDING = "pending"
STATUS_RESOLVED = "resolved"


@dataclass
class EscalationItem:
    """One case routed to a human: why it was escalated, its payload, and its
    current status. ``payload`` carries whatever context a reviewer needs
    (e.g. the user input, the agent's draft output)."""

    id: str
    reason: str
    payload: dict[str, Any] = field(default_factory=dict)
    status: str = STATUS_PENDING
    resolution: str | None = None
    created_at: float = field(default_factory=time.time)
    resolved_at: float | None = None

    @property
    def is_pending(self) -> bool:
        return self.status == STATUS_PENDING


# --------------------------------------------------------------------------- #
# Store interface + implementations
# --------------------------------------------------------------------------- #


class EscalationStore(ABC):
    """Where escalation items are persisted."""

    @abstractmethod
    def put(self, item: EscalationItem) -> None:
        """Insert or overwrite an item by id."""

    @abstractmethod
    def get(self, item_id: str) -> EscalationItem | None:
        """Fetch one item by id, or ``None`` if it doesn't exist."""

    @abstractmethod
    def list_pending(self) -> list[EscalationItem]:
        """List every item still awaiting a human decision, oldest first."""


class InMemoryEscalationStore(EscalationStore):
    """Local, SDK-free store backed by a dict. Default for tests and local dev."""

    def __init__(self) -> None:
        self._items: dict[str, EscalationItem] = {}

    def put(self, item: EscalationItem) -> None:
        self._items[item.id] = item

    def get(self, item_id: str) -> EscalationItem | None:
        return self._items.get(item_id)

    def list_pending(self) -> list[EscalationItem]:
        pending = [i for i in self._items.values() if i.is_pending]
        return sorted(pending, key=lambda i: i.created_at)


class FirestoreEscalationStore(EscalationStore):
    """Firestore-backed store for production.

    The ``google-cloud-firestore`` SDK is imported lazily on first use so
    importing this module (and the whole ``spine`` surface) needs no GCP deps,
    creds, or network. Install the client via the ``firestore`` extra.
    """

    def __init__(
        self,
        collection: str = "spine_escalations",
        *,
        client: Any | None = None,
    ) -> None:
        self.collection = collection
        self._client = client

    def _get_collection(self) -> Any:
        if self._client is None:
            from google.cloud import firestore  # lazy: keeps core SDK-free

            self._client = firestore.Client()
        return self._client.collection(self.collection)

    def put(self, item: EscalationItem) -> None:
        self._get_collection().document(item.id).set(vars(item))

    def get(self, item_id: str) -> EscalationItem | None:
        snap = self._get_collection().document(item_id).get()
        if not snap.exists:
            return None
        return EscalationItem(**snap.to_dict())

    def list_pending(self) -> list[EscalationItem]:
        docs = self._get_collection().where("status", "==", STATUS_PENDING).stream()
        items = [EscalationItem(**d.to_dict()) for d in docs]
        return sorted(items, key=lambda i: i.created_at)


# --------------------------------------------------------------------------- #
# Queue
# --------------------------------------------------------------------------- #

NotifyFn = Callable[[EscalationItem], None]


class HumanQueue:
    """Escalation queue: enqueue a case, list what's pending, resolve it.

    ``notify`` is an optional callable invoked with the new item on enqueue
    (e.g. to page a reviewer) — no real notification backend is wired here.
    """

    def __init__(
        self,
        store: EscalationStore | None = None,
        *,
        notify: NotifyFn | None = None,
    ) -> None:
        self.store = store if store is not None else InMemoryEscalationStore()
        self._notify = notify

    def enqueue(
        self,
        *,
        reason: str,
        payload: dict[str, Any] | None = None,
        item_id: str | None = None,
    ) -> EscalationItem:
        item = EscalationItem(
            id=item_id or str(uuid.uuid4()),
            reason=reason,
            payload=payload or {},
        )
        self.store.put(item)
        if self._notify is not None:
            self._notify(item)
        return item

    def pending(self) -> list[EscalationItem]:
        return self.store.list_pending()

    def resolve(self, item_id: str, *, resolution: str) -> EscalationItem:
        item = self.store.get(item_id)
        if item is None:
            raise KeyError(f"no escalation item with id {item_id!r}")
        item.status = STATUS_RESOLVED
        item.resolution = resolution
        item.resolved_at = time.time()
        self.store.put(item)
        return item


def escalate_if_needed(
    report: GuardrailReport,
    queue: HumanQueue,
    *,
    payload: dict[str, Any] | None = None,
) -> EscalationItem | None:
    """Route a guardrail report to ``queue`` when it escalated.

    Only ``ESCALATE`` decisions route here — a hard ``BLOCK`` is a rejection,
    not a case for human review. Returns the enqueued item, or ``None`` when
    nothing escalated.
    """
    if report.decision != Decision.ESCALATE:
        return None
    reason = "; ".join(r.reason for r in report.escalated) or "guardrail escalation"
    return queue.enqueue(reason=reason, payload=payload)
