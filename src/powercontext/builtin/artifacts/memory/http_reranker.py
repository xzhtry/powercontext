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

"""Rerank Memory candidates with one HTTP scoring service.

The service scores a bounded batch of candidates, so the adapter splits the
coarse pool, keeps every candidate's original global rank in the request, and
merges the returned scores back into one global selection. Candidate identity
is never rewritten: only original ranks are selected and reordered.
"""

from __future__ import annotations

import math
from typing import Any

import httpx

from powercontext.builtin.artifacts.memory.models import MemoryHit
from powercontext.builtin.artifacts.memory.reranking import (
    MemoryRerankDecision,
    _validate_bounds,
)
from powercontext.builtin.inference import InferenceUsage

HTTP_RERANKER_POLICY_ID = "http-cross-encoder-v1"
DEFAULT_BATCH_SIZE = 32


class HTTPMemoryReranker:
    """Score candidates through an HTTP rerank endpoint and merge every batch."""

    def __init__(
        self,
        endpoint: str,
        *,
        client: httpx.AsyncClient,
        batch_size: int = DEFAULT_BATCH_SIZE,
        policy_id: str = HTTP_RERANKER_POLICY_ID,
    ) -> None:
        if not isinstance(endpoint, str) or not endpoint.strip():
            raise ValueError("rerank endpoint must be a non-empty string")  # noqa: TRY003
        if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size < 1:
            raise ValueError("rerank batch_size must be a positive integer")  # noqa: TRY003
        if not isinstance(policy_id, str) or not policy_id.strip():
            raise ValueError("rerank policy_id must be a non-empty string")  # noqa: TRY003
        self.policy_id = policy_id
        self._endpoint = endpoint
        self._client = client
        self._batch_size = batch_size

    async def rerank(
        self,
        query: str,
        candidates: tuple[MemoryHit, ...],
        limit: int,
        /,
    ) -> MemoryRerankDecision:
        """Return the globally best original ranks without changing hit identity."""

        _validate_bounds(len(candidates), limit)

        scores: dict[int, float] = {}
        requests = 0
        for start in range(0, len(candidates), self._batch_size):
            batch = candidates[start : start + self._batch_size]
            ranks = list(range(start + 1, start + 1 + len(batch)))
            payload = {
                "query": query,
                "candidates": [
                    {"rank": rank, "text": candidate.text}
                    for rank, candidate in zip(ranks, batch, strict=True)
                ],
            }
            response = await self._client.post(self._endpoint, json=payload)
            response.raise_for_status()
            requests += 1
            scores.update(_validated_batch_scores(response, ranks))

        ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return MemoryRerankDecision(
            selected_ranks=tuple(rank for rank, _score in ordered[:limit]),
            usage=InferenceUsage(requests=requests),
        )


def _validated_batch_scores(response: httpx.Response, ranks: list[int], /) -> dict[int, float]:
    try:
        payload: Any = response.json()
    except ValueError as error:
        raise ValueError("rerank response is not valid JSON") from error  # noqa: TRY003

    if not isinstance(payload, dict) or set(payload) != {"scores"}:
        raise ValueError("rerank response must contain exactly one 'scores' field")  # noqa: TRY003
    entries = payload["scores"]
    if not isinstance(entries, list):
        raise ValueError("rerank 'scores' must be a list")  # noqa: TRY003

    expected = set(ranks)
    scored: dict[int, float] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"rank", "score"}:
            raise ValueError("each rerank score must contain exactly 'rank' and 'score'")  # noqa: TRY003
        rank = entry["rank"]
        score = entry["score"]
        if not isinstance(rank, int) or isinstance(rank, bool):
            raise ValueError("rerank score rank must be an integer")  # noqa: TRY003
        if rank not in expected:
            raise ValueError(f"rerank score rank {rank!r} is outside the sent batch")  # noqa: TRY003
        if rank in scored:
            raise ValueError(f"rerank score rank {rank!r} was returned twice")  # noqa: TRY003
        if not isinstance(score, (int, float)) or isinstance(score, bool) or not math.isfinite(score):
            raise ValueError("rerank score must be a finite number")  # noqa: TRY003
        scored[rank] = float(score)

    if set(scored) != expected:
        missing = sorted(expected - set(scored))
        raise ValueError(f"rerank response did not score ranks {missing}")  # noqa: TRY003
    return scored


__all__ = ["DEFAULT_BATCH_SIZE", "HTTP_RERANKER_POLICY_ID", "HTTPMemoryReranker"]
