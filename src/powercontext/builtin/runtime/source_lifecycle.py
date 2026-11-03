# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Propagate Source availability through an evidence dependency graph.

Each Scope owns an acyclic graph of registered Sources, Memory entries and Topic
Memories. Withdrawing or restoring a Source re-evaluates every dependent node
with its declared ``all``/``any`` policy, so content that lost its support stops
being generation evidence while its history stays readable.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from powercontext.artifacts import ArtifactRef
from powercontext.builtin.artifacts.memory.models import MemoryCitation
from powercontext.builtin.persistence.database import AsyncDatabase
from powercontext.builtin.persistence.tables import LIFECYCLE_NODES_TABLE
from powercontext.sources.models import SourceRef

Purpose = Literal["generation", "audit"]
Policy = Literal["all", "any"]


class SourceLifecycleError(ValueError):
    """Raised when a registration, event or resolution breaks the contract."""


class SourceLifecycleEvent(BaseModel):
    """One validated availability transition for a registered Source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    revision: int = Field(strict=True, ge=1)
    sequence: int = Field(strict=True, ge=1)
    available: bool = Field(strict=True)
    reason: str

    @field_validator("node_id", "reason")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("must be a non-blank string")  # noqa: TRY003
        return value


@dataclass(frozen=True)
class _Node:
    node_id: str
    family: str
    reference: dict[str, Any]
    parents: tuple[str, ...]
    policy: str
    revision: int
    sequence: int
    available: bool


class SourceLifecycleService:
    """Own the lifecycle graph of every Scope."""

    def __init__(self, database: AsyncDatabase, runtime: Any = None) -> None:
        self._database = database
        self._runtime = runtime
        self._hidden_cache: dict[str, set[str]] = {}

    def bind(self, runtime: Any) -> SourceLifecycleService:
        self._runtime = runtime
        return self

    def for_scope(self, scope_id: str, /) -> ScopedSourceLifecycle:
        return ScopedSourceLifecycle(self, scope_id)

    async def _sync(self, scope_id: str, nodes: dict[str, _Node]) -> None:
        """Mirror graph availability onto the native Memory entry state."""

        runtime = self._runtime
        if runtime is None:
            return
        from powercontext.builtin.runtime.models import GetMemoryEntryRequest

        memory_application = runtime.memory.for_scope(scope_id)
        page = await memory_application.list(include_inactive=True)
        states = {record.entry.entry_id: record.state for record in page.entries}
        context = await runtime._provider.get(scope_id)
        service = context.artifacts.memory
        for node in nodes.values():
            if node.family != "memory":
                continue
            citation = MemoryCitation.model_validate(node.reference)
            desired = "active" if node.available else "inactive"
            if states.get(citation.entry_id) == desired:
                continue
            result = await memory_application.get(GetMemoryEntryRequest(citation=citation))
            head = await service._backend.latest(citation.memory_ref.artifact_id)
            if node.available:
                await service.reactivate(head, entries=(result.entry,), reason="source lifecycle")
            else:
                await service.forget(head, entries=(result.entry,), reason="source lifecycle")

    async def hidden_topics(self, scope_id: str, /) -> set[str]:
        """Return artifact ids of Topic nodes that lost their support.

        Search runs on the hot path, so a contended database degrades to "no
        filtered Topics" instead of failing the caller's search.
        """

        cached = self._hidden_cache.get(scope_id)
        if cached is not None:
            return cached
        try:
            async with self._database.transaction() as connection:
                nodes = await _load_nodes(connection, scope_id)
        except Exception:  # noqa: BLE001 - a locked reader must not break search
            return set()
        return self._remember_hidden(scope_id, nodes)

    def _remember_hidden(self, scope_id: str, nodes: dict[str, _Node]) -> set[str]:
        hidden = {
            ArtifactRef.model_validate(node.reference).artifact_id
            for node in nodes.values()
            if node.family == "topic" and not node.available
        }
        self._hidden_cache[scope_id] = hidden
        return hidden


class ScopedSourceLifecycle:
    """Register evidence and apply availability events inside one Scope."""

    def __init__(self, service: SourceLifecycleService, scope_id: str) -> None:
        self._service = service
        self.scope_id = scope_id

    async def register_source(self, node_id: str, source_ref: SourceRef, *, revision: int = 1) -> None:
        await self._readable_source(source_ref)
        await self._register(
            node_id,
            family="source",
            reference=source_ref.model_dump(mode="json"),
            parents=(),
            policy="all",
            revision=revision,
        )

    async def register_memory(
        self,
        node_id: str,
        citation: MemoryCitation,
        *,
        parents: tuple[str, ...],
        policy: Policy,
    ) -> None:
        await self._readable_memory(citation)
        await self._register(
            node_id,
            family="memory",
            reference=citation.model_dump(mode="json"),
            parents=parents,
            policy=policy,
            revision=1,
        )

    async def register_topic(
        self,
        node_id: str,
        reference: ArtifactRef,
        *,
        parents: tuple[str, ...],
        policy: Policy,
    ) -> None:
        await self._readable_topic(reference)
        await self._register(
            node_id,
            family="topic",
            reference=reference.model_dump(mode="json"),
            parents=parents,
            policy=policy,
            revision=1,
        )

    async def apply(self, event: SourceLifecycleEvent) -> list[str]:
        """Apply one source availability event and return the active node ids."""

        async with self._service._database.transaction() as connection:
            nodes = await _load_nodes(connection, self.scope_id, for_update=True)
            node = nodes.get(event.node_id)
            if node is None or node.family != "source":
                raise SourceLifecycleError("event target is not a registered Source")
            if event.revision != node.revision:
                raise SourceLifecycleError("event revision does not match the registered revision")
            if event.sequence < node.sequence:
                raise SourceLifecycleError("event sequence went backwards")
            if event.sequence == node.sequence:
                if event.available != node.available:
                    raise SourceLifecycleError("event sequence was reused with a different state")
                # A replay is idempotent for the graph, but native state may still be
                # behind if an earlier attempt failed after the graph committed, so the
                # reconciliation below still has to run.
                active = _active_ids(nodes)
            else:
                await _store_node(
                    connection,
                    self.scope_id,
                    replace(node, sequence=event.sequence, available=event.available),
                )
                nodes[event.node_id] = replace(node, sequence=event.sequence, available=event.available)
                await self._propagate(connection, nodes)
                active = _active_ids(nodes)
        # Native writes open their own transaction, so they must run after the graph commits.
        await self._sync_native(nodes)
        self._service._remember_hidden(self.scope_id, nodes)
        return active

    async def resolve(self, node_id: str, *, purpose: Purpose) -> Any:
        """Return the original reference, refusing unavailable nodes for generation."""

        if purpose not in {"generation", "audit"}:
            raise SourceLifecycleError("unknown resolution purpose")
        async with self._service._database.transaction() as connection:
            nodes = await _load_nodes(connection, self.scope_id)
        node = nodes.get(node_id)
        if node is None:
            raise SourceLifecycleError("unknown lifecycle node")
        if purpose == "generation" and not node.available:
            raise SourceLifecycleError("node is not available for generation")
        return _rehydrate(node)

    async def _register(
        self,
        node_id: str,
        *,
        family: str,
        reference: dict[str, Any],
        parents: tuple[str, ...],
        policy: str,
        revision: int,
    ) -> None:
        if not isinstance(node_id, str) or not node_id.strip():
            raise SourceLifecycleError("node id must be a non-blank string")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise SourceLifecycleError("revision must be a positive integer")
        if policy not in {"all", "any"}:
            raise SourceLifecycleError("policy must be all or any")
        if family != "source":
            if not parents:
                raise SourceLifecycleError("a derived node needs at least one parent")
            if len(set(parents)) != len(parents):
                raise SourceLifecycleError("parents must not repeat")
            if node_id in parents:
                raise SourceLifecycleError("a node cannot depend on itself")

        async with self._service._database.transaction() as connection:
            nodes = await _load_nodes(connection, self.scope_id, for_update=True)
            existing = nodes.get(node_id)
            declared = (family, reference, tuple(parents), policy, revision)
            if existing is not None:
                if _signature(existing) != declared:
                    raise SourceLifecycleError("node id is already bound to a different declaration")
                return
            for parent in parents:
                if parent not in nodes:
                    raise SourceLifecycleError("parent must be registered first")
            available = (
                True
                if family == "source"
                else _evaluate(policy, [nodes[parent].available for parent in parents])
            )
            node = _Node(
                node_id=node_id,
                family=family,
                reference=reference,
                parents=tuple(parents),
                policy=policy,
                revision=revision,
                sequence=0,
                available=available,
            )
            await _store_node(connection, self.scope_id, node, create=True)
            nodes[node_id] = node
        await self._sync_native(nodes)
        self._service._remember_hidden(self.scope_id, nodes)

    async def _propagate(self, connection: AsyncConnection, nodes: dict[str, _Node]) -> None:
        for node in _dependency_order(nodes):
            if node.family == "source":
                continue
            available = _evaluate(node.policy, [nodes[parent].available for parent in node.parents])
            if available == node.available:
                continue
            await _store_node(connection, self.scope_id, replace(node, available=available))
            nodes[node.node_id] = replace(node, available=available)

    async def _sync_native(self, nodes: dict[str, _Node]) -> None:
        """Mirror graph availability onto native Memory and Topic state."""

        sync = getattr(self._service, "_sync", None)
        if sync is None:
            return
        await sync(self.scope_id, nodes)

    async def _readable_source(self, reference: SourceRef) -> None:
        runtime = self._service._runtime
        if runtime is None:
            return
        await runtime.records.for_scope(self.scope_id).get_source(reference.source_type, reference.source_id)

    async def _readable_memory(self, citation: MemoryCitation) -> None:
        runtime = self._service._runtime
        if runtime is None:
            return
        from powercontext.builtin.runtime.models import GetMemoryEntryRequest

        await runtime.memory.for_scope(self.scope_id).get(GetMemoryEntryRequest(citation=citation))

    async def _readable_topic(self, reference: ArtifactRef) -> None:
        runtime = self._service._runtime
        if runtime is None:
            return
        await runtime.records.for_scope(self.scope_id).get_artifact_revision(
            reference.family, reference.artifact_id, reference.revision
        )


def _evaluate(policy: str, parents: list[bool]) -> bool:
    return all(parents) if policy == "all" else any(parents)


def _signature(node: _Node) -> tuple[Any, ...]:
    return (node.family, node.reference, node.parents, node.policy, node.revision)


def _active_ids(nodes: dict[str, _Node]) -> list[str]:
    return sorted(node_id for node_id, node in nodes.items() if node.available)


def _dependency_order(nodes: dict[str, _Node]) -> list[_Node]:
    ordered: list[_Node] = []
    placed: set[str] = set()
    pending = list(nodes.values())
    while pending:
        progress = False
        remaining = []
        for node in pending:
            if all(parent in placed for parent in node.parents):
                ordered.append(node)
                placed.add(node.node_id)
                progress = True
            else:
                remaining.append(node)
        if not progress:
            raise SourceLifecycleError("the dependency graph contains a cycle")
        pending = remaining
    return ordered


def _rehydrate(node: _Node) -> Any:
    if node.family == "memory":
        return MemoryCitation.model_validate(node.reference)
    if node.family == "topic":
        return ArtifactRef.model_validate(node.reference)
    return SourceRef.model_validate(node.reference)


async def _load_nodes(
    connection: AsyncConnection,
    scope_id: str,
    *,
    for_update: bool = False,
) -> dict[str, _Node]:
    statement = select(LIFECYCLE_NODES_TABLE).where(LIFECYCLE_NODES_TABLE.c.scope_id == scope_id)
    if for_update:
        statement = statement.with_for_update()
    rows = (await connection.execute(statement)).mappings()
    return {
        str(row["node_id"]): _Node(
            node_id=str(row["node_id"]),
            family=str(row["family"]),
            reference=dict(row["reference"]),
            parents=tuple(row["parents"]),
            policy=str(row["policy"]),
            revision=int(row["revision"]),
            sequence=int(row["sequence"]),
            available=bool(row["available"]),
        )
        for row in rows
    }


async def _store_node(
    connection: AsyncConnection,
    scope_id: str,
    node: _Node,
    *,
    create: bool = False,
) -> None:
    values = {
        "scope_id": scope_id,
        "node_id": node.node_id,
        "family": node.family,
        "reference": node.reference,
        "parents": list(node.parents),
        "policy": node.policy,
        "revision": node.revision,
        "sequence": node.sequence,
        "available": node.available,
    }
    if create:
        await connection.execute(insert(LIFECYCLE_NODES_TABLE).values(**values))
        return
    await connection.execute(
        update(LIFECYCLE_NODES_TABLE)
        .where(
            LIFECYCLE_NODES_TABLE.c.scope_id == scope_id,
            LIFECYCLE_NODES_TABLE.c.node_id == node.node_id,
        )
        .values(**values)
    )


__all__ = ["SourceLifecycleError", "SourceLifecycleEvent", "SourceLifecycleService", "ScopedSourceLifecycle"]
