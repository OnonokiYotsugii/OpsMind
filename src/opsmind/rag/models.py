from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from opsmind.db.models import Base, Created, code_type


class KnowledgeDocument(Created, Base):
    __tablename__ = "knowledge_document"
    __table_args__ = (UniqueConstraint("source", "version", name="uq_knowledge_source_version"),)
    id: Mapped[str] = mapped_column(code_type(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    document_type: Mapped[str] = mapped_column(code_type(32))
    source: Mapped[str] = mapped_column(code_type(200))
    version: Mapped[str] = mapped_column(code_type(32))
    content_hash: Mapped[str] = mapped_column(code_type(64))
    index_key: Mapped[str] = mapped_column(code_type(64))
    status: Mapped[str] = mapped_column(code_type(16))
    chunk_count: Mapped[int] = mapped_column(Integer)
