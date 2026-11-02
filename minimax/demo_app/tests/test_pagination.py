"""分页不变量（回归用例）。

Covers: REQ-INV-004.4, API-INV-002.2
Role: regression
"""

from __future__ import annotations

import pytest

from invoicehub.service import list_invoices


def test_page_metadata(invoices):
    page = list_invoices(invoices, page=2, page_size=3)
    assert page.page == 2
    assert page.page_size == 3
    assert page.total == 7
    assert page.page_count == 3
    assert page.has_next is True


def test_pages_partition_the_result_set(invoices):
    seen: list[str] = []
    for page_number in (1, 2, 3):
        page = list_invoices(invoices, page=page_number, page_size=3)
        seen.extend(item.invoice_id for item in page.items)
    assert seen == [item.invoice_id for item in list_invoices(invoices).items]
    assert len(seen) == len(set(seen)) == 7


def test_out_of_range_page_is_empty_but_keeps_total(invoices):
    page = list_invoices(invoices, page=99, page_size=3)
    assert page.items == ()
    assert page.total == 7
    assert page.has_next is False


def test_invalid_page_is_rejected(invoices):
    with pytest.raises(ValueError):
        list_invoices(invoices, page=0)


@pytest.mark.parametrize("page_size", [0, -1, 101])
def test_invalid_page_size_is_rejected(invoices, page_size):
    with pytest.raises(ValueError):
        list_invoices(invoices, page_size=page_size)
