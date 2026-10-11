from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from opsmind.db.models import Base, Created, code_type


class GraphCheckpoint(Created, Base):
    __tablename__ = "graph_checkpoint"
    run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_run.id", ondelete="RESTRICT"), primary_key=True
    )
    namespace: Mapped[str] = mapped_column(code_type(128), primary_key=True)
    checkpoint_id: Mapped[str] = mapped_column(code_type(64), primary_key=True)
    parent_id: Mapped[str | None] = mapped_column(code_type(64))
    payload: Mapped[dict] = mapped_column(JSON)
    meta: Mapped[dict] = mapped_column(JSON)
    writes: Mapped[dict] = mapped_column(JSON, default=dict)
