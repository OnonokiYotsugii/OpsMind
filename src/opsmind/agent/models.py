from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, Integer, Text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from opsmind.db.models import Base, Updated, code_type


class AgentRun(Updated, Base):
    __tablename__ = "agent_run"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running','waiting_confirmation','completed','failed','rejected')",
            name="status",
        ),
    )
    id: Mapped[str] = mapped_column(code_type(32), primary_key=True)
    actor_no: Mapped[str] = mapped_column(code_type(64))
    status: Mapped[str] = mapped_column(code_type(32))
    messages: Mapped[list] = mapped_column(JSON)
    events: Mapped[list] = mapped_column(JSON)
    pending_action: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    result: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(code_type(64))
    steps: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    max_steps: Mapped[int] = mapped_column(Integer)
    max_tool_calls: Mapped[int] = mapped_column(Integer)
    time_budget_ms: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
