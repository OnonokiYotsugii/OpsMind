from typing import Annotated

from fastapi import APIRouter, Path, Query

from opsmind.api.dependencies import DatabaseSession, DemoActor
from opsmind.schemas.business import (
    EquipmentRead,
    MaintenanceRead,
    Page,
    TicketCreate,
    TicketRead,
    TicketUpdate,
)
from opsmind.services import equipment, tickets

router = APIRouter(prefix="/api/v1")
EquipmentNo = Annotated[str, Path(pattern=r"^[A-Z0-9_-]{1,64}$")]
TicketNo = Annotated[str, Path(pattern=r"^[A-Z0-9_-]{1,64}$")]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=10000)]


@router.get("/equipment/{equipment_no}", response_model=EquipmentRead, tags=["equipment"])
def read_equipment(equipment_no: EquipmentNo, session: DatabaseSession):
    return equipment.get_equipment(session, equipment_no)


@router.get(
    "/equipment/{equipment_no}/maintenance-records",
    response_model=Page[MaintenanceRead],
    tags=["equipment"],
)
def read_maintenance(
    equipment_no: EquipmentNo,
    session: DatabaseSession,
    limit: Limit = 20,
    offset: Offset = 0,
):
    return Page[MaintenanceRead](
        items=[
            MaintenanceRead.model_validate(item)
            for item in equipment.maintenance_history(session, equipment_no, limit, offset)
        ],
        limit=limit,
        offset=offset,
    )


@router.get(
    "/equipment/{equipment_no}/tickets",
    response_model=Page[TicketRead],
    tags=["equipment"],
)
def read_tickets(
    equipment_no: EquipmentNo,
    session: DatabaseSession,
    limit: Limit = 20,
    offset: Offset = 0,
):
    return Page[TicketRead](
        items=[
            TicketRead.model_validate(item)
            for item in equipment.ticket_history(session, equipment_no, limit, offset)
        ],
        limit=limit,
        offset=offset,
    )


@router.post("/tickets", response_model=TicketRead, status_code=201, tags=["tickets"])
def create_ticket(data: TicketCreate, session: DatabaseSession, actor: DemoActor):
    return tickets.create_ticket(session, data, actor)


@router.patch("/tickets/{ticket_no}", response_model=TicketRead, tags=["tickets"])
def update_ticket(
    ticket_no: TicketNo,
    data: TicketUpdate,
    session: DatabaseSession,
    actor: DemoActor,
):
    return tickets.update_ticket(session, ticket_no, data, actor)
