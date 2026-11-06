export type BackendKind = "webgpu" | "wasm";
export type BackendPreference = "auto" | "webgpu" | "wasm";
export type Precision = "fp16" | "int8";

export interface ModelFileRecord {
  file: string;
  bytes: number;
  sha256: string;
  source: string;
}

export interface ModelInfo {
  id: string;
  dimension: number;
  pooling: string;
  queryInstruction: string;
  license: string;
  source: string;
  revision: string | null;
  files: {
    fp32: ModelFileRecord | null;
    fp16: ModelFileRecord | null;
    int8: ModelFileRecord | null;
  };
  quantization: Record<string, string>;
}

export interface HealthResponse {
  ok: boolean;
  ready: boolean;
  error: string | null;
  app: string;
  version: string;
  uptimeSec: number;
  inference: {
    location: "browser";
    cloudInference: false;
    model: string;
    dimension: number;
  };
  retrieval: {
    location: "seekdb";
    mode: "embedded" | "server";
    database: string;
    version: string | null;
  };
  model: ModelInfo;
}

export interface Kb {
  id: string;
  name: string;
  description: string;
  collectionName: string;
  createdAt: number;
  updatedAt: number;
  docCount: number;
  chunkCount: number;
  dimension: number;
  embeddingModel: string;
}

export interface Doc {
  id: string;
  kbId: string;
  title: string;
  source: string;
  charCount: number;
  chunkCount: number;
  contentHash: string | null;
  createdAt: number;
}

export interface SearchHit {
  id: string;
  rank: number;
  docId: string;
  title: string;
  source: string;
  chunkIndex: number;
  chunkCount: number;
  text: string;
  score: number | null;
  scoreLabel: string;
  metadata: Record<string, unknown>;
}

export interface HybridTrace {
  generatedSql: string;
  searchParm: Record<string, unknown>;
  generatedAt: number;
  note: string;
}

export interface SearchResponse {
  hits: SearchHit[];
  mode: "hybrid" | "vector" | "fts" | "vector-fallback";
  query: string;
  ftsQuery: string;
  topK: number;
  dbMs: number;
  totalMs: number;
  count: number;
  seekdb: {
    engine: string | null;
    api: string;
    rank: string;
    rankWindowSize: number;
    rankConstant: number;
    fts: boolean;
    executedInDatabase: true;
  };
  hybridTrace: HybridTrace | null;
}

export interface IngestChunk {
  text: string;
  embedding: number[];
}

export interface IngestDocument {
  title: string;
  source: string;
  text: string;
  chunks: IngestChunk[];
  contentHash?: string;
}

export interface IngestResult {
  duplicate: boolean;
  imported?: number;
  duplicateCount?: number;
  docId?: string;
  title?: string;
  chunkCount?: number;
  writeMs?: number;
  refreshMs?: number;
  registryMs?: number;
  collectionCount?: number;
  message?: string;
  docs?: { docId: string; title: string; chunkCount: number }[];
}

export interface EngineStatus {
  state: "idle" | "loading" | "ready" | "error";
  backend: BackendKind | null;
  precision: Precision | null;
  loadMs: number | null;
  warmupMs: number | null;
  modelBytes: number | null;
  fallbackReason: string | null;
  accelerator: string | null;
  progress: ModelProgress | null;
  error: string | null;
}

export interface ModelProgress {
  file: string;
  loaded: number;
  total: number;
  percent: number;
  status: string;
}

export interface SearchMetrics {
  id: string;
  at: number;
  kbId: string;
  query: string;
  backend: BackendKind | null;
  precision: Precision | null;
  queryEmbedMs: number;
  dbMs: number;
  e2eMs: number;
  count: number;
  warm: boolean;
}

export interface IngestMetrics {
  id: string;
  at: number;
  kbId: string;
  docs: number;
  chunks: number;
  embedMs: number;
  writeMs: number;
  refreshMs: number;
  e2eMs: number;
  backend: BackendKind | null;
  precision: Precision | null;
  batchSize: number;
}

export interface PerformanceRecord {
  searches: SearchMetrics[];
  ingests: IngestMetrics[];
  loads: {
    at: number;
    backend: BackendKind;
    precision: Precision;
    loadMs: number;
    warmupMs: number;
    modelBytes: number;
  }[];
}
