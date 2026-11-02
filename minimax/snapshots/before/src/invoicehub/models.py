"""发票领域模型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class InvoiceStatus(str, Enum):
    """发票状态。值为字符串，便于 JSON 与 CLI 直接传递。"""

    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    VOID = "void"


@dataclass(frozen=True)
class Invoice:
    """一张发票。

    金额使用 ``Decimal``，避免浮点误差（规格 NFR-INV-002）。
    ``issued_at`` 必须带时区，排序依赖它的绝对时间。
    """

    invoice_id: str
    customer_id: str
    status: InvoiceStatus
    total_amount: Decimal
    issued_at: datetime
    currency: str = "CNY"


@dataclass(frozen=True)
class InvoicePage:
    """一页查询结果，附带分页元数据。"""

    items: tuple[Invoice, ...]
    page: int
    page_size: int
    total: int

    @property
    def page_count(self) -> int:
        if self.total == 0:
            return 0
        return (self.total + self.page_size - 1) // self.page_size

    @property
    def has_next(self) -> bool:
        return self.page < self.page_count
