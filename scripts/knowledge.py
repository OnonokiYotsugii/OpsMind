"""Explicit local model preparation, trusted-file ingestion and search."""

import argparse
import json
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from opsmind.core.config import Settings
from opsmind.db.session import create_db_engine
from opsmind.rag.embedding import LocalEmbedding
from opsmind.rag.schemas import DocumentInfo, SearchArgs
from opsmind.rag.service import KnowledgeService


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare")
    ingest = commands.add_parser("import")
    ingest.add_argument("path", type=Path)
    ingest.add_argument(
        "--rebuild", action="store_true", help="Rebuild this immutable document index."
    )
    ingest.add_argument("--title", required=True)
    ingest.add_argument("--source", required=True)
    ingest.add_argument("--version", required=True)
    ingest.add_argument("--document-type", default="manual")
    search = commands.add_parser("search")
    search.add_argument("query")
    search.add_argument("--source")
    search.add_argument("--version")
    args = parser.parse_args()
    settings = Settings()
    if args.command == "prepare":
        embedding = LocalEmbedding(settings.rag_model_cache, download=True)
        print("Local model ready. Dimension:", len(embedding.query("设备供电报警")))
        return
    engine = create_db_engine(settings.database_url.get_secret_value())
    try:
        service = KnowledgeService(sessionmaker(engine, expire_on_commit=False), settings)
        if args.command == "import":
            result = service.import_file(
                args.path,
                DocumentInfo(
                    title=args.title,
                    source=args.source,
                    version=args.version,
                    document_type=args.document_type,
                ),
                rebuild=args.rebuild,
            )
        else:
            result = service.search(
                SearchArgs(query=args.query, source=args.source, version=args.version)
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
