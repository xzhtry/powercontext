# 规有所依 —— 面向软件持续演进的 SDD 上下文管理系统（MiniMax 赛道）

本作品为 `powercontext` 仓库 `2026-competition-ecosystem` 分支的 `minimax/` 目录提交。

它实现了一个可运行的 **SDD 工程上下文模块**：给定一个开发任务，从 **seekdb**
中检索当前有效的规格条目、相关代码符号与测试，把 **PowerContext** 中保存的任务进展
和验证结果拼成上下文，交给 **MiniMax** 生成代码补丁；补丁在一份“修改前快照”上应用，
运行目标测试与回归测试，最后把新的任务状态写回 PowerContext。

> 一句话验证链路：
> **任务 → seekdb 检索（规格/代码/测试）→ PowerContext 状态 → MiniMax 补丁 → 测试 → 状态回写 → 新进程复用**。

## 1. 目录结构

```
minimax/
├── demo_app/                 # 业务工程（发票查询服务 invoicehub）
│   ├── specs/                # 规格、接口契约、ADR（含一条 superseded 干扰项）
│   ├── src/invoicehub/       # 领域模型 / 仓库 / 服务 / CLI
│   ├── tests/                # 目标测试 test_min_amount_filter.py + 回归测试
│   └── data/invoices.json
├── snapshots/before/         # 修改前代码快照（目标测试已存在，实现缺失）
├── samples/
│   ├── TASK-101.json         # 验证样例：任务描述、验收条件、步骤
│   ├── TASK-101.md           # 验证样例（人读版，列明必须命中的来源）
│   └── spec-update/          # 规格 v1 / v2（演进演示）
├── src/sddctx/               # 上下文模块：导入、检索、上下文、状态、MiniMax、运行器
├── tests/                    # 上下文模块自身测试
├── scripts/                  # 初始化/启动/验证/重置脚本
├── evidence/                 # 运行证据：检索轨迹、补丁、测试日志、状态、MiniMax 记录
├── docs/                     # 一页技术说明、验收报告、MiniMax 开发记录
├── .env.example
└── pyproject.toml
```

## 2. 环境与依赖

| 依赖 | 版本 | 说明 |
| --- | --- | --- |
| 操作系统 | Linux / WSL2 Ubuntu 24.04 | 嵌入式 seekdb 的 Python 绑定只支持 Linux |
| Python | 3.11+（实测 3.12.3） | |
| seekdb | `pylibseekdb==1.4.0.post2`（seekdb v1.4.0.0） | 工程资料存储 + ngram 全文索引 |
| PowerContext | `powercontext[cli,server]==1.4.1` | 任务状态保存与读取 |
| MiniMax | Model `MiniMax-M3.1-Flash`，Anthropic/OpenAI 兼容协议 | 代码修改 |

> **WSL 注意**：如果仓库位于 `/mnt/d/...`（drvfs），嵌入式 seekdb 无法打开数据库。
> `scripts/env.sh` 会自动把 `SDDCTX_RUNTIME` 指到 `$HOME/.local/share/sddctx`。
> 也可以显式设置 `SDDCTX_RUNTIME=/path/on/ext4`。原生 Linux 下默认使用 `minimax/runtime`。

### 安装

```bash
cd minimax
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
pip install "powercontext[cli,server]==1.4.1"
cp .env.example .env        # 填入 MINIMAX_API_KEY，按需修改协议/模型
```

## 3. 快速开始

```bash
# 1) 启动 PowerContext（SQLite 存储任务状态）+ 导入 55 条工程资料到 seekdb
bash scripts/init.sh

# 2) 为验证样例构造上下文（会读取 PowerContext 状态）
python -m sddctx.cli context

# 3) 调用 MiniMax 完成代码修改并验证（写入状态）
python -m sddctx.cli run

# 3b) 或者一条命令：调用 MiniMax → 写回 demo_app → 重新导入 → 生成开发记录 → 复验
bash scripts/run_with_minimax.sh

# 4) 新进程读取状态（PowerContext 状态复用）
python -m sddctx.cli state
```

没有 API Key 时，也可以走 MiniMax 网页版：

```bash
python -m sddctx.cli prompt --out evidence/minimax/PROMPT.md
# 把 PROMPT.md 粘贴到 MiniMax，保存模型回复为 evidence/minimax/response.md
python -m sddctx.cli run --response evidence/minimax/response.md --apply-demo
python -m sddctx.cli report
```

