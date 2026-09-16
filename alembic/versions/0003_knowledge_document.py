"""Knowledge document registry; vectors live in local Chroma."""

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_document",
        sa.Column("id", sa.String(32, collation="utf8mb4_bin"), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        *[
            sa.Column(n, sa.String(size, collation="utf8mb4_bin"), nullable=False)
            for n, size in [
                ("document_type", 32),
                ("source", 200),
                ("version", 32),
                ("content_hash", 64),
                ("index_key", 64),
                ("status", 16),
            ]
        ],
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        sa.UniqueConstraint("source", "version", name="uq_knowledge_source_version"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )


def downgrade():
    op.drop_table("knowledge_document")
