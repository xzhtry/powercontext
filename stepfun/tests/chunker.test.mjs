import test from "node:test";
import assert from "node:assert/strict";
import { chunkDocument, countWords, normalizeText } from "../src/lib/chunker.ts";

test("normalizeText collapses CRLF and excess blank lines", () => {
  const value = normalizeText("a\r\n\r\n\r\n\r\nb  \r\n");
  assert.equal(value, "a\n\nb");
});

test("keeps markdown headings and never returns an empty chunk", () => {
  const chunks = chunkDocument("# Alpha\n\nFirst paragraph.\n\n## Beta\n\nSecond paragraph.");
  assert.equal(chunks.length, 2);
  assert.equal(chunks[0].heading, "Alpha");
  assert.equal(chunks[1].heading, "Beta");
  assert.ok(chunks.every((chunk) => chunk.text.trim().length > 0));
});

test("splits long text under the 512-token-friendly budget", () => {
  const text = "向量数据库混合检索需要同时理解语义与关键词。".repeat(80);
  const chunks = chunkDocument(text);
  assert.ok(chunks.length >= 4);
  for (const chunk of chunks) {
    assert.ok(chunk.charCount <= 430, `chunk too long: ${chunk.charCount}`);
    assert.ok(chunk.text.length > 0);
  }
  assert.deepEqual(
    chunks.map((chunk) => chunk.index),
    chunks.map((_, index) => index),
  );
});

test("countWords handles mixed Chinese and English text", () => {
  assert.equal(countWords("seekdb 混合检索 v1"), 6);
});
