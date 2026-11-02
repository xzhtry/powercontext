"""从 JSON 文件读取发票数据。"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from invoicehub.models import Invoice, InvoiceStatus


class InvoiceDataError(ValueError):
    """发票数据文件格式错误。"""


def _parse_invoice(raw: Any) -> Invoice:
    if not isinstance(raw, dict):
        raise InvoiceDataError(f"发票记录必须是对象：{raw!r}")
    try:
        return Invoice(
            invoice_id=str(raw["invoice_id"]),
            customer_id=str(raw["customer_id"]),
            status=InvoiceStatus(str(raw["status"])),
            total_amount=Decimal(str(raw["total_amount"])),
            issued_at=datetime.fromisoformat(str(raw["issued_at"])),
            currency=str(raw.get("currency", "CNY")),
        )
    except (KeyError, ValueError) as error:
        raise InvoiceDataError(f"无法解析发票记录：{raw!r}") from error


def load_invoices(path: str | Path) -> tuple[Invoice, ...]:
    """读取发票 JSON 文件并返回不可变列表。"""

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise InvoiceDataError("发票文件顶层必须是数组")
    return tuple(_parse_invoice(item) for item in data)
