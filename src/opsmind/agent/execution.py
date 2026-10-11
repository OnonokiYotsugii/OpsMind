"""Context-local fencing token shared by nodes and asynchronous checkpoint writes."""

from contextvars import ContextVar

from opsmind.core.errors import BusinessError

run_owner: ContextVar[str | None] = ContextVar("opsmind_run_owner", default=None)


def check_owner(row) -> None:
    owner = run_owner.get()
    if owner is not None and row.graph_owner != owner:
        raise BusinessError(
            "run_lease_lost", "Execution ownership changed; retry from saved state.", 409
        )
