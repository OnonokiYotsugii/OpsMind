"""LangGraph checkpoints and per-run execution leases."""

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "agent_run", sa.Column("graph_owner", sa.String(32, collation="utf8mb4_bin"), nullable=True)
    )
    op.add_column("agent_run", sa.Column("graph_lease_until", DATETIME(fsp=6), nullable=True))
    op.create_table(
        "graph_checkpoint",
        sa.Column(
            "run_id",
            sa.String(32, collation="utf8mb4_bin"),
            sa.ForeignKey("agent_run.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("namespace", sa.String(128, collation="utf8mb4_bin"), primary_key=True),
        sa.Column("checkpoint_id", sa.String(64, collation="utf8mb4_bin"), primary_key=True),
        sa.Column("parent_id", sa.String(64, collation="utf8mb4_bin"), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.Column("writes", sa.JSON(), nullable=False),
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )


def downgrade():
    op.drop_table("graph_checkpoint")
    op.drop_column("agent_run", "graph_lease_until")
    op.drop_column("agent_run", "graph_owner")
