"""发票查询服务：筛选、稳定排序与分页。

设计决策见 ADR-INV-003：所有筛选在服务层完成，仓库只负责读取，
这样测试无需数据库即可覆盖全部查询语义。
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from invoicehub.models import Invoice, InvoicePage, InvoiceStatus

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def _coerce_status(status: InvoiceStatus | str | None) -> InvoiceStatus | None:
    if status is None:
        return None
    if isinstance(status, InvoiceStatus):
        return status
    return InvoiceStatus(str(status))


def _validate_pagination(page: int, page_size: int) -> None:
    if page < 1:
        raise ValueError("page 必须大于等于 1")
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise ValueError(f"page_size 必须在 1 到 {MAX_PAGE_SIZE} 之间")


def _coerce_min_amount(value: Decimal | str | int | None) -> Decimal | None:
    """把金额下限规范为 ``Decimal``，并校验非负（REQ-INV-004.2）。"""

    if value is None:
        return None
    amount = value if isinstance(value, Decimal) else Decimal(str(value))
    if not amount.is_finite():
        raise ValueError("min_amount 必须是有限金额")
    if amount < 0:
        raise ValueError("min_amount 必须大于等于 0")
    return amount


def _sort_key(invoice: Invoice) -> tuple[float, str]:
    """稳定排序：开票时间倒序，同一时间按发票号升序。"""

    return (-invoice.issued_at.timestamp(), invoice.invoice_id)


def list_invoices(
    invoices: Iterable[Invoice],
    *,
    status: InvoiceStatus | str | None = None,
    customer_id: str | None = None,
    min_amount: Decimal | str | int | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> InvoicePage:
    """按状态、客户与金额下限筛选发票，返回一页结果。

    参数：
        invoices: 待查询的发票集合。
        status: 可选状态筛选，接受枚举或字符串。
        customer_id: 可选客户号筛选。
        min_amount: 可选金额下限，含边界；负数非法。
        page: 页码，从 1 开始。
        page_size: 每页条数，1..100。

    返回：
        ``InvoicePage``，其中条目按 (开票时间倒序, 发票号升序) 稳定排序。
    """

    _validate_pagination(page, page_size)
    normalized_status = _coerce_status(status)
    normalized_min_amount = _coerce_min_amount(min_amount)

    filtered = [
        invoice
        for invoice in invoices
        if (normalized_status is None or invoice.status is normalized_status)
        and (customer_id is None or invoice.customer_id == customer_id)
        and (normalized_min_amount is None or invoice.total_amount >= normalized_min_amount)
    ]

    ordered = sorted(filtered, key=_sort_key)
    total = len(ordered)
    start = (page - 1) * page_size
    items = tuple(ordered[start : start + page_size])
    return InvoicePage(items=items, page=page, page_size=page_size, total=total)
