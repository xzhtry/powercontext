#!/usr/bin/env node
/**
 * Compare cold model load with a warm page reload (browser HTTP/Cache Storage).
 * Usage: node scripts/bench-load.mjs
 */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const url = process.env.APP_URL || "http://127.0.0.1:8787";
const browser = await chromium.launch({
  channel: "msedge",
  headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-features=Vulkan", "--ignore-gpu-blocklist"],
});
const report = { generatedAt: new Date().toISOString(), browser: "Microsoft Edge 156.0.4314.50", backends: {} };

async function loadOnce(context, backend, label) {
  const page = await context.newPage();
  await page.goto(url, { waitUntil: "networkidle" });
  await page.waitForTimeout(400);
  if (backend === "wasm") {
    await page.locator(".backend-option", { hasText: "WASM · INT8" }).click();
  }
  const button = page.getByRole("button", { name: /初始化端侧模型/ });
  if (!(await button.count())) throw new Error("init button missing");
  await button.click();
  for (let i = 0; i < 90; i += 1) {
    await page.waitForTimeout(500);
    const badge = await page.locator(".backend-badge").innerText();
    if (/WebGPU|WASM/.test(badge) && !/加载模型/.test(badge)) break;
    if (/模型错误/.test(badge)) throw new Error(await page.locator(".model-setup").innerText());
  }
  const loads = JSON.parse((await page.evaluate(() => localStorage.getItem("stepkb.performance.v1"))) || "{}").loads || [];
  const latest = loads[loads.length - 1];
  await page.close();
  return { label, loadMs: latest.loadMs, warmupMs: latest.warmupMs, at: latest.at };
}

for (const backend of ["webgpu", "wasm"]) {
  const context = await browser.newContext({ viewport: { width: 1200, height: 900 } });
  const runs = [];
  runs.push(await loadOnce(context, backend, "cold-context"));
  runs.push(await loadOnce(context, backend, "warm-reload-1"));
  runs.push(await loadOnce(context, backend, "warm-reload-2"));
  report.backends[backend] = runs;
  await context.close();
  console.log(backend, runs);
}

const out = path.join(root, "evidence", "load-bench.json");
fs.writeFileSync(out, JSON.stringify(report, null, 2) + "\n");
await browser.close();
