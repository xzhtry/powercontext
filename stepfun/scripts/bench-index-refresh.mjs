#!/usr/bin/env node
/**
 * Isolate the index-refresh strategy with synthetic 512d vectors:
 *   A) 20 single-document imports, one refresh after each write
 *   B) 1 batch import of 20 documents, one refresh at the end
 *
 * Synthetic vectors keep model time out of this database-only experiment.
 * Usage: node scripts/bench-index-refresh.mjs
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const base = process.env.STEPKB_API_URL || "http://127.0.0.1:8787";
const corpus = JSON.parse(fs.readFileSync(path.join(root, "public", "samples", "corpus.json"), "utf8"));
const ROUNDS = 3;

async function request(pathname, options) {
  const response = await fetch(base + pathname, {
    headers: { "content-type": "application/json" },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`${response.status} ${JSON.stringify(body)}`);
  return body;
}

function vectorFor(index) {
  const vector = Array.from({ length: 512 }, (_, i) => Math.sin((index + 1) * (i + 1) * 0.017) + 0.001);
  const norm = Math.sqrt(vector.reduce((sum, value) => sum + value * value, 0));
  return vector.map((value) => value / norm);
}

function docPayload(index) {
  const doc = corpus[index % corpus.length];
  return {
    title: `${doc.title} #${index}`,
    source: doc.source,
    text: doc.text,
    chunks: [{ text: doc.text, embedding: vectorFor(index) }],
  };
}

async function createKb(label) {
  return request("/api/kbs", {
    method: "POST",
    body: JSON.stringify({ name: `${label}-${Date.now()}`, description: "refresh benchmark" }),
  });
}

async function perDocRun() {
  const kb = await createKb("refresh-per-doc");
  let writeMs = 0;
  let refreshMs = 0;
  const started = performance.now();
  try {
    for (let i = 0; i < 20; i += 1) {
      const result = await request(`/api/kbs/${kb.id}/docs`, {
        method: "POST",
        body: JSON.stringify(docPayload(i)),
      });
      writeMs += result.writeMs || 0;
      refreshMs += result.refreshMs || 0;
    }
  } finally {
    await request(`/api/kbs/${kb.id}`, { method: "DELETE" });
  }
  return {
    wallMs: performance.now() - started,
    writeMs,
    refreshMs,
    refreshes: 20,
  };
}

async function batchRun() {
  const kb = await createKb("refresh-batch");
  const started = performance.now();
  try {
    const result = await request(`/api/kbs/${kb.id}/docs/batch`, {
      method: "POST",
      body: JSON.stringify({ documents: Array.from({ length: 20 }, (_, index) => docPayload(index)) }),
    });
    return {
      wallMs: performance.now() - started,
      writeMs: result.writeMs,
      refreshMs: result.refreshMs,
      refreshes: 1,
    };
  } finally {
    await request(`/api/kbs/${kb.id}`, { method: "DELETE" });
  }
}

const perDoc = [];
const batch = [];
for (let round = 1; round <= ROUNDS; round += 1) {
  // Alternate order to reduce systematic drift from background compactions.
  if (round % 2 === 1) {
    perDoc.push(await perDocRun());
    batch.push(await batchRun());
  } else {
    batch.push(await batchRun());
    perDoc.push(await perDocRun());
  }
  console.log(`round ${round}: per-doc=${Math.round(perDoc.at(-1).wallMs)}ms batch=${Math.round(batch.at(-1).wallMs)}ms`);
}

function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)];
}

const report = {
  generatedAt: new Date().toISOString(),
  environment: {
    seekdb: "seekdb 1.4.0 server mode",
    documents: 20,
    syntheticVectors: "512d, cosine-normalized, no model time",
    protocol: "3 rounds; alternating order; medians",
  },
  perDocumentRefresh: {
    runs: perDoc,
    medianWallMs: median(perDoc.map((item) => item.wallMs)),
    medianRefreshMs: median(perDoc.map((item) => item.refreshMs)),
  },
  coalescedBatchRefresh: {
    runs: batch,
    medianWallMs: median(batch.map((item) => item.wallMs)),
    medianRefreshMs: median(batch.map((item) => item.refreshMs)),
  },
};
report.speedup = Number(
  (report.perDocumentRefresh.medianWallMs / report.coalescedBatchRefresh.medianWallMs).toFixed(2),
);
const outputFile = path.join(root, "evidence", "refresh-bench.json");
fs.writeFileSync(outputFile, JSON.stringify(report, null, 2) + "\n");
console.log(JSON.stringify(report, null, 2));
