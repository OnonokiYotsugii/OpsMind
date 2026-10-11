from typing import TypedDict


class GraphState(TypedDict, total=False):
    run_id: str
    actor: str
    status: str
    turn: dict | None
    elapsed_ms: int
    effect_id: str
    action: dict | None
