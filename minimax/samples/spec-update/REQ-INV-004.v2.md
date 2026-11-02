---
id: REQ-INV-004
title: 发票列表筛选
version: 2
status: active
applies_to: [invoicehub.service.list_invoices, invoicehub.cli._run_list]
keywords: [发票, 列表, 筛选, 金额下限, min_amount, status, customer_id, 分页, 排序, 回归, 零值, 确定性]
updated_at: 2026-11-02
---

# REQ-INV-004 发票列表筛选

## REQ-INV-004.1 范围

财务后台需要按状态、客户与金额下限查询发票。查询结果必须可分页，且在相同输入下
顺序稳定，便于对账与导出。

## REQ-INV-004.2 金额下限筛选

- 查询接口必须接受 `min_amount`（金额下限），类型为十进制金额。
- 判定规则为**含边界**：`invoice.total_amount >= min_amount` 的发票必须保留。
- `min_amount` 为 `None` 时不得过滤，行为与未传该参数完全一致。
- `min_amount` 为 0 时等价于不过滤非负金额；零值不得被当作“未提供”之外的语义。
- `min_amount` 小于 0 时必须拒绝请求并抛出 `ValueError`，不得静默返回空结果。
- 金额比较必须使用十进制精确值，禁止转换为二进制浮点数后再比较。

## REQ-INV-004.3 组合筛选

`min_amount` 必须能与 `status`、`customer_id` 同时使用，各条件之间是逻辑与（AND）。
组合筛选不得改变各条件单独使用时的语义，条件的书写顺序不得影响结果。

## REQ-INV-004.4 分页与稳定排序

- 排序规则：开票时间倒序；开票时间相同时按发票号升序。
- 分页参数 `page` 从 1 开始，`page_size` 取值 1..100。
- 分页只允许切分已排序结果，不得改变条目顺序或重复条目。
- 页码超出范围时返回空列表，但 `total` 仍为筛选后的总数。
- 筛选、排序、分页必须在同一结果管道内完成；相同输入下多次查询必须返回完全一致的结果。

## REQ-INV-004.5 空结果

没有任何发票满足条件时返回空列表，`total` 为 0，不得抛出异常。
