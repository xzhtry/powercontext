import test from "node:test";
import assert from "node:assert/strict";

const base = process.env.STEPKB_API_URL || "http://127.0.0.1:8787";
const enabled = process.env.STEPKB_INTEGRATION === "1";

async function request(path, options) {
  const response = await fetch(base + path, {
    headers: { "content-type": "application/json" },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`${response.status} ${JSON.stringify(body)}`);
  return body;
}

test("API: hybrid search still uses seekdb when enabled", { skip: !enabled }, async () => {
  const vector = Array.from({ length: 512 }, (_, index) => (index === 3 ? 1 : 0));
  const kb = await request("/api/kbs", {
    method: "POST",
    body: JSON.stringify({ name: `test-${Date.now()}`, description: "automated test" }),
  });
  try {
    const ingest = await request(`/api/kbs/${kb.id}/docs`, {
      method: "POST",
      body: JSON.stringify({
        title: "测试文档",
        source: "test.md",
        text: "seekdb 使用 DBMS_HYBRID_SEARCH 在数据库内融合全文与向量检索。",
        chunks: [
          {
            text: "seekdb 使用 DBMS_HYBRID_SEARCH 在数据库内融合全文与向量检索。",
            embedding: vector,
          },
        ],
      }),
    });
    assert.equal(ingest.chunkCount, 1);

    const result = await request(`/api/kbs/${kb.id}/search`, {
      method: "POST",
      body: JSON.stringify({
        query: "数据库混合检索",
        embedding: vector,
        topK: 3,
        mode: "hybrid",
      }),
    });
    assert.equal(result.seekdb.executedInDatabase, true);
    assert.equal(result.seekdb.rank, "RRF");
    assert.ok(result.hits.length >= 1);
    assert.equal(result.hits[0].title, "测试文档");
    assert.ok(result.hybridTrace.generatedSql.includes("match("));
    assert.ok(result.hybridTrace.generatedSql.includes("cosine_distance"));
    assert.ok(result.hybridTrace.generatedSql.includes("_keyword_rank"));

    const remove = await request(`/api/kbs/${kb.id}/docs/${ingest.docId}`, { method: "DELETE" });
    assert.ok(remove.refreshMs >= 0);
  } finally {
    await request(`/api/kbs/${kb.id}`, { method: "DELETE" });
  }
});
