--- a/src/invoicehub/cli.py
+++ b/src/invoicehub/cli.py
@@ -14,3 +14,25 @@
+from decimal import Decimal
+
+
+def _parse_amount(value: str) -> Decimal:
+    """把命令行传入的金额解析为精确的十进制金额。
+
+    解析必须精确到分，禁止经过 ``float`` 中间值；负数属于非法参数。
+    """
+
+    try:
+        amount = Decimal(value.strip())
+    except ArithmeticError as exc:
+        raise argparse.ArgumentTypeError(f"金额不是合法的十进制数值：{value!r}") from exc
+    if not amount.is_finite():
+        raise argparse.ArgumentTypeError(f"金额必须是有限数值：{value!r}")
+    if amount < 0:
+        raise argparse.ArgumentTypeError(
+            f"金额下限必须是非负数 (must be non-negative, >= 0)，不能为负数，收到：{value!r}"
+        )
+    return amount
+
+
 def build_parser() -> argparse.ArgumentParser:
     parser = argparse.ArgumentParser(prog="invoicehub", description="财务发票查询工具")
     subparsers = parser.add_subparsers(dest="command", required=True)
@@ -19,6 +41,12 @@
     list_parser.add_argument("--data", default="data/invoices.json", help="发票 JSON 文件")
     list_parser.add_argument("--status", default=None, help="状态筛选：draft/issued/paid/void")
     list_parser.add_argument("--customer", default=None, help="客户号筛选")
+    list_parser.add_argument(
+        "--min-amount",
+        type=_parse_amount,
+        default=None,
+        help="金额下限（含边界），例如 1500.00",
+    )
     list_parser.add_argument("--page", type=int, default=1, help="页码，从 1 开始")
     list_parser.add_argument(
         "--page-size", type=int, default=DEFAULT_PAGE_SIZE, help=f"每页条数（1..{MAX_PAGE_SIZE}）"
@@ -43,6 +71,7 @@
         invoices,
         status=args.status,
         customer_id=args.customer,
+        min_amount=args.min_amount,
         page=args.page,
         page_size=args.page_size,
     )
--- a/src/invoicehub/service.py
+++ b/src/invoicehub/service.py
@@ -39,17 +39,55 @@
+from decimal import Decimal
+
+
+def _normalize_min_amount(min_amount: Decimal | int | str | None) -> Decimal | None:
+    """把金额下限规范化为精确的十进制金额。
+
+    ``None`` 表示不做金额过滤；负数属于非法输入，必须抛出 ``ValueError``。
+    """
+
+    if min_amount is None:
+        return None
+    amount = _to_decimal(min_amount)
+    if amount < 0:
+        raise ValueError(
+            f"min_amount 必须是非负数 (must be non-negative, >= 0)，不能为负数，收到：{min_amount!r}"
+        )
+    return amount
+
+
+def _to_decimal(value: Decimal | int | str | float) -> Decimal:
+    """把金额转换成精确的十进制值，禁止经过二进制浮点数。"""
+
+    if isinstance(value, Decimal):
+        return value
+    if isinstance(value, bool):
+        raise ValueError(f"金额必须是十进制数值，收到：{value!r}")
+    if isinstance(value, int):
+        return Decimal(value)
+    if isinstance(value, float):
+        return Decimal(str(value))
+    try:
+        return Decimal(str(value).strip())
+    except ArithmeticError as exc:
+        raise ValueError(f"金额必须是十进制数值，收到：{value!r}") from exc
+
+
 def list_invoices(
     invoices: Iterable[Invoice],
     *,
     status: InvoiceStatus | str | None = None,
     customer_id: str | None = None,
+    min_amount: Decimal | int | str | None = None,
     page: int = 1,
     page_size: int = DEFAULT_PAGE_SIZE,
 ) -> InvoicePage:
-    """按状态与客户筛选发票，返回一页结果。
+    """按状态、客户与金额下限筛选发票，返回一页结果。
 
     参数：
         invoices: 待查询的发票集合。
         status: 可选状态筛选，接受枚举或字符串。
         customer_id: 可选客户号筛选。
+        min_amount: 可选金额下限，只保留 ``total_amount >= min_amount`` 的发票（含边界）。
         page: 页码，从 1 开始。
         page_size: 每页条数，1..100。
 
@@ -59,12 +97,14 @@
 
     _validate_pagination(page, page_size)
     normalized_status = _coerce_status(status)
+    threshold = _normalize_min_amount(min_amount)
 
     filtered = [
         invoice
         for invoice in invoices
         if (normalized_status is None or invoice.status is normalized_status)
         and (customer_id is None or invoice.customer_id == customer_id)
+        and (threshold is None or _to_decimal(invoice.total_amount) >= threshold)
     ]
 
     ordered = sorted(filtered, key=_sort_key)
