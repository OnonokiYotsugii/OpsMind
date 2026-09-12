"""Business vocabulary shared by schemas and services."""

from enum import StrEnum


class EquipmentStatus(StrEnum):
    ACTIVE = "active"
    MAINTENANCE = "maintenance"
    INACTIVE = "inactive"


class EmployeeRole(StrEnum):
    REQUESTER = "requester"
    TECHNICIAN = "technician"
    ADMIN = "admin"


class EmployeeStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class TicketCategory(StrEnum):
    ELECTRICAL = "electrical"
    MECHANICAL = "mechanical"
    SOFTWARE = "software"
    OTHER = "other"


class TicketPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TicketStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
    CANCELLED = "cancelled"


ALLOWED_TRANSITIONS: dict[TicketStatus, frozenset[TicketStatus]] = {
    TicketStatus.OPEN: frozenset({TicketStatus.IN_PROGRESS, TicketStatus.CANCELLED}),
    TicketStatus.IN_PROGRESS: frozenset({TicketStatus.RESOLVED, TicketStatus.CANCELLED}),
    TicketStatus.RESOLVED: frozenset({TicketStatus.IN_PROGRESS, TicketStatus.CLOSED}),
    TicketStatus.CLOSED: frozenset(),
    TicketStatus.CANCELLED: frozenset(),
}
