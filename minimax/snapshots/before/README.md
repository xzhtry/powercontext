# InvoiceHub（业务工程）

一个可运行、带测试的迷你财务发票查询服务，用作 SDD 上下文管理的业务工程。

## 运行

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
pytest
invoicehub list --data data/invoices.json --status paid --page-size 3
```

## 结构

- `src/invoicehub/models.py`：`Invoice` / `InvoicePage` / `InvoiceStatus`
- `src/invoicehub/repository.py`：JSON 读取与校验
- `src/invoicehub/service.py`：筛选、稳定排序、分页
- `src/invoicehub/cli.py`：`invoicehub list` 命令
- `specs/`：需求、接口契约、ADR、NFR（`legacy/` 下有一条已失效需求）
- `tests/`：目标测试 `test_min_amount_filter.py` 与回归测试

CLI 输出 JSON：`items/page/page_size/total/page_count/has_next`；非法参数退出码为 2。
