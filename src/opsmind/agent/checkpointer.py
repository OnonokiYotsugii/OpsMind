"""Full-snapshot MySQL saver for the project's single sequential graph.

No pickle, file paths, external checkpoint IDs or admin deletion API are exposed.
Pending writes follow LangGraph's per-task/index overwrite rules.
"""

import asyncio
import base64
from collections.abc import Callable, Iterator
from threading import RLock

from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    CheckpointTuple,
    get_checkpoint_metadata,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from opsmind.agent.checkpoint_models import GraphCheckpoint
from opsmind.agent.execution import check_owner
from opsmind.agent.models import AgentRun


class MySQLSaver(BaseCheckpointSaver[int]):
    def __init__(self, factory: Callable[[], Session]):
        super().__init__()
        self.factory = factory
        self.lock = RLock()

    def pack(self, value) -> dict:
        kind, data = self.serde.dumps_typed(value)
        return {"type": kind, "data": base64.b64encode(data).decode("ascii")}

    def unpack(self, value: dict):
        return self.serde.loads_typed((value["type"], base64.b64decode(value["data"])))

    @staticmethod
    def config(run_id: str, namespace: str, checkpoint_id: str) -> dict:
        return {
            "configurable": {
                "thread_id": run_id,
                "checkpoint_ns": namespace,
                "checkpoint_id": checkpoint_id,
            }
        }

    def as_tuple(self, row: GraphCheckpoint) -> CheckpointTuple:
        return CheckpointTuple(
            config=self.config(row.run_id, row.namespace, row.checkpoint_id),
            checkpoint=self.unpack(row.payload),
            metadata=self.unpack(row.meta),
            parent_config=self.config(row.run_id, row.namespace, row.parent_id)
            if row.parent_id
            else None,
            pending_writes=[
                (w["task"], w["channel"], self.unpack(w["value"])) for w in row.writes.values()
            ],
        )

    def get_tuple(self, config) -> CheckpointTuple | None:
        values = config["configurable"]
        with self.lock, self.factory() as session:
            query = select(GraphCheckpoint).where(
                GraphCheckpoint.payload["type"].as_string() != "pending",
                GraphCheckpoint.run_id == values["thread_id"],
                GraphCheckpoint.namespace == values.get("checkpoint_ns", ""),
            )
            if values.get("checkpoint_id"):
                query = query.where(GraphCheckpoint.checkpoint_id == values["checkpoint_id"])
            row = session.scalar(query.order_by(GraphCheckpoint.checkpoint_id.desc()).limit(1))
            return self.as_tuple(row) if row else None

    def list(self, config, *, filter=None, before=None, limit=None) -> Iterator[CheckpointTuple]:
        # Internal history inspection; callers never accept arbitrary config from HTTP.
        with self.lock, self.factory() as session:
            query = select(GraphCheckpoint).where(
                GraphCheckpoint.payload["type"].as_string() != "pending"
            )
            if config:
                c = config["configurable"]
                query = query.where(
                    GraphCheckpoint.run_id == c["thread_id"],
                    GraphCheckpoint.namespace == c.get("checkpoint_ns", ""),
                )
            if before:
                query = query.where(
                    GraphCheckpoint.checkpoint_id < before["configurable"]["checkpoint_id"]
                )
            rows = session.scalars(query.order_by(GraphCheckpoint.checkpoint_id.desc()))
            results = []
            for row in rows:
                item = self.as_tuple(row)
                if filter and any(item.metadata.get(k) != v for k, v in filter.items()):
                    continue
                if limit is not None and len(results) >= limit:
                    break
                results.append(item)
        yield from results

    def put(self, config, checkpoint, metadata, new_versions):
        c = config["configurable"]
        key = (c["thread_id"], c.get("checkpoint_ns", ""), checkpoint["id"])
        with self.lock, self.factory() as session, session.begin():
            run = session.get(AgentRun, key[0], with_for_update=True)
            check_owner(run)
            row = session.get(GraphCheckpoint, key, with_for_update=True)
            if row is None:
                row = GraphCheckpoint(
                    run_id=key[0], namespace=key[1], checkpoint_id=key[2], writes={}
                )
                session.add(row)
            row.parent_id = c.get("checkpoint_id")
            row.payload = self.pack(checkpoint)
            row.meta = self.pack(get_checkpoint_metadata(config, metadata))
        return self.config(*key)

    def put_writes(self, config, writes, task_id, task_path="") -> None:
        c = config["configurable"]
        key = (c["thread_id"], c.get("checkpoint_ns", ""), c["checkpoint_id"])
        with self.lock, self.factory() as session, session.begin():
            run = session.get(AgentRun, key[0], with_for_update=True)
            check_owner(run)
            row = session.get(GraphCheckpoint, key, with_for_update=True)
            if row is None:
                # LangGraph may schedule pending writes before the full snapshot put.
                row = GraphCheckpoint(
                    run_id=key[0],
                    namespace=key[1],
                    checkpoint_id=key[2],
                    payload={"type": "pending"},
                    meta={},
                    writes={},
                )
                session.add(row)
            saved = dict(row.writes)
            for index, (channel, value) in enumerate(writes):
                index = WRITES_IDX_MAP.get(channel, index)
                write_key = f"{task_id}:{index}"
                if index >= 0 and write_key in saved:
                    continue
                saved[write_key] = {
                    "task": task_id,
                    "channel": channel,
                    "value": self.pack(value),
                    "path": task_path,
                }
            row.writes = saved

    async def aget_tuple(self, config):
        return await asyncio.to_thread(self.get_tuple, config)

    async def alist(self, config, *, filter=None, before=None, limit=None):
        rows = await asyncio.to_thread(
            lambda: list(self.list(config, filter=filter, before=before, limit=limit))
        )
        for row in rows:
            yield row

    async def aput(self, config, checkpoint, metadata, new_versions):
        return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)

    async def aput_writes(self, config, writes, task_id, task_path=""):
        await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)
