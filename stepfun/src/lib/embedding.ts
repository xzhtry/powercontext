import type {
  BackendKind,
  BackendPreference,
  EngineStatus,
  ModelInfo,
  ModelProgress,
  Precision,
} from "./types";

const MODEL_ID = "bge-small-zh-v1.5";
const MODEL_ROOT = `/models/${MODEL_ID}`;
const QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章：";
const EXPECTED_DIMENSION = 512;

type Extractor = ((input: string | string[], options: Record<string, unknown>) => Promise<{
  dims: number[];
  tolist: () => number[][] | number[][][];
}>) & { dispose?: () => void };

interface WebGpuDetection {
  available: boolean;
  reason: string | null;
  accelerator: string | null;
}

export interface EmbeddingEngineSnapshot extends EngineStatus {
  detection: WebGpuDetection;
}

function emptyStatus(): EngineStatus {
  return {
    state: "idle",
    backend: null,
    precision: null,
    loadMs: null,
    warmupMs: null,
    modelBytes: null,
    fallbackReason: null,
    accelerator: null,
    progress: null,
    error: null,
  };
}

export class EmbeddingEngine {
  private extractor: Extractor | null = null;
  private status: EngineStatus = emptyStatus();
  private detection: WebGpuDetection | null = null;
  private modelInfo: ModelInfo | null = null;
  private listeners = new Set<(snapshot: EmbeddingEngineSnapshot) => void>();

  subscribe(listener: (snapshot: EmbeddingEngineSnapshot) => void): () => void {
    this.listeners.add(listener);
    listener(this.snapshot());
    return () => this.listeners.delete(listener);
  }

  snapshot(): EmbeddingEngineSnapshot {
    return {
      ...this.status,
      detection: this.detection || {
        available: false,
        reason: "尚未检测",
        accelerator: null,
      },
    };
  }

  private emit() {
    const snapshot = this.snapshot();
    for (const listener of this.listeners) listener(snapshot);
  }

  private patch(patch: Partial<EngineStatus>) {
    this.status = { ...this.status, ...patch };
    this.emit();
  }

  async detectWebGpu(): Promise<WebGpuDetection> {
    if (this.detection) return this.detection;
    const gpu = (navigator as unknown as { gpu?: any }).gpu;
    if (!gpu) {
      this.detection = {
        available: false,
        reason: "当前浏览器没有暴露 navigator.gpu",
        accelerator: null,
      };
      this.emit();
      return this.detection;
    }
    try {
      const adapter = await withTimeout(gpu.requestAdapter({ powerPreference: "high-performance" }), 4000);
      if (!adapter) {
        this.detection = {
          available: false,
          reason: "WebGPU 适配器请求返回空",
          accelerator: null,
        };
      } else {
        const typedAdapter = adapter as any;
        const info = typedAdapter.info || (await safeAdapterInfo(typedAdapter));
        const accelerator = [info?.vendor, info?.architecture, info?.device, info?.description]
          .filter(Boolean)
          .join(" · ") || "WebGPU 适配器可用";
        this.detection = { available: true, reason: null, accelerator };
      }
    } catch (error) {
      this.detection = {
        available: false,
        reason: `WebGPU 适配器不可用：${error instanceof Error ? error.message : String(error)}`,
        accelerator: null,
      };
    }
    this.emit();
    return this.detection;
  }

  async loadModel(
    preference: BackendPreference,
    onStatus?: (snapshot: EmbeddingEngineSnapshot) => void,
  ): Promise<void> {
    const unsubscribe = onStatus ? this.subscribe(onStatus) : () => {};
    try {
      await this.dispose();
      this.patch({
        state: "loading",
        backend: null,
        precision: null,
        loadMs: null,
        warmupMs: null,
        fallbackReason: null,
        progress: null,
        error: null,
      });

      const detection = await this.detectWebGpu();
      let backend: BackendKind = preference === "wasm" ? "wasm" : "webgpu";
      let fallbackReason: string | null = null;

      if (preference !== "wasm" && !detection.available) {
        backend = "wasm";
        fallbackReason = detection.reason || "WebGPU 不可用";
      }

      if (backend === "webgpu") {
        try {
          await this.initializePipeline("webgpu", detection.accelerator);
        } catch (error) {
          const reason = `WebGPU 初始化失败：${error instanceof Error ? error.message : String(error)}`;
          await this.dispose();
          backend = "wasm";
          fallbackReason = reason;
          await this.initializePipeline("wasm", null);
        }
      } else {
        await this.initializePipeline("wasm", detection.accelerator);
      }

      const warmStarted = performance.now();
      await this.embedRaw(["warmup"], false);
      const warmupMs = performance.now() - warmStarted;
      this.patch({
        state: "ready",
        warmupMs: Math.round(warmupMs * 10) / 10,
        fallbackReason,
      });
    } catch (error) {
      this.patch({
        state: "error",
        error: error instanceof Error ? error.message : String(error),
      });
      throw error;
    } finally {
      unsubscribe();
    }
  }

