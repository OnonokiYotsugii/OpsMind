"""CPU embeddings. Downloads are allowed only by the explicit preparation command."""

from functools import lru_cache
from threading import Lock
from typing import Protocol

from opsmind.core.errors import BusinessError

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class Embedding(Protocol):
    def documents(self, texts: list[str]) -> list[list[float]]: ...
    def query(self, text: str) -> list[float]: ...


class LocalEmbedding:
    def __init__(self, cache: str, download: bool = False):
        from fastembed import TextEmbedding

        self.model = TextEmbedding(
            model_name=MODEL,
            cache_dir=cache,
            threads=2,
            local_files_only=not download,
        )
        self.lock = Lock()

    def documents(self, texts: list[str]) -> list[list[float]]:
        with self.lock:
            return [v.tolist() for v in self.model.passage_embed(texts, batch_size=16)]

    def query(self, text: str) -> list[float]:
        with self.lock:
            return next(self.model.query_embed(text)).tolist()


@lru_cache(maxsize=4)
def get_embedding(cache: str) -> LocalEmbedding:
    try:
        return LocalEmbedding(cache)
    except Exception:
        raise BusinessError(
            "embedding_unavailable", "Prepare the local embedding model first.", 503
        ) from None
