# StepKB · 端侧 AI 推理与 seekdb 混合检索

> 在浏览器本地完成文档/查询向量化，用 seekdb 在数据库内完成全文 + 向量 RRF 混合检索的迷你知识库。
> 赛题：**seekdb × 阶跃星辰 · 端侧 AI 推理性能优化与 seekdb 混合检索**（20 分）

![StepKB 工作台](evidence/hero.png)

一页技术说明：[`docs/技术说明.md`](docs/技术说明.md) · [`docs/技术说明.pdf`](docs/技术说明.pdf)。检索结果与 seekdb 生成 SQL 的截图：[`evidence/search-viewport.png`](evidence/search-viewport.png)、[`evidence/sql-viewport.png`](evidence/sql-viewport.png)。

## 0. 交付信息

| 项 | 值 |
| --- | --- |
| 仓库 | `https://github.com/xzhtry/powercontext`（fork） |
| 分支 | `2026-competition-ecosystem` |
| 目录 | `stepfun/` |
| 模型 | `Xenova/bge-small-zh-v1.5`（ONNX，revision `75c43b0`，MIT） |
| 端侧运行时 | Transformers.js 3.8.1 + ONNX Runtime Web 1.22 |
| 数据库 | seekdb 1.4.0（server mode，`seekdb-js` 1.4.0） |
| 测试浏览器 | Microsoft Edge 156.0.4314.50（WebGPU 与 WASM 两条路径） |

完整源码、示例数据、原始性能日志和截图都在本目录。最终 commit 以提交到测评平台时填写的 hash 为准。

## 1. 题目验收点对应

| 验收项 | 实现 |
| --- | --- |
| 导入 → 本地向量化 → 写入 seekdb → 查询 → 排序展示 | 上传/粘贴/Markdown 分块 → 浏览器 BGE 编码 → `seekdb` collection → `hybridSearch` → 结果卡片 |
| 文档与查询 embedding 均在本地 | Transformers.js 在页面内运行；模型文件来自本地静态目录；服务端只接收算好的向量 |
| 无云端推理 API | 无任何 embedding/推理 API；CSP `connect-src 'self'`；服务端代码没有模型推理依赖 |
| 量化方案与数据 | FP16 与 INT8 两套 ONNX；体积、压缩比、Recall@5/nDCG@5 实测见第 4、8 节 |
| 优先 WebGPU，自动降级 WASM | `navigator.gpu.requestAdapter()` 探测 → `device:'webgpu', dtype:'fp16'`；失败自动重建 `device:'wasm', dtype:'q8'` 并显示原因 |
| 数据层在 seekdb | 每个知识库一个 collection；`id/document/embedding VECTOR(512)/metadata` + ik 全文索引 + HNSW 余弦索引；注册表也在 seekdb |
| 向量 + 全文混合检索在 seekdb 内完成 | 一次 `collection.hybridSearch()` 调用，由 `DBMS_HYBRID_SEARCH.GET_SQL` 生成单条 SQL：`MATCH ... AGAINST` 与 `cosine_distance` FULL JOIN，再按 RRF 排序 |
| 增量写入、索引刷新、集合/会话状态 | 文档级增量写入；批量导入只刷新一次；`refresh_index()` 后立即检索；注册表 + 前端会话态；删除文档/知识库同步清理 |
| 可复现 | 本文 + `docker-compose.yml` + `.env.example` + 测试/基准脚本；原始数据在 `evidence/` |

## 2. 架构