  private async initializePipeline(backend: BackendKind, accelerator: string | null) {
    const tf = await import("@huggingface/transformers");
    const env = tf.env as any;
    env.allowRemoteModels = false;
    env.allowLocalModels = true;
    env.localModelPath = "/models/";
    env.useBrowserCache = true;
    env.useWasmCache = true;
    env.backends.onnx.wasm.wasmPaths = {
      mjs: "/ort/ort-wasm-simd-threaded.jsep.mjs",
      wasm: "/ort/ort-wasm-simd-threaded.jsep.wasm",
    };
    env.backends.onnx.wasm.numThreads =
      typeof crossOriginIsolated !== "undefined" && crossOriginIsolated
        ? Math.min(4, Math.max(1, navigator.hardwareConcurrency || 2))
        : 1;
    env.backends.onnx.wasm.proxy = false;

    const dtype: Precision = backend === "webgpu" ? "fp16" : "int8";
    const precision = dtype === "fp16" ? "fp16" : "int8";
    const device = backend === "webgpu" ? "webgpu" : "wasm";
    this.patch({ backend, precision, accelerator });

    const loadStarted = performance.now();
    let lastProgress: ModelProgress | null = null;
    const extractor = await tf.pipeline("feature-extraction", MODEL_ID, {
      device,
      dtype: backend === "webgpu" ? "fp16" : "q8",
      progress_callback: (info: any) => {
        if (info?.status === "progress" && info.total) {
          lastProgress = {
            file: info.file || "model",
            loaded: info.loaded || 0,
            total: info.total,
            percent: Math.min(100, Math.round((info.loaded / info.total) * 100)),
            status: info.status,
          };
          this.patch({ progress: lastProgress });
        } else if (info?.status === "done" && lastProgress) {
          this.patch({
            progress: {
              ...lastProgress,
              loaded: lastProgress.total,
              percent: 100,
              status: "done",
            },
          });
        }
      },
    });
    this.extractor = extractor as unknown as Extractor;
    const loadMs = performance.now() - loadStarted;

    try {
      this.modelInfo = await fetch("/api/model").then((res) => (res.ok ? res.json() : null));
    } catch {
      this.modelInfo = null;
    }
    const record =
      precision === "fp16" ? this.modelInfo?.files.fp16 : this.modelInfo?.files.int8;
    this.patch({
      loadMs: Math.round(loadMs * 10) / 10,
      modelBytes: record?.bytes || null,
      progress: { file: `${MODEL_ID}/onnx/${precision === "fp16" ? "model_fp16" : "model_quantized"}.onnx`, loaded: record?.bytes || 0, total: record?.bytes || 0, percent: 100, status: "ready" },
    });
  }

  async embedDocuments(texts: string[]): Promise<number[][]> {
    return this.embedRaw(texts, false);
  }

  async embedQuery(query: string): Promise<number[]> {
    const [vector] = await this.embedRaw([`${QUERY_INSTRUCTION}${query}`], true);
    return vector;
  }

  private async embedRaw(texts: string[], _isQuery: boolean): Promise<number[][]> {
    if (!this.extractor) throw new Error("模型尚未加载");
    if (texts.length === 0) return [];
    const output = await this.extractor(texts, {
      pooling: "cls",
      normalize: true,
      truncation: true,
    });
    const list = output.tolist() as number[][];
    if (!Array.isArray(list) || list.length !== texts.length) {
      throw new Error("模型输出形状异常");
    }
    if (!list.every((vector) => Array.isArray(vector) && vector.length === EXPECTED_DIMENSION)) {
      throw new Error(`模型输出维度异常：期望 ${EXPECTED_DIMENSION}`);
    }
    return list;
  }

  async dispose() {
    try {
      if (this.extractor?.dispose) this.extractor.dispose();
      else if (this.extractor) (this.extractor as unknown as { dispose?: () => void }).dispose?.();
    } catch {
      /* ignore */
    }
    this.extractor = null;
  }
}

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`超时（${ms}ms）`)), ms);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}

async function safeAdapterInfo(adapter: any) {
  try {
    return await adapter.requestAdapterInfo?.();
  } catch {
    return null;
  }
}

export const embeddingInfo = {
  modelId: MODEL_ID,
  dimension: EXPECTED_DIMENSION,
  queryInstruction: QUERY_INSTRUCTION,
  modelRoot: MODEL_ROOT,
};
