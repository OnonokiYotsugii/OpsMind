import asyncio
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from opsmind.core.config import Settings
from opsmind.core.errors import BusinessError
from opsmind.rag.embedding import get_embedding
from opsmind.rag.models import KnowledgeDocument
from opsmind.rag.schemas import DocumentInfo, SearchArgs
from opsmind.rag.service import KnowledgeService
from opsmind.rag.vector import VectorIndex

pytestmark = pytest.mark.integration


class ControlledEmbedding:
    """Only test transaction/index mechanics; semantic tests use the real model below."""

    def documents(self, texts):
        return [[1.0, 0.0, 0.0] for _ in texts]

    def query(self, text):
        return [1.0, 0.0, 0.0]


@pytest.fixture
def service(db_connection, tmp_path):
    def factory():
        return Session(
            bind=db_connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )

    settings = Settings(_env_file=None, rag_index_path=str(tmp_path / "index"))
    return KnowledgeService(factory, settings, ControlledEmbedding())


def import_sample(service, tmp_path):
    path = tmp_path / "manual.md"
    path.write_text("# 演示手册\nE102 表示供电电压异常。", encoding="utf-8")
    info = DocumentInfo(title="演示手册", source="test-manual", version="1", document_type="manual")
    return path, info, service.import_file(path, info)


def test_import_repeated_and_version_conflict(service, tmp_path):
    path, info, result = import_sample(service, tmp_path)
    assert service.import_file(path, info)["reused"]
    assert service.index.collection.count() == 1
    items = service.search(SearchArgs(query="E102"))["items"]
    assert items[0]["citation"] == f"KB-{result['id']}-0"
    assert service.search(SearchArgs(query="E102", version="missing"))["items"] == []
    path.write_text("changed", encoding="utf-8")
    with pytest.raises(BusinessError, match="new version"):
        service.import_file(path, info)


def test_partial_index_not_visible_and_retry_recovers(service, tmp_path, monkeypatch):
    original = service.index.upsert

    def fail_after_upsert(*args):
        original(*args)
        raise RuntimeError("Injected interruption")

    monkeypatch.setattr(service.index, "upsert", fail_after_upsert)
    with pytest.raises(RuntimeError):
        import_sample(service, tmp_path)
    assert service.index.collection.count() == 1
    assert service.search(SearchArgs(query="E102"))["items"] == []
    monkeypatch.setattr(service.index, "upsert", original)
    import_sample(service, tmp_path)
    assert len(service.search(SearchArgs(query="E102"))["items"]) == 1
    assert service.index.collection.count() == 1


def test_distance_filter(service, tmp_path, monkeypatch):
    import_sample(service, tmp_path)
    monkeypatch.setattr(service.embedding, "query", lambda text: [0.0, 1.0, 0.0])
    assert service.search(SearchArgs(query="unrelated"))["items"] == []


def test_restart_index(service, tmp_path):
    import_sample(service, tmp_path)
    service._index = VectorIndex(service.settings.rag_index_path)
    assert service.search(SearchArgs(query="E102"))["items"]


@pytest.mark.parametrize(
    argnames="suffix,content",
    ids=["unsupported", "oversize", "empty", "invalid-utf8"],
    argvalues=[(".pdf", b"x"), (".txt", b"x" * 200001), (".md", b"# heading"), (".txt", b"\xff")],
)
def test_bad_import(service, tmp_path, suffix, content):
    path = tmp_path / ("bad" + suffix)
    path.write_bytes(content)
    with pytest.raises((ValueError, UnicodeError)):
        service.import_file(
            path, DocumentInfo(title="bad", source="bad", version="1", document_type="manual")
        )
    with service.factory() as session:
        assert (
            session.scalar(select(KnowledgeDocument).where(KnowledgeDocument.source == "bad"))
            is None
        )


def test_real_multilingual_retrieval(service, request):
    if not request.config.getoption("--embedding"):
        pytest.skip("Use --embedding after explicit model preparation.")
    service._embedding = get_embedding(str(Path(".cache/embeddings").resolve()))
    service.import_file(
        Path("knowledge/demo-power.md"),
        DocumentInfo(title="演示说明书", source="real-demo", version="1", document_type="manual"),
    )
    hits = service.search(SearchArgs(query="DEMO-24V E102 供电电压异常"))["items"]
    assert hits and "E102" in hits[0]["text"]
    assert not service.search(SearchArgs(query="如何制作草莓蛋糕"))["items"]


def test_agent_search_and_citations(service, tmp_path):
    from opsmind.agent.runtime import AgentRuntime
    from opsmind.agent.store import AgentStore
    from opsmind.llm.tool_protocol import ToolTurn
    from tests.integration.test_agent import ScriptedModel, call

    _, _, result = import_sample(service, tmp_path)
    store = AgentStore(service.factory, service.settings)
    model = ScriptedModel(
        [
            call("search_knowledge", {"query": "E102"}),
            ToolTurn({"role": "assistant", "content": f"可能供电异常 [KB-{result['id']}-0]"}, None),
        ]
    )
    runtime = AgentRuntime(store, model)
    runtime.knowledge = service
    run = asyncio.run(runtime.create("查询 E102", "EMP-1001"))
    assert run.status == "completed" and "参考来源" in run.result
    assert run.pending_action is None


def test_search_api(service, tmp_path):
    from fastapi.testclient import TestClient

    from opsmind.main import create_app

    import_sample(service, tmp_path)
    # The API resolves a real local embedding; no ready source avoids loading it here.
    app = create_app(service.settings)
    app.state.session_factory = service.factory
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/knowledge/search", json={"query": "E102", "source": "absent"}
        )
        assert response.status_code == 200 and response.json()["items"] == []
        assert client.post("/api/v1/knowledge/search", json={"query": " "}).status_code == 422


def test_rebuild_restores_missing_vector(service, tmp_path):
    path, info, result = import_sample(service, tmp_path)
    service.index.collection.delete(ids=[f"{result['id']}-0"])
    assert service.index.collection.count() == 0
    restored = service.import_file(path, info, rebuild=True)
    assert restored["id"] == result["id"] and service.index.collection.count() == 1


def test_agent_budget_prevents_search_execution(service, tmp_path, monkeypatch):
    from opsmind.agent.runtime import AgentRuntime
    from opsmind.agent.store import AgentStore
    from tests.integration.test_agent import ScriptedModel, call

    store = AgentStore(
        service.factory, service.settings.model_copy(update={"agent_max_tool_calls": 1})
    )
    model = ScriptedModel(
        [
            call("get_equipment", {"equipment_no": "EQ-10023"}),
            call("search_knowledge", {"query": "E102"}, "second"),
        ]
    )
    runtime = AgentRuntime(store, model)

    def forbidden(args):
        raise AssertionError("Search must not execute after budget exhaustion")

    monkeypatch.setattr(runtime.knowledge, "search", forbidden)
    result = asyncio.run(runtime.create("查询", "EMP-1001"))
    assert result.error_code == "max_tool_calls_exceeded"
