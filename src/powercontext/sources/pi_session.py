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

"""Capture the raw visible events of one selected Pi session branch.

A Pi archive is a tree: each entry points at its ``parentId``, so one leaf
selects a single history path. This module turns that path into one immutable
Source per visible event and keeps a durable checkpoint so a later run only
imports events the branch has not delivered yet.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from pydantic import BaseModel, model_validator

from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources import (
    TEXT_EVIDENCE_PROJECTION_KEY,
    AdapterSourceDefinition,
    ConnectorRunCompletion,
    ConnectorRunSession,
    ConnectorRunStatus,
    TextEvidence,
)
from powercontext.sources.models import Source, SourceMaterialization

PI_EVENT_SOURCE_NAME = "pi-event"
PI_EVENT_SOURCE_VERSION = "1"
PI_SESSION_CONNECTOR_NAME = "pi-session-history"
PI_SESSION_CONNECTOR_VERSION = "1"
_CHECKPOINT_VERSION = 1


class PiSessionInput(BaseModel):
    """One offline Pi archive plus the leaf that selects its history path."""

    content: bytes
    leaf_id: str | None = None


class PiEventInput(BaseModel):
    """One visible event on the selected branch, including its raw record."""

    session_id: str
    event_id: str
    parent_id: str | None
    event_type: str
    role: str
    content: str
    record: dict[str, Any]


class PiEventSource(Source):
    """Captured Pi event whose identity is the session and event id."""

    materialization: Literal[SourceMaterialization.CAPTURED] = SourceMaterialization.CAPTURED
    source_id: str
    session_id: str
    event_id: str
    parent_id: str | None
    event_type: str
    role: str
    content: str
    record: dict[str, Any]

    @model_validator(mode="after")
    def validate_event_identity(self) -> PiEventSource:
        expected = pi_event_source_id(self.session_id, self.event_id)
        if self.source_id != expected:
            raise ValueError("source_id must be the pi event identity")  # noqa: TRY003
        if self.name != expected:
            raise ValueError("name must equal source_id")  # noqa: TRY003
        return self


def pi_event_source_id(session_id: str, event_id: str) -> str:
    """Return the delimiter-safe identity ``pi:<session>:<event>``."""

    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session_id must be a non-empty string")  # noqa: TRY003
    if not isinstance(event_id, str) or not event_id.strip():
        raise ValueError("event_id must be a non-empty string")  # noqa: TRY003
    identity = f"pi:{quote(session_id, safe='')}:{quote(event_id, safe='')}"
    if len(identity) > MAX_SOURCE_ID_LENGTH:
        raise ValueError(f"source_id must not exceed {MAX_SOURCE_ID_LENGTH} characters")  # noqa: TRY003
    return identity


def parse_pi_session(value: PiSessionInput) -> tuple[PiEventInput, ...]:
    """Return the visible events of the selected branch, ordered root to leaf."""

    records = _load_records(_decode_content(value.content))
    session_id = _validated_header(records[0])
    graph, order = _build_graph(records[1:])
    leaf_id = _selected_leaf(value.leaf_id, graph, order)
    if leaf_id is None:
        return ()

    events: list[PiEventInput] = []
    for record in _branch_records(graph, leaf_id):
        event = _event_from_record(session_id, record)
        if event is not None:
            events.append(event)
    return tuple(events)


def _decode_content(content: bytes) -> str:
    if not isinstance(content, (bytes, bytearray, memoryview)):
        raise ValueError("session content must be bytes")  # noqa: TRY003
    try:
        return bytes(content).decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("session content must be valid UTF-8") from error  # noqa: TRY003


def _load_records(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSON record: {error}") from error  # noqa: TRY003
        if not isinstance(record, dict):
            raise ValueError("every session record must be a JSON object")  # noqa: TRY003
        records.append(record)
    if not records:
        raise ValueError("session archive must start with a session record")  # noqa: TRY003
    return records


def _validated_header(header: dict[str, Any]) -> str:
    if header.get("type") != "session":
        raise ValueError("first record must be a session record")  # noqa: TRY003
    if header.get("version") != 3:
        raise ValueError("session version must be 3")  # noqa: TRY003
    session_id = header.get("id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session id must be a non-empty string")  # noqa: TRY003
    return session_id


def _build_graph(records: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    graph: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for record in records:
        event_id = record.get("id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("every record must declare a non-empty id")  # noqa: TRY003
        if event_id in graph:
            raise ValueError(f"duplicate record id {event_id!r}")  # noqa: TRY003
        parent_id = record.get("parentId")
        if parent_id is not None:
            if not isinstance(parent_id, str) or not parent_id.strip():
                raise ValueError("parentId must be null or a non-empty string")  # noqa: TRY003
            if parent_id not in graph:
                raise ValueError(f"record {event_id!r} references unknown parent {parent_id!r}")  # noqa: TRY003
        graph[event_id] = record
        order.append(event_id)
    return graph, order


def _selected_leaf(leaf_id: str | None, graph: dict[str, dict[str, Any]], order: list[str]) -> str | None:
    if leaf_id is None:
        return order[-1] if order else None
    if not isinstance(leaf_id, str) or leaf_id not in graph:
        raise ValueError(f"unknown leaf id {leaf_id!r}")  # noqa: TRY003
    return leaf_id


def _branch_records(graph: dict[str, dict[str, Any]], leaf_id: str) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    visited: set[str] = set()
    current: str | None = leaf_id
    while current is not None:
        if current in visited:
            raise ValueError("session records form a cycle")  # noqa: TRY003
        visited.add(current)
        record = graph[current]
        chain.append(record)
        parent = record.get("parentId")
        current = parent if isinstance(parent, str) else None
    chain.reverse()
    return chain


def _event_from_record(session_id: str, record: dict[str, Any]) -> PiEventInput | None:
    event_type = record.get("type")
    if not isinstance(event_type, str):
        return None

    if event_type == "message":
        message = record.get("message")
        if not isinstance(message, dict):
            return None
        role = message.get("role")
        if not isinstance(role, str) or not role:
            return None
        body = _message_body(role, message)
    elif event_type in {"compaction", "branch_summary"}:
        role = event_type
        summary = record.get("summary")
        body = summary if isinstance(summary, str) else ""
    elif event_type == "custom_message":
        role = "custom"
        body = _join_blocks(record.get("content"))
    else:
        return None

    if not body:
        return None

    parent_id = record.get("parentId")
    return PiEventInput(
        session_id=session_id,
        event_id=record["id"],
        parent_id=parent_id if isinstance(parent_id, str) else None,
        event_type=event_type,
        role=role,
        content=f"{role}: {body}",
        record=record,
    )


def _message_body(role: str, message: dict[str, Any]) -> str:
    if role == "toolResult":
        tool_name = message.get("toolName")
        call_id = message.get("toolCallId")
        text = _join_blocks(message.get("content"))
        return f"[tool_result {_as_text(tool_name)} {_as_text(call_id)}] {text}"
    if role == "bashExecution":
        return f"$ {_as_text(message.get('command'))}\n{_as_text(message.get('output'))}"
    return _join_blocks(message.get("content"))


def _join_blocks(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = [_block_text(block) for block in content]
    return "\n".join(part for part in parts if part)


def _block_text(block: object) -> str:
    if isinstance(block, str):
        return block
    if not isinstance(block, dict):
        return ""
    block_type = block.get("type")
    if block_type == "text":
        text = block.get("text")
        return text if isinstance(text, str) else ""
    if block_type == "toolCall":
        return _tool_call_marker(block)
    return ""  # thinking, image and unknown blocks never become evidence text


def _tool_call_marker(block: dict[str, Any]) -> str:
    arguments = block.get("arguments")
    try:
        encoded = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        encoded = "null"
    return f"[tool_call {_as_text(block.get('name'))} {_as_text(block.get('id'))}] {encoded}"


def _as_text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _record_digest(record: dict[str, Any]) -> str:
    encoded = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _imported_records(checkpoint: object) -> dict[str, str]:
    if checkpoint is None:
        return {}
    if not isinstance(checkpoint, dict):
        raise ValueError("connector checkpoint must be a JSON object")  # noqa: TRY003
    records = checkpoint.get("records")
    if records is None:
        return {}
    if not isinstance(records, dict):
        raise ValueError("connector checkpoint records must be a JSON object")  # noqa: TRY003
    return {str(identity): str(digest) for identity, digest in records.items()}


class PiSessionConnector:
    """Import the events of one selected branch without repeating shared history."""

    name = PI_SESSION_CONNECTOR_NAME
    version = PI_SESSION_CONNECTOR_VERSION
    source_definitions = frozenset({PI_EVENT_SOURCE_NAME})

    def __init__(self, path: str | Path, leaf_id: str | None = None) -> None:
        self._path = Path(path)
        self._leaf_id = leaf_id

    async def run(self, session: ConnectorRunSession, /) -> ConnectorRunCompletion:
        events = parse_pi_session(
            PiSessionInput(content=self._path.read_bytes(), leaf_id=self._leaf_id)
        )
        imported = _imported_records(session.checkpoint)

        pending: list[tuple[str, str, PiEventInput]] = []
        for event in events:
            identity = pi_event_source_id(event.session_id, event.event_id)
            digest = _record_digest(event.record)
            recorded = imported.get(identity)
            if recorded is None:
                pending.append((identity, digest, event))
            elif recorded != digest:
                raise ValueError(  # noqa: TRY003
                    f"event {event.event_id!r} was rewritten after it was imported"
                )

        for identity, _digest, event in pending:
            await session.submit(identity, PI_EVENT_SOURCE_NAME, event)

        if not pending and session.checkpoint is not None:
            return ConnectorRunCompletion(status=ConnectorRunStatus.COMPLETE, checkpoint=session.checkpoint)
        merged = dict(imported)
        merged.update({identity: digest for identity, digest, _event in pending})
        return ConnectorRunCompletion(
            status=ConnectorRunStatus.COMPLETE,
            checkpoint={"version": _CHECKPOINT_VERSION, "records": dict(sorted(merged.items()))},
        )


class PiEventSourceAdapter:
    """Resolve and read one captured Pi event."""

    input_class = PiEventInput
    name = PI_EVENT_SOURCE_NAME
    source_class = PiEventSource

    async def resolve(self, value: PiEventInput, /) -> PiEventSource:
        source_id = pi_event_source_id(value.session_id, value.event_id)
        return PiEventSource(
            name=source_id,
            source_id=source_id,
            session_id=value.session_id,
            event_id=value.event_id,
            parent_id=value.parent_id,
            event_type=value.event_type,
            role=value.role,
            content=value.content,
            record=value.record,
        )

    async def read(self, source: PiEventSource, /) -> PiEventInput:
        return PiEventInput(
            session_id=source.session_id,
            event_id=source.event_id,
            parent_id=source.parent_id,
            event_type=source.event_type,
            role=source.role,
            content=source.content,
            record=source.record,
        )


class PiEventTextEvidenceProjection:
    """Expose the complete event text as canonical textual evidence."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PiEventSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: PiEventSource, /) -> TextEvidence:
        return TextEvidence(
            source_type=PI_EVENT_SOURCE_NAME,
            source_id=source.source_id,
            content=source.content,
            metadata={
                "session_id": source.session_id,
                "event_id": source.event_id,
                "parent_id": source.parent_id,
                "event_type": source.event_type,
                "role": source.role,
            },
        )


PI_EVENT_SOURCE_ADAPTER = PiEventSourceAdapter()
PI_EVENT_SOURCE_DEFINITION: AdapterSourceDefinition[PiEventInput, PiEventSource, PiEventInput] = (
    AdapterSourceDefinition(
        PI_EVENT_SOURCE_ADAPTER,
        version=PI_EVENT_SOURCE_VERSION,
        projections=(PiEventTextEvidenceProjection(),),
    )
)

__all__ = [
    "PI_EVENT_SOURCE_DEFINITION",
    "PI_EVENT_SOURCE_NAME",
    "PI_SESSION_CONNECTOR_NAME",
    "PiEventInput",
    "PiEventSource",
    "PiSessionConnector",
    "PiSessionInput",
    "parse_pi_session",
    "pi_event_source_id",
]
