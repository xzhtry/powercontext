"""目标功能测试：min_amount 金额下限筛选。

这些用例在实现前先写（并先运行失败），实现后必须全部通过。
Covers: REQ-INV-004.2, REQ-INV-004.3, API-INV-002.3
Role: target
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from invoicehub.models import InvoiceStatus
from invoicehub.service import list_invoices

APP_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(APP_ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "invoicehub.cli", "list", "--data", "data/invoices.json", *args],
        cwd=APP_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_min_amount_keeps_invoices_at_or_above_threshold(invoices):
    page = list_invoices(invoices, min_amount=Decimal("1200.00"))
    assert [item.invoice_id for item in page.items] == ["INV-1007", "INV-1003", "INV-1001", "INV-1004", "INV-1006"]
    assert page.total == 5


def test_min_amount_is_inclusive(invoices):
    page = list_invoices(invoices, min_amount=Decimal("1500.00"))
    assert [item.invoice_id for item in page.items] == ["INV-1007", "INV-1003"]


def test_min_amount_combines_with_status_filter(invoices):
    page = list_invoices(invoices, min_amount=Decimal("1200"), status=InvoiceStatus.PAID)
    assert [item.invoice_id for item in page.items] == ["INV-1003", "INV-1001", "INV-1006"]


def test_min_amount_combines_with_customer_and_pagination(invoices):
    page = list_invoices(invoices, min_amount="1200", customer_id="CUST-001", page=1, page_size=1)
    assert [item.invoice_id for item in page.items] == ["INV-1001"]
    assert page.total == 2


def test_min_amount_none_keeps_existing_behavior(invoices):
    assert list_invoices(invoices, min_amount=None).total == list_invoices(invoices).total


def test_negative_min_amount_is_rejected(invoices):
    with pytest.raises(ValueError):
        list_invoices(invoices, min_amount=Decimal("-0.01"))


def test_cli_accepts_min_amount():
    result = run_cli("--min-amount", "1500.00")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert [item["invoice_id"] for item in payload["items"]] == ["INV-1007", "INV-1003"]
