# 验证报告

## 1. 环境

| 项目 | 值 |
| --- | --- |
| 日期 | 2026-11-05 |
| 系统 | Windows 11（AMD64） |
| Python | 3.12.14（项目 `.venv`） |
| seekdb | 1.4.0.0（Windows 服务端模式，端口 18882 用于本次复跑） |
| PowerContext | 1.4.1（SQLite，loopback 18766 用于本次复跑） |
| Web | FastAPI 0.162 + Uvicorn 0.54 |
| 运行时目录 | `C:\ob\pc-eco\qoder\runtime-clean`（ASCII 路径） |

> 日常运行用 `scripts\run.ps1`，默认端口 8787 / 18881 / 18765。本次验收用独立端口与独立运行时目录，避免与开发中的实例混淆。

## 2. 单元测试

```powershell
cd qoder
.\.venv\Scripts\python.exe -m pytest tests/test_units.py -q
```

结果：

```
.........                                                                [100%]
9 passed
```

覆盖：

- query term 提取、停用词、缩写、中文同义词扩展；
- SQL 字面量转义、摘要片段与 HTML 高亮转义；
- 综述模板的章节、引用编号、参考列表、支持→挑战排序；
- 508 篇数据集与 9 条示例证据的形状；
- FastAPI 路由注册与静态壳存在。

## 3. 冷启动（自动拉起 seekdb 与 PowerContext）

```powershell
$env:RT_RUNTIME="C:\ob\pc-eco\qoder\runtime-clean"
$env:RT_SEEKDB_PORT="18882"
$env:RT_PC_PORT="18766"
$env:RT_PORT="18889"
$env:RT_AUTOSTART="1"
.\.venv\Scripts\python.exe -m app
```

首次启动会自动：

1. 创建 seekdb 数据目录并启动 `seekdb.exe`（约 20 秒内可连接）；
2. 创建 PowerContext SQLite 并启动 Server；
3. 建表、建立 `FULLTEXT INDEX ... WITH PARSER ngram`；
4. 播种 **508 篇** arXiv 摘要；
5. 写入 **9 条**示例证据 + 研究 brief + 初始会话摘要 = **11 条** PowerContext Memory。

健康检查结果：

```json
{
  "seekdb": true,
  "powercontext": true,
  "papers": 508,
  "memory_available": true,
  "memory_error": ""
}
```

## 4. 端到端验收

```powershell
.\.venv\Scripts\python.exe scripts\verify.py --base-url http://127.0.0.1:18889
```

结果（清理后的可读版）：

```
[PASS] seekdb 可用且已播种 — papers=508
[PASS] PowerContext 可用
[PASS] 全文检索命中 — total=35
[PASS] 检索结果由 seekdb 驱动 — seekdb FULLTEXT ngram + lexical verification
[PASS] 相关度排序把 RAGTruth 放在前列
[PASS] 结果带可核对摘要与链接
[PASS] 找到用于验证的论文 — The Power of Noise: Redefining Retrieval for RAG Systems
[PASS] 证据写入 seekdb
[PASS] 证据表包含新增判断 — before=9 after=10
[PASS] 综述包含「## 3. 支持证据」
[PASS] 综述包含「## 4. 挑战与限定」
[PASS] 综述包含「## 参考」
[PASS] 综述包含「生成说明」
[PASS] 综述已写入 seekdb — 1
[PASS] 综述写入 PowerContext — art_0b4ad10d7afc459fa75080385a3d01d1
[PASS] PowerContext 可读取
[PASS] 记忆包含证据判断 — {'synthesis': 1, 'evidence-decision': 10, 'session-summary': 1, 'research-brief': 1}
[PASS] 记忆包含综述草稿
[PASS] 新会话生成交接摘要
[PASS] 交接摘要写入记忆 — art_c3b9e1d620b14d629fcf99f1300a263f
[PASS] 记忆数量增加 — 13 -> 14
[PASS] 存在会话交接记录 — count=2

验收通过。
```

实测检索耗时：**80 ms**（`RAG hallucination`，35 条命中；另一轮为 59 ms，随机器负载变化）。

## 5. 跨进程 / 跨重启恢复

1. 停掉 Web 进程与由它拉起的 seekdb / PowerContext；
2. 用相同 `RT_RUNTIME` 与端口重新启动；
3. 读取 `/api/memory` 与 `/api/bootstrap`。

结果：

```
memory_available True
total 14
kinds {'synthesis': 1, 'evidence-decision': 10, 'session-summary': 2, 'research-brief': 1}
brief 检索增强生成（RAG）真的能让大模型更可靠吗？
last_session True
```

说明：

- seekdb 数据目录与 PowerContext SQLite 都持久化；
- 重启后 brief 与上次会话摘要可以恢复；
- 不会重复播种（`papers=508`，证据 10 条，未重新写 9 条示例）。

> 注意：如果强制终止后立即重启，旧进程可能仍占用端口，导致新进程绑定失败。先确认 `18882` / `18766` 已释放，再启动。

## 6. 页面验收

真实截图见 [`../site/assets/`](../site/assets/)：

| 页面 | 验证点 |
| --- | --- |
| `today.webp` | 研究 brief、508 篇、9 条证据、12 条记忆、证据天平、上次会话 |
| `library.webp` | `RAG hallucination` 35 条命中、RAGTruth 首条、SQL 轨迹入口 |
| `evidence.webp` | 9 条证据、支持/挑战/混合分布、年份覆盖 |
| `synthesis.webp` | 规则生成、引用编号 `[n]`、参考列表 |
| `memory.webp` | active memory 时间线（验证后 14 条）、artifact id、类型筛选 |

## 7. 未覆盖 / 已知限制

- 没有做多用户并发压测；当前是单用户本地应用。
- 没有接入外部 LLM；综述语言由规则模板生成，追求可复现与可核对。
- 示例库是 arXiv 摘要，不是全文；检索召回受摘要长度限制。
- Windows 原生 seekdb 需要避开 excluded port range，并建议运行时路径为 ASCII。
- 真实用户使用数据尚未收集；网站没有把它写成已发生的事实。
