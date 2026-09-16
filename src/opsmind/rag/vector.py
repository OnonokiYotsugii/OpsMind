"""Explicit vectors prevent accidental default model downloads."""

from opsmind.rag.chunking import Chunk
from opsmind.rag.embedding import MODEL

INDEX_KEY = "minilm-multi-c100-v1"


class VectorIndex:
    def __init__(self, path: str):
        import chromadb
        from chromadb.config import Settings

        self.client = chromadb.PersistentClient(
            path=path, settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection(
            "opsmind-" + INDEX_KEY,
            embedding_function=None,
            metadata={"hnsw:space": "cosine", "embedding_model": MODEL},
        )

    def upsert(self, doc_id: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        self.collection.upsert(
            ids=[f"{doc_id}-{i}" for i in range(len(chunks))],
            embeddings=vectors,
            documents=[c.text for c in chunks],
            metadatas=[
                {"document_id": doc_id, "heading": c.heading, "line": c.line} for c in chunks
            ],
        )

    def query(self, vector: list[float], ids: list[str], limit: int) -> dict:
        return self.collection.query(
            query_embeddings=[vector],
            where={"document_id": {"$in": ids}},
            n_results=limit,
            include=["documents", "metadatas", "distances"],
        )
