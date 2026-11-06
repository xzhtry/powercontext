#!/usr/bin/env node
/**
 * Copy the self-hosted ONNX Runtime WebAssembly runtime that Transformers.js
 * needs into public/ort. Keeping it local avoids a CDN dependency and lets the
 * app declare connect-src 'self' in its CSP.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ortDistCandidates = [
  path.join(root, "node_modules", "onnxruntime-web", "dist"),
  path.join(root, "node_modules", "@huggingface", "transformers", "node_modules", "onnxruntime-web", "dist"),
];
const ortDist = ortDistCandidates.find((dir) => fs.existsSync(dir));
if (!ortDist) {
  console.error("onnxruntime-web is not installed. Run `pnpm install` first.");
  process.exit(1);
}

const files = ["ort-wasm-simd-threaded.jsep.mjs", "ort-wasm-simd-threaded.jsep.wasm"];
const outDir = path.join(root, "public", "ort");
fs.mkdirSync(outDir, { recursive: true });
for (const file of files) {
  const source = path.join(ortDist, file);
  if (!fs.existsSync(source)) {
    console.error(`Missing ${source}`);
    process.exit(1);
  }
  fs.copyFileSync(source, path.join(outDir, file));
  console.log(`[assets] ${file} (${(fs.statSync(source).size / 1048576).toFixed(1)} MiB)`);
}

const modelDir = path.join(root, "public", "models", "bge-small-zh-v1.5");
const required = ["onnx/model_fp16.onnx", "onnx/model_quantized.onnx", "tokenizer.json", "config.json"];
const missing = required.filter((file) => !fs.existsSync(path.join(modelDir, file)));
if (missing.length) {
  console.warn(
    "\n[assets] Model assets missing: " +
      missing.join(", ") +
      "\nRun `pnpm fetch:models` to download the public BGE-small-zh-v1.5 ONNX files.\n",
  );
} else {
  console.log("[assets] BGE-small-zh-v1.5 fp16 + int8 present");
}
