# 代码修改材料

| 材料 | 位置 | 说明 |
| --- | --- | --- |
| 修改前快照 | `snapshots/before/` | 目标测试已写好，`min_amount` 实现缺失 |
| 修改后代码 | `demo_app/` | 最终提交代码（测试、规格、数据与快照一致） |
| 代码差异 | `changes/min-amount.diff` | `snapshots/before` → `demo_app` 的 unified diff |
| 每次运行的补丁 | `evidence/patches/<run_id>.diff` | MiniMax/参考补丁的原始产物 |
| MiniMax 响应 | `evidence/minimax/<run_id>.json` | 请求元数据、响应全文、Prompt 哈希 |

## 变更内容

1. `src/invoicehub/service.py`
   - 新增 `_coerce_min_amount`：`Decimal` 规范化、非负校验；
   - `list_invoices` 新增 `min_amount` 参数，按 `>=` 过滤，与 `status`、`customer_id` 组合。
2. `src/invoicehub/cli.py`
   - `build_parser` 新增 `--min-amount`；
   - `_run_list` 把参数解析为 `Decimal` 并传入服务层。
3. `tests/test_min_amount_filter.py`
   - 目标测试（`Role: target`），覆盖含边界、组合筛选、None、负数、CLI。

## 说明

- 差异只改 `src/invoicehub/`；`tests/`、`specs/`、`data/` 在修改前后保持一致，避免
  “通过改测试让结果变绿”。
- 修改前 7 个目标用例失败、回归 17 个通过；修改后 24 个全部通过，日志见
  `evidence/tests/`。
- `changes/min-amount.diff` 是离线复验用的参考实现；真实 MiniMax 运行会生成自己的
  `evidence/patches/<run_id>.diff`。若模型补丁被采纳，以该补丁与 `demo_app` 为准，
  并重新执行 `scripts/verify_all.sh`。
