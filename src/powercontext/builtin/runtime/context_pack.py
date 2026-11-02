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

"""Self-describing context packs and prefix-reuse deltas.

A complete context travels as one pack of UTF-8 chunks. When the receiver still
holds the previous pack, the next round travels as a delta that names how many
leading chunks it keeps and carries only the remaining suffix, so the receiver
rebuilds the exact target bytes without any sender-side state.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from typing import Any

CONTEXT_PACK_SCHEMA = "powercontext.context-pack.v1"
CONTEXT_PACK_DELTA_SCHEMA = "powercontext.context-pack-delta.v1"
DEFAULT_CHUNK_BYTES = 512
# Incremental rounds chunk finer than a one-off pack: every additional boundary
# caps how many bytes a mid-context edit can invalidate.
INCREMENTAL_CHUNK_BYTES = 256

_PACK_FIELDS = frozenset({"schema", "items", "digest", "byte_count"})
_DELTA_FIELDS = frozenset({"schema", "base_digest", "target_digest", "prefix_items", "appended"})
_CONTINUATION_MASK = 0xC0
_CONTINUATION_PREFIX = 0x80


class ContextPackError(ValueError):
    """Raised when a pack, delta or chunking request violates the protocol."""


@dataclass(frozen=True, slots=True)
class ContextPack:
    """One complete context expressed as ordered UTF-8 chunks."""

    items: tuple[bytes, ...]
    digest: str
    byte_count: int

    @classmethod
    def build(cls, items: tuple[bytes, ...] | list[bytes]) -> ContextPack:
        chunks = tuple(_as_bytes(item) for item in items)
        digest = _pack_digest(chunks)
        encoded_items = [_encode_chunk(item) for item in chunks]
        return cls(items=chunks, digest=digest, byte_count=_solved_byte_count(digest, encoded_items))

    @classmethod
    def from_content(cls, content: str | bytes, *, chunk_bytes: int = DEFAULT_CHUNK_BYTES) -> ContextPack:
        return cls.build(_chunk_utf8(_as_bytes(content), chunk_bytes))

    @classmethod
    def from_bytes(cls, payload: bytes | str) -> ContextPack:
        document = _parse_document(payload, _PACK_FIELDS, "pack")
        if document["schema"] != CONTEXT_PACK_SCHEMA:
            raise ContextPackError("pack schema is not supported")
        items = _decode_chunks(document["items"], "pack")
        digest = _checked_digest(document["digest"], "pack")
        byte_count = document["byte_count"]
        if not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count < 0:
            raise ContextPackError("pack byte_count must be a non-negative integer")
        if digest != _pack_digest(items):
            raise ContextPackError("pack digest does not match its items")
        pack = cls(items=items, digest=digest, byte_count=byte_count)
        actual = len(pack.to_bytes())
        if actual != byte_count:
            raise ContextPackError(f"pack byte_count {byte_count} does not match {actual} bytes")
        return pack

    def to_bytes(self) -> bytes:
        return _canonical_json({
            "schema": CONTEXT_PACK_SCHEMA,
            "items": [_encode_chunk(item) for item in self.items],
            "digest": self.digest,
            "byte_count": self.byte_count,
        })


@dataclass(frozen=True, slots=True)
class ContextPackDelta:
    """The suffix of one target pack plus the base prefix it reuses."""

    base_digest: str
    target_digest: str
    prefix_items: int
    appended: tuple[bytes, ...]

    @classmethod
    def between(cls, base: ContextPack, target: ContextPack) -> ContextPackDelta:
        prefix = 0
        limit = min(len(base.items), len(target.items))
        while prefix < limit and base.items[prefix] == target.items[prefix]:
            prefix += 1
        return cls(
            base_digest=base.digest,
            target_digest=target.digest,
            prefix_items=prefix,
            appended=target.items[prefix:],
        )

    @classmethod
    def from_bytes(cls, payload: bytes | str) -> ContextPackDelta:
        document = _parse_document(payload, _DELTA_FIELDS, "delta")
        if document["schema"] != CONTEXT_PACK_DELTA_SCHEMA:
            raise ContextPackError("delta schema is not supported")
        prefix = document["prefix_items"]
        if not isinstance(prefix, int) or isinstance(prefix, bool) or prefix < 0:
            raise ContextPackError("delta prefix_items must be a non-negative integer")
        return cls(
            base_digest=_checked_digest(document["base_digest"], "delta base"),
            target_digest=_checked_digest(document["target_digest"], "delta target"),
            prefix_items=prefix,
            appended=_decode_chunks(document["appended"], "delta"),
        )

    @property
    def byte_count(self) -> int:
        return len(self.to_bytes())

    def to_bytes(self) -> bytes:
        return _canonical_json({
            "schema": CONTEXT_PACK_DELTA_SCHEMA,
            "base_digest": self.base_digest,
            "target_digest": self.target_digest,
            "prefix_items": self.prefix_items,
            "appended": [_encode_chunk(item) for item in self.appended],
        })


def apply_context_pack_delta(base: ContextPack, delta: ContextPackDelta) -> ContextPack:
    """Rebuild and verify the target pack from one base pack and one delta."""

    if not isinstance(base, ContextPack) or not isinstance(delta, ContextPackDelta):
        raise ContextPackError("delta application needs a pack and a delta")
    if base.digest != delta.base_digest:
        raise ContextPackError("delta base digest does not match the provided pack")
    if delta.prefix_items > len(base.items):
        raise ContextPackError("delta prefix exceeds the base pack length")
    rebuilt = ContextPack.build((*base.items[: delta.prefix_items], *delta.appended))
    if rebuilt.digest != delta.target_digest:
        raise ContextPackError("delta target digest does not match the rebuilt pack")
    return rebuilt


def _as_bytes(value: object) -> bytes:
    if isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    raise ContextPackError("context content must be text or bytes")


def _chunk_utf8(raw: bytes, chunk_bytes: int) -> tuple[bytes, ...]:
    if not isinstance(chunk_bytes, int) or isinstance(chunk_bytes, bool) or chunk_bytes < 1:
        raise ContextPackError("chunk_bytes must be a positive integer")
    if not raw:
        return ()
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ContextPackError("context content must be valid UTF-8") from error
    if chunk_bytes >= len(raw):
        return (raw,)
    chunks: list[bytes] = []
    start = 0
    while start < len(raw):
        end = min(start + chunk_bytes, len(raw))
        while end < len(raw) and raw[end] & _CONTINUATION_MASK == _CONTINUATION_PREFIX:
            end -= 1
        if end == start:
            raise ContextPackError("chunk_bytes cannot hold one UTF-8 character")
        chunks.append(raw[start:end])
        start = end
    return tuple(chunks)


def _pack_digest(items: tuple[bytes, ...]) -> str:
    unsigned = {
        "schema": CONTEXT_PACK_SCHEMA,
        "items": [_encode_chunk(item) for item in items],
    }
    return "sha256:" + hashlib.sha256(_canonical_json(unsigned)).hexdigest()


def _solved_byte_count(digest: str, encoded_items: list[str]) -> int:
    """Find the byte_count value that makes the pack length self-consistent."""

    length = len(_pack_json(digest, encoded_items, 0))
    while True:
        candidate = len(_pack_json(digest, encoded_items, length))
        if candidate == length:
            return length
        length = candidate


def _pack_json(digest: str, encoded_items: list[str], byte_count: int) -> bytes:
    return _canonical_json({
        "schema": CONTEXT_PACK_SCHEMA,
        "items": encoded_items,
        "digest": digest,
        "byte_count": byte_count,
    })


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _encode_chunk(item: bytes) -> str:
    return base64.b64encode(item).decode("ascii")


def _parse_document(payload: bytes | str, fields: frozenset[str], label: str) -> dict[str, Any]:
    try:
        document = json.loads(payload)
    except (TypeError, ValueError) as error:
        raise ContextPackError(f"{label} is not valid JSON") from error
    if not isinstance(document, dict):
        raise ContextPackError(f"{label} must be a JSON object")
    if set(document) != set(fields):
        raise ContextPackError(f"{label} must contain exactly {sorted(fields)}")
    return document


def _decode_chunks(value: object, label: str) -> tuple[bytes, ...]:
    if not isinstance(value, list):
        raise ContextPackError(f"{label} chunks must be a list")
    chunks: list[bytes] = []
    for item in value:
        if not isinstance(item, str):
            raise ContextPackError(f"{label} chunks must be base64 strings")
        try:
            chunks.append(base64.b64decode(item.encode("ascii"), validate=True))
        except (binascii.Error, UnicodeEncodeError, ValueError) as error:
            raise ContextPackError(f"{label} chunk is not valid base64") from error
    return tuple(chunks)


def _checked_digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise ContextPackError(f"{label} digest must be a sha256 string")
    try:
        int(value.removeprefix("sha256:"), 16)
    except ValueError as error:
        raise ContextPackError(f"{label} digest must be hexadecimal") from error
    if value != value.lower():
        raise ContextPackError(f"{label} digest must be lowercase")
    return value


__all__ = [
    "CONTEXT_PACK_DELTA_SCHEMA",
    "CONTEXT_PACK_SCHEMA",
    "DEFAULT_CHUNK_BYTES",
    "INCREMENTAL_CHUNK_BYTES",
    "ContextPack",
    "ContextPackDelta",
    "ContextPackError",
    "apply_context_pack_delta",
]
