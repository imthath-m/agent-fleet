"""`order_lookup` — read-only lookup against a committed fixture store.

There is no customer order system to talk to pre-sale (Decision 4), so the
store is a JSON file in the repo. It is opened for reading only; an unknown id
returns `{"found": false}` rather than raising, because a missing order is an
ordinary support outcome, not a tool failure.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from spine.tracing import StepType, timed_span

ORDERS_PATH = Path(__file__).resolve().parents[3] / "data" / "fixtures" / "orders.json"


@lru_cache(maxsize=1)
def _orders(path: str = str(ORDERS_PATH)) -> dict[str, dict]:
    with Path(path).open() as f:
        return json.load(f)


def order_lookup(order_id: str, *, path: str | Path = ORDERS_PATH) -> dict:
    """Return `{"found": True, **order}` or `{"found": False, "order_id": ...}`."""
    with timed_span("tool.order_lookup", step=StepType.TOOL_CALL):
        order = _orders(str(path)).get(order_id)
        if order is None:
            return {"found": False, "order_id": order_id}
        return {"found": True, **order}


def order_exists(order_id: str) -> bool:
    """Whether `order_id` is in the store — used by `issue_refund` to validate
    before proposing. Deliberately not a tool: it emits no span of its own."""
    return order_id in _orders()
