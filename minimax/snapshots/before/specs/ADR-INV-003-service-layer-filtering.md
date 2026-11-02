---
id: ADR-INV-003
title: 筛选逻辑放在服务层
version: 1
status: active
applies_to: [invoicehub.service.list_invoices, invoicehub.repository]
keywords: [设计决策, 服务层, 筛选, 测试, 分层, 回归]
updated_at: 2026-10-20
---

# ADR-INV-003 筛选逻辑放在服务层

## ADR-INV-003.1 决策

所有筛选、排序与分页逻辑集中在 `invoicehub.service.list_invoices`。
`invoicehub.repository` 只负责把 JSON 读成不可变的 `Invoice` 元组，不做筛选。

## ADR-INV-003.2 理由

- 查询语义可以用纯函数测试覆盖，不需要启动数据库或服务。
- 新增筛选条件时只改一处，CLI 与后续 HTTP 适配层共享同一实现。
- 排序与分页属于同一条结果管道，放在一起可以保证分页切分的是同一份有序结果。

## ADR-INV-003.3 影响

新增或修改筛选条件必须同时补充服务层测试；若改动涉及输出字段，还需要补充 CLI 测试。
