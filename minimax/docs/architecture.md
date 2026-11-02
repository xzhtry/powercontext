# 一页技术说明：规有所依

## 问题

持续演进的软件项目里，规格、接口契约、设计决策、代码与测试各自变更。AI 助手需要判断
“这次任务该遵守什么、该改哪里、如何验证”，跨会话后还要知道“已经做了什么”。

## 总体结构

```
                 ┌─────────────────────────────┐
  任务 JSON ───▶ │ sddctx.context              │
                 │  1. seekdb 全文检索         │──▶ 规格条目（含版本/行号）
                 │  2. 规格 applies → 代码符号 │──▶ 代码片段（文件/符号/行号）
                 │  3. 测试 covers → 回归集合  │──▶ 目标测试 + 回归测试
                 │  4. PowerContext entries    │──▶ 已完成/待办/验证结果
                 └──────────────┬──────────────┘
                                ▼
                 MiniMax（Anthropic/OpenAI 兼容）
                                ▼
                 补丁应用到 snapshots/before
                                ▼
             pytest 目标测试 + 回归测试 + 全量测试
                                ▼
             PowerContext Memory（kind=task-state）写回
```

## 各部分职责

| 文件 | 职责 |
| --- | --- |
| `src/sddctx/ingest.py` | 解析 Markdown 规格（front matter + H2 条目）、Python AST（函数/测试），生成带路径/行号/哈希的资料条目 |
| `src/sddctx/db.py` | seekdb 建表（`materials` + ngram 全文索引）、导入、全文检索、标签查询、运行记录 |
| `src/sddctx/retrieval.py` | 任务 → 检索 → 选择 → 校验来源 → 上下文 JSON |
| `src/sddctx/state.py` | PowerContext Scope / Memory 读写，`run_seq` 递增 |
| `src/sddctx/minimax_client.py` | MiniMax 请求（协议/模型/超时可配置），不落盘 Key |
| `src/sddctx/runner.py` | 提示词、补丁解析/校验、应用、测试、状态回写、证据落盘 |

## 上下文选择规则

1. **规格**：对“任务标题 + 描述 + 验收条件”做 seekdb ngram 全文检索
   `MATCH(title, body, keywords) AGAINST(...)`，叠加标识符命中加权，取前 10 个 active 条目。
   `status=superseded` 的历史规格（CSV 导出）不会被选中。
2. **代码**：读取所选规格 `applies_to`（如 `invoicehub.service.list_invoices`），
   映射到代码条目的 `symbol_key`，精确取回函数片段；只有不足 3 个时才用全文检索补充同模块符号。
   这样“该改哪里”由规格决定，而不是靠猜。
3. **测试**：测试文件/函数的 `Covers:` 标签与所选规格条目求交集；
   目标测试（`Role: target`）全部保留，回归测试（分页、既有筛选、CLI）一并保留。
4. **来源校验**：每条来源都带 `path` + `lines` + `content_hash`；构造上下文时重新读取文件，
   校验行号范围与哈希。文件不存在或已变化会写入 `warnings`，不会伪造来源。
5. **可重复**：选择结果的稳定摘要写入 `db.context_digest`，同一任务/同一资料库得到同一摘要。

## 规格演进

规格文件带 `version`/`status` 元数据。`import` 全量重建 `materials` 表，检索只读取
`status=active` 的最新导入内容；旧版本不会残留。`samples/spec-update/` 提供 v1/v2 两份
规格，`scripts/demo_spec_update.sh` 证明：更新并重新导入后上下文返回 v2 文本，恢复 v1 后
再次返回 v1——不是固定答案。已失效的 `REQ-INV-001`（CSV 导出）始终不会被选入。

## 任务状态

PowerContext 中保存一条 `kind=task-state` 的 Memory entry，文本前缀 `SDDCTX_STATE_V1`，
内容是紧凑 JSON：

```json
{"task_id": "TASK-101", "run_seq": 2, "status": "verified",
 "completed": ["..."], "pending": [],
 "verifications": [{"name": "target", "exit_code": 0, "passed": 7, "failed": 0,
                    "code_version": "src-sha256:... + patch ..."}]}
```

每次运行 `save_state` 读取当前最大 `run_seq` 后 `+1` 写入；`load_state` 从
`/v1/memory/entries/list` 读取并选最大 `run_seq`。模块重启只是新进程，状态仍在
PowerContext Server 中；`scripts/demo_state_reuse.sh` 还会重启 Server 再读取。

## 验证

- 目标测试：修改前 7 个失败（`TypeError: unexpected keyword argument 'min_amount'` 与
  CLI 不认识 `--min-amount`），修改后 7 个全部通过。
- 回归测试：17 个既有用例（状态/客户筛选、分页、稳定排序、CLI）在修改前后均通过。
- 全量：24 个用例全部通过。
- 测试日志记录命令、退出码、代码内容哈希与补丁哈希，见 `evidence/tests/`。

## 技术分工

- **seekdb**：工程资料与全文索引的唯一来源；上下文中的每条规格/代码/测试都能追溯到
  `materials.material_id` 与 SQL 检索轨迹。
- **PowerContext**：任务状态（进展/验证）在跨进程、跨服务重启后复用。
- **MiniMax**：读取上下文生成补丁；开发记录包含请求摘要、响应、补丁和对应测试结果。

## 限制与取舍

- 嵌入 seekdb 只支持 Linux；WSL 下需把运行目录放到 ext4。
- 检索没有引入 embedding：当前样例规模下 ngram 全文检索 + 规格/测试显式映射足够，
  也避免了额外模型依赖和不确定性。
- 只覆盖单任务、单 Scope；并发运行与多任务隔离留作扩展。
