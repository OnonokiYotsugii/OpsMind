from sqlalchemy import select
from sqlalchemy.orm import Session

from opsmind.core.errors import BusinessError
from opsmind.db.models import Equipment, MaintenanceRecord, Ticket


def get_equipment(session: Session, equipment_no: str) -> Equipment:
    equipment = session.scalar(select(Equipment).where(Equipment.equipment_no == equipment_no))
    if equipment is None:
        raise BusinessError("equipment_not_found", "Equipment does not exist.", 404)
    return equipment


def maintenance_history(
    session: Session,
    equipment_no: str,
    limit: int,
    offset: int,
) -> list[MaintenanceRecord]:
    equipment = get_equipment(session, equipment_no)
    return list(
        session.scalars(
            select(MaintenanceRecord)
            .where(MaintenanceRecord.equipment_id == equipment.id)
            .order_by(MaintenanceRecord.maintenance_at.desc(), MaintenanceRecord.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )


def ticket_history(session: Session, equipment_no: str, limit: int, offset: int) -> list[Ticket]:
    equipment = get_equipment(session, equipment_no)
    return list(
        session.scalars(
            select(Ticket)
            .where(Ticket.equipment_id == equipment.id)
            .order_by(Ticket.created_at.desc(), Ticket.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