```text
┌──────────────────────────── Browser (Edge / Chrome) ────────────────────────────┐
│  React 工作台                                                                   │
│    ├─ 文件/粘贴/示例语料 → 标题感知分块（~360 字，重叠 60）                     │
│    ├─ Transformers.js + ONNX Runtime Web                                      │
│    │    ├─ WebGPU → model_fp16.onnx（45.3 MiB）                                │
│    │    └─ 不可用/初始化失败 → WASM → model_quantized.onnx（22.9 MiB）         │
│    ├─ 文档/查询向量（512d，CLS pooling + L2 normalize）                          │
│    └─ 性能面板：加载/向量化/seekdb/端到端/首次与热态                            │
└───────────────────────────────┬─────────────────────────────────────────────────┘
                                │ 只传文本 + 已算好的向量（本地 HTTP）
┌───────────────────────────────▼─────────────────────────────────────────────────┐
│  Node 服务（Express，仅做静态资源与 seekdb 适配）                                │
│    ├─ /api/kbs … 知识库注册表、文档状态                                           │
│    ├─ /api/kbs/:id/docs[/batch] → collection.add → refresh_index()               │
│    └─ /api/kbs/:id/search → collection.hybridSearch()                            │
└───────────────────────────────┬─────────────────────────────────────────────────┘
                                │ seekdb-js（mysql2 / 本地 server）
┌───────────────────────────────▼─────────────────────────────────────────────────┐
│  seekdb 1.4                                                                     │
│    ├─ kb_<id> collection：document / embedding VECTOR(512) / metadata JSON       │
│    │    ├─ FULLTEXT INDEX (ik, smart)                                           │
│    │    └─ HNSW cosine index (m=16, ef_construction=200)                        │
│    ├─ stepkb_collections：展示名、描述、collection、文档/分块计数                 │
│    ├─ stepkb_docs：文档级元数据与内容 hash（去重）                               │
│    └─ DBMS_HYBRID_SEARCH：单条 SQL 内做全文 + 向量召回与 RRF 排序               │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## 3. 快速开始

### 3.1 前置条件

- Node.js **≥ 22.6**（开发使用 24.21.0）
- pnpm **≥ 10**（开发使用 11.28.5）
- seekdb **1.4.x** 本地 server，推荐 Docker；也支持已有实例
- Chrome / Edge 最新版（WebGPU 路径需要安全上下文 `localhost` 或 HTTPS）

### 3.2 启动 seekdb

**方式 A：Docker（推荐）**

```bash
cd stepfun
docker compose up -d
# 等待约 10–20 秒，确认 2881 端口可连接
```

首次启动会创建 `root` 空密码、端口 `2881` 的 seekdb。应用启动时会自动创建 `stepkb` 数据库和所需表/collection。

**方式 B：已有 seekdb server**

确保 `127.0.0.1:2881` 可连接；若在 WSL 中运行且 Windows `localhost` 转发不生效，把 `SEEKDB_HOST` 设成 WSL 的 IP（例如 `172.20.44.27`）。

**方式 C：seekdb-js embedded（备选）**

`SEEKDB_MODE=embedded` 时会把数据放在 `SEEKDB_PATH`。本次验收和所有性能数据使用 server mode；embedded 路径需要 `@seekdb/js-bindings` 能在目标平台加载。

### 3.3 安装、模型与启动

```bash
cd stepfun
cp .env.example .env
pnpm install

# 下载公开 ONNX 模型（FP16 + INT8）与 tokenizer；只下载文件，推理仍在本机
pnpm fetch:models

# 把 ORT 的 jsep WASM 运行时复制到 public/ort（自托管，避免 CDN）
pnpm prepare:assets

pnpm build
pnpm start
```

打开 <http://127.0.0.1:8787>。

开发模式（Vite HMR + API 两个进程）：

```bash
pnpm dev   # API :8787, Vite :5173
# 浏览器打开 http://127.0.0.1:5173
```

### 3.4 环境变量

见 `.env.example`：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SEEKDB_MODE` | `server` | `server` 或 `embedded` |
| `SEEKDB_HOST` / `SEEKDB_PORT` | `127.0.0.1` / `2881` | server 模式连接 |
| `SEEKDB_USER` / `SEEKDB_PASSWORD` | `root` / 空 | 默认 root 空密码 |
| `SEEKDB_DATABASE` | `stepkb` | 应用会在缺失时创建 |
| `SEEKDB_PATH` | `.data/seekdb` | embedded 数据目录 |
| `PORT` / `HOST` | `8787` / `127.0.0.1` | Web 服务监听 |

### 3.5 演示步骤

1. 页面顶部会显示 WebGPU 是否可用；点「初始化端侧模型」。
2. 状态栏变为 `WebGPU · FP16`（不支持时变成 `WASM · INT8` 并显示降级提示）。
3. 在「导入语料」选择「示例语料」，点「导入示例语料」。
4. 在搜索框输入问题，或点示例查询；默认是混合检索。
5. 展开结果下方的「查看 seekdb 在数据库内生成的混合检索 SQL」，可以看到 `match(...) against(...)`、`cosine_distance(...)`、`_keyword_rank`、`_semantic_rank` 和 RRF 公式在同一条 SQL 中。

