"""End-to-end acceptance for a running 研脉 instance.

Usage:
    python scripts/verify.py
    python scripts/verify.py --base-url http://127.0.0.1:8787

The script mutates the demo database on purpose: it adds one evidence row,
generates one synthesis, and creates a new session.  Run ``scripts/reset.ps1``
to return to the pristine seed.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class Failure(RuntimeError):
    pass


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    if not condition:
        raise Failure(name)


class _Client:
    """Minimal httpx.Client replacement backed by urllib."""

    def __init__(self, base_url: str, timeout: int = 40) -> None:
        self.base = base_url
        self.timeout = timeout

    def __enter__(self) -> "_Client":
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def _request(self, method: str, path: str, **kwargs: Any) -> "_Response":
        url = self.base + path
        if "params" in kwargs and kwargs["params"]:
            url += "?" + urllib.parse.urlencode(kwargs["params"])
        data = None
        headers = {"Accept": "application/json"}
        if "json" in kwargs:
            data = json.dumps(kwargs["json"]).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
            body = resp.read().decode("utf-8")
            return _Response(resp.status, body)
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            return _Response(error.code, body)

    def get(self, path: str, **kwargs: Any) -> "_Response":
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> "_Response":
        return self._request("POST", path, **kwargs)


class _Response:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text

    def json(self) -> Any:
        return json.loads(self.text)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self.text[:200]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    with _Client(base_url=base, timeout=40) as client:
        try:
            health = client.get("/api/health").json()
        except Exception as error:  # noqa: BLE001
            print(f"无法连接 {base}: {error}")
            print("请先运行：powershell -ExecutionPolicy Bypass -File scripts\\run.ps1")
            return 2
        check(
            "seekdb 可用且已播种",
            health.get("seekdb") is True and int(health.get("papers", 0)) >= 400,
            f"papers={health.get('papers')}",
        )
        check(
            "PowerContext 可用",
            health.get("memory_available") is True,
            health.get("memory_error", ""),
        )

        search = client.get("/api/search", params={"q": "RAG hallucination"}).json()
        results = search.get("results", [])
        check("全文检索命中", int(search.get("total", 0)) >= 5, f"total={search.get('total')}")
        check(
            "检索结果由 seekdb 驱动",
            "MATCH" in (search.get("sql_trace", {}).get("statement", "") or ""),
            search.get("mode", ""),
        )
        check(
            "相关度排序把 RAGTruth 放在前列",
            any("RAGTruth" in item.get("title", "") for item in results[:5]),
            results[0]["title"][:80] if results else "no results",
        )
        check(
            "结果带可核对摘要与链接",
            bool(results)
            and bool(results[0].get("url"))
            and bool(results[0].get("snippet_html")),
        )

        noise = client.get("/api/search", params={"q": "power of noise retrieval"}).json()
        candidates = noise.get("results", [])
        target = next(
            (item for item in candidates if "Power of Noise" in item.get("title", "")),
            candidates[0] if candidates else None,
        )
        check("找到用于验证的论文", target is not None, target["title"][:80] if target else "")

        evidence_before = client.get("/api/evidence").json()
        before_ids = {int(item["paper_id"]) for item in evidence_before.get("items", [])}
        note = "验证脚本：检索到的噪声段落会改变 RAG 的证据使用方式，必须作为限定条件记录。"
        saved = client.post(
            "/api/evidence",
            json={
                "paper_id": int(target["paper_id"]),
                "stance": "challenge",
                "note": note,
            },
        )
        saved.raise_for_status()
        check("证据写入 seekdb", saved.json().get("evidence", {}).get("note") == note)
        evidence_after = client.get("/api/evidence").json()
        after_ids = {int(item["paper_id"]) for item in evidence_after.get("items", [])}
        check(
            "证据表包含新增判断",
            int(target["paper_id"]) in after_ids,
            f"before={len(before_ids)} after={len(after_ids)}",
        )

        synthesis = client.post("/api/synthesis", json={"template": "review"})
        synthesis.raise_for_status()
        draft = synthesis.json()
        markdown = draft.get("markdown", "")
        for required in ("## 3. 支持证据", "## 4. 挑战与限定", "## 参考", "生成说明"):
            check(f"综述包含「{required}」", required in markdown)
        check("综述已写入 seekdb", bool(draft.get("synthesis_id")), str(draft.get("synthesis_id")))
        check("综述写入 PowerContext", bool(draft.get("memory")), str(draft.get("memory", {}).get("artifact_id")))

        memory = client.get("/api/memory").json()
        check("PowerContext 可读取", memory.get("available") is True, memory.get("error", ""))
        kinds = memory.get("by_kind", {})
        check("记忆包含证据判断", int(kinds.get("evidence-decision", 0)) >= 1, str(kinds))
        check("记忆包含综述草稿", int(kinds.get("synthesis", 0)) >= 1, str(kinds))

        memory_before = int(memory.get("total", 0))
        session = client.post("/api/session/new", json={}).json()
        handoff = session.get("handoff", {})
        check("新会话生成交接摘要", bool(handoff.get("summary")), handoff.get("summary", "")[:100])
        check("交接摘要写入记忆", bool(handoff.get("memory")), str(handoff.get("memory", {}).get("artifact_id")))
        memory_after = client.get("/api/memory").json()
        check(
            "记忆数量增加",
            int(memory_after.get("total", 0)) > memory_before,
            f"{memory_before} -> {memory_after.get('total')}",
        )
        session_entries = [
            entry for entry in memory_after.get("entries", []) if entry.get("kind") == "session-summary"
        ]
        check("存在会话交接记录", bool(session_entries), f"count={len(session_entries)}")

        print("\n验收通过。报告摘要：")
        print(f"  - seekdb 文献: {health.get('papers')}")
        print(f"  - 检索: total={search.get('total')}, elapsed={search.get('elapsed_ms')}ms")
        print(f"  - 证据: {len(evidence_after.get('items', []))} 条")
        print(f"  - 综述: #{draft.get('synthesis_id')}，{len(markdown)} 字符")
        print(f"  - PowerContext: {memory_after.get('total')} 条 active memory")
        print(f"  - 新会话: {handoff.get('summary', '')[:80]}…")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Failure as error:
        print(f"\n验收失败：{error}")
        raise SystemExit(1) from error
