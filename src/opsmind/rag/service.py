"""SQL ready state gates visibility of non-transactional vector writes."""

import hashlib
import re
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from opsmind.core.config import Settings
from opsmind.core.errors import BusinessError
from opsmind.rag.chunking import split_document
from opsmind.rag.embedding import Embedding, get_embedding
from opsmind.rag.models import KnowledgeDocument
from opsmind.rag.schemas import DocumentInfo, SearchArgs
from opsmind.rag.vector import INDEX_KEY, VectorIndex


def exact_alarm_heading(query: str, heading: str) -> bool:
    """Allow explicit model + alarm matches among vector candidates, not fuzzy guesses."""

    def identifiers(text: str) -> tuple[set[str], set[str]]:
        text = text.upper()
        models = set(re.findall(r"(?<![A-Z0-9-])[A-Z][A-Z0-9]*-[A-Z0-9]+(?![A-Z0-9-])", text))
        alarms = set(re.findall(r"(?<![A-Z0-9])E[0-9]{3,5}(?![A-Z0-9])", text))
        return models, alarms

    models, alarms = identifiers(query)
    heading_models, heading_alarms = identifiers(heading)
    return bool(models and alarms and models <= heading_models and alarms <= heading_alarms)


class KnowledgeService:
    def __init__(
        self,
        factory: Callable[[], Session],
        settings: Settings,
        embedding: Embedding | None = None,
        index: VectorIndex | None = None,
    ):
        self.factory = factory
        self.settings = settings
        self._embedding = embedding
        self._index = index

    @property
    def embedding(self) -> Embedding:
        return self._embedding or get_embedding(self.settings.rag_model_cache)

    @property
    def index(self) -> VectorIndex:
        if self._index is None:
            self._index = VectorIndex(self.settings.rag_index_path)
        return self._index

    def import_file(self, path: Path, info: DocumentInfo, rebuild: bool = False) -> dict:
        if path.suffix.lower() not in {".md", ".txt"}:
            raise ValueError("Only UTF-8 Markdown and TXT are supported.")
        with path.open("rb") as stream:
            raw = stream.read(200_001)
        if len(raw) > 200_000:
            raise ValueError("Document exceeds 200 KB.")
        text = raw.decode("utf-8-sig").replace("\r\n", "\n")
        chunks = split_document(text)
        if not chunks or len(chunks) > 1000:
            raise ValueError("Document must contain 1 to 1000 chunks.")
        digest = hashlib.sha256(text.encode()).hexdigest()
        with self.factory() as session, session.begin():
            row = session.scalar(
                select(KnowledgeDocument)
                .where(
                    KnowledgeDocument.source == info.source,
                    KnowledgeDocument.version == info.version,
                )
                .with_for_update()
            )
            if row:
                if (
                    row.content_hash != digest
                    or row.index_key != INDEX_KEY
                    or row.title != info.title
                    or row.document_type != info.document_type
                ):
                    raise BusinessError(
                        "document_version_conflict", "Changed documents require a new version.", 409
                    )
                if row.status == "ready" and not rebuild:
                    return {
                        "id": row.id,
                        "status": "ready",
                        "chunks": row.chunk_count,
                        "reused": True,
                    }
                doc_id = row.id
                row.status = "indexing"
            else:
                doc_id = uuid4().hex
                session.add(
                    KnowledgeDocument(
                        id=doc_id,
                        **info.model_dump(),
                        content_hash=digest,
                        index_key=INDEX_KEY,
                        status="indexing",
                        chunk_count=len(chunks),
                    )
                )
        # No database transaction is held during embedding or vector IO.
        # Retries use identical IDs. Partial writes stay invisible until SQL marks ready.
        vectors = self.embedding.documents([c.text for c in chunks])
        self.index.upsert(doc_id, chunks, vectors)
        with self.factory() as session, session.begin():
            row = session.get(KnowledgeDocument, doc_id)
            row.status = "ready"
        return {"id": doc_id, "status": "ready", "chunks": len(chunks), "reused": False}

    def search(self, args: SearchArgs) -> dict:
        with self.factory() as session:
            query = select(KnowledgeDocument).where(
                KnowledgeDocument.status == "ready",
                KnowledgeDocument.index_key == INDEX_KEY,
            )
            if args.source:
                query = query.where(KnowledgeDocument.source == args.source)
            if args.version:
                query = query.where(KnowledgeDocument.version == args.version)
            docs = {
                r.id: {"title": r.title, "source": r.source, "version": r.version}
                for r in session.scalars(query)
            }
        if not docs:
            return {"items": [], "note": "No ready documents match. Do not invent an answer."}
        try:
            hits = self.index.query(self.embedding.query(args.query), list(docs), args.limit)
        except BusinessError:
            raise
        except Exception:
            raise BusinessError(
                "knowledge_unavailable", "Knowledge index is unavailable.", 503
            ) from None
        items = []
        for cid, text, meta, distance in zip(
            hits["ids"][0],
            hits["documents"][0],
            hits["metadatas"][0],
            hits["distances"][0],
            strict=True,
        ):
            if distance > self.settings.rag_max_distance and not exact_alarm_heading(
                args.query, meta["heading"]
            ):
                continue
            items.append(
                {
                    "citation": "KB-" + cid,
                    **docs[meta["document_id"]],
                    "heading": meta["heading"],
                    "line": meta["line"],
                    "text": text,
                    "distance": round(distance, 4),
                }
            )
        return {
            "items": items,
            "note": "Reference only. Distance is not confidence; versions may differ.",
        }
