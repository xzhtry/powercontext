# 验证样例 TASK-101：发票列表新增金额下限筛选

## 1. 要改什么

在 `demo_app`（invoicehub 发票查询服务）中新增 `min_amount` 金额下限筛选：

- 服务层 `list_invoices` 接受 `min_amount`，保留 `total_amount >= min_amount` 的发票（**含边界**）；
- `min_amount is None` 时行为不变，负数抛 `ValueError`；
- 可与 `status`、`customer_id`、分页组合；
- CLI `invoicehub list` 新增 `--min-amount`，输出 JSON 字段和排序保持不变。

## 2. 哪些原有行为必须保持

- 状态筛选、客户筛选、二者组合的既有语义；
- 排序：开票时间倒序，同一时间按发票号升序；
- 分页：`page` 从 1 开始，`page_size` 1..100，越界页返回空列表但 `total` 不变；
- CLI 输出字段：`items/page/page_size/total/page_count/has_next`；
- 非法参数退出码为 2。

## 3. 初始数据

- `snapshots/before/`：修改前代码（目标测试已存在、实现缺失）。
- `demo_app/data/invoices.json`：7 张发票，金额覆盖 0.00 / 800.00 / 1200.00 / 1500.00 / 2000.50，
  其中 1200.00 用于边界，1200.00 有三张用于稳定排序与分页。
- 规格：`demo_app/specs/`（v1），其中 `REQ-INV-001` 为 `superseded` 干扰项。

## 4. 操作步骤

```bash
cd minimax
bash scripts/init.sh                       # 启动 PowerContext + 导入 seekdb
python -m sddctx.cli context --json evidence/context/TASK-101.json
python -m sddctx.cli run                   # 需要 .env 中的 MiniMax Key
```

没有 Key 时可用已提交补丁离线复验：

```bash
python -m sddctx.cli run --patch changes/min-amount.diff
```

## 5. 上下文中必须包含的来源

规格（`section_id`）：

- `REQ-INV-004.2` 金额下限筛选（含边界、None、负数、Decimal）
- `REQ-INV-004.3` 组合筛选
- `REQ-INV-004.4` 分页与稳定排序
- `API-INV-002.3` 金额下限参数
- `ADR-INV-003.1` 筛选逻辑放在服务层

代码（`path::symbol`）：

- `src/invoicehub/service.py::list_invoices`
- `src/invoicehub/cli.py::build_parser`
- `src/invoicehub/cli.py::_run_list`

测试：

- 目标：`tests/test_min_amount_filter.py`（7 个用例，`Role: target`，Covers 覆盖上述规格）
- 回归：`tests/test_pagination.py`、`tests/test_list_invoices.py`、`tests/test_cli.py`

不得出现：`specs/legacy/REQ-INV-001-csv-export.md`（`status=superseded`）。

## 6. 预期结果

| 阶段 | 预期 |
| --- | --- |
| 修改前 | `pytest tests/test_min_amount_filter.py`：7 failed（缺少 `min_amount` 参数 / CLI 不认识 `--min-amount`） |
| 修改前回归 | `test_list_invoices.py`、`test_pagination.py`、`test_cli.py`：17 passed |
| 修改后 | 目标测试 7 passed；回归 17 passed；全量 24 passed |
| 规格更新 | 把 `REQ-INV-004` 换成 v2 并重新导入后，`context.specs` 中 `REQ-INV-004.2.version == 2` 且文本包含“零值” |
| 状态复用 | 新进程 `state` 读到同一 `run_seq`、`completed`、`verifications`，并出现在 `context.state` |

实际命令与退出码见 `evidence/tests/`，验收核对见 `docs/acceptance.md`。

## 7. 重置

```bash
bash scripts/reset.sh
bash scripts/init.sh
```
