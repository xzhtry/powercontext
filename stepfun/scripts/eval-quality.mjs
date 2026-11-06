#!/usr/bin/env node
/**
 * Controlled retrieval-quality evaluation for the three ONNX precisions.
 *
 * Same corpus, chunking, query instruction and model revision for every row.
 * Only the ONNX precision changes. Embeddings run locally in Node (CPU) so the
 * comparison is not entangled with WebGPU/WASM backend differences.
 *
 * Output: evidence/quality-eval.json + a Markdown table on stdout.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { env, pipeline } from "@huggingface/transformers";
import { chunkDocument } from "../src/lib/chunker.ts";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const outputFile = path.join(root, "evidence", "quality-eval.json");
const corpus = JSON.parse(fs.readFileSync(path.join(root, "public", "samples", "corpus.json"), "utf8"));
const queries = JSON.parse(fs.readFileSync(path.join(root, "public", "samples", "queries.json"), "utf8"));
const QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章：";
const TOP_K = 5;
const runtimeModelRoot = path.join(root, "public", "models");
const baselineModelRoot = path.join(root, "models-baseline");

env.allowRemoteModels = false;
env.allowLocalModels = true;

const chunks = [];
for (const doc of corpus) {
  chunkDocument(doc.text).forEach((chunk) => {
    chunks.push({ docId: doc.id, title: doc.title, text: chunk.text, index: chunk.index });
  });
}
console.log(`corpus: ${corpus.length} docs / ${chunks.length} chunks / ${queries.length} queries`);

function cosine(a, b) {
  let dot = 0;
  for (let i = 0; i < a.length; i += 1) dot += a[i] * b[i];
  return dot;
}

function evaluate(rankedDocIds, relevant) {
  const top = rankedDocIds.slice(0, TOP_K);
  const relevantSet = new Set(relevant);
  const hits = top.filter((id) => relevantSet.has(id)).length;
  const recall = hits / relevantSet.size;
  let dcg = 0;
  top.forEach((id, index) => {
    if (relevantSet.has(id)) dcg += 1 / Math.log2(index + 2);
  });
  let idcg = 0;
  for (let i = 0; i < Math.min(relevantSet.size, TOP_K); i += 1) idcg += 1 / Math.log2(i + 2);
  return { recall, ndcg: idcg ? dcg / idcg : 0, top };
}

const dtypeSpecs = [
  { name: "FP32", dtype: "fp32", file: "onnx/model.onnx", root: baselineModelRoot },
  { name: "FP16", dtype: "fp16", file: "onnx/model_fp16.onnx", root: runtimeModelRoot },
  { name: "INT8", dtype: "q8", file: "onnx/model_quantized.onnx", root: runtimeModelRoot },
];

const results = [];
let referenceVectors = null;
for (const spec of dtypeSpecs) {
  console.log(`\n=== ${spec.name} (${spec.file}) ===`);
  env.localModelPath = spec.root;
  const loadStarted = performance.now();
  const extractor = await pipeline("feature-extraction", "bge-small-zh-v1.5", {
    dtype: spec.dtype,
    device: "cpu",
  });
  const loadMs = performance.now() - loadStarted;
  const docVectors = [];
  const docStarted = performance.now();
  for (let start = 0; start < chunks.length; start += 16) {
    const batch = chunks.slice(start, start + 16);
    const output = await extractor(
      batch.map((chunk) => chunk.text),
      { pooling: "cls", normalize: true, truncation: true },
    );
    docVectors.push(...output.tolist());
  }
  const docMs = performance.now() - docStarted;

  const queryVectors = [];
  const queryStarted = performance.now();
  for (const item of queries) {
    const output = await extractor([`${QUERY_PREFIX}${item.query}`], {
      pooling: "cls",
      normalize: true,
      truncation: true,
    });
    queryVectors.push(output.tolist()[0]);
  }
  const queryMs = performance.now() - queryStarted;

  if (!referenceVectors) referenceVectors = docVectors;
  let fidelity = 0;
  for (let i = 0; i < docVectors.length; i += 1) fidelity += cosine(referenceVectors[i], docVectors[i]);
  fidelity /= docVectors.length;

  const rows = [];
  for (let q = 0; q < queries.length; q += 1) {
    const scored = chunks
      .map((chunk, index) => ({ ...chunk, score: cosine(queryVectors[q], docVectors[index]) }))
      .sort((a, b) => b.score - a.score);
    const rankedDocs = [];
    const bestScore = new Map();
    for (const item of scored) {
      if (!bestScore.has(item.docId)) {
        bestScore.set(item.docId, item.score);
        rankedDocs.push(item.docId);
      }
    }
    const metrics = evaluate(rankedDocs, queries[q].relevant);
    rows.push({
      query: queries[q].query,
      relevant: queries[q].relevant,
      top5: metrics.top.map((docId) => ({
        docId,
        title: corpus.find((doc) => doc.id === docId)?.title || docId,
        score: Number(bestScore.get(docId).toFixed(6)),
      })),
      recallAt5: metrics.recall,
      ndcgAt5: metrics.ndcg,
    });
  }
  const aggregate = {
    recallAt5: rows.reduce((sum, row) => sum + row.recallAt5, 0) / rows.length,
    ndcgAt5: rows.reduce((sum, row) => sum + row.ndcgAt5, 0) / rows.length,
    mrr: rows.reduce((sum, row) => {
      const index = row.top5.findIndex((item) => queries.find((q) => q.query === row.query).relevant.includes(item.docId));
      return sum + (index >= 0 ? 1 / (index + 1) : 0);
    }, 0) / rows.length,
  };

  const modelFile = path.join(spec.root, "bge-small-zh-v1.5", spec.file);
  const record = {
    precision: spec.name,
    dtype: spec.dtype,
    modelBytes: fs.statSync(modelFile).size,
    loadMs: Math.round(loadMs),
    docEmbedMs: Math.round(docMs),
    queryEmbedMs: Math.round(queryMs),
    docsPerSecond: Number((chunks.length / (docMs / 1000)).toFixed(2)),
    queriesPerSecond: Number((queries.length / (queryMs / 1000)).toFixed(2)),
    vectorFidelityVsFp32: Number(fidelity.toFixed(6)),
    ...aggregate,
    rows,
  };
  results.push(record);
  console.log(
    `Recall@5=${aggregate.recallAt5.toFixed(4)} nDCG@5=${aggregate.ndcgAt5.toFixed(4)} ` +
      `MRR=${aggregate.mrr.toFixed(4)} fidelity=${fidelity.toFixed(5)} load=${loadMs.toFixed(0)}ms ` +
      `docs=${(chunks.length / (docMs / 1000)).toFixed(1)}/s`,
  );
  await extractor.dispose?.();
}

const baseline = results[0];
const report = {
  generatedAt: new Date().toISOString(),
  environment: {
    runtime: `Node ${process.version} / onnxruntime-node (CPU)`,
    platform: `${process.platform}-${process.arch}`,
    model: "Xenova/bge-small-zh-v1.5 @ 75c43b0",
    pooling: "cls + L2 normalize",
    queryInstruction: QUERY_PREFIX,
    corpusDocs: corpus.length,
    chunks: chunks.length,
    queries: queries.length,
    topK: TOP_K,
  },
  results,
  summary: results.map((row) => ({
    precision: row.precision,
    modelBytes: row.modelBytes,
    compressionVsFp32: Number((baseline.modelBytes / row.modelBytes).toFixed(2)),
    recallAt5: Number(row.recallAt5.toFixed(4)),
    ndcgAt5: Number(row.ndcgAt5.toFixed(4)),
    mrr: Number(row.mrr.toFixed(4)),
    deltaRecall: Number((row.recallAt5 - baseline.recallAt5).toFixed(4)),
    deltaNdcg: Number((row.ndcgAt5 - baseline.ndcgAt5).toFixed(4)),
    docsPerSecond: row.docsPerSecond,
  })),
};
fs.mkdirSync(path.dirname(outputFile), { recursive: true });
fs.writeFileSync(outputFile, JSON.stringify(report, null, 2) + "\n");
console.log(`\nSaved ${outputFile}`);
console.log("\n| precision | bytes | compression | Recall@5 | nDCG@5 | MRR | docs/s |");
console.log("| --- | ---: | ---: | ---: | ---: | ---: | ---: |");
for (const row of report.summary) {
  console.log(
    `| ${row.precision} | ${row.modelBytes} | ${row.compressionVsFp32}× | ${row.recallAt5} | ${row.ndcgAt5} | ${row.mrr} | ${row.docsPerSecond} |`,
  );
}
