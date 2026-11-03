"""补丁解析与路径校验的单元测试（不调用模型）。"""

from __future__ import annotations

import pytest

from sddctx.runner import extract_diff, validate_diff

PATCH = """--- a/src/invoicehub/service.py
+++ b/src/invoicehub/service.py
@@ -1 +1 @@
-old
+new
"""


def test_extracts_fenced_diff():
    text = "说明\n```diff\n" + PATCH + "```\n"
    assert extract_diff(text) == PATCH


def test_extracts_bare_diff():
    assert extract_diff("前缀\n" + PATCH) == PATCH


def test_rejects_missing_diff():
    with pytest.raises(ValueError):
        extract_diff("没有补丁")


def test_accepts_only_src_targets():
    assert validate_diff(PATCH) == ["src/invoicehub/service.py"]


def test_normalizes_missing_path_prefixes():
    diff = "--- src/invoicehub/service.py\n+++ src/invoicehub/service.py\n@@ -1 +1 @@\n-a\n+b\n"
    normalized = extract_diff(diff)
    assert "--- a/src/invoicehub/service.py" in normalized
    assert "+++ b/src/invoicehub/service.py" in normalized
    assert validate_diff(normalized) == ["src/invoicehub/service.py"]


def test_normalizes_windows_separators():
    diff = "--- a/src\\invoicehub\\service.py\n+++ b/src\\invoicehub\\service.py\n@@ -1 +1 @@\n-a\n+b\n"
    normalized = extract_diff(diff)
    assert "a/src/invoicehub/service.py" in normalized
    assert validate_diff(normalized) == ["src/invoicehub/service.py"]


@pytest.mark.parametrize(
    "target",
    ["tests/test_min_amount_filter.py", "specs/REQ-INV-004.md", "../outside.py"],
)
def test_rejects_non_src_targets(target):
    diff = f"--- a/{target}\n+++ b/{target}\n@@ -1 +1 @@\n-a\n+b\n"
    with pytest.raises(ValueError):
        validate_diff(diff)