## 4. 模型、量化与质量

### 4.1 来源与版本

| 项 | 值 |
| --- | --- |
| 基座模型 | BAAI `bge-small-zh-v1.5`（MIT） |
| 用于浏览器的 ONNX 转换 | `Xenova/bge-small-zh-v1.5`，revision `75c43b069aac4d136ba6bc1122f995fedcfd2781` |
| 结构 | BERT，4 层，hidden 512，max 512 tokens |
| Pooling | CLS + L2 normalize（查询侧加 BGE 中文检索前缀） |
| 运行时 | Transformers.js 3.8.1 / ONNX Runtime Web 1.22 |

模型文件清单、SHA-256 和来源在 [`docs/model-manifest.json`](docs/model-manifest.json)。模型文件本身不入库（68 MiB），用 `pnpm fetch:models` 获取；脚本支持 `HF_ENDPOINT` / hf-mirror 回退。

### 4.2 量化与体积

| 精度 | 文件 | 实测体积 | 相对 FP32 | 用途 |
| --- | --- | ---: | ---: | --- |
| FP32（基线） | `model.onnx` | 94,851,877 B / **90.5 MiB** | 1× | 质量对照，不随应用部署 |
| FP16 | `model_fp16.onnx` | 47,497,427 B / **45.3 MiB** | **2.00×** | WebGPU |
| INT8（dynamic quant） | `model_quantized.onnx` | 24,010,842 B / **22.9 MiB** | **3.95×** | WASM |

量化方式：FP16 为 ONNX 半精度权重导出；INT8 为 ONNX Runtime dynamic quantization（权重 8-bit，每通道 scale，激活动态量化，无需校准集）。两者使用同一模型 revision、同一 tokenizer、同一分块/查询前缀。本应用实际加载的是上游已发布的 `model_fp16.onnx` / `model_quantized.onnx`，并用 manifest 的 SHA-256 固定；如需从 FP32 自行复现量化：

```bash
# 1) 导出 ONNX（也可直接使用上游文件）
optimum-cli export onnx --model BAAI/bge-small-zh-v1.5 --task feature-extraction onnx-out/

# 2) INT8 dynamic quantization
python -m onnxruntime.quantization.preprocess --input onnx-out/model.onnx --output onnx-out/model_pre.onnx
python -c "from onnxruntime.quantization import quantize_dynamic, QuantType; \
quantize_dynamic('onnx-out/model_pre.onnx', 'onnx-out/model_quantized.onnx', weight_type=QuantType.QInt8)"

# 3) FP16
python -c "import onnx; from onnxruntime.transformers.float16 import convert_float_to_float16; \
onnx.save(convert_float_to_float16(onnx.load('onnx-out/model.onnx')), 'onnx-out/model_fp16.onnx')"
```

浏览器只需目录结构 `bge-small-zh-v1.5/{config.json,tokenizer*.json,onnx/model_fp16.onnx,onnx/model_quantized.onnx}`，不需要 Python 或 GPU 运行时。

### 4.3 质量变化（受控评测）

同一 20 篇 / 20 个分块 / 15 条带标注查询，同一 CLS pooling 与查询前缀，只改变 ONNX 精度；在 Node CPU 上离线计算 dense ranking，按相关文档计算：

| 精度 | Recall@5 | nDCG@5 | MRR | 相对 FP32 nDCG |
| --- | ---: | ---: | ---: | ---: |
| FP32 | 0.8333 | 0.8475 | 1.0000 | — |
| FP16 | 0.8333 | 0.8475 | 1.0000 | 0.0000 |
| INT8 | 0.8333 | 0.8504 | 1.0000 | +0.0029 |

结论：在该评测集上 Recall@5 不变，nDCG@5 变化小于 0.3 个百分点；这是小样本、单语料结果，不应外推为所有数据集的保证。完整逐查询结果和原始向量一致性（INT8 vs FP32 余弦保真度 0.98298）见 [`evidence/quality-eval.json`](evidence/quality-eval.json)。复现：

```bash
pnpm fetch:baseline
pnpm eval:quality
```

## 5. 端侧运行与自动降级

