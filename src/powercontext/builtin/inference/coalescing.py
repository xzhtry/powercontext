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

"""Coalesce concurrent Embedding work and reuse successful vectors.

One wrapper sits in front of a model. Every call dedupes its own texts, joins
the in-flight future of a text another call already asked for, and joins the
next batch window for texts nobody has requested yet. Batches run in their own
tasks, so a cancelled caller never cancels work that other callers depend on,
and each caller is charged only for the batches it actually waited for.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from typing import Any

from powercontext.builtin.inference.models import EmbeddingResult, InferenceUsage

DEFAULT_MAX_BATCH_SIZE = 64
DEFAULT_COALESCE_MS = 5.0
DEFAULT_CACHE_SIZE = 1024

_Vector = tuple[float, ...]


class CoalescingEmbeddingModel:
    """Share in-flight Embedding work across calls and cache successful vectors."""

    def __init__(
        self,
        model: Any,
        *,
        max_batch_size: int = DEFAULT_MAX_BATCH_SIZE,
        coalesce_ms: float = DEFAULT_COALESCE_MS,
        cache_size: int = DEFAULT_CACHE_SIZE,
    ) -> None:
        if not isinstance(max_batch_size, int) or isinstance(max_batch_size, bool) or max_batch_size < 1:
            raise ValueError("max_batch_size must be a positive integer")  # noqa: TRY003
        if isinstance(coalesce_ms, bool) or not isinstance(coalesce_ms, (int, float)) or coalesce_ms < 0:
            raise ValueError("coalesce_ms must be a non-negative number")  # noqa: TRY003
        if not isinstance(cache_size, int) or isinstance(cache_size, bool) or cache_size < 0:
            raise ValueError("cache_size must be a non-negative integer")  # noqa: TRY003
        self.profile = model.profile
        self._model = model
        self._max_batch_size = max_batch_size
        self._coalesce_seconds = float(coalesce_ms) / 1000.0
        self._cache_size = cache_size
        self._cache: OrderedDict[str, _Vector] = OrderedDict()
        self._inflight: dict[str, asyncio.Future[tuple[_Vector, InferenceUsage]]] = {}
        self._queue: list[str] = []
        self._flusher: asyncio.Task[None] | None = None

    async def embed(self, texts: Any) -> EmbeddingResult:
        items = tuple(texts)
        if not items:
            return EmbeddingResult(vectors=(), usage=InferenceUsage(requests=0))

        cached: dict[str, _Vector] = {}
        pending: dict[str, asyncio.Future[tuple[_Vector, InferenceUsage]]] = {}
        for text in dict.fromkeys(items):
            vector = self._cache_lookup(text)
            if vector is not None:
                cached[text] = vector
                continue
            future = self._inflight.get(text)
            if future is None:
                future = asyncio.get_running_loop().create_future()
                self._inflight[text] = future
                self._queue.append(text)
            pending[text] = future
        if self._queue and self._flusher is None:
            self._flusher = asyncio.ensure_future(self._flush())

        resolved: dict[str, tuple[_Vector, InferenceUsage]] = {}
        if pending:
            resolved = await self._await_pending(pending)

        vectors: list[_Vector] = []
        usages: dict[int, InferenceUsage] = {}
        for text in items:
            if text in cached:
                vectors.append(cached[text])
                continue
            vector, usage = resolved[text]
            vectors.append(vector)
            usages[id(usage)] = usage
        return EmbeddingResult(vectors=tuple(vectors), usage=_sum_usage(usages.values()))

    async def _await_pending(
        self,
        pending: dict[str, asyncio.Future[tuple[_Vector, InferenceUsage]]],
    ) -> dict[str, tuple[_Vector, InferenceUsage]]:
        gather = asyncio.ensure_future(asyncio.gather(*pending.values()))
        gather.add_done_callback(_consume_result)
        resolved = await asyncio.shield(gather)
        return dict(zip(pending.keys(), resolved, strict=True))

    async def _flush(self) -> None:
        try:
            await asyncio.sleep(self._coalesce_seconds)
        finally:
            self._flusher = None
        while self._queue:
            batch = self._queue[: self._max_batch_size]
            del self._queue[: self._max_batch_size]
            asyncio.ensure_future(self._run(batch))

    async def _run(self, texts: list[str]) -> None:
        try:
            result = await self._model.embed(tuple(texts))
            vectors = tuple(tuple(float(value) for value in vector) for vector in result.vectors)
            if len(vectors) != len(texts):
                raise ValueError("embedding model returned a wrong number of vectors")  # noqa: TRY003
            usage = result.usage
            for text, vector in zip(texts, vectors, strict=True):
                self._cache_store(text, vector)
                self._settle(text, (vector, usage))
        except Exception as error:  # noqa: BLE001 - the failure belongs to every waiter of this batch
            for text in texts:
                self._fail(text, error)

    def _settle(self, text: str, value: tuple[_Vector, InferenceUsage]) -> None:
        future = self._inflight.pop(text, None)
        if future is not None and not future.done():
            future.set_result(value)

    def _fail(self, text: str, error: BaseException) -> None:
        future = self._inflight.pop(text, None)
        if future is not None and not future.done():
            future.set_exception(error)

    def _cache_lookup(self, text: str) -> _Vector | None:
        if self._cache_size == 0:
            return None
        vector = self._cache.get(text)
        if vector is None:
            return None
        self._cache.move_to_end(text)
        return vector

    def _cache_store(self, text: str, vector: _Vector) -> None:
        if self._cache_size == 0:
            return
        self._cache[text] = vector
        self._cache.move_to_end(text)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)


def _sum_usage(usages: Any) -> InferenceUsage:
    entries = list(usages)
    if not entries:
        return InferenceUsage(requests=0)
    requests = sum(int(usage.requests) for usage in entries)
    inputs = [usage.input_tokens for usage in entries]
    outputs = [usage.output_tokens for usage in entries]
    return InferenceUsage(
        requests=requests,
        input_tokens=None if all(value is None for value in inputs) else sum(int(value or 0) for value in inputs),
        output_tokens=None if all(value is None for value in outputs) else sum(int(value or 0) for value in outputs),
    )


def _consume_result(task: asyncio.Future[Any]) -> None:
    if task.cancelled():
        return
    try:
        task.exception()
    except (asyncio.CancelledError, Exception):  # noqa: BLE001 - already delivered to the waiter
        pass


__all__ = ["DEFAULT_CACHE_SIZE", "DEFAULT_COALESCE_MS", "DEFAULT_MAX_BATCH_SIZE", "CoalescingEmbeddingModel"]
