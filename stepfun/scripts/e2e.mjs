#!/usr/bin/env node
/**
 * Browser end-to-end + backend benchmark.
 *
 * Usage:
 *   node scripts/e2e.mjs --backend=webgpu
 *   node scripts/e2e.mjs --backend=wasm
 *   node scripts/e2e.mjs --backend=fallback
 *
 * Requires a running StepKB server (default http://127.0.0.1:8787) and the
 * public sample corpus. The script creates a fresh knowledge base, imports the
 * 20-document corpus with the selected backend, then runs all 15 labelled
 * queries and stores latency + result evidence in evidence/.
 */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const arg = process.argv.find((item) => item.startsWith("--backend="));
const backendRequest = (arg?.split("=")[1] || process.env.E2E_BACKEND || "webgpu").toLowerCase();
const appUrl = process.env.APP_URL || "http://127.0.0.1:8787";
const queries = JSON.parse(fs.readFileSync(path.join(root, "public", "samples", "queries.json"), "utf8"));
const stamp = new Date().toISOString().replace(/[:.]/g, "-");
const tag = process.env.E2E_TAG || backendRequest;
const outputFile = path.join(root, "evidence", `benchmark-${tag}.json`);
const logLines = [];
const log = (...args) => {
  const line = args.join(" ");
  logLines.push(line);
  console.log(line);
};

const browser = await chromium.launch({
  channel: "msedge",
  headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-features=Vulkan", "--ignore-gpu-blocklist"],
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 1200 },
  deviceScaleFactor: 1,
});
if (backendRequest === "fallback") {
  await context.addInitScript(() => {
    try {
      Object.defineProperty(Navigator.prototype, "gpu", {
        configurable: true,
        get: () => undefined,
      });
    } catch {
      /* ignore */
    }
  });
}
const page = await context.newPage();
const errors = [];
page.on("console", (msg) => {
  if (msg.type() === "error" && !/Some nodes were not assigned/.test(msg.text())) {
    errors.push(msg.text().slice(0, 500));
  }
});
page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));

await page.goto(appUrl, { waitUntil: "networkidle" });
await page.waitForTimeout(600);

let badge = await page.locator(".backend-badge").innerText();
if (/模型未加载/.test(badge)) {
  if (backendRequest === "wasm") {
    await page.locator(".backend-option", { hasText: "WASM · INT8" }).click();
  }
  const initButton = page.getByRole("button", { name: /初始化端侧模型/ });
  await initButton.click();
}
for (let i = 0; i < 120; i += 1) {
  await page.waitForTimeout(1000);
  badge = await page.locator(".backend-badge").innerText();
  if (/WebGPU|WASM/.test(badge) && !/加载模型/.test(badge)) break;
  if (/模型错误/.test(badge)) throw new Error(`Model error: ${await page.locator(".model-setup").innerText()}`);
}
log(`[backend=${backendRequest}] badge: ${badge.replace(/\n/g, " ")}`);
const fallbackNotice = await page.locator(".notice.amber").innerText().catch(() => "");
if (backendRequest === "fallback") {
  if (!fallbackNotice) throw new Error("Expected a WebGPU fallback notice, none found");
  log(`fallback notice: ${fallbackNotice.replace(/\n/g, " ")}`);
}

// Create a fresh KB so document vectors are produced by the selected backend.
await page.locator(".new-kb-btn").click();
await page.locator(".modal input").fill(`Bench ${backendRequest} ${stamp.slice(-8)}`);
await page.locator(".modal button[type=submit]").click();
await page.locator(".modal").waitFor({ state: "detached", timeout: 30000 });
await page.waitForTimeout(400);
log("created KB:", await page.locator(".kb-item.active .kb-name").innerText());

const importButton = page.getByRole("button", { name: /导入示例语料/ }).first();
const importStart = Date.now();
await importButton.click();
for (let i = 0; i < 240; i += 1) {
  await page.waitForTimeout(500);
  if (await page.locator(".progress-panel.done").count()) {
    log(`import: ${(await page.locator(".progress-panel.done").innerText()).replace(/\n/g, " | ")} in ${Date.now() - importStart}ms`);
    break;
  }
  if (await page.locator(".progress-panel.error").count()) {
    throw new Error(`Import failed: ${await page.locator(".progress-panel.error").innerText()}`);
  }
}
await page.waitForTimeout(500);
const docCount = await page.locator(".count-badge").innerText();
log("doc count:", docCount);
if (docCount !== "20") throw new Error(`Expected 20 docs, got ${docCount}`);

const observed = [];
for (const item of queries) {
  await page.locator(".search-input-wrap input").fill(item.query);
  const started = Date.now();
  await page.getByRole("button", { name: /^检索$/ }).click();
  await page.waitForFunction(
    (query) => document.querySelector(".results")?.getAttribute("data-query") === query,
    item.query,
    { timeout: 120000 },
  );
  const wallMs = Date.now() - started;
  const titles = await page.locator(".result-title-row h4").allInnerTexts();
  const timingText = (await page.locator(".timing-row").innerText()).replace(/\n/g, " | ");
  const modes = await page.locator(".results-mode").innerText();
  observed.push({
    query: item.query,
    relevant: item.relevant,
    wallMs,
    timingText,
    mode: modes,
    top5: titles.slice(0, 5),
  });
  log(`query ${observed.length}/${queries.length}: ${wallMs}ms | ${timingText} | top=${titles[0]}`);
}

const storedPerf = JSON.parse(
  (await page.evaluate(() => localStorage.getItem("stepkb.performance.v1"))) || "{}",
);
const currentLoad = storedPerf.loads?.[storedPerf.loads.length - 1] || null;
const currentSearches = (storedPerf.searches || []).slice(-queries.length);
const currentIngest = (storedPerf.ingests || []).slice(-1)[0] || null;
await page.screenshot({ path: path.join(root, "evidence", `benchmark-${tag}.png`), fullPage: true });

const summary = {
  backendRequest,
  tag,
  generatedAt: new Date().toISOString(),
  badge: badge.replace(/\n/g, " "),
  fallbackNotice: fallbackNotice.replace(/\n/g, " "),
  load: currentLoad,
  ingest: currentIngest,
  searches: currentSearches,
  observed,
  errors,
};
fs.mkdirSync(path.join(root, "evidence"), { recursive: true });
fs.writeFileSync(outputFile, JSON.stringify(summary, null, 2) + "\n");
fs.writeFileSync(
  path.join(root, "evidence", `benchmark-${tag}.log`),
  logLines.join("\n") + "\n",
);
log("saved", outputFile);
log("errors", JSON.stringify(errors));
await browser.close();
