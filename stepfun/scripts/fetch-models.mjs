#!/usr/bin/env node
/**
 * Download the public BGE-small-zh-v1.5 ONNX assets from a Hugging Face mirror.
 *
 * The browser app never calls a remote inference API. This script only obtains
 * the open model files ahead of time so inference can run fully on-device.
 *
 * Usage:
 *   node scripts/fetch-models.mjs                # fp16 + int8 (deployed files)
 *   node scripts/fetch-models.mjs --baseline     # + fp32 (for quality comparison)
 *   HF_ENDPOINT=https://huggingface.co node scripts/fetch-models.mjs
 */
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

const MODEL_REPO = "Xenova/bge-small-zh-v1.5";
const MODEL_ID = "bge-small-zh-v1.5";
const BASE_ENDPOINTS = [
  process.env.HF_ENDPOINT,
  "https://hf-mirror.com",
  "https://huggingface.co",
].filter(Boolean);
const outRoot = path.resolve("public/models", MODEL_ID);
const baselineRoot = path.resolve("models-baseline");
const withBaseline = process.argv.includes("--baseline");

const baseFiles = [
  "config.json",
  "tokenizer.json",
  "tokenizer_config.json",
  "special_tokens_map.json",
  "vocab.txt",
];
const onnxFiles = ["onnx/model_fp16.onnx", "onnx/model_quantized.onnx"];

fs.mkdirSync(path.join(outRoot, "onnx"), { recursive: true });

async function fetchWithFallback(rel) {
  let lastError;
  for (const endpoint of BASE_ENDPOINTS) {
    const url = `${endpoint.replace(/\/$/, "")}/${MODEL_REPO}/resolve/main/${rel}`;
    for (let attempt = 1; attempt <= 3; attempt += 1) {
      try {
        const res = await fetch(url, { redirect: "follow" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return { res, url };
      } catch (error) {
        lastError = error;
        if (attempt < 3) await new Promise((r) => setTimeout(r, 1000 * attempt));
      }
    }
    console.warn(`  mirror failed: ${endpoint} (${lastError?.message})`);
  }
  throw new Error(`Could not download ${rel}: ${lastError?.message}`);
}

async function download(rel, targetRoot = outRoot) {
  const dest = path.join(targetRoot, rel);
  const part = `${dest}.part`;
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  const { res, url } = await fetchWithFallback(rel);
  const expected = Number(res.headers.get("content-length") || 0);
  console.log(`\n↓ ${rel} (${expected ? (expected / 1048576).toFixed(1) + " MiB" : "size unknown"})`);
  console.log(`  ${url}`);
  const hash = crypto.createHash("sha256");
  const out = fs.createWriteStream(part);
  let received = 0;
  let lastLog = 0;
  for await (const chunk of res.body) {
    out.write(chunk);
    hash.update(chunk);
    received += chunk.length;
    const now = Date.now();
    if (now - lastLog > 1000) {
      lastLog = now;
      const pct = expected ? ((received / expected) * 100).toFixed(0) + "%" : "";
      process.stdout.write(`\r  ${(received / 1048576).toFixed(1)} MiB ${pct}`);
    }
  }
  await new Promise((resolve, reject) => out.end((err) => (err ? reject(err) : resolve())));
  if (expected && received !== expected) {
    fs.rmSync(part, { force: true });
    throw new Error(`Size mismatch for ${rel}: ${received} != ${expected}`);
  }
  fs.rmSync(dest, { force: true });
  fs.renameSync(part, dest);
  const sha256 = hash.digest("hex");
  process.stdout.write(`\r  done ${(received / 1048576).toFixed(1)} MiB\n`);
  return { file: rel, bytes: received, sha256, source: url };
}

const records = [];
for (const rel of [...baseFiles, ...onnxFiles]) {
  records.push(await download(rel));
}
let baseline = null;
if (withBaseline) {
  const baselineModelDir = path.join(baselineRoot, MODEL_ID);
  baseline = await download("onnx/model.onnx", baselineModelDir);
  for (const rel of baseFiles) {
    fs.copyFileSync(path.join(outRoot, rel), path.join(baselineModelDir, rel));
  }
}

const manifest = {
  model: MODEL_ID,
  repo: `https://huggingface.co/${MODEL_REPO}`,
  revision: "75c43b069aac4d136ba6bc1122f995fedcfd2781",
  license: "MIT",
  downloadedAt: new Date().toISOString(),
  precision: ["fp16", "int8"],
  files: records,
  baseline: baseline
    ? {
        ...baseline,
        location: `models-baseline/${MODEL_ID}/onnx/model.onnx`,
        note: "Development-only baseline for the controlled quantization evaluation; not served by the web app.",
      }
    : null,
};
fs.writeFileSync(path.join(outRoot, "manifest.json"), JSON.stringify(manifest, null, 2) + "\n");
fs.mkdirSync(path.resolve("docs"), { recursive: true });
fs.writeFileSync(path.resolve("docs", "model-manifest.json"), JSON.stringify(manifest, null, 2) + "\n");
console.log(`\nSaved ${records.length} runtime files to ${outRoot}`);
if (baseline) console.log(`Saved FP32 baseline to ${path.join(baselineRoot, MODEL_ID, "onnx/model.onnx")}`);
console.log("Manifest:", path.join(outRoot, "manifest.json"));