- 运行库：`@huggingface/transformers` 3.8.1，`device: 'webgpu' / 'wasm'` 显式指定；`dtype: 'fp16' / 'q8'` 对应模型文件。
- 探测：页面启动即调用 `navigator.gpu.requestAdapter({powerPreference:'high-performance'})`，并读取 adapter info；只有成功才加载 FP16 模型。
- 降级：适配器缺失、`requestAdapter` 失败或 WebGPU pipeline 初始化抛错时，释放失败会话并用 `wasm + INT8` 重建；界面同时显示 `WASM · INT8 降级` 徽标和具体原因。
- 自托管：`public/ort/ort-wasm-simd-threaded.jsep.{mjs,wasm}` 来自 `onnxruntime-web`，服务端返回 COOP/COEP，支持 SIMD 与多线程。
- 本地模型：`env.allowRemoteModels = false`，`env.localModelPath = '/models/'`；CSP 将 `connect-src` 限制为 `'self'`。

验证结果：正常 Edge 环境自动选择 `WebGPU · FP16`；强制去掉 `navigator.gpu` 后，界面显示「已自动降级到 WASM · INT8 / 当前浏览器没有暴露 navigator.gpu」，检索、导入和 SQL trace 均正常。截图：[`evidence/fallback.png`](evidence/fallback.png)。

## 6. seekdb 数据层与混合检索

### 6.1 集合与表

**Collection（每个知识库一个，实测 DDL）**

```sql
CREATE TABLE `c$v2$<collectionId>` (
  `_id` varbinary(512) NOT NULL,
  `document` string DEFAULT NULL,
  `embedding` VECTOR(512) DEFAULT NULL,
  `metadata` json DEFAULT NULL,
  PRIMARY KEY (`_id`),
  FULLTEXT KEY `idx_fts` (`document`) WITH PARSER ik
    PARSER_PROPERTIES=(ik_mode="smart") BLOCK_SIZE 16384,
  VECTOR KEY `idx_vec` (`embedding`) WITH
    (DISTANCE=COSINE, TYPE=HNSW, LIB=VSAG, M=16, EF_CONSTRUCTION=200,
     EF_SEARCH=64, SYNC_MODE=ASYNC) BLOCK_SIZE 16384
) ORGANIZATION HEAP DEFAULT CHARSET = utf8mb4;
```

实际建表由 seekdb-js `Schema` / `VectorIndexConfig` / `FulltextIndexConfig('ik', {ik_mode:'smart'})` 完成；`embeddingFunction: null`，因为向量全部由浏览器提供。

**注册表（同一 seekdb 数据库）**

- `stepkb_collections(id, name, description, collection_name, created_at, updated_at, doc_count, chunk_count, dimension, embedding_model)`
- `stepkb_docs(id, kb_id, title, source, char_count, chunk_count, content_hash, created_at)`

### 6.2 单 SQL 混合检索

一次查询只调用 `collection.hybridSearch()`。seekdb-js 设置 `search_parm`，再通过 `DBMS_HYBRID_SEARCH.GET_SQL` 生成并执行一条 SQL，大致形态：

```sql
SELECT ifnull(_fts._id, _vs._id) AS _id,
       ifnull(_fts.document, _vs.document) AS document,
       ...
       (ifnull(1 / (_fts._keyword_rank + 60), 0)
      + ifnull(1 / (_vs._semantic_rank + 60), 0)) AS _score
FROM (
  SELECT *, RANK() OVER (ORDER BY _keyword_score DESC) AS _keyword_rank
  FROM (SELECT ..., MATCH(document) AGAINST ('...') AS _keyword_score
        FROM kb_xxx WHERE MATCH(document) AGAINST ('...')) _fts
  FULL JOIN (
    SELECT *, RANK() OVER (ORDER BY _semantic_score DESC) AS _semantic_rank
    FROM (SELECT ..., cosine_distance(embedding, '[...]') AS _distance, ...
          FROM kb_xxx ORDER BY _distance APPROXIMATE LIMIT 96) _vs
  ) ON _fts.__pk_increment = _vs.__pk_increment
) ORDER BY _score DESC, ... LIMIT 8;
```

