"""CLI 既有行为（回归用例）。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(APP_ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "invoicehub.cli", "list", *args],
        cwd=APP_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_cli_lists_invoices_as_json():
    result = run_cli("--data", "data/invoices.json", "--page-size", "3")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["total"] == 7
    assert payload["page_size"] == 3
    assert len(payload["items"]) == 3


def test_cli_filters_by_status():
    result = run_cli("--data", "data/invoices.json", "--status", "paid")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert {item["invoice_id"] for item in payload["items"]} == {"INV-1001", "INV-1003", "INV-1006"}


def test_cli_rejects_invalid_page_size():
    result = run_cli("--data", "data/invoices.json", "--page-size", "0")
    assert result.returncode == 2
    assert "page_size" in result.stderr
