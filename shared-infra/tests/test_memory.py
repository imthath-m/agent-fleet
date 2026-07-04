from spine.memory import InMemoryMemoryStore, InMemorySessionStore, SessionState

# --------------------------------------------------------------------------- #
# Session store round-trip
# --------------------------------------------------------------------------- #


def test_session_store_round_trip():
    store = InMemorySessionStore()
    state = SessionState(session_id="s1", data={"topic": "billing"})

    store.put(state)

    assert store.get("s1") == state
    assert store.get("missing") is None


def test_session_store_get_or_create():
    store = InMemorySessionStore()

    created = store.get_or_create("s1")
    assert created.session_id == "s1"
    assert created.messages == []

    # Second call returns the same state, not a fresh one.
    again = store.get_or_create("s1")
    assert again is created


def test_session_store_append_message():
    store = InMemorySessionStore()

    store.append_message("s1", {"role": "user", "text": "hi"})
    state = store.append_message("s1", {"role": "assistant", "text": "hello"})

    assert [m["role"] for m in state.messages] == ["user", "assistant"]
    assert store.get("s1").messages == state.messages


# --------------------------------------------------------------------------- #
# Long-term memory store round-trip
# --------------------------------------------------------------------------- #


def test_memory_store_round_trip():
    store = InMemoryMemoryStore()

    entry = store.add("user-1", "billing-agent", "Prefers email over phone contact.")

    entries = store.get_all("user-1", "billing-agent")
    assert entries == [entry]


def test_memory_store_scoped_by_user_and_agent():
    store = InMemoryMemoryStore()

    store.add("user-1", "agent-a", "fact for user-1/agent-a")
    store.add("user-1", "agent-b", "fact for user-1/agent-b")
    store.add("user-2", "agent-a", "fact for user-2/agent-a")

    assert [e.text for e in store.get_all("user-1", "agent-a")] == ["fact for user-1/agent-a"]
    assert [e.text for e in store.get_all("user-1", "agent-b")] == ["fact for user-1/agent-b"]
    assert [e.text for e in store.get_all("user-2", "agent-a")] == ["fact for user-2/agent-a"]
    assert store.get_all("user-3", "agent-a") == []


# --------------------------------------------------------------------------- #
# KEY TEST (plan.md §5 verify criterion): memory persists across sessions.
# --------------------------------------------------------------------------- #


def test_memory_persists_across_sessions_for_same_user_and_agent():
    # A single backing store simulates the persistent memory backend (Memory
    # Bank in production); session state itself is scoped per session_id and
    # does not carry memory.
    memory_store = InMemoryMemoryStore()
    session_store = InMemorySessionStore()

    # --- Session 1: user chats, the agent writes a long-term memory fact.
    session_store.append_message("session-1", {"role": "user", "text": "I prefer aisle seats."})
    memory_store.add("user-42", "travel-agent", "User prefers aisle seats.")

    # --- Session 2: a brand new session for the same user/agent. Session
    # state is fresh (no messages carried over)...
    fresh_session = session_store.get_or_create("session-2")
    assert fresh_session.messages == []

    # ...but long-term memory for that user/agent is still readable.
    remembered = memory_store.get_all("user-42", "travel-agent")
    assert [e.text for e in remembered] == ["User prefers aisle seats."]

    # And it's genuinely not session-scoped: a totally different session id
    # sees the same memory for the same user/agent.
    remembered_again = memory_store.get_all("user-42", "travel-agent")
    assert remembered_again == remembered
