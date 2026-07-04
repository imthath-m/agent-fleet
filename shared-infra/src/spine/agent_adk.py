"""ADK adapter: builds a ``google.adk`` agent from a spine ``Agent``.

ADK is imported lazily so the SDK-free core stays importable without it. Use
this when deploying to Vertex AI Agent Engine; the base ``spine.agent.Agent``
remains fully runnable locally against ``FakeModelClient`` without ADK.
"""

from __future__ import annotations

from spine.agent import Agent


def to_adk_agent(agent: Agent, *, name: str = "spine_agent"):
    """Adapt a spine ``Agent`` into an ADK ``Agent``.

    Returns a ``google.adk.agents.Agent`` whose model, instructions, and tools
    mirror the spine agent. Tools are wrapped as ADK ``FunctionTool``s.
    """
    # Lazy import: keeps ADK optional for the core package.
    from google.adk.agents import Agent as AdkAgent
    from google.adk.tools import FunctionTool

    adk_tools = [FunctionTool(func=tool.fn) for tool in agent.tools]

    return AdkAgent(
        name=name,
        model=agent.config.model,
        instruction=agent.instructions,
        tools=adk_tools,
    )
