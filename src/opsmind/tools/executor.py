"""Read execution and transaction-only writes; approval is enforced by AgentStore."""

from pydantic import BaseModel
from sqlalchemy.orm import Session

from opsmind.core.errors import BusinessError
from opsmind.schemas.business import EquipmentRead, MaintenanceRead, TicketRead
from opsmind.services import equipment, tickets
from opsmind.tools.registry import Risk, ToolDefinition


def compact(data):
    if isinstance(data, str):
        return data if len(data) <= 600 else data[:600] + "…[truncated]"
    if isinstance(data, list):
        return [compact(item) for item in data]
    if isinstance(data, dict):
        return {key: compact(value) for key, value in data.items()}
    return data


def execute_read(session: Session, definition: ToolDefinition, params: BaseModel) -> dict:
    if definition.risk != Risk.LOW:
        raise BusinessError("approval_required", "Write tools require explicit confirmation.", 409)
    values = params.model_dump()
    if definition.name == "get_equipment":
        data = EquipmentRead.model_validate(equipment.get_equipment(session, **values)).model_dump(
            mode="json",
        )
    elif definition.name == "get_maintenance_history":
        data = [
            MaintenanceRead.model_validate(row).model_dump(mode="json")
            for row in equipment.maintenance_history(session, **values)
        ]
    elif definition.name == "get_ticket_history":
        data = [
            TicketRead.model_validate(row).model_dump(mode="json")
            for row in equipment.ticket_history(session, **values)
        ]
    else:
        raise BusinessError("unknown_tool", "Tool is not executable.", 422)
    return {"ok": True, "data": compact(data), "note": "Long text may be truncated."}


def execute_approved_write(
    session: Session,
    definition: ToolDefinition,
    params: BaseModel,
    actor: str,
) -> dict:
    """Internal only. Caller holds locked run and approval within this transaction."""
    if not session.in_transaction():
        raise RuntimeError("An approval transaction is required.")
    if definition.name == "create_ticket" and definition.risk == Risk.MEDIUM:
        row = tickets.create_ticket_in_transaction(session, params, actor)
    elif definition.name == "update_ticket" and definition.risk == Risk.HIGH:
        row = tickets.update_ticket_in_transaction(session, params.ticket_no, params.changes, actor)
    else:
        raise BusinessError("unknown_write_tool", "Write tool is not allowed.", 422)
    return {"ok": True, "data": TicketRead.model_validate(row).model_dump(mode="json")}
