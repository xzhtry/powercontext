# 验收自查

对照赛题 4.1 的六项必做条件。以下命令均在 `minimax/` 目录执行，环境为
WSL2 Ubuntu 24.04 + Python 3.12.3（仓库在 `/mnt/d`，运行时目录自动落在
`$HOME/.local/share/sddctx`）。

## 0. 一键复验

```bash
bash scripts/verify_all.sh
```

输出以 `ALL PASS：离线复验完成。` 结束（不需要 MiniMax Key，使用已归档补丁复验）。

## 1. 能够运行

| 检查 | 结果 |
| --- | --- |
| 按 README 安装依赖（`pip install -e .`、`powercontext[cli,server]==1.4.1`） | 通过 |
| 初始化数据（`bash scripts/init.sh`） | 通过，导入 53 条资料（15 规格 / 16 代码 / 22 测试），见 `evidence/import/latest.json` |
| 启动上下文模块并执行验证样例（`python -m sddctx.cli context` / `run`） | 通过 |
| 不依赖未交付的本地文件或状态 | 通过；`scripts/reset.sh` 后重新 `init.sh` 可复现 |

## 2. MiniMax 实际参与

**状态：待真实 Key。** 接口、提示词、补丁校验与记录生成均已实现：

```bash
cp .env.example .env    # 填 MINIMAX_API_KEY
bash scripts/run_with_minimax.sh
```

- 请求/响应全文：`evidence/minimax/<run_id>.json` 与 `.prompt.md`
- 开发记录：`docs/minimax-dev-record.md`（由 `python -m sddctx.cli report` 生成）
- 代码差异：`evidence/patches/<run_id>.diff`，与提交的 `demo_app/src` 对应

若暂无 API Key，可用网页版 MiniMax：`prompt` 导出 Prompt → 手工获取回复 →
`run --response` 应用并记录，流程见 README。

## 3. 上下文正确

命令：

```bash
python -m sddctx.cli context --json evidence/context/TASK-101-final.json
```

必须出现（样例规定，见 `samples/TASK-101.md`）：

- 规格：`REQ-INV-004.2`、`REQ-INV-004.3`、`REQ-INV-004.4`、`API-INV-002.3`、`ADR-INV-003.1`
- 代码：`src/invoicehub/service.py::list_invoices`、`src/invoicehub/cli.py::build_parser`、`src/invoicehub/cli.py::_run_list`
- 测试：`tests/test_min_amount_filter.py`（7 个 target）以及 `test_pagination.py`、`test_list_invoices.py`、`test_cli.py`
- 不得出现：`specs/legacy/REQ-INV-001-csv-export.md`（`status=superseded`）
- 每条来源带 `path`、`lines`、`content_hash`，且 `file_exists=true`、`fresh=true`

规格更新：

```bash
bash scripts/demo_spec_update.sh
```

输出三次 `OK`：v1 → v2（文本出现“零值”）→ 恢复 v1；证据在
`evidence/spec-update/`。

## 4. 数据库实际参与

- 工程资料全部存入 seekdb：`$SDDCTX_RUNTIME/seekdb`，表 `materials`，ngram 全文索引。
- 快速核对：`python -m sddctx.cli stats` → 15 条规格 / 16 条代码 / 22 条测试，索引包含 `ft_materials`。
- 每次 `context` 的检索 SQL 记录在 JSON 的 `db.query_trace`，示例：
  `SELECT ... MATCH(title, body, keywords) AGAINST ('...') ...`。
- 导入清单：`evidence/import/latest.json`；检索结果中的 `material_id` 可回查该清单/数据库。

## 5. 状态能够复用

```bash
bash scripts/demo_state_reuse.sh
```

脚本用参考补丁写入状态，重启 PowerContext 与上下文模块进程，再读取并注入新上下文；
输出 `OK：重启后读到 run_seq=...`。证据：`evidence/state/`。

- 写入：`/v1/memory/remember`（`kind=task-state`，文本前缀 `SDDCTX_STATE_V1`）
- 读取：`/v1/memory/entries/list`，按最大 `run_seq` 选最新状态
- 使用：`context.state` 与 MiniMax Prompt 的“任务状态”段落

## 6. 代码修改有效

```bash
bash scripts/verify_before_after.sh
```

| 阶段 | 结果 |
| --- | --- |
| 修改前目标测试 | 7 failed（`TypeError: unexpected keyword argument 'min_amount'`、CLI 不认识 `--min-amount`） |
| 修改前回归测试 | 17 passed |
| 修改后目标测试 | 7 passed |
| 修改后回归测试 | 17 passed |
| 修改后全量 | 24 passed |

日志：`evidence/tests/before-*.log`、`after-*.log`、`run-*.log`；每条记录包含命令、退出码、
`src-sha256` 代码哈希与补丁哈希。

## 材料清单

| 赛题要求 | 位置 |
| --- | --- |
| 完整源码 | `minimax/src/sddctx/`、`minimax/demo_app/` |
| 运行说明 | `minimax/README.md` |
| 验证样例 | `minimax/samples/TASK-101.json`、`TASK-101.md` |
| 修改前后快照 | `minimax/snapshots/before/`、`minimax/demo_app/` |
| 代码差异 | `minimax/changes/min-amount.diff`（参考补丁）、`minimax/evidence/patches/`（每次运行补丁） |
| 测试与日志 | `minimax/demo_app/tests/`、`minimax/evidence/tests/` |
| 技术使用记录 | `minimax/docs/minimax-dev-record.md`、`evidence/context/`、`evidence/state/` |
| 一页技术说明 | `minimax/docs/architecture.md` |
