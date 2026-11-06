import test from "node:test";
import assert from "node:assert/strict";
import { buildFtsQuery } from "../server/database.mjs";

test("strips query_string operators and punctuation", () => {
  const query = buildFtsQuery('RRF + "rank_constant" - (hybrid) ?');
  assert.ok(query.includes("RRF"));
  assert.ok(query.includes("rank"));
  assert.ok(query.includes("constant"));
  assert.ok(!query.includes("+"));
  assert.ok(!query.includes("?"));
});

test("keeps Chinese phrases intact", () => {
  assert.equal(buildFtsQuery("向量数据库混合检索"), "向量数据库混合检索");
});

test("drops empty and stopword-only queries", () => {
  assert.equal(buildFtsQuery("   ？？？ "), "");
  assert.equal(buildFtsQuery("the a is"), "");
});

test("limits the number of FTS terms", () => {
  const query = buildFtsQuery("alpha beta gamma delta epsilon zeta eta theta iota kappa");
  assert.ok(query.split(" OR ").length <= 8);
});
