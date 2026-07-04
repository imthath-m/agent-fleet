"""Minimal base Agent: instructions + tools + a ModelClient.

SDK-free core. Runnable end to end against ``FakeModelClient`` with no ADK
dependency. The optional ADK adapter lives in ``spine.agent_adk``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from spine.models import DEFAULT_CONFIG, ModelClient, ModelConfig


@dataclass
class Tool:
    """A callable the agent can reference by name.

    Phase 1 keeps this a simple registry entry; there is no automatic
    function-calling loop yet (that arrives with the ADK adapter).
    """

    name: str
    description: str
    fn: Callable[..., object]

    def __call__(self, *args: object, **kwargs: object) -> object:
        return self.fn(*args, **kwargs)


@dataclass
class Agent:
    """A base agent that composes a system prompt, tools, and a model client."""

    instructions: str
    model: ModelClient
    tools: list[Tool] = field(default_factory=list)
    config: ModelConfig = DEFAULT_CONFIG

    def __post_init__(self) -> None:
        self._tools_by_name = {t.name: t for t in self.tools}

    def get_tool(self, name: str) -> Tool:
        return self._tools_by_name[name]

    def call_tool(self, name: str, *args: object, **kwargs: object) -> object:
        return self.get_tool(name)(*args, **kwargs)

    def run(self, user_input: str) -> str:
        """Run one turn: compose the prompt, call the model, return its text."""
        prompt = self._build_prompt(user_input)
        response = self.model.generate(
            prompt,
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_output_tokens,
        )
        return response.text

    def _build_prompt(self, user_input: str) -> str:
        parts = [self.instructions.strip()]
        if self.tools:
            listing = "\n".join(f"- {t.name}: {t.description}" for t in self.tools)
            parts.append(f"Available tools:\n{listing}")
        parts.append(f"User: {user_input}")
        return "\n\n".join(parts)
