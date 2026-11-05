# MiniMax 开发记录

- 生成时间：2026-11-05T11:46:04+00:00
- 任务：TASK-101（上下文摘要 `9a65343a40d5a7e867143c9ca12544a69653bec872d7e7a8980b775cd1b854b6`）
- 调用方式：`manual-minimax-web`
- 模型：`MiniMax web (model not specified)`，协议：`manual`，端点：`MiniMax web chat`
- 用量：`null`，时延：None ms
- Prompt：`evidence/minimax/run-634988b89b.prompt.md`（sha256 `cc2d02228e35dea3…`）
- 响应：sha256 `9fae38b105751f71…`，response id `None`
- 补丁：`evidence/patches/run-634988b89b.diff`（+70 / -1 行，sha256 `9fae38b105751f71`）

## 提供的上下文

见 `evidence/context/run-634988b89b.json`。模型只看到检索得到的规格、代码符号、测试清单与 PowerContext 状态：

| 类别 | 条目 |
| --- | --- |
| 规格 | `REQ-INV-004.2` v1<br>`REQ-INV-004.3` v1<br>`REQ-INV-004.1` v1<br>`REQ-INV-004.5` v1<br>`API-INV-002.4` v1<br>`API-INV-002.3` v1<br>`ADR-INV-003.3` v1<br>`ADR-INV-003.2` v1<br>`ADR-INV-003.1` v1<br>`REQ-INV-004.4` v1 |
| 代码 | `src/invoicehub/cli.py::build_parser`<br>`src/invoicehub/cli.py::_run_list`<br>`src/invoicehub/service.py::list_invoices` |
| 测试 | `tests/test_min_amount_filter.py::test_min_amount_keeps_invoices_at_or_above_threshold`<br>`tests/test_min_amount_filter.py::test_min_amount_is_inclusive`<br>`tests/test_min_amount_filter.py::test_min_amount_combines_with_status_filter`<br>`tests/test_min_amount_filter.py::test_min_amount_combines_with_customer_and_pagination`<br>`tests/test_min_amount_filter.py::test_min_amount_none_keeps_existing_behavior`<br>`tests/test_min_amount_filter.py::test_negative_min_amount_is_rejected`<br>`tests/test_min_amount_filter.py::test_cli_accepts_min_amount`<br>`tests/test_list_invoices.py::test_unknown_status_is_rejected`<br>`tests/test_list_invoices.py::test_combines_status_and_customer`<br>`tests/test_list_invoices.py::test_filters_by_status`<br>`tests/test_cli.py::test_cli_lists_invoices_as_json`<br>`tests/test_cli.py::test_cli_filters_by_status`<br>`tests/test_cli.py::test_cli_rejects_invalid_page_size`<br>`tests/test_pagination.py::test_page_metadata`<br>`tests/test_pagination.py::test_pages_partition_the_result_set`<br>`tests/test_pagination.py::test_out_of_range_page_is_empty_but_keeps_total`<br>`tests/test_pagination.py::test_invalid_page_is_rejected`<br>`tests/test_pagination.py::test_invalid_page_size_is_rejected` |

## 代码修改过程

1. `sddctx run` 调用 MiniMax，要求只输出 unified diff，且只修改 `src/invoicehub/`。
2. 补丁先做路径校验，再在 `snapshots/before` 的副本上 dry-run / 应用。
3. 依次运行目标测试、回归测试、全量测试；全部通过才写回 `demo_app/src`。

## 验证结果

| 套件 | 命令 | 退出码 | 通过 | 失败 | 日志 |
| --- | --- | --- | --- | --- | --- |
| target | `/home/xzh/sdd-venv/bin/python -m pytest tests/test_min_amount_filter.py` | 0 | 7 | 0 | `evidence/tests/run-634988b89b-target.log` |
| regression | `/home/xzh/sdd-venv/bin/python -m pytest tests/test_list_invoices.py tests/test_pagination.py tests/test_cli.py` | 0 | 17 | 0 | `evidence/tests/run-634988b89b-regression.log` |
| full | `/home/xzh/sdd-venv/bin/python -m pytest` | 0 | 24 | 0 | `evidence/tests/run-634988b89b-full.log` |

结论：全部通过。

## 状态写入

- PowerContext `run_seq=1`，状态 `verified`，artifact `{'family': 'atomic-memory', 'artifact_id': 'art_dd35016214ae4ed094925147bb44abf2', 'revision': 1}`。
- 读取方式：`python -m sddctx.cli state`；读取后的状态会进入下一次 `context.state`。

## 复现

```bash
bash scripts/make_prompt.sh
# 把 evidence/minimax/PROMPT.md 发给 MiniMax，保存回复为 evidence/minimax/response.md
bash scripts/apply_web_response.sh evidence/minimax/response.md "MiniMax web (model not specified)"
python -m sddctx.cli report
```

> 模型响应全文保存在 `evidence/minimax/`，Prompt 全文保存在同一目录的 `.prompt.md`；本记录不包含 API Key。
