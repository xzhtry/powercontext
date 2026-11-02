"""共享测试数据。

固定数据让“修改前失败 / 修改后通过”的验证可重复，且不依赖运行日期。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from invoicehub.models import Invoice, InvoiceStatus


def _invoice(
    invoice_id: str,
    customer_id: str,
    status: InvoiceStatus,
    amount: str,
    issued_at: str,
) -> Invoice:
    return Invoice(
        invoice_id=invoice_id,
        customer_id=customer_id,
        status=status,
        total_amount=Decimal(amount),
        issued_at=datetime.fromisoformat(issued_at),
    )


@pytest.fixture
def invoices() -> tuple[Invoice, ...]:
    return (
        _invoice("INV-1005", "CUST-003", InvoiceStatus.VOID, "0.00", "2026-08-30T08:00:00+08:00"),
        _invoice("INV-1004", "CUST-002", InvoiceStatus.DRAFT, "1200.00", "2026-09-01T09:00:00+08:00"),
        _invoice("INV-1001", "CUST-001", InvoiceStatus.PAID, "1200.00", "2026-09-01T09:00:00+08:00"),
        _invoice("INV-1006", "CUST-001", InvoiceStatus.PAID, "1200.00", "2026-09-01T09:00:00+08:00"),
        _invoice("INV-1003", "CUST-002", InvoiceStatus.PAID, "1500.00", "2026-09-02T11:00:00+08:00"),
        _invoice("INV-1002", "CUST-001", InvoiceStatus.ISSUED, "800.00", "2026-09-03T15:30:00+08:00"),
        _invoice("INV-1007", "CUST-004", InvoiceStatus.ISSUED, "2000.50", "2026-09-04T10:00:00+08:00"),
    )
