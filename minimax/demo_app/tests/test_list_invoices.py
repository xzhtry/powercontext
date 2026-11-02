"""既有列表行为：筛选与稳定排序（回归用例）。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from invoicehub.models import InvoiceStatus
from invoicehub.service import list_invoices


def test_returns_all_invoices_without_filters(invoices):
    page = list_invoices(invoices)
    assert page.total == 7
    assert len(page.items) == 7


def test_filters_by_status(invoices):
    page = list_invoices(invoices, status=InvoiceStatus.PAID)
    assert [item.invoice_id for item in page.items] == ["INV-1003", "INV-1001", "INV-1006"]
    assert page.total == 3


def test_filters_by_customer(invoices):
    page = list_invoices(invoices, customer_id="CUST-001")
    assert [item.invoice_id for item in page.items] == ["INV-1002", "INV-1001", "INV-1006"]


def test_combines_status_and_customer(invoices):
    page = list_invoices(invoices, status="paid", customer_id="CUST-001")
    assert [item.invoice_id for item in page.items] == ["INV-1001", "INV-1006"]


def test_sorts_by_issued_at_desc_then_invoice_id(invoices):
    page = list_invoices(invoices)
    assert [item.invoice_id for item in page.items] == [
        "INV-1007",
        "INV-1002",
        "INV-1003",
        "INV-1001",
        "INV-1004",
        "INV-1006",
        "INV-1005",
    ]


def test_unknown_status_is_rejected(invoices):
    with pytest.raises(ValueError):
        list_invoices(invoices, status="archived")


def test_amounts_are_decimal(invoices):
    page = list_invoices(invoices, customer_id="CUST-004")
    assert page.items[0].total_amount == Decimal("2000.50")
