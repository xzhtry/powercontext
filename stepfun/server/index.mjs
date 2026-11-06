import fs from "node:fs";
import path from "node:path";
import express from "express";
import { config } from "./config.mjs";
import { KnowledgeDatabase } from "./database.mjs";

const app = express();
const db = new KnowledgeDatabase();
const startedAt = Date.now();
let ready = false;
let startupError = null;

app.disable("x-powered-by");
app.use(express.json({ limit: "20mb" }));

app.use((req, res, next) => {
  res.setHeader("Cross-Origin-Opener-Policy", "same-origin");
  res.setHeader("Cross-Origin-Embedder-Policy", "require-corp");
  res.setHeader("X-Content-Type-Options", "nosniff");
  res.setHeader("Referrer-Policy", "no-referrer");
  res.setHeader(
    "Content-Security-Policy",
    "default-src 'self'; script-src 'self' 'wasm-unsafe-eval' blob:; " +
      "worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; " +
      "font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
  );
  next();
});

app.use((req, res, next) => {
  const begin = performance.now();
  res.on("finish", () => {
    if (req.path.startsWith("/api/")) {
      console.log(
        `${req.method} ${req.path} ${res.statusCode} ${(performance.now() - begin).toFixed(1)}ms`,
      );
    }
  });
  next();
});

function requireReady(req, res, next) {
  if (!ready) {
    return res.status(503).json({
      error: "seekdb not ready",
      detail: startupError || "The local seekdb connection is still initializing",
    });
  }
  next();
}

function readModelManifest() {
  const candidates = [
    path.join(config.root, "public", "models", "bge-small-zh-v1.5", "manifest.json"),
    path.join(config.root, "docs", "model-manifest.json"),
  ];
  for (const file of candidates) {
    try {
      return JSON.parse(fs.readFileSync(file, "utf8"));
    } catch {
      /* try the next location */
    }
  }
  return null;
}

function publicModelInfo() {
  const manifest = readModelManifest();
  const files = manifest?.files || [];
  const find = (suffix) => files.find((entry) => entry.file.endsWith(suffix));
  return {
    id: config.model.id,
    dimension: config.model.dimension,
    pooling: config.model.pooling,
    queryInstruction: "为这个句子生成表示以用于检索相关文章：",
    license: manifest?.license || "MIT",
    source: manifest?.repo || "https://huggingface.co/Xenova/bge-small-zh-v1.5",
    revision: manifest?.revision || null,
    files: {
      fp32: find("model.onnx") || null,
      fp16: find("model_fp16.onnx") || null,
      int8: find("model_quantized.onnx") || null,
    },
    quantization: {
      fp16: "ONNX FP16 weight-only export; WebGPU execution",
      int8: "ONNX dynamic INT8 quantization (model_quantized.onnx); WASM execution",
      baseline: "ONNX FP32 (model.onnx), used only for the controlled quality comparison",
    },
  };
}

app.get("/api/health", (req, res) => {
  res.json({
    ok: ready,
    ready,
    error: startupError,
    app: "stepkb",
    version: "1.0.0",
    uptimeSec: Math.round((Date.now() - startedAt) / 1000),
    inference: {
      location: "browser",
      cloudInference: false,
      model: config.model.id,
      dimension: config.model.dimension,
    },
    retrieval: {
      location: "seekdb",
      mode: config.seekdb.mode,
      database: config.seekdb.database,
      version: db.version,
    },
    model: publicModelInfo(),
  });
});

app.get("/api/model", (req, res) => {
  res.json(publicModelInfo());
});

app.get("/api/stats", requireReady, async (req, res, next) => {
  try {
    res.json(await db.stats());
  } catch (error) {
    next(error);
  }
});

app.get("/api/kbs", requireReady, async (req, res, next) => {
  try {
    res.json({ items: await db.listKbs() });
  } catch (error) {
    next(error);
  }
});

app.post("/api/kbs", requireReady, async (req, res, next) => {
  try {
    const kb = await db.createKb({ name: req.body?.name, description: req.body?.description });
    res.status(201).json(kb);
  } catch (error) {
    next(error);
  }
});

app.delete("/api/kbs/:id", requireReady, async (req, res, next) => {
  try {
    res.json(await db.deleteKb(req.params.id));
  } catch (error) {
    next(error);
  }
});

app.get("/api/kbs/:id/docs", requireReady, async (req, res, next) => {
  try {
    const kb = await db.getKb(req.params.id);
    if (!kb) return res.status(404).json({ error: "知识库不存在" });
    res.json({ kb, items: await db.listDocs(req.params.id) });
  } catch (error) {
    next(error);
  }
});

app.delete("/api/kbs/:id/docs/:docId", requireReady, async (req, res, next) => {
  try {
    res.json(await db.deleteDoc(req.params.id, req.params.docId));
  } catch (error) {
    next(error);
  }
});