`scripts/init.sh` 的产物：

- seekdb 数据库：`$SDDCTX_RUNTIME/seekdb`
- PowerContext：`$SDDCTX_RUNTIME/powercontext/powercontext.db`
- 导入清单：`evidence/import/latest.json`

## 4. 调用入口与输入输出

**入口**：CLI `python -m sddctx.cli <command>`

| 命令 | 输入 | 输出 |
| --- | --- | --- |
| `init` / `import` | `--demo-app`（默认 `demo_app`） | 导入统计、资料清单 JSON |
| `context` | `--task`（默认 `samples/TASK-101.json`）、`--json` | 规格/代码/测试来源、PowerContext 状态、seekdb 查询轨迹 |
| `state` | — | 当前任务的已完成/待办/验证结果 |
| `run` | `--task`、`--patch`（可选，离线）、`--response`（网页版响应）、`--apply-demo` | MiniMax 补丁、测试结果、状态写入、证据文件 |
| `prompt` | `--task`、`--out` | 可粘贴到 MiniMax 的完整 Prompt 与对应上下文 |
| `report` | — | `docs/minimax-dev-record.md` |
| `stats` | — | seekdb 资料数量、索引与最近检索次数 |

`context` 的 JSON 关键字段：

```json
{
  "specs": [{"section_id": "REQ-INV-004.2", "version": 1, "path": "specs/...md", "lines": [18, 24], "text": "..."}],
  "code":  [{"path": "src/invoicehub/service.py", "symbol": "list_invoices", "lines": [39, 74], "snippet": "..."}],
  "tests": [{"path": "tests/test_min_amount_filter.py", "symbol": "...", "role": "target", "covers": ["REQ-INV-004.2"]}],
  "state": {"run_seq": 2, "status": "verified", "completed": [], "pending": [], "verifications": []},
  "db":    {"engine": "seekdb (OceanBase embedded)", "query": "...", "query_trace": [], "context_digest": "..."},
  "sources": [{"kind": "spec", "path": "...", "lines": [18, 24], "file_exists": true, "fresh": true}]
}
```

## 5. 验证

```bash
# 业务工程测试（修改后全部通过）
cd demo_app && pytest && cd ..

# 上下文模块测试（导入、检索、规格更新、来源校验）
pytest tests

# 目标测试“修改前失败、修改后通过”；回归测试始终通过
bash scripts/verify_before_after.sh

# 规格更新并重新导入后，上下文使用新内容
bash scripts/demo_spec_update.sh

# 任务状态跨进程/跨服务重启复用
bash scripts/demo_state_reuse.sh
```

## 6. 技术分工

| 技术 | 在本作品中的作用 | 证据 |
| --- | --- | --- |
| MiniMax | 读取上下文并生成代码补丁（`src/invoicehub/service.py`、`cli.py`） | `evidence/minimax/`、`docs/minimax-dev-record.md` |
| seekdb | 存储 55 条工程资料（规格/代码/测试），建立 ngram 全文索引；`context` 的每次选择都由 SQL 检索驱动 | `evidence/context/*.json` 的 `db.query_trace`、`evidence/import/latest.json` |
| PowerContext | 以 Memory entry（`kind=task-state`）保存任务进展/验证结果；下一次运行（含重启后）通过 `entries/list` 读取并注入上下文 | `evidence/state/*.json`、`scripts/demo_state_reuse.sh` |

## 7. 已知限制

- `run` 需要 `MINIMAX_API_KEY`；没有 Key 时可用 `--patch` 复验已提交的补丁。
- 检索使用 seekdb 全文索引（ngram）+ 规格/测试之间的显式映射，未启用向量检索。
- PowerContext 任务状态使用 SQLite 存储；seekdb 专门承担工程资料与检索。
- 单个 Scope / 单个验证任务；跨任务并发未做压力测试。
- 嵌入式 seekdb 不支持 WSL 的 `/mnt/*` 路径（drvfs），需使用 Linux 文件系统路径。

## 8. 重置

```bash
bash scripts/reset.sh           # 清空运行态（seekdb、PowerContext、状态、工作目录）
bash scripts/reset.sh --full    # 同时清空 evidence 下的运行日志
```

重置后重新执行 `bash scripts/init.sh` 即可从空状态复现。
