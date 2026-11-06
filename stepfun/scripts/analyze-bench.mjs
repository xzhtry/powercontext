#!/usr/bin/env node
/**
 * Aggregate the repeated browser runs into the tables used by the README and
 * the one-page technical note. Raw files stay in evidence/ for auditability.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const evidence = path.join(root, "evidence");
const corpus = JSON.parse(fs.readFileSync(path.join(root, "public", "samples", "corpus.json"), "utf8"));
const titleToId = new Map(corpus.map((doc) => [doc.title, doc.id]));

function readRuns(prefix) {
  return fs
    .readdirSync(evidence)
    .filter((file) => new RegExp(`^benchmark-${prefix}-\\d+\\.json$`).test(file))
    .sort()
    .map((file) => ({ file, data: JSON.parse(fs.readFileSync(path.join(evidence, file), "utf8")) }));
}

function median(values) {
  const sorted = [...values].filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
  if (!sorted.length) return null;
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function quality(observed) {
  let recall = 0;
  let ndcg = 0;
  let top1 = 0;
  for (const item of observed) {
    const ids = item.top5.map((title) => titleToId.get(title)).filter(Boolean);
    const relevant = new Set(item.relevant);
    if (ids[0] && relevant.has(ids[0])) top1 += 1;
    const hits = ids.slice(0, 5).filter((id) => relevant.has(id)).length;
    recall += hits / relevant.size;
    let dcg = 0;
    ids.slice(0, 5).forEach((id, index) => {
      if (relevant.has(id)) dcg += 1 / Math.log2(index + 2);
    });
    let idcg = 0;
    for (let i = 0; i < Math.min(relevant.size, 5); i += 1) idcg += 1 / Math.log2(i + 2);
    ndcg += idcg ? dcg / idcg : 0;
  }
  return {
    queries: observed.length,
    recallAt5: Number((recall / observed.length).toFixed(4)),
    ndcgAt5: Number((ndcg / observed.length).toFixed(4)),
    top1: `${top1}/${observed.length}`,
  };
}

const groups = {};
for (const backend of ["webgpu", "wasm"]) {
  const runs = readRuns(backend);
  if (!runs.length) continue;
  const loads = runs.map((run) => run.data.load).filter(Boolean);
  const ingests = runs.map((run) => run.data.ingest).filter(Boolean);
  const searches = runs.flatMap((run) => run.data.searches || []);
  const observed = runs.flatMap((run) => run.data.observed || []);
  const warm = searches.filter((item) => item.warm);
  groups[backend] = {
    runs: runs.length,
    loadMedianMs: median(loads.map((item) => item.loadMs)),
    warmupMedianMs: median(loads.map((item) => item.warmupMs)),
    modelBytes: loads[0]?.modelBytes || null,
    importEmbedMedianMs: median(ingests.map((item) => item.embedMs)),
    importWriteMedianMs: median(ingests.map((item) => item.writeMs)),
    importRefreshMedianMs: median(ingests.map((item) => item.refreshMs)),
    importE2eMedianMs: median(ingests.map((item) => item.e2eMs)),
    queryEmbedMedianMs: median(warm.map((item) => item.queryEmbedMs)),
    seekdbMedianMs: median(warm.map((item) => item.dbMs)),
    e2eMedianMs: median(warm.map((item) => item.e2eMs)),
    e2eP95Ms: (() => {
      const sorted = warm.map((item) => item.e2eMs).sort((a, b) => a - b);
      return sorted[Math.floor(sorted.length * 0.95)] || null;
    })(),
    coldE2eMedianMs: median(
      runs.map((run) => (run.data.searches || []).find((item) => !item.warm)?.e2eMs).filter(Boolean),
    ),
    ...quality(observed),
  };
}

const fallbackRun = (() => {
  try {
    return JSON.parse(fs.readFileSync(path.join(evidence, "benchmark-fallback.json"), "utf8"));
  } catch {
    return null;
  }
})();

const summary = {
  generatedAt: new Date().toISOString(),
  environment: {
    os: "Windows 11 26300",
    browser: "Microsoft Edge 156.0.4314.50",
    cpu: "Intel Core Ultra 7 155H (16C/22T)",
    gpu: "Intel Arc Graphics",
    ram: "31.5 GiB",
    seekdb: "seekdb 1.4.0 (server mode, v1.4.0.0)",
    corpus: "20 docs / 20 chunks / 15 labelled queries",
    protocol: "fresh browser context per run; 3 runs per backend; 15 queries per run",
  },
  backends: groups,
  fallback: fallbackRun
    ? {
        badge: fallbackRun.badge,
        notice: fallbackRun.fallbackNotice,
        ...quality(fallbackRun.observed),
      }
    : null,
};
fs.writeFileSync(path.join(evidence, "benchmark-summary.json"), JSON.stringify(summary, null, 2) + "\n");

const lines = [];
lines.push("# StepKB 实测汇总", "");
lines.push(`生成时间：${summary.generatedAt}`, "");
lines.push("## 环境", "");
for (const [key, value] of Object.entries(summary.environment)) lines.push(`- ${key}: ${value}`);
lines.push("", "## 浏览器 / 后端对比（3 次运行的中位数，热态 42 条查询）", "");
lines.push("| 指标 | WebGPU · FP16 | WASM · INT8 |");
lines.push("| --- | ---: | ---: |");
const a = groups.webgpu || {};
const b = groups.wasm || {};
const rows = [
  ["模型文件体积", a.modelBytes, b.modelBytes, "bytes"],
  ["模型加载（冷启动）", a.loadMedianMs, b.loadMedianMs, "ms"],
  ["模型预热", a.warmupMedianMs, b.warmupMedianMs, "ms"],
  ["20 篇导入 · 浏览器向量化", a.importEmbedMedianMs, b.importEmbedMedianMs, "ms"],
  ["20 篇导入 · 写入 + 刷新", a.importWriteMedianMs, b.importWriteMedianMs, "ms"],
  ["其中索引刷新", a.importRefreshMedianMs, b.importRefreshMedianMs, "ms"],
  ["导入端到端", a.importE2eMedianMs, b.importE2eMedianMs, "ms"],
  ["查询向量化", a.queryEmbedMedianMs, b.queryEmbedMedianMs, "ms"],
  ["seekdb 检索", a.seekdbMedianMs, b.seekdbMedianMs, "ms"],
  ["端到端查询", a.e2eMedianMs, b.e2eMedianMs, "ms"],
  ["端到端 p95", a.e2eP95Ms, b.e2eP95Ms, "ms"],
  ["首次查询端到端", a.coldE2eMedianMs, b.coldE2eMedianMs, "ms"],
  ["混合检索 Recall@5", a.recallAt5, b.recallAt5, ""],
  ["混合检索 nDCG@5", a.ndcgAt5, b.ndcgAt5, ""],
  ["Top-1 命中", a.top1, b.top1, ""],
];
for (const [label, left, right, unit] of rows) {
  const fmt = (value) =>
    value == null ? "—" : unit === "bytes" ? `${(value / 1024 / 1024).toFixed(1)} MiB` : unit === "ms" ? `${Math.round(value)} ms` : String(value);
  lines.push(`| ${label} | ${fmt(left)} | ${fmt(right)} |`);
}
lines.push("", "## 自动降级验证", "");
if (summary.fallback) {
  lines.push(`- 结果：${summary.fallback.badge}`);
  lines.push(`- 界面提示：${summary.fallback.notice}`);
  lines.push(`- 混合检索 Recall@5 / nDCG@5：${summary.fallback.recallAt5} / ${summary.fallback.ndcgAt5}`);
}
lines.push("", "## 原始数据", "");
lines.push("- `benchmark-webgpu-1..3.json` / `benchmark-wasm-1..3.json`");
lines.push("- `benchmark-fallback.json`");
lines.push("- `quality-eval.json`");
fs.writeFileSync(path.join(evidence, "benchmark-summary.md"), lines.join("\n") + "\n");
console.log(lines.join("\n"));
