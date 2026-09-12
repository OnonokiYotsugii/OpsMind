"""P1 ORM mapping; migration files are the source of schema history."""

from datetime import UTC, datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, MetaData, String, Text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utc_now() -> datetime:
    """MySQL DATETIME stores naive UTC; API adds the UTC timezone on output."""
    return datetime.now(UTC).replace(tzinfo=None)


def code_type(length: int = 32) -> String:
    return String(length, collation="utf8mb4_bin")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class Created:
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utc_now)


class Updated(Created):
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        default=utc_now,
        onupdate=utc_now,
    )


class Equipment(Updated, Base):
    __tablename__ = "equipment"
    __table_args__ = (
        CheckConstraint("status IN ('active','maintenance','inactive')", name="status"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    equipment_no: Mapped[str] = mapped_column(code_type(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    model: Mapped[str] = mapped_column(String(128))
    manufacturer: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(code_type(), default="active")
    location: Mapped[str] = mapped_column(String(255))
    last_maintenance_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))


class Employee(Created, Base):
    __tablename__ = "employee"
    __table_args__ = (
        CheckConstraint("role IN ('requester','technician','admin')", name="role"),
        CheckConstraint("status IN ('active','inactive')", name="status"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_no: Mapped[str] = mapped_column(code_type(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    department: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(code_type())
    status: Mapped[str] = mapped_column(code_type(), default="active")


class MaintenanceRecord(Created, Base):
    __tablename__ = "maintenance_record"
    __table_args__ = (
        Index("ix_maintenance_equipment_time", "equipment_id", "maintenance_at", "id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipment.id", ondelete="RESTRICT"),
    )
    fault_description: Mapped[str] = mapped_column(Text)
    maintenance_action: Mapped[str] = mapped_column(Text)
    result: Mapped[str] = mapped_column(Text)
    maintained_by: Mapped[int] = mapped_column(ForeignKey("employee.id", ondelete="RESTRICT"))
    maintenance_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))


class Ticket(Updated, Base):
    __tablename__ = "ticket"
    __table_args__ = (
        CheckConstraint(
            "category IN ('electrical','mechanical','software','other')", name="category"
        ),
        CheckConstraint("priority IN ('low','medium','high','urgent')", name="priority"),
        CheckConstraint(
            "status IN ('open','in_progress','resolved','closed','cancelled')",
            name="status",
        ),
        Index("ix_ticket_equipment_time", "equipment_id", "created_at", "id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticket_no: Mapped[str] = mapped_column(code_type(64), unique=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(code_type())
    priority: Mapped[str] = mapped_column(code_type(16))
    status: Mapped[str] = mapped_column(code_type(), default="open")
    diagnosis: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("employee.id", ondelete="RESTRICT"))
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("employee.id", ondelete="RESTRICT"))
