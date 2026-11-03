你是一名严格的规格驱动开发（SDD）助手。你只能依据用户提供的上下文修改代码。
要求：
1. 只输出 unified diff，放在 ```diff 代码块中；不要输出解释、总结或其它代码块。
2. 路径相对 demo_app 根目录，使用 a/src/... 与 b/src/...。
3. 只允许修改 src/invoicehub/ 下的文件；禁止修改 tests/、specs/、data/。
4. 必须满足上下文中的全部规格条目，并保持既有行为（回归测试）不变。
5. 使用 Python 3.11+，金额使用 decimal.Decimal。

# 开发任务
发票列表新增金额下限筛选
在 invoicehub 发票查询服务中新增 min_amount（金额下限）筛选：支持与 status、customer_id 组合，遵循含边界语义；保持既有的分页、稳定排序与空结果行为不变；并在 CLI 中新增 --min-amount 参数。

## 验收条件
- list_invoices 接受 min_amount，只保留 total_amount >= min_amount 的发票（含边界）
- min_amount 为 None 时结果与未传一致
- min_amount 为负数时抛出 ValueError
- min_amount 可与 status、customer_id、分页组合使用
- CLI invoicehub list 支持 --min-amount，保持既有 JSON 字段与排序
- 既有回归测试（状态/客户筛选、分页、排序、CLI）全部通过

## 必须遵守的规格（来自 seekdb 检索）
### [REQ-INV-004.2] REQ-INV-004.2 金额下限筛选（v1，来源 specs/REQ-INV-004-invoice-list-filtering.md:18-24）
## REQ-INV-004.2 金额下限筛选

- 查询接口必须接受 `min_amount`（金额下限），类型为十进制金额。
- 判定规则为**含边界**：`invoice.total_amount >= min_amount` 的发票必须保留。
- `min_amount` 为 `None` 时不得过滤，行为与未传该参数完全一致。
- `min_amount` 小于 0 时必须拒绝请求并抛出 `ValueError`，不得静默返回空结果。
- 金额比较必须使用十进制精确值，禁止转换为二进制浮点数后再比较。

### [REQ-INV-004.3] REQ-INV-004.3 组合筛选（v1，来源 specs/REQ-INV-004-invoice-list-filtering.md:26-29）
## REQ-INV-004.3 组合筛选

`min_amount` 必须能与 `status`、`customer_id` 同时使用，各条件之间是逻辑与（AND）。
组合筛选不得改变各条件单独使用时的语义。

### [REQ-INV-004.1] REQ-INV-004.1 范围（v1，来源 specs/REQ-INV-004-invoice-list-filtering.md:13-16）
## REQ-INV-004.1 范围

财务后台需要按状态、客户与金额下限查询发票。查询结果必须可分页，且在相同输入下
顺序稳定，便于对账与导出。

### [REQ-INV-004.5] REQ-INV-004.5 空结果（v1，来源 specs/REQ-INV-004-invoice-list-filtering.md:38-40）
## REQ-INV-004.5 空结果

没有任何发票满足条件时返回空列表，`total` 为 0，不得抛出异常。

### [API-INV-002.4] API-INV-002.4 输出兼容性（v1，来源 specs/API-INV-002-list-invoices-contract.md:31-33）
## API-INV-002.4 输出兼容性

新增 `--min-amount` 不得改变输出 JSON 的既有字段名、字段类型与排序规则。

### [API-INV-002.3] API-INV-002.3 金额下限参数（v1，来源 specs/API-INV-002-list-invoices-contract.md:24-29）
## API-INV-002.3 金额下限参数

- 新增 `--min-amount`，取值为十进制字符串，例如 `1500.00`。
- 解析必须精确到分，不得使用 `float` 中间值。
- 负数属于非法参数，命令以退出码 2 结束，并在标准错误中包含可读原因。
- 未提供 `--min-amount` 时不得改变既有输出。

### [ADR-INV-003.3] ADR-INV-003.3 影响（v1，来源 specs/ADR-INV-003-service-layer-filtering.md:24-26）
## ADR-INV-003.3 影响

新增或修改筛选条件必须同时补充服务层测试；若改动涉及输出字段，还需要补充 CLI 测试。

### [ADR-INV-003.2] ADR-INV-003.2 理由（v1，来源 specs/ADR-INV-003-service-layer-filtering.md:18-22）
## ADR-INV-003.2 理由

- 查询语义可以用纯函数测试覆盖，不需要启动数据库或服务。
- 新增筛选条件时只改一处，CLI 与后续 HTTP 适配层共享同一实现。
- 排序与分页属于同一条结果管道，放在一起可以保证分页切分的是同一份有序结果。

### [ADR-INV-003.1] ADR-INV-003.1 决策（v1，来源 specs/ADR-INV-003-service-layer-filtering.md:13-16）
## ADR-INV-003.1 决策

所有筛选、排序与分页逻辑集中在 `invoicehub.service.list_invoices`。
`invoicehub.repository` 只负责把 JSON 读成不可变的 `Invoice` 元组，不做筛选。

### [REQ-INV-004.4] REQ-INV-004.4 分页与稳定排序（v1，来源 specs/REQ-INV-004-invoice-list-filtering.md:31-36）
## REQ-INV-004.4 分页与稳定排序

- 排序规则：开票时间倒序；开票时间相同时按发票号升序。
- 分页参数 `page` 从 1 开始，`page_size` 取值 1..100。
- 分页只允许切分已排序结果，不得改变条目顺序或重复条目。
- 页码超出范围时返回空列表，但 `total` 仍为筛选后的总数。

## 需要修改的代码
### src/invoicehub/cli.py::build_parser（行 14-26）
```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="invoicehub", description="财务发票查询工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="查询发票列表")
    list_parser.add_argument("--data", default="data/invoices.json", help="发票 JSON 文件")
    list_parser.add_argument("--status", default=None, help="状态筛选：draft/issued/paid/void")
    list_parser.add_argument("--customer", default=None, help="客户号筛选")
    list_parser.add_argument("--page", type=int, default=1, help="页码，从 1 开始")
    list_parser.add_argument(
        "--page-size", type=int, default=DEFAULT_PAGE_SIZE, help=f"每页条数（1..{MAX_PAGE_SIZE}）"
    )
    return parser
