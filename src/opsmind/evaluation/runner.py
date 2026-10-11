"""Rollback-isolated evaluation against local opsmind_test only."""

import asyncio
import hashlib
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from opsmind.agent.models import AgentRun
from opsmind.agent.runtime import AgentRuntime
from opsmind.agent.store import AgentStore
from opsmind.core.config import Settings
from opsmind.db.models import Ticket
from opsmind.db.seed import seed_demo
from opsmind.db.session import create_db_engine, validated_mysql_url
from opsmind.evaluation.dataset import Case, load_cases
from opsmind.evaluation.fixtures import ScriptedClient
from opsmind.evaluation.scoring import aggregate, extract_calls, grade, subset
from opsmind.llm.client import OpenAICompatibleClient
from opsmind.observability.trace import build_trace
from opsmind.rag.schemas import DocumentInfo, SearchArgs
from opsmind.rag.service import KnowledgeService
from opsmind.rag.vector import VectorIndex


def test_url(settings: Settings) -> str:
    raw = settings.test_database_url.get_secret_value()
    url = validated_mysql_url(raw)
    if url.host not in {"localhost", "127.0.0.1"} or url.database != "opsmind_test":
        raise ValueError("Evaluation requires local opsmind_test.")
    for normal in (settings.database_url, settings.migration_database_url):
        if (
            normal.get_secret_value()
            and validated_mysql_url(normal.get_secret_value()).database == url.database
        ):
            raise ValueError("Evaluation database must differ from application databases.")
    return raw


def tickets_snapshot(factory) -> dict:
    with factory() as session:
        return {
            r.id: tuple(getattr(r, c.name) for c in Ticket.__table__.columns)
            for r in session.scalars(select(Ticket))
        }


def load_corpus(service: KnowledgeService, root: Path) -> None:
    for source in ("demo-power", "demo-process"):
        service.import_file(
            root / "knowledge" / f"{source}.md",
            DocumentInfo(title=source, source=source, version="1.0", document_type="manual"),
        )


async def run_case(case: Case, factory, settings: Settings, mode: str, index, root: Path) -> dict:
    started = time.monotonic()
    service = KnowledgeService(factory, settings, index=index)
    before = tickets_snapshot(factory)
    if case.expected_sources is not None or any(
        t.tool == "search_knowledge" for t in case.required_tools
    ):
        await asyncio.to_thread(load_corpus, service, root)
    if case.kind == "retrieval":
        data = await asyncio.to_thread(service.search, SearchArgs(query=case.prompt))
        hits = data["items"]
        score = grade(case, "completed", "", [], hits, True, 0, None)
        return {
            "id": case.id,
            "category": case.category,
            "kind": case.kind,
            **score,
            "runtime_error": False,
            "wall_ms": round((time.monotonic() - started) * 1000),
            "metrics": {},
            "retrieved_sources": [h["source"] for h in hits],
        }
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as http:
        client = (
            ScriptedClient(case.scripted)
            if mode == "scripted"
            else OpenAICompatibleClient(settings, http)
        )
        runtime = AgentRuntime(AgentStore(factory, settings), client)
        runtime.knowledge = service
        run = await runtime.create(case.prompt, case.actor)
        if case.approval != "none" and run.pending_action:
            action = run.pending_action
            # Even synthetic approvals must match the predeclared tool and parameters.
            matches = any(
                e.tool == action["tool"] and subset(e.arguments, action["arguments"])
                for e in case.required_tools
            )
            if matches:
                run = await runtime.decide(
                    run.id, case.actor, action["action_id"], case.approval == "approve"
                )
    after = tickets_snapshot(factory)
    writes = sum(before.get(k) != after.get(k) for k in before.keys() | after.keys())
    with factory() as session:
        messages = session.get(AgentRun, run.id).messages
    retrievals = [e for e in run.events if e["kind"] == "retrieval"]
    hits = [h for e in retrievals for h in e["items"]]
    receipts = [e for e in run.events if e["kind"] == "decision" and e.get("approved") and e["ok"]]
    score = grade(
        case,
        run.status,
        run.result or "",
        extract_calls(messages),
        hits,
        bool(retrievals),
        writes,
        run.error_code,
        len(receipts),
    )
    trace = build_trace(run)
    return {
        "id": case.id,
        "category": case.category,
        "kind": case.kind,
        **score,
        "runtime_error": run.status == "failed",
        "wall_ms": round((time.monotonic() - started) * 1000),
        "metrics": trace["metrics"],
        "trace": trace,
        "observed_status": run.status,
        "observed_writes": writes,
    }


def evaluate(
    dataset: Path,
    settings: Settings,
    mode: str = "scripted",
    limit: int = 100,
    allow_test_writes: bool = False,
) -> dict:
    if mode not in {"scripted", "live"}:
        raise ValueError("Unknown evaluation mode.")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be 1..100")
    loaded = load_cases(dataset)
    cases = [c for c in loaded if mode == "scripted" or not c.scripted_only][:limit]
    if not cases:
        raise ValueError("Select at least one case.")
    if mode == "live" and any(c.approval == "approve" for c in cases) and not allow_test_writes:
        raise ValueError("Live approval fixtures require --allow-test-writes (test DB only).")
    engine = create_db_engine(test_url(settings))
    root = Path(__file__).resolve().parents[3]
    run_id = uuid4().hex
    index = VectorIndex(str(root / ".data" / "evaluation" / run_id))
    results = []
    try:
        for case in cases:
            with engine.connect() as connection:
                transaction = connection.begin()

                def factory():
                    return Session(
                        bind=connection,
                        expire_on_commit=False,
                        join_transaction_mode="create_savepoint",
                    )

                started = time.monotonic()
                try:
                    with factory() as session:
                        seed_demo(session)
                    result = asyncio.run(run_case(case, factory, settings, mode, index, root))
                except Exception as exc:
                    # Do not echo exception bodies containing SQL, file content or credentials.
                    result = {
                        "id": case.id,
                        "category": case.category,
                        "kind": case.kind,
                        "passed": False,
                        "checks": {
                            "evaluation_execution": False,
                            **({"classification": False} if case.expected_label else {}),
                        },
                        "tool_correct": False if case.kind == "agent" else None,
                        "retrieval_correct": False if case.expected_sources is not None else None,
                        "runtime_error": True,
                        "wall_ms": round((time.monotonic() - started) * 1000),
                        "error_type": type(exc).__name__,
                    }
                finally:
                    transaction.rollback()
                results.append(result)
    finally:
        engine.dispose()
    return {
        "schema_version": 1,
        "run_id": run_id,
        "mode": mode,
        "created_at": datetime.now(UTC).isoformat(),
        "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "excluded_scripted_only": [c.id for c in loaded if mode == "live" and c.scripted_only],
        "model": settings.llm_model if mode == "live" else "scripted-fixture",
        "summary": aggregate(results),
        "results": results,
    }