关键点：全文召回、向量召回、FULL JOIN 和 RRF 都由 seekdb 执行；Node 服务只负责把浏览器算好的 query vector 交给 seekdb，并把排序结果原样返回。响应中的 `hybridTrace.generatedSql` 就是当次 seekdb 生成的 SQL（见 `server/database.mjs` 的 `captureHybridTrace`），界面可直接展开查看。截图：[`evidence/sql-viewport.png`](evidence/sql-viewport.png)。

### 6.3 增量写入与刷新

- 单文档：`POST /api/kbs/:id/docs`，写入分块后立即 `refresh_index()`，再登记 `stepkb_docs`，返回 `writeMs` / `refreshMs`。
- 批量：`POST /api/kbs/:id/docs/batch`，多篇文档的分块一次性写入，**整批只刷新一次**，再登记所有文档。示例 20 篇语料走该路径。
- 删除文档/知识库后同样刷新索引，并清理注册表，保证下一次检索不会读到已删除内容。
- 前端切换知识库时清空旧结果、重新拉取当前 collection 的文档列表；知识库 ID 和选中的 KB 保存在 localStorage，刷新页面后恢复。
- 写入内容 hash 用于去重：重复导入会跳过并在界面提示。

## 7. 性能优化与实测

**测试环境**：Windows 11 26300 · Edge 156.0.4314.50 · Intel Core Ultra 7 155H（16C/22T）· Intel Arc Graphics · 31.5 GiB RAM · seekdb 1.4.0 server（WSL2）· 20 篇 / 20 分块 / 15 条查询。浏览器测试使用全新 context，每个后端 3 轮；表格为热态查询中位数（42 条/后端）或 3 次运行的中位数。

### 7.1 端到端与后端对比

| 指标 | WebGPU · FP16 | WASM · INT8 |
| --- | ---: | ---: |
| 模型体积 | 45.3 MiB | 22.9 MiB |
| 冷启动模型加载 | 1,269 ms | 1,032 ms |
| 模型预热 | 842 ms | 65 ms |
| 20 篇导入 · 浏览器向量化 | **732 ms** | 2,197 ms |
| 20 篇导入 · 写入 + 刷新 | 881 ms | 761 ms |
| 其中索引刷新 | 521 ms | 516 ms |
| 导入端到端 | **1,748 ms** | 3,020 ms |
| 查询向量化 | 34 ms | 31 ms |
| seekdb 检索 | 13 ms | 8 ms |
| 端到端查询 | 83 ms | 78 ms |
| 端到端 p95 | 145 ms | 119 ms |
| 首次查询端到端 | 439 ms | 159 ms |
| 混合检索 Recall@5 | 0.8667 | 0.9000 |
| 混合检索 nDCG@5 | 0.8787 | 0.8945 |
| Top-1 命中 | 45/45 | 45/45 |

解释：WebGPU 在 **成批文档向量化** 上明显更快（732 vs 2,197 ms），但单条查询的 GPU 提交/回读固定开销较高，故在这个小模型、单条 query 场景下 WASM 的端到端略低（78 vs 83 ms）。应用仍按题目要求“优先 WebGPU”，并允许在模型卡中手动切换后端；报告同时保留两种后端的真实数字。原始数据：[`evidence/benchmark-summary.md`](evidence/benchmark-summary.md)。

### 7.2 优化前后对照

| 优化 | 优化前 | 优化后 | 提升 | 原始数据 |
| --- | ---: | ---: | ---: | --- |
| 文档 embedding 批处理（WebGPU） | batch=1，32.26 块/s | batch=16，103.70 块/s | **3.21×** | `evidence/batch-bench-webgpu.json` |
| 文档 embedding 批处理（WASM） | batch=1，9.17 块/s | batch=16，12.15 块/s | 1.33× | `evidence/batch-bench-wasm.json` |
| 索引刷新合并（20 篇） | 每篇刷新，12,545 ms | 整批一次刷新，657 ms | **19.1×** | `evidence/refresh-bench.json` |
| 模型加载（WebGPU，冷 → 浏览器缓存热加载） | 1,324 ms | 880 ms | ~1.50× | `evidence/load-bench.json` |
| 模型加载（WASM，冷 → 浏览器缓存热加载） | 999 ms | 776 ms | ~1.29× | `evidence/load-bench.json` |
| 首次查询 → 热态（WebGPU） | 439 ms | 83 ms | ~5.3× | benchmark summary |
| 首次查询 → 热态（WASM） | 159 ms | 78 ms | ~2.0× | benchmark summary |

