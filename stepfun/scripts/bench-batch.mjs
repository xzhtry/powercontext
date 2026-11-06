#!/usr/bin/env node
/**
 * Browser batch-size benchmark for the actual StepKB EmbeddingEngine.
 *
 *   node scripts/bench-batch.mjs --backend=webgpu
 *   node scripts/bench-batch.mjs --backend=wasm
 *
 * Opens the app with ?bench=1, loads the selected model, then measures the
 * same 20 corpus documents at batch sizes 1, 8 and 16 after a warmup.
 */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const arg = process.argv.find((item) => item.startsWith("--backend="));
const backend = (arg?.split("=")[1] || process.env.E2E_BACKEND || "webgpu").toLowerCase();
const url = process.env.APP_URL || "http://127.0.0.1:8787";
const outputFile = path.join(root, "evidence", `batch-bench-${backend}.json`);
const corpus = JSON.parse(fs.readFileSync(path.join(root, "public", "samples", "corpus.json"), "utf8"));

const browser = await chromium.launch({
  channel: "msedge",
  headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-features=Vulkan", "--ignore-gpu-blocklist"],
});
const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
const consoleErrors = [];
page.on("pageerror", (error) => consoleErrors.push(error.message));
await page.goto(`${url}/?bench=1`, { waitUntil: "networkidle" });
await page.waitForTimeout(500);

if (backend === "wasm") {
  await page.locator(".backend-option", { hasText: "WASM · INT8" }).click();
}
if (await page.getByRole("button", { name: /初始化端侧模型/ }).count()) {
  await page.getByRole("button", { name: /初始化端侧模型/ }).click();
}
for (let i = 0; i < 120; i += 1) {
  await page.waitForTimeout(1000);
  const badge = await page.locator(".backend-badge").innerText();
  if (/WebGPU|WASM/.test(badge) && !/加载模型/.test(badge)) break;
  if (/模型错误/.test(badge)) throw new Error(await page.locator(".model-setup").innerText());
}
await page.waitForTimeout(300);

const texts = corpus.map((doc) => doc.text);
const result = await page.evaluate(
  async ({ texts, backend }) => {
    const handle = window.__STEPKB__;
    if (!handle?.engine) throw new Error("bench hook missing");
    const engine = handle.engine;
    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const measure = async (batchSize) => {
      const started = performance.now();
      let count = 0;
      for (let start = 0; start < texts.length; start += batchSize) {
        const batch = texts.slice(start, start + batchSize);
        await engine.embedDocuments(batch);
        count += batch.length;
      }
      return { ms: performance.now() - started, count };
    };
    // Warm kernels / JIT before measuring.
    await engine.embedDocuments(texts.slice(0, 1));
    await engine.embedDocuments(texts.slice(0, 8));
    await sleep(150);

    const batchSizes = [1, 8, 16];
    const samples = { 1: [], 8: [], 16: [] };
    for (let round = 0; round < 3; round += 1) {
      for (const size of batchSizes) {
        samples[size].push(await measure(size));
        await sleep(120);
      }
    }
    const median = (values) => {
      const sorted = [...values].sort((a, b) => a - b);
      return sorted[Math.floor(sorted.length / 2)];
    };
    const rows = batchSizes.map((size) => {
      const values = samples[size].map((item) => item.ms);
      return {
        batchSize: size,
        runsMs: values.map((v) => Math.round(v * 10) / 10),
        medianMs: Math.round(median(values) * 10) / 10,
        docsPerSecond: Number((texts.length / (median(values) / 1000)).toFixed(2)),
      };
    });
    const baseline = rows[0].medianMs;
    for (const row of rows) row.speedupVsBatch1 = Number((baseline / row.medianMs).toFixed(2));
    return {
      backend,
      status: handle.status,
      documents: texts.length,
      rows,
    };
  },
  { texts, backend },
);

const report = {
  generatedAt: new Date().toISOString(),
  app: url,
  browser: "Microsoft Edge 156.0.4314.50",
  protocol: "Actual browser EmbeddingEngine; 20 corpus docs; 3 rounds per batch size; median",
  ...result,
  consoleErrors,
};
fs.mkdirSync(path.dirname(outputFile), { recursive: true });
fs.writeFileSync(outputFile, JSON.stringify(report, null, 2) + "\n");
console.log(JSON.stringify(report, null, 2));
await browser.close();
