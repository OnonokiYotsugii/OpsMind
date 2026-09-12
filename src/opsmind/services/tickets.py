"""Each write owns one transaction; database failures roll back the whole write."""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from opsmind.core.domain import ALLOWED_TRANSITIONS, TicketStatus
from opsmind.core.errors import BusinessError
from opsmind.db.models import Employee, Ticket
from opsmind.schemas.business import TicketCreate, TicketUpdate
from opsmind.services.equipment import get_equipment


def get_actor(session: Session, employee_no: str) -> Employee:
    actor = session.scalar(select(Employee).where(Employee.employee_no == employee_no))
    if actor is None or actor.status != "active":
        raise BusinessError("actor_unavailable", "Configured demo employee is not active.", 403)
    return actor


def check_assignee(session: Session, employee_id: int | None) -> None:
    if employee_id is None:
        return
    employee = session.get(Employee, employee_id)
    if (
        employee is None
        or employee.status != "active"
        or employee.role not in {"technician", "admin"}
    ):
        raise BusinessError(
            "invalid_assignee", "Assignee must be an active technician or admin.", 422
        )


def create_ticket(session: Session, data: TicketCreate, actor_no: str) -> Ticket:
    with session.begin():
        actor = get_actor(session, actor_no)
        equipment = get_equipment(session, data.equipment_no)
        if equipment.status == "inactive":
            raise BusinessError(
                "equipment_inactive", "Cannot create tickets for inactive equipment."
            )
        if actor.role == "requester" and data.assigned_to is not None:
            raise BusinessError("assignment_forbidden", "Requester cannot assign tickets.", 403)
        check_assignee(session, data.assigned_to)
        ticket = Ticket(
            ticket_no=f"TK-{uuid4().hex.upper()}",
            equipment_id=equipment.id,
            created_by=actor.id,
            status="open",
            **data.model_dump(exclude={"equipment_no"}),
        )
        session.add(ticket)
        session.flush()
    return ticket


def update_ticket(session: Session, ticket_no: str, data: TicketUpdate, actor_no: str) -> Ticket:
    with session.begin():
        actor = get_actor(session, actor_no)
        if actor.role not in {"technician", "admin"}:
            raise BusinessError("update_forbidden", "Only technicians and admins can update.", 403)
        # Serialize modifications so simultaneous status transitions see the latest state.
        ticket = session.scalar(
            select(Ticket).where(Ticket.ticket_no == ticket_no).with_for_update()
        )
        if ticket is None:
            raise BusinessError("ticket_not_found", "Ticket does not exist.", 404)
        old_status = TicketStatus(ticket.status)
        if old_status in {TicketStatus.CLOSED, TicketStatus.CANCELLED}:
            raise BusinessError("ticket_finalized", "Closed or cancelled tickets cannot be edited.")
        changes = data.model_dump(exclude_unset=True)
        new_status = data.status or old_status
        if new_status != old_status and new_status not in ALLOWED_TRANSITIONS[old_status]:
            raise BusinessError("invalid_transition", f"Cannot move {old_status} to {new_status}.")
        assignee = changes.get("assigned_to", ticket.assigned_to)
        if "assigned_to" in changes:
            check_assignee(session, assignee)
        if new_status in {TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED, TicketStatus.CLOSED}:
            if assignee is None:
                raise BusinessError("assignee_required", "Assign a technician before progressing.")
        diagnosis = changes.get("diagnosis", ticket.diagnosis)
        if new_status in {TicketStatus.RESOLVED, TicketStatus.CLOSED} and not diagnosis:
            raise BusinessError("diagnosis_required", "Resolution requires a diagnosis.")
        for key, value in changes.items():
            setattr(ticket, key, value)
        session.flush()
    return ticket