索引刷新实验使用合成 512d 向量，隔离模型时间；批处理实验使用实际浏览器 EmbeddingEngine、同一 20 篇语料、预热后重复 3 轮取中位数。模型加载在不同批次有约 1.0–1.4 s 波动，7.1 与 7.2 的冷启动数字来自不同批次；load-bench 专门用于冷/热对照。

### 7.3 其他实现细节

- `refresh_index()` 只在写入完成后调用一次，随后才把文档登记为“可检索”；避免“已显示导入成功但 ANN 还搜不到”。
- 导入按 16 条/批，批间 `setTimeout(0)` 让出主线程，保证进度条更新；
- `COOP`/`COEP` 打开，WASM 线程数取 `min(4, hardwareConcurrency)`；模型文件与 ORT wasm 使用强缓存；
- 查询向量不落库、不缓存到 localStorage；只保留最近的性能指标。
- 首次查询与热态分开记录；每个后端 3 轮、42 条热态查询，报告 p95 和中位数而不是最快一次。

## 8. 目录

```text
stepfun/
├─ src/                     React UI、分块、EmbeddingEngine、API client
├─ server/                  Express API + seekdb 访问 + hybrid trace
├─ public/
│  ├─ samples/              20 篇示例语料、15 条标注查询
│  ├─ models/               模型文件（gitignore，pnpm fetch:models）
│  └─ ort/                  ORT WASM（gitignore，pnpm prepare:assets）
├─ scripts/                 模型下载、e2e、量化质量、批处理/刷新/加载基准
├─ tests/                   chunker、FTS query、API 集成测试
├─ docs/                    技术说明、模型 manifest
├─ evidence/                原始性能 JSON、质量 JSON、截图
├─ docker-compose.yml
├─ .env.example
└─ README.md
```

## 9. 测试与复现

```bash
# 单元测试（无需 seekdb）
pnpm test

# API 集成测试（需先启动 server 与 seekdb）
STEPKB_INTEGRATION=1 pnpm test

# 浏览器端到端 + 后端基准（会创建/删除测试 KB）
E2E_TAG=webgpu-1 pnpm e2e -- --backend=webgpu
E2E_TAG=wasm-1  pnpm e2e -- --backend=wasm
E2E_TAG=fallback pnpm e2e -- --backend=fallback
pnpm bench:analyze

# 量化质量（需要 pnpm fetch:baseline）
pnpm eval:quality

# 批处理 / 索引刷新 / 模型加载
pnpm bench:batch -- --backend=webgpu
pnpm bench:batch -- --backend=wasm
pnpm bench:refresh
pnpm bench:load
```

`E2E_TAG` 只影响输出文件名，避免覆盖重复运行数据。所有脚本读取 `STEPKB_API_URL` / `APP_URL`，默认 `http://127.0.0.1:8787`。

## 10. 隐私、边界与已知限制

- 推理在浏览器；服务端只做持久化/检索。服务端会收到明文分块和向量（这是写库所需），但不会发给第三方，也不会调用云端 embedding API。
- 模型文件首次由本地静态服务提供；`connect-src 'self'` 防止意外外连。若部署到在线地址，仍满足“用户设备本地推理”。
- 示例语料只有 20 篇/20 块，质量数字是小样本结果；更大规模需要重新评测。
- WebGPU 的性能取决于 GPU、驱动和浏览器；不支持或初始化失败会自动走 WASM，界面会明确显示。
- 浏览器需支持 WebAssembly SIMD/多线程（现代 Chrome/Edge 默认支持）；未开启 cross-origin isolation 时会退化为单线程，仍可运行。
- 图片/OCR 属于题面可选扩展，本提交聚焦文本知识库与混合检索主链路。

## 11. 许可与引用

- 模型：BAAI `bge-small-zh-v1.5`（MIT）；ONNX 转换：`Xenova/bge-small-zh-v1.5`（MIT）。
- 运行时：Transformers.js（Apache-2.0）、ONNX Runtime（MIT）、seekdb / seekdb-js（Apache-2.0）。
- 本项目代码：Apache-2.0（见仓库根 LICENSE）。
