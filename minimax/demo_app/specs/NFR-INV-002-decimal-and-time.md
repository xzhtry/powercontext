---
id: NFR-INV-002
title: 金额与时间精度
version: 1
status: active
applies_to: [invoicehub.models.Invoice]
keywords: [金额, 精度, Decimal, 浮点, 时区, 排序]
updated_at: 2026-09-15
---

# NFR-INV-002 金额与时间精度

## NFR-INV-002.1 金额精度

发票金额一律使用 `decimal.Decimal` 表示，读取 JSON 时通过字符串构造。
任何筛选阈值也必须使用十进制比较，禁止出现 `float` 参与金额判断。

## NFR-INV-002.2 时间与排序

`issued_at` 必须带时区信息；排序按绝对时间比较，而不是按字符串字典序。
