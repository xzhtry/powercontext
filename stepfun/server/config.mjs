import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

// Load .env if present (Node >=20.12). Environment variables always win.
const envFile = path.join(root, ".env");
if (fs.existsSync(envFile)) {
  try {
    process.loadEnvFile(envFile);
  } catch {
    /* ignore a malformed optional env file */
  }
}

const mode = (process.env.SEEKDB_MODE || "server").toLowerCase();
const port = Number(process.env.PORT || 8787);
const host = process.env.HOST || "127.0.0.1";

export const config = {
  root,
  port,
  host,
  isProduction: process.env.NODE_ENV === "production",
  seekdb: {
    mode,
    path: process.env.SEEKDB_PATH || path.join(root, ".data", "seekdb"),
    host: process.env.SEEKDB_HOST || "127.0.0.1",
    port: Number(process.env.SEEKDB_PORT || 2881),
    user: process.env.SEEKDB_USER || "root",
    password: process.env.SEEKDB_PASSWORD || "",
    database: process.env.SEEKDB_DATABASE || "stepkb",
    connectTimeoutMs: Number(process.env.SEEKDB_CONNECT_TIMEOUT_MS || 15000),
  },
  model: {
    id: "bge-small-zh-v1.5",
    dimension: 512,
    pooling: "cls",
  },
};

export function seekdbArgs({ admin = false } = {}) {
  if (config.seekdb.mode === "embedded") {
    return { path: config.seekdb.path, ...(admin ? {} : { database: config.seekdb.database }) };
  }
  return {
    host: config.seekdb.host,
    port: config.seekdb.port,
    user: config.seekdb.user,
    password: config.seekdb.password,
    ...(admin ? { database: "information_schema" } : { database: config.seekdb.database }),
  };
}