```

### src/invoicehub/cli.py::_run_list（行 40-63）
```python
def _run_list(args: argparse.Namespace) -> int:
    invoices = load_invoices(args.data)
    page = list_invoices(
        invoices,
        status=args.status,
        customer_id=args.customer,
        page=args.page,
        page_size=args.page_size,
    )
    print(
        json.dumps(
            {
                "items": [_invoice_to_dict(item) for item in page.items],
                "page": page.page,
                "page_size": page.page_size,
                "total": page.total,
                "page_count": page.page_count,
                "has_next": page.has_next,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0
```

### src/invoicehub/service.py::list_invoices（行 39-74）
```python
def list_invoices(
    invoices: Iterable[Invoice],
    *,
    status: InvoiceStatus | str | None = None,
    customer_id: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> InvoicePage:
    """按状态与客户筛选发票，返回一页结果。

    参数：
        invoices: 待查询的发票集合。
        status: 可选状态筛选，接受枚举或字符串。
        customer_id: 可选客户号筛选。
        page: 页码，从 1 开始。
        page_size: 每页条数，1..100。

    返回：
        ``InvoicePage``，其中条目按 (开票时间倒序, 发票号升序) 稳定排序。
    """

    _validate_pagination(page, page_size)
    normalized_status = _coerce_status(status)

    filtered = [
        invoice
        for invoice in invoices
        if (normalized_status is None or invoice.status is normalized_status)
        and (customer_id is None or invoice.customer_id == customer_id)
    ]

    ordered = sorted(filtered, key=_sort_key)
    total = len(ordered)
    start = (page - 1) * page_size
    items = tuple(ordered[start : start + page_size])
    return InvoicePage(items=items, page=page, page_size=page_size, total=total)
```

## 用于验证的测试（不得修改）
- [target] tests/test_min_amount_filter.py::test_min_amount_keeps_invoices_at_or_above_threshold covers=REQ-INV-004.2,REQ-INV-004.3,API-INV-002.3
- [target] tests/test_min_amount_filter.py::test_min_amount_is_inclusive covers=REQ-INV-004.2,REQ-INV-004.3,API-INV-002.3
- [target] tests/test_min_amount_filter.py::test_min_amount_combines_with_status_filter covers=REQ-INV-004.2,REQ-INV-004.3,API-INV-002.3
- [target] tests/test_min_amount_filter.py::test_min_amount_combines_with_customer_and_pagination covers=REQ-INV-004.2,REQ-INV-004.3,API-INV-002.3
- [target] tests/test_min_amount_filter.py::test_min_amount_none_keeps_existing_behavior covers=REQ-INV-004.2,REQ-INV-004.3,API-INV-002.3
- [target] tests/test_min_amount_filter.py::test_negative_min_amount_is_rejected covers=REQ-INV-004.2,REQ-INV-004.3,API-INV-002.3
- [target] tests/test_min_amount_filter.py::test_cli_accepts_min_amount covers=REQ-INV-004.2,REQ-INV-004.3,API-INV-002.3
- [regression] tests/test_list_invoices.py::test_unknown_status_is_rejected covers=-
- [regression] tests/test_list_invoices.py::test_combines_status_and_customer covers=-
- [regression] tests/test_list_invoices.py::test_filters_by_status covers=-
- [regression] tests/test_cli.py::test_cli_lists_invoices_as_json covers=-
- [regression] tests/test_cli.py::test_cli_filters_by_status covers=-
- [regression] tests/test_cli.py::test_cli_rejects_invalid_page_size covers=-
- [regression] tests/test_pagination.py::test_page_metadata covers=REQ-INV-004.4,API-INV-002.2
- [regression] tests/test_pagination.py::test_pages_partition_the_result_set covers=REQ-INV-004.4,API-INV-002.2
- [regression] tests/test_pagination.py::test_out_of_range_page_is_empty_but_keeps_total covers=REQ-INV-004.4,API-INV-002.2
- [regression] tests/test_pagination.py::test_invalid_page_is_rejected covers=REQ-INV-004.4,API-INV-002.2
- [regression] tests/test_pagination.py::test_invalid_page_size_is_rejected covers=REQ-INV-004.4,API-INV-002.2

## 任务状态（来自 PowerContext）
- 状态：empty（第 0 次运行）
- 已完成：无
- 待办：读取并确认适用的规格条目; 定位需要修改的代码符号; 实现 min_amount 筛选; 补充 CLI --min-amount; 运行目标功能测试; 运行相关回归测试

输出格式（必须严格遵守）：
```diff
--- a/src/invoicehub/service.py
+++ b/src/invoicehub/service.py
@@ ... @@
```

