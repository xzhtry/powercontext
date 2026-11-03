# 提交说明 · 记仇客栈

## 0. 提测信息（由提交者填写）

| 字段 | 值 |
| --- | --- |
| 仓库 | `https://github.com/xzhtry/powercontext`（私有/公开以实际提交为准） |
| 分支 | `2026-competition-ecosystem` |
| Commit | 以提交时 `git rev-parse HEAD` 的输出为准（本目录当前在 `2026-competition-ecosystem` 分支） |
| 作品目录 | `dify/` |
| Dify 版本 | 0.15.3 |
| DSL | `dify/dsl/grudge-inn.chatflow.yml`（Docker 用 `.docker.yml`） |

> 本目录的所有资产均基于 `2026-competition-ecosystem` 分支开发；导入 Dify 的 DSL 不包含真实 API Key、密码或其他凭据。

---

## 1. 提交产物对照

| 题目要求 | 本作品对应材料 |
| --- | --- |
| **4.1 Dify DSL** | `dsl/grudge-inn.chatflow.yml`（本机/同网络）；`dsl/grudge-inn.chatflow.docker.yml`（Dify 在 Docker） |
| DSL 用途与导入顺序 | 见第 2 节；两个文件二选一，仅 HTTP 节点 host 不同 |
| 适用 Dify 版本/部署方式 | 0.15.3，源码或 Docker 自托管；见 `docs/dify-setup.md` |
| 重新绑定知识库/工具/地址 | 本作品不使用知识库；只需改两个 HTTP 节点 URL 与模型 endpoint，见 `docs/dify-setup.md` 4.3 |
| **4.2 运行说明** | `README.md`、`docs/dify-setup.md` |
| 创意、玩法、体验方式 | `README.md` 第 1 节 |
| Dify 与指定技术分工 | `README.md` 第 2 节、`docs/architecture.md` |
| 运行环境、版本、模型 | `README.md` 第 4 节、`docs/dify-setup.md` 第 2–3 节 |
| 安装/导入/初始化/启动 | `scripts/setup.sh`、`scripts/init.sh`、`docs/dify-setup.md` |
| 外部服务与网络条件 | 默认零外部 Key；Dify 与后端需互通；Docker 用 `host.docker.internal` |
| 已知限制 | `README.md` 第 9 节 |
| **4.3 验证样例与证据** | `docs/validation.md`、`evidence/dify-run.md`、`evidence/dify-run.json`、`evidence/live-verification.json`、`evidence/dify-nodes.txt` |
| 初始数据/记忆状态 | `scripts/verify_live.py` 会先 reset；卡池由 `app/data/cards.json` 自动导入 |
| 实际运行结果 | Dify API 的实际回答、跨会话对照、节点执行状态 |
| seekdb/PowerContext 作用 | `evidence/live-verification.json` 的 `seekdb_cards` / `powercontext_state`；`docs/validation.md` 第 3 节 |
| 连续操作与恢复 | `docs/validation.md` 第 5 节；`scripts/reset.sh` |
| **4.4 按依赖补充** | 见第 3 节 |

---

## 2. 导入与运行顺序

1. **启动后端**（Linux/WSL2）：

   ```bash
   cd dify
   bash scripts/setup.sh
   bash scripts/init.sh
   curl -s http://127.0.0.1:8787/health
   ```

2. **启动 Dify 0.15.3**（源码或 Docker），详见 `docs/dify-setup.md`。

3. **配置模型**：
   - 默认：OpenAI-API-compatible，模型 `grudge-narrator`，endpoint `http://127.0.0.1:8787/v1`（Docker 用 `host.docker.internal`）；
   - 可选：Ollama `qwen2.5:3b` 或任意 OpenAI-compatible 模型。

4. **导入 DSL**：
   - 本机/同网络：`dsl/grudge-inn.chatflow.yml`
   - Dify 在 Docker：`dsl/grudge-inn.chatflow.docker.yml`
   - 导入后检查 5 个节点，点击“发布”。

5. **体验**：
   - Dify 应用页填写玩家名号，开始输入行动；
   - 或使用 Service API（`docs/dify-setup.md` 第 5.2 节）。

6. **跑验收**（可选）：

   ```bash
   python scripts/verify_live.py
   python scripts/dify_scenario.py
   bash scripts/collect_dify_nodes.sh
   ```

---

## 3. 依赖补充材料

| 涉及内容 | 材料 |
| --- | --- |
| seekdb（作为应用数据/检索，不作为 Dify 元数据库） | `pylibseekdb==1.4.0.post2`；`app/store.py`；`app/data/cards.json`；启动时自动建表/建 ngram 全文索引/导入 46 张卡；`/v1/stats` 可核对 |
| PowerContext | `powercontext[cli,server]==1.4.1`；`scripts/start_powercontext.sh` 启动专用 SQLite 服务（8766）；`app/memory.py`；每个玩家一个 Scope；`inn-state` / `inn-episode` |
| 预置数据 | `app/data/cards.json`（46 张原创卡）；无需手工导入，`Store` 首次启动自动写入 |
| 预置记忆 | 无；每个玩家从 `DEFAULT_STATE` 开始；`scripts/reset.sh` 可重置 |
| 现成插件 | 无；只使用 Dify 内置 HTTP Request / LLM / Answer 节点 |
| 自定义插件 | 无 |
| 自定义后端 | `app/` 全部源码；`requirements.txt`；启动说明见 README |
| 自定义前端 | 可选：`web/` + `app/play.py`，仅作为 Dify Service API 的代理入口；不绕过 Dify。主入口仍是 Dify 应用界面/API |
| 数据来源 | 46 张卡文案为本作品原创；未复用公开工作流数据 |
| 许可 | 代码 MIT；Dify/PowerContext/seekdb 遵循各自仓库许可 |

---

## 4. 关键版本与验证环境

- OS：WSL2 Ubuntu 24.04.5
- Python：3.12.3
- seekdb：`5.7.25-OceanBase seekdb-v1.4.0.0`（`pylibseekdb 1.4.0.post2`）
- PowerContext：1.4.1
- Dify：0.15.3（DSL 0.1.5）
- Dify 元数据库：PostgreSQL 16.15；Redis 7
- 模型：默认 `grudge-narrator`（本作品后端提供的 OpenAI-compatible 叙事端点，零 Key）

---

## 5. 复核提示

- **seekdb 是实际使用的**：每回合 `prepare` 的“可用素材”来自 `inn_cards` 的 `MATCH ... AGAINST` 全文检索；`inn_plans`/`inn_ledger` 记录判定与流水。`/v1/stats` 返回版本、46 张卡、plans/ledger 行数。
- **PowerContext 是实际使用的**：每回合写 `inn-state` + `inn-episode`；新会话用同一个 `player_id` 能回扣旧事，新 `player_id` 不会。`/v1/state` 返回 `scope_id`、`episodes`、`entries`。
- **Dify 是实际编排的**：5 个节点在 `workflow_node_executions` 中均为 `succeeded`；LLM 节点输出、commit 节点输出与最终 Answer 一致。
- **默认模型是本地叙事端点**：如果评审希望体验更自然的文风，按 `docs/dify-setup.md` 3.2 换成 Ollama/Qwen 或真实模型即可，不需要改业务代码。
