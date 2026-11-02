"""命令行入口：invoicehub list。"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation

from invoicehub.repository import InvoiceDataError, load_invoices
from invoicehub.service import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, list_invoices


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="invoicehub", description="财务发票查询工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="查询发票列表")
    list_parser.add_argument("--data", default="data/invoices.json", help="发票 JSON 文件")
    list_parser.add_argument("--status", default=None, help="状态筛选：draft/issued/paid/void")
    list_parser.add_argument("--customer", default=None, help="客户号筛选")
    list_parser.add_argument("--min-amount", default=None, help="金额下限，十进制字符串，含边界")
    list_parser.add_argument("--page", type=int, default=1, help="页码，从 1 开始")
    list_parser.add_argument(
        "--page-size", type=int, default=DEFAULT_PAGE_SIZE, help=f"每页条数（1..{MAX_PAGE_SIZE}）"
    )
    return parser


def _invoice_to_dict(invoice) -> dict[str, object]:
    return {
        "invoice_id": invoice.invoice_id,
        "customer_id": invoice.customer_id,
        "status": invoice.status.value,
        "total_amount": str(invoice.total_amount),
        "issued_at": invoice.issued_at.isoformat(),
        "currency": invoice.currency,
    }


def _run_list(args: argparse.Namespace) -> int:
    invoices = load_invoices(args.data)
    min_amount = Decimal(args.min_amount) if args.min_amount is not None else None
    page = list_invoices(
        invoices,
        status=args.status,
        customer_id=args.customer,
        min_amount=min_amount,
        page=args.page,
        page_size=args.page_size,
    )
    print(
        json.dumps(
            {
                "items": [_invoice_to_dict(item) for item in page.items],
                "page": page.page,
                "page_size": page.page_size,
                "total": page.total,
                "page_count": page.page_count,
                "has_next": page.has_next,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            return _run_list(args)
    except (ValueError, InvoiceDataError, InvalidOperation) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2
    return 2


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
