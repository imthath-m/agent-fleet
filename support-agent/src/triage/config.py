"""Central config for the triage agent. Constants only — no logic.

`KB_NAMESPACE` is the sole tenancy primitive (Q5, resolved as namespace-only
tenancy) and must not be hardcoded anywhere else in this package.
"""

from spine.models import ModelConfig

AGENT_ID = "triage-agent"

KB_NAMESPACE = "ubuntu-docs"

MODEL_CONFIG = ModelConfig()

CONFIDENCE_THRESHOLD = 0.6

RETRIEVAL_TOP_K = 4

HIGH_RISK_TOOLS = ("issue_refund", "crm_update")
