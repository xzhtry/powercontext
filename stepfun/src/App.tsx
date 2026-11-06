import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type ReactNode,
} from "react";
import { api, loadSamples } from "./lib/api";
import { chunkDocument, type DocumentChunk } from "./lib/chunker";
import { EmbeddingEngine, embeddingInfo, type EmbeddingEngineSnapshot } from "./lib/embedding";
import {
  downloadJson,
  formatBytes,
  formatMs,
  formatNumber,
  loadPerformance,
  median,
  p95,
  savePerformance,
  sha256Hex,
} from "./lib/metrics";
import type {
  BackendPreference,
  Doc,
  EngineStatus,
  HealthResponse,
  IngestDocument,
  IngestMetrics,
  Kb,
  PerformanceRecord,
  SearchMetrics,
  SearchResponse,
} from "./lib/types";
import { Icon } from "./components/Icons";
import "./styles.css";

interface SampleDoc {
  id: string;
  title: string;
  source: string;
  tags: string[];
  text: string;
}

interface ImportProgress {
  busy: boolean;
  phase: "idle" | "chunking" | "embedding" | "writing" | "done" | "error";
  message: string;
  current: number;
  total: number;
  percent: number;
  detail?: string;
}

const EMPTY_PROGRESS: ImportProgress = {
  busy: false,
  phase: "idle",
  message: "",
  current: 0,
  total: 0,
  percent: 0,
};

type SearchMode = "hybrid" | "vector" | "fts";
type IngestTab = "sample" | "paste" | "file";

