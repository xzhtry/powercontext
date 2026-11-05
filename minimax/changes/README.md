# 代码修改材料

| 材料 | 位置 | 说明 |
| --- | --- | --- |
| 修改前快照 | `snapshots/before/` | 目标测试已写好，`min_amount` 实现缺失 |
| 修改后代码 | `demo_app/` | 最终提交代码（MiniMax 网页版补丁已应用） |
| 最终代码差异 | `changes/final-minimax.diff` | MiniMax 返回并实际应用的 unified diff |
| 参考差异 | `changes/min-amount.diff` | 离线复验用的参考实现（非提交代码来源） |
| 每次运行的补丁 | `evidence/patches/<run_id>.diff` | MiniMax/参考补丁的原始产物 |
| MiniMax 响应 | `evidence/minimax/response.md`、`run-*.json` | 回复原文、Prompt 哈希、测试结果 |

## 变更内容（MiniMax 实际输出）

1. `src/invoicehub/cli.py`
   - 新增 `_parse_amount`：用 `Decimal` 解析 `--min-amount`，拒绝非有限值与负数；
   - `build_parser` 注册 `--min-amount`，`_run_list` 将其传入服务层。
2. `src/invoicehub/service.py`
   - 新增 `_normalize_min_amount` / `_to_decimal`：十进制规范化与非负校验；
   - `list_invoices` 新增 `min_amount` 参数，按 `total_amount >= min_amount` 含边界过滤，
     并与 `status`、`customer_id` 组合；
   - docstring 同步更新。
3. `tests/test_min_amount_filter.py`
   - 修改前已存在的目标测试（`Role: target`），覆盖含边界、组合筛选、None、负数、CLI。

## 说明

- 差异只改 `src/invoicehub/`；`tests/`、`specs/`、`data/` 在修改前后保持一致，避免
  “通过改测试让结果变绿”。
- 修改前 7 个目标用例失败、回归 17 个通过；修改后目标 7、回归 17、全量 24 全部通过，
  日志见 `evidence/tests/`。
- `changes/final-minimax.diff` 是 `evidence/patches/run-634988b89b.diff` 的副本；
  `changes/min-amount.diff` 仅用于无 Key 时的离线复验。
