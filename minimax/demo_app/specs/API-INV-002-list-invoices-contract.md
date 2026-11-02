---
id: API-INV-002
title: 发票列表查询接口契约
version: 1
status: active
applies_to: [invoicehub.cli.build_parser, invoicehub.cli._run_list, invoicehub.service.list_invoices]
keywords: [接口契约, CLI, list, 参数, min_amount, page, page_size, JSON, 退出码]
updated_at: 2026-10-28
---

# API-INV-002 发票列表查询接口契约

## API-INV-002.1 命令契约

`invoicehub list` 是发票列表的对外入口，参数以 `--` 前缀传递，结果以 JSON 输出到标准输出。
成功退出码为 0；参数或数据非法时退出码为 2，错误信息写入标准错误。

## API-INV-002.2 分页参数

- `--page`：整数，默认 1，必须大于等于 1。
- `--page-size`：整数，默认 20，必须位于 1..100。
- 输出 JSON 必须包含 `page`、`page_size`、`total`、`page_count`、`has_next` 与 `items`。

## API-INV-002.3 金额下限参数

- 新增 `--min-amount`，取值为十进制字符串，例如 `1500.00`。
- 解析必须精确到分，不得使用 `float` 中间值。
- 负数属于非法参数，命令以退出码 2 结束，并在标准错误中包含可读原因。
- 未提供 `--min-amount` 时不得改变既有输出。

## API-INV-002.4 输出兼容性

新增 `--min-amount` 不得改变输出 JSON 的既有字段名、字段类型与排序规则。
