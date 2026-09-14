"""Persist Agent state and atomic approval receipts."""

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_run",
        sa.Column("id", sa.String(32, collation="utf8mb4_bin"), primary_key=True),
        sa.Column("actor_no", sa.String(64, collation="utf8mb4_bin"), nullable=False),
        sa.Column("status", sa.String(32, collation="utf8mb4_bin"), nullable=False),
        sa.Column("messages", sa.JSON(), nullable=False),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("pending_action", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(64, collation="utf8mb4_bin"), nullable=True),
        *[
            sa.Column(name, sa.Integer(), nullable=False)
            for name in (
                "steps",
                "tool_calls",
                "elapsed_ms",
                "max_steps",
                "max_tool_calls",
                "time_budget_ms",
            )
        ],
        sa.Column("expires_at", DATETIME(fsp=6), nullable=False),
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "status IN ('running','waiting_confirmation','completed','failed','rejected')",
            name="status",
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )


def downgrade() -> None:
    op.drop_table("agent_run")