const BACKEND_PREF_KEY = "stepkb.backend-preference";
const ACTIVE_KB_KEY = "stepkb.active-kb";
const TOP_K_KEY = "stepkb.top-k";
const MODEL_EMBED_BATCH = 16;

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [kbs, setKbs] = useState<Kb[]>([]);
  const [activeKbId, setActiveKbId] = useState(() => localStorage.getItem(ACTIVE_KB_KEY) || "");
  const [docs, setDocs] = useState<Doc[]>([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [engineStatus, setEngineStatus] = useState<EngineStatus | null>(null);
  const [engineSnapshot, setEngineSnapshot] = useState<EmbeddingEngineSnapshot | null>(null);
  const [preference, setPreference] = useState<BackendPreference>(() => {
    const stored = localStorage.getItem(BACKEND_PREF_KEY);
    return stored === "webgpu" || stored === "wasm" ? stored : "auto";
  });
  const [searchQuery, setSearchQuery] = useState("");
  const [topK, setTopK] = useState(() => Number(localStorage.getItem(TOP_K_KEY)) || 8);
  const [searchMode, setSearchMode] = useState<SearchMode>("hybrid");
  const [searching, setSearching] = useState(false);
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null);
  const [lastSearchTiming, setLastSearchTiming] = useState<{
    embedMs: number;
    e2eMs: number;
    dbMs: number;
    warm: boolean;
  } | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [ingestTab, setIngestTab] = useState<IngestTab>("sample");
  const [progress, setProgress] = useState<ImportProgress>(EMPTY_PROGRESS);
  const [sampleDocs, setSampleDocs] = useState<SampleDoc[]>([]);
  const [sampleQueries, setSampleQueries] = useState<{ query: string; relevant: string[] }[]>([]);
  const [pasteTitle, setPasteTitle] = useState("");
  const [pasteText, setPasteText] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const [toast, setToast] = useState<{ message: string; kind: "ok" | "error" | "info" } | null>(null);
  const [showTech, setShowTech] = useState(false);
  const [showKbModal, setShowKbModal] = useState(false);
  const [newKbName, setNewKbName] = useState("");
  const [newKbDesc, setNewKbDesc] = useState("");
  const [kbSaving, setKbSaving] = useState(false);
  const [perf, setPerf] = useState<PerformanceRecord>(() => loadPerformance());
  const [showAllDocs, setShowAllDocs] = useState(false);

  const engineRef = useRef<EmbeddingEngine | null>(null);
  const progressRef = useRef<HTMLDivElement | null>(null);
  const toastTimer = useRef<number | null>(null);
  const docsRequestRef = useRef(0);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const activeKb = useMemo(
    () => kbs.find((kb) => kb.id === activeKbId) || null,
    [kbs, activeKbId],
  );
  const modelInfo = health?.model || null;
  const detection = engineSnapshot?.detection;
  const modelReady = engineStatus?.state === "ready";
  const showFallback = modelReady && Boolean(engineStatus?.fallbackReason);
  const visibleDocs = showAllDocs ? docs : docs.slice(0, 6);

  const notify = useCallback((message: string, kind: "ok" | "error" | "info" = "info") => {
    setToast({ message, kind });
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 4800);
  }, []);

  const refreshHealth = useCallback(async () => {
    try {
      const next = await api.health();
      setHealth(next);
      setHealthError(next.ok ? null : next.error || "seekdb 尚未就绪");
      return next;
    } catch (error) {
      setHealthError(error instanceof Error ? error.message : String(error));
      return null;
    }
  }, []);

  const refreshKbs = useCallback(async () => {
    try {
      const { items } = await api.listKbs();
      setKbs(items);
      return items;
    } catch (error) {
      setHealthError(error instanceof Error ? error.message : String(error));
      return [];
    }
  }, []);

  const refreshDocs = useCallback(async (kbId: string) => {
    if (!kbId) {
      setDocs([]);
      return;
    }
    const requestId = ++docsRequestRef.current;
    setDocsLoading(true);
    try {
      const { items } = await api.listDocs(kbId);
      if (requestId === docsRequestRef.current) setDocs(items);
    } catch (error) {
      if (requestId === docsRequestRef.current) {
        notify(error instanceof Error ? error.message : String(error), "error");
      }
    } finally {
      if (requestId === docsRequestRef.current) setDocsLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      const next = await refreshHealth();
      if (cancelled) return;
      if (next?.ok && kbs.length === 0) {
        await refreshKbs();
      }
    };
    tick();
    const timer = window.setInterval(tick, 12000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
    // Refresh cadence is intentionally independent of the current KB list.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshHealth]);

  useEffect(() => {
    let cancelled = false;
    loadSamples<SampleDoc[]>("corpus.json")
      .then((items) => {
        if (!cancelled) setSampleDocs(items);
      })
      .catch(() => {
        if (!cancelled) notify("示例语料加载失败，请确认 public/samples/corpus.json 存在", "error");
      });
    loadSamples<{ query: string; relevant: string[] }[]>("queries.json")
      .then((items) => {
        if (!cancelled) setSampleQueries(items);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [notify]);

  useEffect(() => {
    const engine = new EmbeddingEngine();
    engineRef.current = engine;
    const unsubscribe = engine.subscribe((snapshot) => {
      setEngineSnapshot(snapshot);
      setEngineStatus({
        state: snapshot.state,
        backend: snapshot.backend,
        precision: snapshot.precision,
        loadMs: snapshot.loadMs,
        warmupMs: snapshot.warmupMs,
        modelBytes: snapshot.modelBytes,
        fallbackReason: snapshot.fallbackReason,
        accelerator: snapshot.accelerator,
        progress: snapshot.progress,
        error: snapshot.error,
      });
    });
    engine.detectWebGpu();
    return () => {
      unsubscribe();
      engine.dispose();
    };
  }, []);

  // A narrowly gated automation surface used by scripts/bench-batch.mjs.
  // The normal UI never exposes inference handles to the page.
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("bench") !== "1") return;
    (window as unknown as { __STEPKB__: unknown }).__STEPKB__ = {
      get engine() {
        return engineRef.current;
      },
      get status() {
        return engineRef.current?.snapshot();
      },
      embeddingInfo,
    };
  }, []);

  useEffect(() => {
    if (kbs.length === 0) {
      if (activeKbId) setActiveKbId("");
      return;
    }
    if (!kbs.some((kb) => kb.id === activeKbId)) {
      setActiveKbId(kbs[0].id);
    }
  }, [kbs, activeKbId]);

  useEffect(() => {
    if (activeKbId) {
      localStorage.setItem(ACTIVE_KB_KEY, activeKbId);
      setSearchResult(null);
      setLastSearchTiming(null);
      setSearchError(null);
      if (!progress.busy) setProgress(EMPTY_PROGRESS);
      void refreshDocs(activeKbId);
    } else {
      setDocs([]);
    }
    // Progress must not be reset while an import is still running; KB switching
    // is blocked in that state by the sidebar click handler.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeKbId, refreshDocs]);

  useEffect(() => {
    localStorage.setItem(BACKEND_PREF_KEY, preference);
  }, [preference]);

  useEffect(() => {
    localStorage.setItem(TOP_K_KEY, String(topK));
  }, [topK]);

  useEffect(() => {
    if (progress.busy && progressRef.current) {
      progressRef.current.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [progress.busy, progress.phase]);

  const recordLoad = useCallback((snapshot: EmbeddingEngineSnapshot) => {
    if (!snapshot.backend || !snapshot.precision || snapshot.loadMs == null) return;
    setPerf((previous) => {
      const next: PerformanceRecord = {
        ...previous,
        loads: [
          ...previous.loads,
          {
            at: Date.now(),
            backend: snapshot.backend!,
            precision: snapshot.precision!,
            loadMs: snapshot.loadMs!,
            warmupMs: snapshot.warmupMs || 0,
            modelBytes: snapshot.modelBytes || 0,
          },
        ].slice(-20),
      };
      savePerformance(next);
      return next;
    });
  }, []);

  const handleLoadModel = useCallback(async () => {
    const engine = engineRef.current;
    if (!engine) return;
    try {
      await engine.loadModel(preference);
      const snapshot = engine.snapshot();
      recordLoad(snapshot);
      notify(
        snapshot.fallbackReason
          ? "WebGPU 不可用，已自动降级到 WASM INT8，核心流程可正常使用"
          : `端侧模型已就绪：${snapshot.backend === "webgpu" ? "WebGPU" : "WASM"} · ${
              snapshot.precision === "fp16" ? "FP16" : "INT8"
            }`,
        snapshot.fallbackReason ? "info" : "ok",
      );
    } catch (error) {
      notify(error instanceof Error ? error.message : String(error), "error");
    }
  }, [notify, preference, recordLoad]);

  const handleCreateKb = async (event: FormEvent) => {
    event.preventDefault();
    if (!newKbName.trim()) return;
    if (progress.busy) {
      notify("导入进行中，完成后再新建知识库", "info");
      return;
    }
    setKbSaving(true);
    try {
      const kb = await api.createKb(newKbName.trim(), newKbDesc.trim());
      await refreshKbs();
      setActiveKbId(kb.id);
      setShowKbModal(false);
      setNewKbName("");
      setNewKbDesc("");
      notify(`已创建知识库「${kb.name}」`, "ok");
    } catch (error) {
      notify(error instanceof Error ? error.message : String(error), "error");
    } finally {
      setKbSaving(false);
    }
  };

  const handleDeleteKb = async (kb: Kb) => {
    if (!window.confirm(`删除知识库「${kb.name}」及其全部文档？此操作不可撤销。`)) return;
    try {
      await api.deleteKb(kb.id);
      const remaining = await refreshKbs();
      if (activeKbId === kb.id) setActiveKbId(remaining[0]?.id || "");
      notify(`已删除知识库「${kb.name}」`, "ok");
    } catch (error) {
      notify(error instanceof Error ? error.message : String(error), "error");
    }
  };

  const handleDeleteDoc = async (doc: Doc) => {
    if (!activeKb) return;
    if (!window.confirm(`从「${activeKb.name}」删除《${doc.title}》？`)) return;
    try {
      const result = await api.deleteDoc(activeKb.id, doc.id);
      await Promise.all([refreshDocs(activeKb.id), refreshKbs()]);
      setSearchResult(null);
      notify(`已删除文档并刷新索引（${formatMs(result.refreshMs)}）`, "ok");
    } catch (error) {
      notify(error instanceof Error ? error.message : String(error), "error");
    }
  };

  const hasWarmSearch = useMemo(
    () =>
      perf.searches.some(
        (item) =>
          item.kbId === activeKbId &&
          item.backend === engineStatus?.backend &&
          item.precision === engineStatus?.precision,
      ),
    [perf.searches, activeKbId, engineStatus?.backend, engineStatus?.precision],
  );

  const handleSearch = async (event?: FormEvent, overrideQuery?: string) => {
    event?.preventDefault();
    const query = (overrideQuery ?? searchQuery).trim();
    if (!query) return;
    if (!activeKb) {
      notify("请先选择或创建一个知识库", "error");
      return;
    }
    if (!modelReady) {
      notify("请先初始化端侧模型", "error");
      return;
    }
    if (searching) return;
    const engine = engineRef.current;
    if (!engine) return;

    setSearching(true);
    setSearchError(null);
    const started = performance.now();
    try {
      const embedStarted = performance.now();
      const embedding = await engine.embedQuery(query);
      const embedMs = performance.now() - embedStarted;
      const result = await api.search(activeKb.id, {
        query,
        embedding,
        topK,
        mode: searchMode,
      });
      setSearchResult(result);
      setSearchQuery(query);
      const warm = hasWarmSearch;
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
      const e2eMs = performance.now() - started;
      setLastSearchTiming({ embedMs, e2eMs, dbMs: result.dbMs, warm });
      const metric: SearchMetrics = {
        id: crypto.randomUUID(),
        at: Date.now(),
        kbId: activeKb.id,
        query,
        backend: engineStatus?.backend || null,
        precision: engineStatus?.precision || null,
        queryEmbedMs: Math.round(embedMs * 10) / 10,
        dbMs: result.dbMs,
        e2eMs: Math.round(e2eMs * 10) / 10,
        count: result.count,
        warm,
      };
      setPerf((previous) => {
        const next = { ...previous, searches: [...previous.searches, metric].slice(-100) };
        savePerformance(next);
        return next;
      });
    } catch (error) {
      setSearchError(error instanceof Error ? error.message : String(error));
    } finally {
      setSearching(false);
    }
  };

  const importDocuments = useCallback(
    async (items: { title: string; source: string; text: string }[]) => {
      if (!activeKb) {
        notify("请先选择或创建一个知识库", "error");
        return;
      }
      if (!modelReady || !engineRef.current) {
        notify("请先初始化端侧模型", "error");
        return;
      }
      if (progress.busy) return;
      const valid = items.filter((item) => item.text.trim().length > 0);
      if (valid.length === 0) {
        notify("没有可导入的文本内容", "error");
        return;
      }

      setProgress({
        busy: true,
        phase: "chunking",
        message: "正在切分文档…",
        current: 0,
        total: valid.length,
        percent: 0,
      });
      const started = performance.now();
      try {
        const knownHashes = new Set(docs.map((doc) => doc.contentHash).filter(Boolean) as string[]);
        const prepared: {
          title: string;
          source: string;
          text: string;
          hash: string;
          chunks: DocumentChunk[];
        }[] = [];
        let skipped = 0;
        for (const item of valid) {
          const text = item.text.trim();
          if (text.length > 250_000) {
            throw new Error(`《${item.title}》超过 250,000 字符，请拆分后再导入`);
          }
          const hash = await sha256Hex(text);
          if (knownHashes.has(hash)) {
            skipped += 1;
            continue;
          }
          knownHashes.add(hash);
          const chunks = chunkDocument(text);
          if (chunks.length === 0) continue;
          prepared.push({
            title: item.title.trim() || "未命名文档",
            source: item.source || item.title,
            text,
            hash,
            chunks,
          });
        }

        if (prepared.length === 0) {
          setProgress(EMPTY_PROGRESS);
          notify(skipped > 0 ? "这批文档均已存在，未重复导入" : "没有可导入的文本", "info");
          return;
        }

        const flatChunks: { docIndex: number; chunkIndex: number; text: string }[] = [];
        prepared.forEach((doc, docIndex) => {
          doc.chunks.forEach((chunk, chunkIndex) => {
            flatChunks.push({ docIndex, chunkIndex, text: chunk.text });
          });
        });
        const totalChunks = flatChunks.length;
        const vectors = new Map<string, number[]>();
        const embedStarted = performance.now();
        for (let start = 0; start < flatChunks.length; start += MODEL_EMBED_BATCH) {
          const batch = flatChunks.slice(start, start + MODEL_EMBED_BATCH);
          const embedded = await engineRef.current.embedDocuments(batch.map((chunk) => chunk.text));
          embedded.forEach((vector, offset) => {
            const item = batch[offset];
            vectors.set(`${item.docIndex}:${item.chunkIndex}`, vector);
          });
          const current = Math.min(totalChunks, start + batch.length);
          setProgress({
            busy: true,
            phase: "embedding",
            message: `浏览器本地向量化中 · batch ${Math.floor(start / MODEL_EMBED_BATCH) + 1}`,
            current,
            total: totalChunks,
            percent: Math.round((current / totalChunks) * 78),
            detail: `${MODEL_EMBED_BATCH} 条/批 · ${engineStatus?.backend === "webgpu" ? "WebGPU" : "WASM"}`,
          });
          // Let React paint the progress bar between batches.
          await new Promise<void>((resolve) => setTimeout(resolve, 0));
        }
        const embedMs = performance.now() - embedStarted;

        const documents: IngestDocument[] = prepared.map((doc, docIndex) => ({
          title: doc.title,
          source: doc.source,
          text: doc.text,
          contentHash: doc.hash,
          chunks: doc.chunks.map((chunk, chunkIndex) => ({
            text: chunk.text,
            embedding: vectors.get(`${docIndex}:${chunkIndex}`) || [],
          })),
        }));

        setProgress({
          busy: true,
          phase: "writing",
          message: "写入 seekdb 并刷新索引…",
          current: totalChunks,
          total: totalChunks,
          percent: 86,
          detail: `${documents.length} 篇文档 · ${totalChunks} 个分块`,
        });
        const result = await api.ingestBatch(activeKb.id, documents);
        const e2eMs = performance.now() - started;
        const totalDuplicates = (result.duplicateCount || 0) + skipped;
        const metric: IngestMetrics = {
          id: crypto.randomUUID(),
          at: Date.now(),
          kbId: activeKb.id,
          docs: prepared.length,
          chunks: totalChunks,
          embedMs: Math.round(embedMs * 10) / 10,
          writeMs: result.writeMs || 0,
          refreshMs: result.refreshMs || 0,
          e2eMs: Math.round(e2eMs * 10) / 10,
          backend: engineStatus?.backend || null,
          precision: engineStatus?.precision || null,
          batchSize: MODEL_EMBED_BATCH,
        };
        setPerf((previous) => {
          const next = { ...previous, ingests: [...previous.ingests, metric].slice(-50) };
          savePerformance(next);
          return next;
        });
        setProgress({
          busy: false,
          phase: "done",
          message: `导入完成：${prepared.length} 篇 · ${totalChunks} 个分块`,
          current: totalChunks,
          total: totalChunks,
          percent: 100,
          detail: `向量化 ${formatMs(embedMs)} · 写入+刷新 ${formatMs(result.writeMs)}`,
        });
        await Promise.all([refreshDocs(activeKb.id), refreshKbs()]);
        notify(
          totalDuplicates > 0
            ? `导入完成，跳过 ${totalDuplicates} 篇重复文档`
            : `已导入 ${prepared.length} 篇文档，索引已刷新，可立即检索`,
          "ok",
        );
      } catch (error) {
        setProgress({
          busy: false,
          phase: "error",
          message: error instanceof Error ? error.message : String(error),
          current: 0,
          total: 0,
          percent: 0,
        });
        notify(error instanceof Error ? error.message : String(error), "error");
      }
    },
    [activeKb, docs, engineStatus?.backend, engineStatus?.precision, modelReady, notify, progress.busy, refreshDocs, refreshKbs],
  );

  const handleImportSample = () => {
    if (sampleDocs.length === 0) {
      notify("示例语料尚未加载完成", "error");
      return;
    }
    void importDocuments(sampleDocs.map((doc) => ({ title: doc.title, source: doc.source, text: doc.text })));
  };

  const handleImportPaste = () => {
    if (!pasteText.trim()) {
      notify("请粘贴文档内容", "error");
      return;
    }
    void importDocuments([
      {
        title: pasteTitle.trim() || "未命名文档",
        source: "paste.txt",
        text: pasteText,
      },
    ]);
  };

  const handleFiles = async (files: FileList | File[]) => {
    const list = Array.from(files).filter((file) => /\.(txt|md|markdown)$/i.test(file.name));
    if (list.length === 0) {
      notify("目前支持 .txt / .md 文本文件", "error");
      return;
    }
    const items: { title: string; source: string; text: string }[] = [];
    for (const file of list) {
      if (file.size > 2 * 1024 * 1024) {
        notify(`《${file.name}》超过 2 MiB，已跳过`, "error");
        continue;
      }
      const text = await file.text();
      const heading = text.match(/^#{1,6}\s+(.+?)\s*$/m)?.[1]?.trim();
      items.push({
        title: heading || file.name.replace(/\.(txt|md|markdown)$/i, ""),
        source: file.name,
        text,
      });
    }
    await importDocuments(items);
  };

  const handleFileInput = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) void handleFiles(event.target.files);
    event.target.value = "";
  };

  const clearPerformance = () => {
    if (!window.confirm("清空本机保存的性能记录？")) return;
    const empty: PerformanceRecord = { searches: [], ingests: [], loads: [] };
    setPerf(empty);
    savePerformance(empty);
  };

  const sampleQueriesForUi = sampleQueries.slice(0, 4);
  const searchPlaceholder =
    activeKb?.docCount && activeKb.docCount > 0
      ? "试试：如何让新导入的文档立刻被检索到？"
      : "先导入示例语料，再输入问题…";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Icon name="logo" size={26} />
          </div>
          <div>
            <div className="brand-name">StepKB</div>
            <div className="brand-sub">端侧知识库 · seekdb</div>
          </div>
        </div>

        <div className="sidebar-section">
          <div className="sidebar-heading">
            <span>知识库</span>
            <button className="icon-btn inverse" title="新建知识库" onClick={() => setShowKbModal(true)}>
              <Icon name="plus" size={16} />
            </button>
          </div>
          <div className="kb-list">
            {kbs.length === 0 && (
              <div className="kb-empty">
                {health?.ready ? "还没有知识库" : "等待 seekdb 连接…"}
              </div>
            )}
            {kbs.map((kb) => (
              <button
                key={kb.id}
                className={`kb-item ${kb.id === activeKbId ? "active" : ""}`}
                disabled={progress.busy}
                onClick={() => {
                  if (progress.busy) {
                    notify("导入进行中，完成后再切换知识库", "info");
                    return;
                  }
                  setActiveKbId(kb.id);
                }}
              >
                <span className="kb-icon">
                  <Icon name="layers" size={16} />
                </span>
                <span className="kb-copy">
                  <span className="kb-name">{kb.name}</span>
                  <span className="kb-meta">
                    {formatNumber(kb.docCount)} 篇 · {formatNumber(kb.chunkCount)} 块
                  </span>
                </span>
                {kb.id === activeKbId && <span className="kb-active-dot" />}
              </button>
            ))}
          </div>
          <button className="new-kb-btn" onClick={() => setShowKbModal(true)}>
            <Icon name="plus" size={15} /> 新建知识库
          </button>
        </div>

        <div className="sidebar-section sidebar-bottom">
          <div className="db-card">
            <div className="db-card-top">
              <span className={`status-dot ${health?.ready ? "ok" : "bad"}`} />
              <span>seekdb</span>
              <span className="db-mode">{health?.retrieval.mode || "—"}</span>
            </div>
            <div className="db-version">{health?.retrieval.version || healthError || "连接中…"}</div>
            <div className="db-line">
              <Icon name="shield" size={13} /> 向量、原文与检索均在 seekdb
            </div>
          </div>
          <div className="privacy-note">
            <Icon name="lock" size={14} />
            <span>推理在本机浏览器完成，无云端 API</span>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="mobile-brand">
            <div className="brand-mark small">
              <Icon name="logo" size={20} />
            </div>
            <span>StepKB</span>
          </div>
          <div className="topbar-title">
            <div className="crumbs">
              <span>工作台</span>
              <span className="crumb-sep">/</span>
              <span className="current">{activeKb?.name || "未选择知识库"}</span>
            </div>
            <h1>
              端侧推理 × seekdb
              <span className="gradient-text">混合检索</span>
            </h1>
          </div>
          <div className="topbar-actions">
            <BackendBadge status={engineStatus} />
            <button className="ghost-btn" onClick={() => setShowTech(true)}>
              <Icon name="book" size={16} /> 技术说明
            </button>
          </div>
        </header>

        {showFallback && (
          <div className="notice amber">
            <Icon name="alert" size={17} />
            <div>
              <strong>已自动降级到 WASM · INT8</strong>
              <span>{engineStatus?.fallbackReason}</span>
            </div>
          </div>
        )}

        {!health?.ready && (
          <div className="notice red">
            <Icon name="database" size={18} />
            <div>
              <strong>seekdb 尚未就绪</strong>
              <span>{healthError || health?.error || "正在连接本地 seekdb…"}</span>
            </div>
            <button className="small-btn" onClick={() => void refreshHealth()}>
              重试
            </button>
          </div>
        )}

        <section className="hero-card">
          <div className="hero-copy">
            <div className="eyebrow">
              <span className="pulse-dot" />
              LOCAL-FIRST KNOWLEDGE BASE
            </div>
            <h2>
              让每一段文字，
              <br />
              都在浏览器里变成
              <span className="hero-highlight">可检索的向量</span>
            </h2>
            <p>
              使用 BGE-small-zh-v1.5 在本地编码，向量、原文和元数据写入 seekdb；
              查询时由 seekdb 在数据库内完成全文 + 向量 RRF 混合检索。
            </p>
            <div className="hero-chips">
              <span>
                <Icon name="cpu" size={15} /> WebGPU / WASM
              </span>
              <span>
                <Icon name="database" size={15} /> seekdb 1.4
              </span>
              <span>
                <Icon name="lock" size={15} /> 0 云端推理
              </span>
            </div>
          </div>
          <div className="hero-visual" aria-hidden="true">
            <div className="orbit orbit-one" />
            <div className="orbit orbit-two" />
            <div className="hero-core">
              <div className="hero-core-icon">
                <Icon name="sparkles" size={26} />
              </div>
              <div className="hero-core-label">512d · zh</div>
            </div>
            <div className="float-card float-a">
              <span className="float-k">embed</span>
              <strong>{engineStatus?.backend === "webgpu" ? "GPU" : "WASM"}</strong>
            </div>
            <div className="float-card float-b">
              <span className="float-k">rank</span>
              <strong>RRF 60</strong>
            </div>
            <div className="float-card float-c">
              <span className="float-k">store</span>
              <strong>seekdb</strong>
            </div>
          </div>
        </section>

        <ModelSetup
          status={engineStatus}
          detection={detection}
          modelInfo={modelInfo}
          preference={preference}
          onPreference={setPreference}
          onLoad={() => void handleLoadModel()}
          health={health}
        />

        <div className="workspace">
          <div className="primary-column">
            <section className="card search-card">
              <div className="card-head">
                <div>
                  <div className="card-kicker">
                    <Icon name="search" size={15} /> HYBRID RETRIEVAL
                  </div>
                  <h3>在知识库中提问</h3>
                </div>
                <div className="search-toolbar">
                  <div className="segmented" role="group" aria-label="检索模式">
                    <button
                      className={searchMode === "hybrid" ? "selected" : ""}
                      onClick={() => setSearchMode("hybrid")}
                      title="seekdb 内完成全文 + 向量 RRF 融合"
                    >
                      混合检索
                    </button>
                    <button
                      className={searchMode === "vector" ? "selected" : ""}
                      onClick={() => setSearchMode("vector")}
                    >
                      仅语义
                    </button>
                    <button
                      className={searchMode === "fts" ? "selected" : ""}
                      onClick={() => setSearchMode("fts")}
                    >
                      仅全文
                    </button>
                  </div>
                  <select
                    className="topk-select"
                    value={topK}
                    onChange={(event) => setTopK(Number(event.target.value))}
                    aria-label="结果数量"
                  >
                    {[5, 8, 12, 20].map((value) => (
                      <option key={value} value={value}>
                        Top {value}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <form className="search-form" onSubmit={(event) => void handleSearch(event)}>
                <div className="search-input-wrap">
                  <Icon name="search" size={20} />
                  <input
                    value={searchQuery}
                    onChange={(event) => setSearchQuery(event.target.value)}
                    placeholder={searchPlaceholder}
                    disabled={searching}
                    aria-label="检索查询"
                  />
                  {searchQuery && (
                    <button
                      type="button"
                      className="clear-input"
                      aria-label="清空查询"
                      onClick={() => setSearchQuery("")}
                    >
                      <Icon name="close" size={15} />
                    </button>
                  )}
                </div>
                <button
                  className="primary-btn"
                  type="submit"
                  disabled={searching || !modelReady || !activeKb || !searchQuery.trim()}
                >
                  {searching ? <span className="spinner light" /> : <Icon name="arrow" size={17} />}
                  {searching ? "检索中" : "检索"}
                </button>
              </form>

              <div className="search-hints">
                <span className="hint-label">试试</span>
                {(sampleQueriesForUi.length
                  ? sampleQueriesForUi
                  : [
                      { query: "seekdb 是怎么融合两路检索结果的？" },
                      { query: "WebGPU 不可用时会发生什么？" },
                      { query: "新文档什么时候可以被检索到？" },
                    ]
                ).map((item) => (
                  <button
                    key={item.query}
                    className="hint-chip"
                    onClick={() => {
                      setSearchQuery(item.query);
                      void handleSearch(undefined, item.query);
                    }}
                    disabled={!modelReady || searching}
                  >
                    {item.query}
                  </button>
                ))}
              </div>

              <div className="mode-note">
                {searchMode === "hybrid" ? (
                  <>
                    <Icon name="database" size={14} />
                    查询向量 + 全文条件一次提交给 seekdb，由 <code>DBMS_HYBRID_SEARCH</code> 生成单条 SQL 完成 RRF 融合。
                  </>
                ) : searchMode === "vector" ? (
                  <>
                    <Icon name="info" size={14} />
                    仅语义模式只调用 seekdb 向量查询，用于对照；正式验收请使用混合检索。
                  </>
                ) : (
                  <>
                    <Icon name="info" size={14} />
                    仅全文模式只调用 seekdb 全文过滤，不计算语义相似度。
                  </>
                )}
              </div>

              {searchError && (
                <div className="inline-error">
                  <Icon name="alert" size={16} /> {searchError}
                </div>
              )}

              {searchResult && (
                <SearchResults
                  result={searchResult}
                  query={searchResult.query}
                  timing={lastSearchTiming}
                />
              )}
            </section>

            <section className="card ingest-card">
              <div className="card-head">
                <div>
                  <div className="card-kicker">
                    <Icon name="upload" size={15} /> INGEST PIPELINE
                  </div>
                  <h3>导入语料</h3>
                </div>
                <div className="ingest-stats">
                  <span>{formatNumber(activeKb?.docCount || 0)} 篇文档</span>
                  <span>{formatNumber(activeKb?.chunkCount || 0)} 个分块</span>
                </div>
              </div>

              <div className="tab-row">
                <button
                  className={ingestTab === "sample" ? "tab active" : "tab"}
                  onClick={() => setIngestTab("sample")}
                >
                  <Icon name="sparkles" size={15} /> 示例语料
                </button>
                <button
                  className={ingestTab === "paste" ? "tab active" : "tab"}
                  onClick={() => setIngestTab("paste")}
                >
                  <Icon name="file" size={15} /> 粘贴文本
                </button>
                <button
                  className={ingestTab === "file" ? "tab active" : "tab"}
                  onClick={() => setIngestTab("file")}
                >
                  <Icon name="upload" size={15} /> 上传文件
                </button>
              </div>

              {ingestTab === "sample" && (
                <div className="sample-panel">
                  <div className="sample-copy">
                    <div className="sample-icon">
                      <Icon name="layers" size={22} />
                    </div>
                    <div>
                      <strong>{sampleDocs.length || 20} 篇中文技术文档</strong>
                      <p>
                        覆盖 seekdb 混合检索、RRF、HNSW、量化、WebGPU、WASM 降级与性能评测。
                        首次导入会依次完成切分、本地向量化、写入与索引刷新。
                      </p>
                    </div>
                  </div>
                  <button
                    className="primary-btn"
                    onClick={handleImportSample}
                    disabled={progress.busy || !modelReady || !activeKb}
                  >
                    {progress.busy ? <span className="spinner light" /> : <Icon name="bolt" size={16} />}
                    导入示例语料
                  </button>
                </div>
              )}

              {ingestTab === "paste" && (
                <div className="paste-panel">
                  <label className="field">
                    <span>标题</span>
                    <input
                      value={pasteTitle}
                      onChange={(event) => setPasteTitle(event.target.value)}
                      placeholder="例如：团队新员工 FAQ"
                    />
                  </label>
                  <label className="field">
                    <span>
                      正文 <em>{formatNumber(pasteText.length)} 字符</em>
                    </span>
                    <textarea
                      value={pasteText}
                      onChange={(event) => setPasteText(event.target.value)}
                      placeholder="粘贴 Markdown 或纯文本，系统会按标题与段落自动分块…"
                      rows={6}
                    />
                  </label>
                  <div className="panel-actions">
                    <span className="muted">
                      <Icon name="lock" size={13} /> 文本只发送给本地 seekdb，不经过云端推理
                    </span>
                    <button
                      className="primary-btn"
                      onClick={handleImportPaste}
                      disabled={progress.busy || !modelReady || !activeKb || !pasteText.trim()}
                    >
                      {progress.busy ? <span className="spinner light" /> : <Icon name="upload" size={16} />}
                      本地向量化并导入
                    </button>
                  </div>
                </div>
              )}

              {ingestTab === "file" && (
                <div className="file-panel">
                  <div
                    className={`drop-zone ${dragActive ? "drag-active" : ""}`}
                    onDragOver={(event) => {
                      event.preventDefault();
                      setDragActive(true);
                    }}
                    onDragLeave={() => setDragActive(false)}
                    onDrop={(event) => {
                      event.preventDefault();
                      setDragActive(false);
                      if (event.dataTransfer.files) void handleFiles(event.dataTransfer.files);
                    }}
                    onClick={() => fileInputRef.current?.click()}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") fileInputRef.current?.click();
                    }}
                  >
                    <span className="drop-icon">
                      <Icon name="upload" size={24} />
                    </span>
                    <strong>拖入 .txt / .md 文件</strong>
                    <span>或点击选择文件 · 单文件 ≤ 2 MiB</span>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".txt,.md,.markdown,text/plain,text/markdown"
                      multiple
                      hidden
                      onChange={handleFileInput}
                    />
                  </div>
                  <div className="file-tips">
                    <span>
                      <Icon name="file" size={14} /> 支持多文件批量导入
                    </span>
                    <span>
                      <Icon name="bolt" size={14} /> 16 条/批本地推理
                    </span>
                    <span>
                      <Icon name="refresh" size={14} /> 整批刷新一次索引
                    </span>
                  </div>
                </div>
              )}

              {progress.busy || progress.phase === "done" || progress.phase === "error" ? (
                <div className={`progress-panel ${progress.phase}`} ref={progressRef}>
                  <div className="progress-top">
                    <span>
                      {progress.phase === "done" ? (
                        <Icon name="check" size={16} />
                      ) : progress.phase === "error" ? (
                        <Icon name="alert" size={16} />
                      ) : (
                        <span className="spinner" />
                      )}
                      {progress.message}
                    </span>
                    {progress.total > 0 && (
                      <span className="progress-count">
                        {progress.current}/{progress.total}
                      </span>
                    )}
                  </div>
                  <div className="progress-track">
                    <div
                      className={`progress-fill ${progress.phase === "error" ? "error" : ""}`}
                      style={{ width: `${Math.max(progress.phase === "done" ? 100 : progress.percent, 4)}%` }}
                    />
                  </div>
                  <div className="progress-detail">
                    {progress.detail || "所有推理在浏览器内完成"}
                  </div>
                </div>
              ) : null}
            </section>
          </div>

          <aside className="inspector">
            <PerformanceCard
              perf={perf}
              engineStatus={engineStatus}
              onExport={() =>
                downloadJson("stepkb-performance.json", {
                  exportedAt: new Date().toISOString(),
                  model: modelInfo,
                  engine: engineStatus,
                  records: perf,
                })
              }
              onClear={clearPerformance}
            />
            <DocsCard
              docs={visibleDocs}
              total={docs.length}
              loading={docsLoading}
              activeKb={activeKb}
              showAll={showAllDocs}
              onToggle={() => setShowAllDocs((value) => !value)}
              onDelete={(doc) => void handleDeleteDoc(doc)}
              onImport={() => setIngestTab("sample")}
            />
            <div className="card tip-card">
              <div className="tip-icon">
                <Icon name="info" size={18} />
              </div>
              <div>
                <strong>验收路径</strong>
                <p>
                  初始化模型 → 导入示例语料 → 混合检索 → 查看结果下方的 seekdb 生成 SQL，
                  即可验证存储与融合都发生在数据库内。
                </p>
              </div>
            </div>
          </aside>
        </div>

        <footer className="footer">
          <span>
            StepKB · BGE-small-zh-v1.5 · {modelInfo?.license || "MIT"} · 推理在浏览器本地完成
          </span>
          <span className="footer-right">
            <button onClick={() => setShowTech(true)}>技术说明</button>
            <a href="https://github.com/oceanbase/powercontext/tree/2026-competition-ecosystem" target="_blank" rel="noreferrer">
              比赛分支
            </a>
          </span>
        </footer>
      </main>

      {toast && (
        <div className={`toast ${toast.kind}`} role="status">
          <span className="toast-icon">
            <Icon name={toast.kind === "ok" ? "check" : toast.kind === "error" ? "alert" : "info"} size={16} />
          </span>
          {toast.message}
        </div>
      )}

      {showKbModal && (
        <Modal title="新建知识库" onClose={() => setShowKbModal(false)}>
          <form className="modal-form" onSubmit={handleCreateKb}>
            <label className="field">
              <span>名称</span>
              <input
                autoFocus
                value={newKbName}
                onChange={(event) => setNewKbName(event.target.value)}
                placeholder="例如：产品文档 / 论文笔记"
                maxLength={80}
              />
            </label>
            <label className="field">
              <span>描述（可选）</span>
              <textarea
                value={newKbDesc}
                onChange={(event) => setNewKbDesc(event.target.value)}
                rows={3}
                maxLength={500}
                placeholder="这个知识库收录什么内容？"
              />
            </label>
            <div className="modal-actions">
              <button type="button" className="ghost-btn" onClick={() => setShowKbModal(false)}>
                取消
              </button>
              <button type="submit" className="primary-btn" disabled={kbSaving || !newKbName.trim()}>
                {kbSaving ? <span className="spinner light" /> : <Icon name="plus" size={16} />}
                创建
              </button>
            </div>
          </form>
        </Modal>
      )}

      {showTech && (
        <TechNoteModal
          health={health}
          engineStatus={engineStatus}
          perf={perf}
          onClose={() => setShowTech(false)}
        />
      )}
    </div>
  );
}

function BackendBadge({ status }: { status: EngineStatus | null }) {
  if (!status || status.state === "idle") {
    return (
      <span className="backend-badge idle">
        <span className="status-dot bad" /> 模型未加载
      </span>
    );
  }
  if (status.state === "loading") {
    return (
      <span className="backend-badge loading">
        <span className="spinner" /> 加载模型 {status.progress?.percent ?? 0}%
      </span>
    );
  }
  if (status.state === "error") {
    return (
      <span className="backend-badge error">
        <span className="status-dot bad" /> 模型错误
      </span>
    );
  }
  return (
    <span className={`backend-badge ${status.backend}`}>
      <span className="status-dot ok" />
      {status.backend === "webgpu" ? "WebGPU" : "WASM"} · {status.precision === "fp16" ? "FP16" : "INT8"}
      {status.fallbackReason && <span className="badge-warn">降级</span>}
    </span>
  );
}

function ModelSetup({
  status,
  detection,
  modelInfo,
  preference,
  onPreference,
  onLoad,
  health,
}: {
  status: EngineStatus | null;
  detection?: { available: boolean; reason: string | null; accelerator: string | null };
  modelInfo: HealthResponse["model"] | null;
  preference: BackendPreference;
  onPreference: (value: BackendPreference) => void;
  onLoad: () => void;
  health: HealthResponse | null;
}) {
  const state = status?.state || "idle";
  const loading = state === "loading";
  const ready = state === "ready";
  const sizeFp16 = modelInfo?.files.fp16?.bytes || 47497427;
  const sizeInt8 = modelInfo?.files.int8?.bytes || 24010842;

  return (
    <section className={`model-setup ${ready ? "is-ready" : ""}`}>
      <div className="model-setup-main">
        <div className="model-status-icon">
          {ready ? <Icon name="check" size={20} /> : loading ? <span className="spinner" /> : <Icon name="cpu" size={22} />}
        </div>
        <div className="model-setup-copy">
          <div className="model-topline">
            <span className="card-kicker">
              <Icon name="cpu" size={14} /> ON-DEVICE MODEL
            </span>
            {ready ? (
              <span className="success-text">已就绪</span>
            ) : loading ? (
              <span className="loading-text">加载中</span>
            ) : (
              <span className="muted">尚未加载</span>
            )}
          </div>
          <h3>
            BGE-small-zh-v1.5
            <span className="model-tag">512d</span>
            <span className="model-tag">MIT</span>
          </h3>
          <p>
            {ready
              ? `推理后端 ${status?.backend === "webgpu" ? "WebGPU" : "WASM"} · ${
                  status?.precision === "fp16" ? "FP16" : "INT8"
                }，模型加载 ${formatMs(status?.loadMs)}，预热 ${formatMs(status?.warmupMs)}。`
              : "模型文件从本地静态目录加载，不会发起云端推理请求。向量化与查询编码都在当前设备完成。"}
          </p>
          <div className="backend-options">
            <label className={`backend-option ${preference === "auto" ? "selected" : ""}`}>
              <input
                type="radio"
                name="backend-preference"
                checked={preference === "auto"}
                onChange={() => onPreference("auto")}
              />
              <span>
                <strong>自动选择</strong>
                <small>优先 WebGPU，失败自动降级</small>
              </span>
            </label>
            <label className={`backend-option ${preference === "webgpu" ? "selected" : ""}`}>
              <input
                type="radio"
                name="backend-preference"
                checked={preference === "webgpu"}
                onChange={() => onPreference("webgpu")}
              />
              <span>
                <strong>WebGPU · FP16</strong>
                <small>{formatBytes(sizeFp16)} · GPU 加速</small>
              </span>
            </label>
            <label className={`backend-option ${preference === "wasm" ? "selected" : ""}`}>
              <input
                type="radio"
                name="backend-preference"
                checked={preference === "wasm"}
                onChange={() => onPreference("wasm")}
              />
              <span>
                <strong>WASM · INT8</strong>
                <small>{formatBytes(sizeInt8)} · 兼容优先</small>
              </span>
            </label>
          </div>
          {detection && (
            <div className={`detection-line ${detection.available ? "available" : "unavailable"}`}>
              <span className={`status-dot ${detection.available ? "ok" : "warn"}`} />
              {detection.available
                ? `WebGPU 可用${detection.accelerator ? ` · ${detection.accelerator}` : ""}`
                : `WebGPU 不可用 · ${detection.reason || "将使用 WASM"}`}
            </div>
          )}
          {loading && (
            <div className="load-progress">
              <div className="progress-track slim">
                <div
                  className="progress-fill"
                  style={{ width: `${Math.max(status?.progress?.percent || 0, 4)}%` }}
                />
              </div>
              <span>
                {status?.progress?.file || "准备模型文件"}
                {status?.progress ? ` · ${formatBytes(status.progress.loaded)} / ${formatBytes(status.progress.total)}` : ""}
              </span>
            </div>
          )}
          {status?.error && (
            <div className="inline-error">
              <Icon name="alert" size={15} /> {status.error}
            </div>
          )}
        </div>
      </div>
      <div className="model-setup-action">
        {ready ? (
          <>
            <div className="ready-stat">
              <span>模型文件体积</span>
              <strong>{formatBytes(status?.modelBytes)}</strong>
            </div>
            <button className="ghost-btn" onClick={onLoad} disabled={loading}>
              <Icon name="refresh" size={15} /> 重新加载
            </button>
          </>
        ) : (
          <button className="primary-btn large" onClick={onLoad} disabled={loading || !health?.ready}>
            {loading ? <span className="spinner light" /> : <Icon name="bolt" size={17} />}
            {loading ? "加载中…" : "初始化端侧模型"}
          </button>
        )}
      </div>
    </section>
  );
}

function SearchResults({
  result,
  query,
  timing,
}: {
  result: SearchResponse;
  query: string;
  timing: { embedMs: number; e2eMs: number; dbMs: number; warm: boolean } | null;
}) {
  return (
    <div className="results" data-query={result.query}>
      <div className="results-head">
        <div>
          <span className="results-query">“{result.query}”</span>
          <span className="results-count">{result.count} 条结果</span>
          <span className="results-mode">
            {result.mode === "vector-fallback" ? "向量回退" : result.mode === "hybrid" ? "seekdb RRF 混合" : result.mode === "vector" ? "seekdb 向量" : "seekdb 全文"}
          </span>
        </div>
        <div className="timing-row">
          <span title="查询向量化">
            <Icon name="cpu" size={13} /> {formatMs(timing?.embedMs)}
          </span>
          <span title="seekdb 检索">
            <Icon name="database" size={13} /> {formatMs(result.dbMs)}
          </span>
          <span title="端到端">
            <Icon name="clock" size={13} /> {formatMs(timing?.e2eMs)}
          </span>
          <span className={`warm-pill ${timing?.warm ? "warm" : "cold"}`}>
            {timing?.warm ? "热态" : "首次"}
          </span>
        </div>
      </div>

      {result.mode === "vector-fallback" && (
        <div className="mode-warning">
          <Icon name="alert" size={15} /> 查询没有可用的全文关键词，本次由 seekdb 执行语义检索。
        </div>
      )}

      <div className="result-list">
        {result.hits.map((hit) => (
          <article className="result-item" key={hit.id}>
            <div className="result-rank">{String(hit.rank).padStart(2, "0")}</div>
            <div className="result-body">
              <div className="result-title-row">
                <h4>{highlight(hit.title, query)}</h4>
                {hit.score != null && (
                  <span className="score-pill" title={`${hit.scoreLabel} 分数（由 seekdb 返回）`}>
                    {hit.scoreLabel} {hit.score.toFixed(4)}
                  </span>
                )}
              </div>
              <p>{highlight(hit.text, query)}</p>
              <div className="result-meta">
                <span>
                  <Icon name="file" size={12} /> {hit.source || "未命名来源"}
                </span>
                <span>
                  chunk {hit.chunkIndex + 1}/{hit.chunkCount}
                </span>
                <span className="doc-id" title={hit.docId || ""}>
                  {hit.docId?.slice(0, 14) || hit.id.slice(0, 14)}
                </span>
              </div>
            </div>
          </article>
        ))}
        {result.hits.length === 0 && (
          <div className="empty-state">
            <Icon name="search" size={24} />
            <strong>没有找到相关内容</strong>
            <span>换一个问法，或先导入更多语料。</span>
          </div>
        )}
      </div>

      {result.hybridTrace?.generatedSql && (
        <details className="sql-trace">
          <summary>
            <Icon name="terminal" size={15} />
            查看 seekdb 在数据库内生成的混合检索 SQL
            <span className="sql-badge">单条 SQL · RRF</span>
          </summary>
          <div className="sql-trace-body">
            <div className="sql-config">
              <span>API: {result.seekdb.api}</span>
              <span>rank_window_size: {result.seekdb.rankWindowSize}</span>
              <span>rank_constant: {result.seekdb.rankConstant}</span>
              <span>全文条件: {result.ftsQuery || "—"}</span>
            </div>
            <pre>{result.hybridTrace.generatedSql}</pre>
            <p>{result.hybridTrace.note}</p>
          </div>
        </details>
      )}
    </div>
  );
}

function PerformanceCard({
  perf,
  engineStatus,
  onExport,
  onClear,
}: {
  perf: PerformanceRecord;
  engineStatus: EngineStatus | null;
  onExport: () => void;
  onClear: () => void;
}) {
  const warmSearches = perf.searches.filter((item) => item.warm);
  const coldSearches = perf.searches.filter((item) => !item.warm);
  const latestLoad = perf.loads[perf.loads.length - 1];
  const medianE2e = median(warmSearches.map((item) => item.e2eMs));
  const p95E2e = p95(warmSearches.map((item) => item.e2eMs));
  const medianDb = median(warmSearches.map((item) => item.dbMs));
  const medianEmbed = median(warmSearches.map((item) => item.queryEmbedMs));
  const medianCold = median(coldSearches.map((item) => item.e2eMs));
  const latestIngest = perf.ingests[perf.ingests.length - 1];
  const ingestThroughput =
    latestIngest && latestIngest.embedMs > 0
      ? latestIngest.chunks / (latestIngest.embedMs / 1000)
      : null;

  return (
    <section className="card perf-card">
      <div className="card-head compact">
        <div>
          <div className="card-kicker">
            <Icon name="gauge" size={15} /> PERFORMANCE
          </div>
          <h3>本机性能</h3>
        </div>
        <div className="icon-actions">
          <button className="icon-btn" title="导出性能 JSON" onClick={onExport}>
            <Icon name="download" size={16} />
          </button>
          <button className="icon-btn" title="清空记录" onClick={onClear}>
            <Icon name="trash" size={15} />
          </button>
        </div>
      </div>

      <div className="perf-backend">
        <span className={`status-dot ${engineStatus?.state === "ready" ? "ok" : "bad"}`} />
        <span>
          {engineStatus?.state === "ready"
            ? `${engineStatus.backend === "webgpu" ? "WebGPU" : "WASM"} · ${
                engineStatus.precision === "fp16" ? "FP16" : "INT8"
              }`
            : "模型未就绪"}
        </span>
        {engineStatus?.loadMs != null && <span className="perf-load">{formatMs(engineStatus.loadMs)} 加载</span>}
      </div>

      <div className="perf-grid">
        <Metric label="热态端到端" value={formatMs(medianE2e)} sub={p95E2e ? `p95 ${formatMs(p95E2e)}` : "暂无热态查询"} />
        <Metric label="seekdb 检索" value={formatMs(medianDb)} sub="数据库中位数" />
        <Metric label="查询向量化" value={formatMs(medianEmbed)} sub="浏览器本地" />
        <Metric label="首次查询" value={formatMs(medianCold)} sub="冷启动对照" />
      </div>

      {latestLoad && (
        <div className="perf-row">
          <span>模型加载 / 预热</span>
          <strong>
            {formatMs(latestLoad.loadMs)} / {formatMs(latestLoad.warmupMs)}
          </strong>
        </div>
      )}
      {latestIngest && (
        <div className="perf-row">
          <span>最近导入吞吐</span>
          <strong>
            {ingestThroughput ? `${ingestThroughput.toFixed(1)} 块/s` : "—"}
            <small> · {latestIngest.chunks} 块</small>
          </strong>
        </div>
      )}
      <div className="perf-row muted-row">
        <span>样本量</span>
        <span>
          {perf.searches.length} 次检索 · {perf.ingests.length} 次导入
        </span>
      </div>
      <div className="perf-hint">
        首次加载、模型预热与后续请求分开统计；热态指标取中位数。
      </div>
    </section>
  );
}

function Metric({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{sub}</small>
    </div>
  );
}

function DocsCard({
  docs,
  total,
  loading,
  activeKb,
  showAll,
  onToggle,
  onDelete,
  onImport,
}: {
  docs: Doc[];
  total: number;
  loading: boolean;
  activeKb: Kb | null;
  showAll: boolean;
  onToggle: () => void;
  onDelete: (doc: Doc) => void;
  onImport: () => void;
}) {
  return (
    <section className="card docs-card">
      <div className="card-head compact">
        <div>
          <div className="card-kicker">
            <Icon name="file" size={15} /> DOCUMENTS
          </div>
          <h3>已入库文档</h3>
        </div>
        <span className="count-badge">{formatNumber(total)}</span>
      </div>

      {loading ? (
        <div className="docs-loading">
          <span className="spinner" /> 读取集合…
        </div>
      ) : docs.length === 0 ? (
        <div className="empty-state small">
          <Icon name="file" size={20} />
          <strong>当前知识库为空</strong>
          <button className="text-btn" onClick={onImport}>
            导入示例语料
          </button>
        </div>
      ) : (
        <div className="doc-list">
          {docs.map((doc) => (
            <div className="doc-item" key={doc.id}>
              <span className="doc-file-icon">
                <Icon name="file" size={14} />
              </span>
              <div className="doc-item-copy">
                <strong title={doc.title}>{doc.title}</strong>
                <span>
                  {doc.chunkCount} 块 · {formatNumber(doc.charCount)} 字符
                </span>
              </div>
              <button className="icon-btn danger" title="删除文档" onClick={() => onDelete(doc)}>
                <Icon name="trash" size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
      {total > 6 && (
        <button className="show-more" onClick={onToggle}>
          {showAll ? "收起" : `查看全部 ${total} 篇`}
          <Icon name="chevron" size={14} className={showAll ? "rotate" : ""} />
        </button>
      )}
      {activeKb && (
        <div className="collection-line">
          collection <code>{activeKb.collectionName}</code>
        </div>
      )}
    </section>
  );
}

function Modal({
  title,
  onClose,
  children,
  wide = false,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", handler);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className={`modal ${wide ? "wide" : ""}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="关闭">
            <Icon name="close" size={18} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

function TechNoteModal({
  health,
  engineStatus,
  perf,
  onClose,
}: {
  health: HealthResponse | null;
  engineStatus: EngineStatus | null;
  perf: PerformanceRecord;
  onClose: () => void;
}) {
  const warm = perf.searches.filter((item) => item.warm);
  const medianE2e = median(warm.map((item) => item.e2eMs));
  const medianDb = median(warm.map((item) => item.dbMs));
  const lastIngest = perf.ingests[perf.ingests.length - 1];
  const fp32 = health?.model.files.fp32?.bytes || 94851877;
  const fp16 = health?.model.files.fp16?.bytes || 47497427;
  const int8 = health?.model.files.int8?.bytes || 24010842;

  return (
    <Modal title="StepKB 技术说明" onClose={onClose} wide>
      <div className="tech-note">
        <div className="tech-summary">
          <div>
            <span className="tech-label">模型</span>
            <strong>BGE-small-zh-v1.5</strong>
            <small>512d · CLS pooling · MIT</small>
          </div>
          <div>
            <span className="tech-label">端侧后端</span>
            <strong>
              {engineStatus?.state === "ready"
                ? `${engineStatus.backend === "webgpu" ? "WebGPU" : "WASM"} · ${
                    engineStatus.precision === "fp16" ? "FP16" : "INT8"
                  }`
                : "未加载"}
            </strong>
            <small>WebGPU 优先 / WASM 自动降级</small>
          </div>
          <div>
            <span className="tech-label">检索</span>
            <strong>seekdb RRF</strong>
            <small>DBMS_HYBRID_SEARCH</small>
          </div>
          <div>
            <span className="tech-label">热态端到端</span>
            <strong>{formatMs(medianE2e)}</strong>
            <small>中位数 · {warm.length} 次</small>
          </div>
        </div>

        <div className="tech-grid">
          <section>
            <h4>1. 模型与量化</h4>
            <p>
              BGE-small-zh-v1.5 来自智源研究院，本应用使用 Hugging Face
              <code>Xenova/bge-small-zh-v1.5</code> 的 ONNX 转换版本（MIT），固定 revision
              <code>75c43b0</code>。FP32 基线 {formatBytes(fp32)}，FP16 {formatBytes(fp16)}（压缩比{" "}
              {(fp32 / fp16).toFixed(2)}×），INT8 {formatBytes(int8)}（压缩比{" "}
              {(fp32 / int8).toFixed(2)}×）。WebGPU 使用 FP16，WASM 使用动态 INT8；两组都在同一
              20 篇 / 15 查询的标注集上评测 Recall@5 与 nDCG@5。
            </p>
          </section>
          <section>
            <h4>2. 端侧运行与降级</h4>
            <p>
              Transformers.js + ONNX Runtime Web 在浏览器执行 tokenizer 与 feature-extraction。
              启动时用 <code>navigator.gpu.requestAdapter()</code> 探测 WebGPU；可用则显式设置{" "}
              <code>device: "webgpu", dtype: "fp16"</code>。适配器缺失或初始化异常时释放失败会话，
              自动重建 <code>device: "wasm", dtype: "q8"</code> 会话，并显示降级原因；WASM 线程数由
              COOP/COEP 与硬件并发数决定。查询前缀“为这个句子生成表示以用于检索相关文章：”只加在
              query 侧。
            </p>
          </section>
          <section>
            <h4>3. seekdb 数据与混合检索</h4>
            <p>
              每个知识库对应一个 collection：<code>id</code>、<code>document</code>、{" "}
              <code>embedding VECTOR(512)</code>、<code>metadata JSON</code>，同时启用 ik 全文索引与
              HNSW 余弦索引。注册表 <code>stepkb_collections</code> 与 <code>stepkb_docs</code>{" "}
              记录集合、会话与文档状态。检索调用一次 <code>collection.hybridSearch</code>，由 seekdb
              的 <code>DBMS_HYBRID_SEARCH.GET_SQL</code> 生成单条 SQL：MATCH ... AGAINST 与
              cosine_distance 做 FULL JOIN，再以 RRF 公式排序；客户端不合并两路结果。
            </p>
          </section>
          <section>
            <h4>4. 写入、刷新与优化</h4>
            <p>
              文档在浏览器内按约 360 字切块，16 条一批编码，整批写入后用一次{" "}
              <code>refresh_index()</code>（<code>CALL dbms_index_manager.refresh()</code>）刷新索引，
              随后才登记为可检索。示例导入合并 20 次写入为一次刷新；查询编码复用常驻会话。当前实测：
              模型加载 {formatMs(engineStatus?.loadMs)}，热态 seekdb 检索 {formatMs(medianDb)}，
              {lastIngest ? `最近导入 ${lastIngest.chunks} 块、写入+刷新 ${formatMs(lastIngest.writeMs)}。` : "性能面板会随使用实时累计。"}
            </p>
          </section>
        </div>

        <div className="tech-foot">
          <Icon name="shield" size={15} />
          模型文件与推理均在本地；CSP 将 connect-src 限制为 self，未配置任何云端推理 API。
        </div>
      </div>
    </Modal>
  );
}

function highlight(text: string, query: string): ReactNode {
  const terms = Array.from(
    new Set(
      query
        .normalize("NFKC")
        .split(/[\s,，。！？!?;；:：、/\\()[\]{}"'“”‘’]+/u)
        .filter((term) => term.length >= 2)
        .slice(0, 8),
    ),
  ).sort((a, b) => b.length - a.length);
  if (terms.length === 0) return text;
  const escaped = terms.map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const regex = new RegExp(`(${escaped.join("|")})`, "gi");
  const pieces = text.split(regex);
  const termSet = new Set(terms.map((term) => term.toLowerCase()));
  return pieces.map((piece, index) =>
    termSet.has(piece.toLowerCase()) ? <mark key={`${piece}-${index}`}>{piece}</mark> : piece,
  );
}
