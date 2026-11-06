import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const children = [];

function start(label, args, extraEnv = {}) {
  const child = spawn(process.execPath, args, {
    cwd: root,
    env: { ...process.env, ...extraEnv },
    stdio: "inherit",
    windowsHide: false,
  });
  child.on("exit", (code) => {
    console.log(`[dev] ${label} exited with ${code}`);
    stopAll();
    process.exit(code || 0);
  });
  children.push(child);
  return child;
}

function stopAll() {
  for (const child of children) {
    if (!child.killed) child.kill("SIGTERM");
  }
}

console.log("[dev] starting seekdb API on http://127.0.0.1:8787");
console.log("[dev] starting Vite on http://127.0.0.1:5173");
start("api", [path.join(root, "server", "index.mjs")]);
setTimeout(() => {
  start("vite", [path.join(root, "node_modules", "vite", "bin", "vite.js")]);
}, 1200);

process.on("SIGINT", () => {
  stopAll();
  process.exit(0);
});
process.on("SIGTERM", () => {
  stopAll();
  process.exit(0);
});
