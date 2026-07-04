"""spine — shared agentic-AI platform library for production agents on GCP.

Phase 1 surface: centralized model config + client interface, a base Agent
runnable with an in-memory fake model, and a local tool backend.
"""

from spine.agent import Agent, Tool
from spine.models import (
    FakeModelClient,
    ModelClient,
    ModelConfig,
    ModelResponse,
    WrappedModelClient,
)

__all__ = [
    "Agent",
    "Tool",
    "ModelClient",
    "ModelConfig",
    "ModelResponse",
    "FakeModelClient",
    "WrappedModelClient",
]
