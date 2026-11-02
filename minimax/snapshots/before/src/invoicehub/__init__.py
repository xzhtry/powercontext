"""InvoiceHub：一个可运行、带测试的迷你财务发票查询服务。

模块刻意保持小而完整：领域模型、JSON 仓库、查询服务与 CLI。
SDD 上下文管理示例以本工程作为“业务工程”，所有规格、代码、测试都会被导入
seekdb 并用于为开发任务构造上下文。
"""

from invoicehub.models import Invoice, InvoicePage, InvoiceStatus
from invoicehub.service import list_invoices

__all__ = ["Invoice", "InvoicePage", "InvoiceStatus", "list_invoices"]
__version__ = "0.3.0"
