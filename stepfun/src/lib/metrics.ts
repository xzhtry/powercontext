import type { PerformanceRecord } from "./types";

const KEY = "stepkb.performance.v1";

export function emptyPerformance(): PerformanceRecord {
  return { searches: [], ingests: [], loads: [] };
}

export function loadPerformance(): PerformanceRecord {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return emptyPerformance();
    const parsed = JSON.parse(raw) as PerformanceRecord;
    return {
      searches: Array.isArray(parsed.searches) ? parsed.searches.slice(-100) : [],
      ingests: Array.isArray(parsed.ingests) ? parsed.ingests.slice(-50) : [],
      loads: Array.isArray(parsed.loads) ? parsed.loads.slice(-20) : [],
    };
  } catch {
    return emptyPerformance();
  }
}

export function savePerformance(record: PerformanceRecord) {
  try {
    const trimmed: PerformanceRecord = {
      searches: record.searches.slice(-100),
      ingests: record.ingests.slice(-50),
      loads: record.loads.slice(-20),
    };
    localStorage.setItem(KEY, JSON.stringify(trimmed));
  } catch {
    /* quota errors are non-fatal */
  }
}

export function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

export function p95(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95))];
}

export function average(values: number[]): number | null {
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

export function formatMs(value: number | null | undefined, digits = 0): string {
  if (value == null || !Number.isFinite(value)) return "—";
  if (value < 1) return `${value.toFixed(2)} ms`;
  if (value < 1000) return `${value.toFixed(digits)} ms`;
  return `${(value / 1000).toFixed(2)} s`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || !Number.isFinite(bytes)) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MiB`;
}

export function formatNumber(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("zh-CN").format(Math.round(value));
}

export function downloadJson(filename: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function sha256Hex(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  if (crypto?.subtle) {
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
  }
  // Small deterministic fallback for non-secure contexts. The server still
  // treats this only as a duplicate-detection hint.
  let hash = 2166136261;
  for (const byte of bytes) {
    hash ^= byte;
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, "0").repeat(8);
}
