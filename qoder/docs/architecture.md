# 技术说明：研脉 ResearchThread

## 1. 设计目标

研脉要验证的不是“能不能用大模型写综述”，而是一个更基础的问题：

> 能不能把**检索到的论文**、**人的判断**、**研究进度**放进一个可核对、可恢复的工作流里？

因此设计上刻意做了三个约束：

1. **不依赖外部模型**：核心闭环必须离线可跑；综述由证据表 + 规则模板生成，引用编号可逐条核对。
2. **两个指定技术都必须实际工作**：seekdb 承担检索与证据存储，PowerContext 承担跨会话研究记忆；不能只是“安装了”。
3. **每个结论都能回到证据**：综述中的 `[n]` 必须对应证据表的一条判断，再对应 arXiv 摘要与链接。

## 2. 组件

```
Browser SPA
  │  fetch JSON
  ▼
FastAPI (app/main.py)
  ├─ app/seekdb.py      seekdb 生命周期 + SQL
  ├─ app/memory.py      PowerContext Server + Memory client
  ├─ app/synthesis.py   规则化综述/周报
  └─ app/static/        单页 UI
```

### 2.1 seekdb 层

Windows 下 `pylibseekdb` 的原生 `open()` 会启动本地 runtime 并绑定端口；本机 `2881` 落在 Windows excluded port range（`2859–2958`）内，绑定失败返回 `code=-1`。因此实现采用**服务端模式**：

- 从 `pylibseekdb.libs` 找到随 wheel 分发的 `seekdb.exe`；
- 在运行时目录创建 `etc/log/run/store`；
- 以 `--nodaemon --base-dir ... --data-dir ... --port 18881` 启动；
- 通过 PyMySQL 走 MySQL 协议连接；
- Linux/macOS 使用 `pylibseekdb.open()` 嵌入式模式，SQL 完全一致。

这满足赛道“seekdb 可使用嵌入式、服务端、Docker 等部署方式”的要求，同时避开 Windows 端口/路径兼容问题。

### 2.2 数据模型（seekdb）

| 表 | 作用 |
| --- | --- |
| `papers` | 论文元数据 + 摘要；`FULLTEXT INDEX ft_papers(title, abstract) WITH PARSER ngram` |
| `evidence` | 每条论文一条判断：`support` / `challenge` / `mixed` + 中文 note；`paper_id` 唯一 |
| `syntheses` | 生成的综述/周报 Markdown、引用的 evidence ids |
| `search_log` | 每次检索的 query、filters、结果数、耗时、top ids |
| `activity` | 导入、判断、综述、会话等操作流，用于今日研究台 |

`papers` 只播种一次（`COUNT(*) == 0` 时）；`evidence` 在空表时写入 `data/demo.json` 的 9 条示例判断。

### 2.3 检索策略

SQL 形态：

```sql
SELECT paper_id, title, abstract,
       MATCH(title, abstract) AGAINST ('rag hallucination') AS fts_score
FROM papers
WHERE MATCH(title, abstract) AGAINST ('rag hallucination')
ORDER BY fts_score DESC, pub_year DESC
LIMIT 160;
```

`ngram` 解析器对英文也会产生较多部分匹配，因此结果在 Python 侧再做一次**词法核验**：

- 从 query 提取英文词/缩写，过滤停用词；中文词通过同义词表扩展（如“幻觉”→`hallucination`，“检索增强”→`retrieval augmented generation`）；
- 对每条候选，统计 query term 在 `title + abstract` 中的命中数；
- 2 个词以内要求全部命中；更长的 query 至少命中 `max(2, len(terms)-2)` 个；
- 排序分数 = `fts_score + 0.35 * matched_terms + 0.6 * title_hits`。

这样既保留 seekdb 的全文检索能力，又避免把所有含单个常见词的论文都算作命中。UI 的 SQL 轨迹展示实际 SQL、候选数与核验后数量。

### 2.4 PowerContext 层

PowerContext Server 以 SQLite 为元数据存储，HTTP API 使用：

- `POST /v1/scopes` 创建/取得研究 Scope（本地 `runtime/powercontext-scope.json` 缓存 scope_id）；
- `POST /v1/memory/remember` 写入 Memory；
- `POST /v1/memory/entries/list` 读取 Memory。

每条 Memory 的 `text` 是：

```
RT_V1
{"schema":"researchthread.memory.v1","kind":"...","summary":"...","session_id":"...","created_at":"...","payload":{...}}
```

`kind` 取值：

| kind | 写入时机 | payload |
| --- | --- | --- |
| `research-brief` | 首次启动 / 用户编辑 brief | question, scope, criteria, stage, next_action |
| `evidence-decision` | 新增/编辑/移除证据 | paper_id, arxiv_id, title, stance, note |
| `synthesis` | 生成综述 | synthesis_id, title, evidence_count |
| `session-summary` | 开始新会话 | 本次检索数、新增证据数、最后动作、下一步 |

选择显式写入而不是自动抽取，是因为没有配置生成模型时 PowerContext 的自动抽取不可用；显式写入更可核对，也避免把论文正文复制进记忆。

### 2.5 会话与恢复

- 应用启动时生成一个 `sess-...` ID；
- `GET /api/bootstrap` 读取最新 `research-brief`、`session-summary`，并把最近 8 条记忆返回给今日研究台；
- `POST /api/session/new` 先用当前计数写一条 `session-summary`，再轮换 session ID；seekdb 数据不变；
- 页面刷新/重启后，从 PowerContext 读取同一 Scope 的最新 brief 与会话摘要。

### 2.6 综述生成

`app/synthesis.py` 是纯函数：

- 输入 brief + evidence 列表 + 模板；
- 输出 title、Markdown、counts；
- 引用编号按**支持 → 挑战 → 混合 → 年份倒序**排序，保证 `[1]` 起是支持证据；
- “一句话结论”按支持/挑战数量生成条件句，不做无证据的断言；
- 参考列表逐条带作者、年份、标题、venue、arXiv URL；
- 文末明确标注“规则模板生成，未调用外部大模型”。

## 3. 失败模式

| 失败 | 行为 |
| --- | --- |
| PowerContext 未启动 | 应用仍可启动；今日研究台显示降级；检索/证据写 seekdb 不丢；记忆页提供“重新连接” |
| PowerContext 写入失败 | 证据先写 seekdb，接口标记 `memory_available=false`，UI toast 提示 |
| seekdb 启动失败 | 应用启动报错并输出 launch log 尾部；不会静默使用假数据 |
| 搜索无结果 | 回退 `LIKE` 查询；UI 显示空状态和建议查询 |
| 端口冲突 | 通过 `RT_PORT` / `RT_SEEKDB_PORT` / `RT_PC_PORT` 修改 |
| 运行时路径含中文 | Windows 默认使用 `%USERPROFILE%\ResearchThread`；文档建议 ASCII 路径 |

## 4. 安全与数据边界

- 所有 SQL 值通过 `sql_literal()` 转义；不拼接用户原始 SQL。
- 应用只监听 `127.0.0.1`；PowerContext 访问模式设为 `disabled`，只在本机回环。
- 不保存 API Key；项目不需要外部模型 Key。
- 论文摘要来自公开 arXiv API；UI 外链原文；不保存 PDF。
- 记忆只保存研究决策与摘要，不保存论文全文。
