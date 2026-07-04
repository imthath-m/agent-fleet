"""Memory & state abstraction so products don't hardcode storage (plan.md §4).

Two distinct concerns, each behind its own interface:

- :class:`SessionStore` — session/conversation state (Firestore-style),
  scoped to one ``session_id``. Ephemeral / not expected to outlive a session.
- :class:`MemoryStore` — long-term, cross-session agent memory (Vertex Memory
  Bank-style), scoped to a ``(user_id, agent_id)`` pair so a *new* session for
  the same user/agent can read memory written in an earlier session.

Both ship an in-memory implementation as the local, SDK-free default used in
tests and local dev; ``FirestoreSessionStore`` and ``MemoryBankStore`` are
lazy-import adapters behind the same interfaces (mirrors ``spine.hitl``).
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

# --------------------------------------------------------------------------- #
# Session / conversation state
# --------------------------------------------------------------------------- #


@dataclass
class SessionState:
    """One session's state: arbitrary app data plus the message history."""

    session_id: str
    data: dict[str, Any] = field(default_factory=dict)
    messages: list[dict[str, Any]] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)


class SessionStore(ABC):
    """Where session/conversation state is persisted, keyed by ``session_id``."""

    @abstractmethod
    def get(self, session_id: str) -> SessionState | None:
        """Fetch a session's state, or ``None`` if it doesn't exist yet."""

    @abstractmethod
    def put(self, state: SessionState) -> None:
        """Insert or overwrite a session's state."""

    def get_or_create(self, session_id: str) -> SessionState:
        """Fetch a session's state, creating an empty one if it's new."""
        state = self.get(session_id)
        if state is None:
            state = SessionState(session_id=session_id)
            self.put(state)
        return state

    def append_message(self, session_id: str, message: dict[str, Any]) -> SessionState:
        """Append one message to a session's history and persist it."""
        state = self.get_or_create(session_id)
        state.messages.append(message)
        state.updated_at = time.time()
        self.put(state)
        return state


class InMemorySessionStore(SessionStore):
    """Local, SDK-free store backed by a dict. Default for tests and local dev."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    def get(self, session_id: str) -> SessionState | None:
        return self._sessions.get(session_id)

    def put(self, state: SessionState) -> None:
        self._sessions[state.session_id] = state


class FirestoreSessionStore(SessionStore):
    """Firestore-backed session store for production.

    The ``google-cloud-firestore`` SDK is imported lazily on first use so
    importing this module (and the whole ``spine`` surface) needs no GCP deps,
    creds, or network. Install the client via the ``firestore`` extra.
    """

    def __init__(
        self,
        collection: str = "spine_sessions",
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

    def get(self, session_id: str) -> SessionState | None:
        snap = self._get_collection().document(session_id).get()
        if not snap.exists:
            return None
        return SessionState(**snap.to_dict())

    def put(self, state: SessionState) -> None:
        self._get_collection().document(state.session_id).set(vars(state))


# --------------------------------------------------------------------------- #
# Long-term, cross-session memory
# --------------------------------------------------------------------------- #


@dataclass
class MemoryEntry:
    """One long-term memory fact, scoped to a user/agent pair."""

    id: str
    user_id: str
    agent_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


class MemoryStore(ABC):
    """Where long-term cross-session memory is persisted, keyed by
    ``(user_id, agent_id)`` — deliberately *not* keyed by ``session_id``, so a
    fresh session for the same user/agent reads memory written earlier."""

    @abstractmethod
    def add(
        self,
        user_id: str,
        agent_id: str,
        text: str,
        *,
        metadata: dict[str, Any] | None = None,
        entry_id: str | None = None,
    ) -> MemoryEntry:
        """Append one memory entry for ``(user_id, agent_id)``."""

    @abstractmethod
    def get_all(self, user_id: str, agent_id: str) -> list[MemoryEntry]:
        """Return every memory entry for ``(user_id, agent_id)``, oldest first."""


class InMemoryMemoryStore(MemoryStore):
    """Local, SDK-free store backed by a dict. Default for tests and local dev.

    Backed by a single dict instance for the process lifetime, so constructing
    a "new session" against the *same store instance* is exactly how
    cross-session persistence is exercised without any real backend.
    """

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], list[MemoryEntry]] = {}

    def add(
        self,
        user_id: str,
        agent_id: str,
        text: str,
        *,
        metadata: dict[str, Any] | None = None,
        entry_id: str | None = None,
    ) -> MemoryEntry:
        entry = MemoryEntry(
            id=entry_id or str(uuid.uuid4()),
            user_id=user_id,
            agent_id=agent_id,
            text=text,
            metadata=metadata or {},
        )
        self._entries.setdefault((user_id, agent_id), []).append(entry)
        return entry

    def get_all(self, user_id: str, agent_id: str) -> list[MemoryEntry]:
        return list(self._entries.get((user_id, agent_id), []))


class MemoryBankStore(MemoryStore):
    """Vertex AI Memory Bank adapter for production.

    The ``google-cloud-aiplatform`` SDK is imported lazily on first use so
    importing this module (and the whole ``spine`` surface) needs no GCP deps,
    creds, or network. Install the client via the ``vertex`` extra.
    """

    def __init__(
        self,
        project: str,
        *,
        location: str = "us-central1",
        client: Any | None = None,
    ) -> None:
        self._project = project
        self._location = location
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            from google.cloud import aiplatform  # lazy: keeps core SDK-free

            aiplatform.init(project=self._project, location=self._location)
            self._client = aiplatform
        return self._client

    def add(
        self,
        user_id: str,
        agent_id: str,
        text: str,
        *,
        metadata: dict[str, Any] | None = None,
        entry_id: str | None = None,
    ) -> MemoryEntry:
        client = self._get_client()
        entry = MemoryEntry(
            id=entry_id or str(uuid.uuid4()),
            user_id=user_id,
            agent_id=agent_id,
            text=text,
            metadata=metadata or {},
        )
        client.memory_bank.generate_memories(
            scope={"user_id": user_id, "agent_id": agent_id},
            fact=entry.text,
        )
        return entry

    def get_all(self, user_id: str, agent_id: str) -> list[MemoryEntry]:
        client = self._get_client()
        memories = client.memory_bank.retrieve_memories(
            scope={"user_id": user_id, "agent_id": agent_id},
        )
        return [
            MemoryEntry(
                id=m.id,
                user_id=user_id,
                agent_id=agent_id,
                text=m.fact,
            )
            for m in memories
        ]