app.post("/api/kbs/:id/docs", requireReady, async (req, res, next) => {
  try {
    const body = req.body || {};
    const result = await db.ingest({
      kbId: req.params.id,
      title: body.title,
      source: body.source,
      text: body.text,
      chunks: body.chunks,
      contentHash: body.contentHash,
    });
    res.status(result.duplicate ? 200 : 201).json(result);
  } catch (error) {
    next(error);
  }
});

app.post("/api/kbs/:id/docs/batch", requireReady, async (req, res, next) => {
  try {
    const result = await db.ingestBatch({
      kbId: req.params.id,
      documents: req.body?.documents,
    });
    res.status(result.duplicate ? 200 : 201).json(result);
  } catch (error) {
    next(error);
  }
});

app.post("/api/kbs/:id/search", requireReady, async (req, res, next) => {
  try {
    const body = req.body || {};
    const result = await db.search({
      kbId: req.params.id,
      query: body.query,
      embedding: body.embedding,
      topK: clampInt(body.topK, 1, 20, 8),
      mode: ["hybrid", "vector", "fts"].includes(body.mode) ? body.mode : "hybrid",
      rankWindowSize: clampInt(body.rankWindowSize, 1, 500, 60),
      rankConstant: clampInt(body.rankConstant, 1, 500, 60),
    });
    console.log(
      `[search] kb=${req.params.id} mode=${result.mode} q="${result.query.slice(0, 60)}" ` +
        `hits=${result.count} db=${result.dbMs}ms`,
    );
    res.json(result);
  } catch (error) {
    next(error);
  }
});

const distDir = path.join(config.root, "dist");
const publicDir = path.join(config.root, "public");
const modelsDir = path.join(publicDir, "models");
const ortDir = path.join(publicDir, "ort");

if (fs.existsSync(modelsDir)) {
  app.use(
    "/models",
    express.static(modelsDir, {
      maxAge: "30d",
      setHeaders: (res) => {
        res.setHeader("Cross-Origin-Resource-Policy", "same-origin");
        res.setHeader("Cache-Control", "public, max-age=2592000, immutable");
      },
    }),
  );
}
if (fs.existsSync(ortDir)) {
  app.use(
    "/ort",
    express.static(ortDir, {
      maxAge: "30d",
      setHeaders: (res) => {
        res.setHeader("Cross-Origin-Resource-Policy", "same-origin");
        res.setHeader("Cache-Control", "public, max-age=2592000, immutable");
      },
    }),
  );
}

if (fs.existsSync(distDir)) {
  app.use(express.static(distDir, { index: false, maxAge: "1h" }));
  app.get(/.*/, (req, res, next) => {
    if (req.path.startsWith("/api/")) return next();
    res.sendFile(path.join(distDir, "index.html"));
  });
} else {
  app.get("/", (req, res) => {
    res.status(200).type("text/plain").send(
      "StepKB API is running. The frontend has not been built yet.\n" +
        "Development: run two terminals: `node server/index.mjs` and `npx vite` (open http://127.0.0.1:5173).\n" +
        "Production: `npm run build && npm start`.\n",
    );
  });
}

app.use((req, res) => {
  if (req.path.startsWith("/api/")) {
    return res.status(404).json({ error: "Not found" });
  }
  res.status(404).type("text/plain").send("Not found");
});

app.use((error, req, res, next) => {
  if (res.headersSent) return next(error);
  const status = Number(error.status) || 500;
  if (status >= 500) console.error("[api error]", error);
  res.status(status).json({
    error: error.message || "服务器内部错误",
    ...(status >= 500 && !config.isProduction && error.stack ? { stack: error.stack } : {}),
  });
});

function clampInt(value, min, max, fallback) {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.min(max, Math.max(min, Math.trunc(number)));
}

async function main() {
  try {
    await db.connect();
    const stats = await db.stats();
    ready = true;
    console.log(
      `[stepkb] ready · seekdb ${db.version} · ${stats.kbCount} KBs / ${stats.docCount} docs / ${stats.chunkCount} chunks`,
    );
  } catch (error) {
    startupError = error.message;
    console.error("\n[stepkb] Failed to initialize seekdb.\n");
    console.error(error.message);
    if (config.seekdb.mode === "server") {
      console.error(
        `\nStart a local seekdb server on ${config.seekdb.host}:${config.seekdb.port}, ` +
          "or set SEEKDB_MODE=embedded (Linux/macOS native bindings).",
      );
    }
    console.error("\nThe HTTP server will still start so /api/health can report the failure.\n");
  }

  const server = app.listen(config.port, config.host, () => {
    console.log(`[stepkb] http://${config.host}:${config.port}`);
  });

  const shutdown = async (signal) => {
    console.log(`\n[stepkb] ${signal}, closing...`);
    server.close(async () => {
      await db.close().catch(() => {});
      process.exit(0);
    });
    setTimeout(() => process.exit(1), 8000).unref();
  };
  process.on("SIGINT", () => shutdown("SIGINT"));
  process.on("SIGTERM", () => shutdown("SIGTERM"));
}

main();
