"""Create four business tables. This migration is independent of live ORM models."""

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def code(length: int = 32) -> sa.String:
    return sa.String(length, collation="utf8mb4_bin")


def primary_key() -> sa.Column:
    return sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True)


def created() -> sa.Column:
    return sa.Column("created_at", DATETIME(fsp=6), nullable=False)


def updated() -> sa.Column:
    return sa.Column("updated_at", DATETIME(fsp=6), nullable=False)


def upgrade() -> None:
    op.create_table(
        "equipment",
        primary_key(),
        sa.Column("equipment_no", code(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("manufacturer", sa.String(128), nullable=False),
        sa.Column("status", code(), nullable=False),
        sa.Column("location", sa.String(255), nullable=False),
        sa.Column("last_maintenance_at", DATETIME(fsp=6), nullable=True),
        created(),
        updated(),
        sa.CheckConstraint("status IN ('active','maintenance','inactive')", name="status"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_table(
        "employee",
        primary_key(),
        sa.Column("employee_no", code(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("department", sa.String(128), nullable=False),
        sa.Column("role", code(), nullable=False),
        sa.Column("status", code(), nullable=False),
        created(),
        sa.CheckConstraint("role IN ('requester','technician','admin')", name="role"),
        sa.CheckConstraint("status IN ('active','inactive')", name="status"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_table(
        "maintenance_record",
        primary_key(),
        sa.Column(
            "equipment_id",
            sa.BigInteger(),
            sa.ForeignKey("equipment.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("fault_description", sa.Text(), nullable=False),
        sa.Column("maintenance_action", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column(
            "maintained_by",
            sa.BigInteger(),
            sa.ForeignKey("employee.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("maintenance_at", DATETIME(fsp=6), nullable=False),
        created(),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "ix_maintenance_equipment_time",
        "maintenance_record",
        ["equipment_id", "maintenance_at", "id"],
    )
    op.create_table(
        "ticket",
        primary_key(),
        sa.Column("ticket_no", code(64), nullable=False, unique=True),
        sa.Column(
            "equipment_id",
            sa.BigInteger(),
            sa.ForeignKey("equipment.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", code(), nullable=False),
        sa.Column("priority", code(16), nullable=False),
        sa.Column("status", code(), nullable=False),
        sa.Column("diagnosis", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            sa.BigInteger(),
            sa.ForeignKey("employee.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "assigned_to",
            sa.BigInteger(),
            sa.ForeignKey("employee.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        created(),
        updated(),
        sa.CheckConstraint(
            "category IN ('electrical','mechanical','software','other')", name="category"
        ),
        sa.CheckConstraint("priority IN ('low','medium','high','urgent')", name="priority"),
        sa.CheckConstraint(
            "status IN ('open','in_progress','resolved','closed','cancelled')", name="status"
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_ticket_equipment_time", "ticket", ["equipment_id", "created_at", "id"])


def downgrade() -> None:
    op.drop_table("ticket")
    op.drop_table("maintenance_record")
    op.drop_table("employee")
    op.drop_table("equipment")
