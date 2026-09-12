from datetime import UTC, datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from opsmind.core.domain import EquipmentStatus, TicketCategory, TicketPriority, TicketStatus

EquipmentNumber = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9_-]{1,64}$")]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Description = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)
]
Diagnosis = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_validator(
        "created_at",
        "updated_at",
        "maintenance_at",
        "last_maintenance_at",
        check_fields=False,
    )
    @classmethod
    def attach_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class EquipmentRead(ReadModel):
    id: int
    equipment_no: str
    name: str
    model: str
    manufacturer: str
    status: EquipmentStatus
    location: str
    last_maintenance_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MaintenanceRead(ReadModel):
    id: int
    equipment_id: int
    fault_description: str
    maintenance_action: str
    result: str
    maintained_by: int
    maintenance_at: datetime
    created_at: datetime


class TicketRead(ReadModel):
    id: int
    ticket_no: str
    equipment_id: int
    title: str
    description: str
    category: TicketCategory
    priority: TicketPriority
    status: TicketStatus
    diagnosis: str | None
    created_by: int
    assigned_to: int | None
    created_at: datetime
    updated_at: datetime


class Page[T](BaseModel):
    items: list[T]
    limit: int
    offset: int


class TicketCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    equipment_no: EquipmentNumber
    title: Title
    description: Description
    category: TicketCategory
    priority: TicketPriority = TicketPriority.MEDIUM
    diagnosis: Diagnosis | None = None
    assigned_to: int | None = Field(default=None, gt=0, strict=True)


class TicketUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Title | None = None
    description: Description | None = None
    category: TicketCategory | None = None
    priority: TicketPriority | None = None
    status: TicketStatus | None = None
    diagnosis: Diagnosis | None = None
    assigned_to: int | None = Field(default=None, gt=0, strict=True)

    @model_validator(mode="after")
    def validate_patch(self) -> "TicketUpdate":
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update.")
        nullable = {"diagnosis", "assigned_to"}
        for field in self.model_fields_set - nullable:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        return self
