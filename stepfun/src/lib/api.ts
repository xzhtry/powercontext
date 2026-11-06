import type {
  Doc,
  HealthResponse,
  IngestDocument,
  IngestResult,
  Kb,
  SearchResponse,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: {
        "content-type": "application/json",
        ...(init?.headers || {}),
      },
    });
  } catch (error) {
    throw new Error(`无法连接本地服务：${error instanceof Error ? error.message : String(error)}`);
  }
  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = { error: text };
    }
  }
  if (!response.ok) {
    const message =
      (body as { error?: string } | null)?.error ||
      `请求失败（HTTP ${response.status}）`;
    throw new Error(message);
  }
  return body as T;
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),

  listKbs: () => request<{ items: Kb[] }>("/api/kbs"),

  createKb: (name: string, description = "") =>
    request<Kb>("/api/kbs", {
      method: "POST",
      body: JSON.stringify({ name, description }),
    }),

  deleteKb: (id: string) =>
    request<{ id: string }>(`/api/kbs/${encodeURIComponent(id)}`, { method: "DELETE" }),

  listDocs: (kbId: string) =>
    request<{ kb: Kb; items: Doc[] }>(`/api/kbs/${encodeURIComponent(kbId)}/docs`),

  deleteDoc: (kbId: string, docId: string) =>
    request<{ docId: string; deleteMs: number; refreshMs: number }>(
      `/api/kbs/${encodeURIComponent(kbId)}/docs/${encodeURIComponent(docId)}`,
      { method: "DELETE" },
    ),

  ingest: (kbId: string, doc: IngestDocument) =>
    request<IngestResult>(`/api/kbs/${encodeURIComponent(kbId)}/docs`, {
      method: "POST",
      body: JSON.stringify(doc),
    }),

  ingestBatch: (kbId: string, documents: IngestDocument[]) =>
    request<IngestResult>(`/api/kbs/${encodeURIComponent(kbId)}/docs/batch`, {
      method: "POST",
      body: JSON.stringify({ documents }),
    }),

  search: (
    kbId: string,
    payload: {
      query: string;
      embedding: number[];
      topK: number;
      mode: "hybrid" | "vector" | "fts";
    },
  ) =>
    request<SearchResponse>(`/api/kbs/${encodeURIComponent(kbId)}/search`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

export async function loadSamples<T>(file: string): Promise<T> {
  const response = await fetch(`/samples/${file}`, { headers: { accept: "application/json" } });
  if (!response.ok) throw new Error(`示例数据加载失败（HTTP ${response.status}）`);
  return (await response.json()) as T;
}
