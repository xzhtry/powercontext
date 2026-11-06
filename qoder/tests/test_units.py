"""Pure-function and static-asset tests that do not need seekdb/PowerContext."""

from __future__ import annotations

import json
from pathlib import Path

from app import synthesis
from app.seekdb import _highlight, _snippet, _term_list, sql_literal

ROOT = Path(__file__).resolve().parents[1]


def test_terms_keep_acronyms_and_drop_stopwords() -> None:
    terms = _term_list("How does RAG reduce hallucination in long contexts?")
    assert "rag" in terms
    assert "hallucination" in terms
    assert "contexts" in terms
    assert "does" not in terms
    assert len(terms) <= 10


def test_terms_expand_chinese_synonyms() -> None:
    terms = _term_list("幻觉 检索增强 可靠性")
    assert "hallucination" in terms
    assert "retrieval" in terms
    assert "augmented" in terms
    assert "reliability" in terms


def test_sql_literal_escapes_quotes_and_backslashes() -> None:
    assert sql_literal("O'Reilly") == "'O\\'Reilly'"
    assert sql_literal("a\\b") == "'a\\\\b'"
    assert sql_literal(None) == "NULL"
    assert sql_literal(True) == "1"


def test_snippet_and_highlight_escape_html() -> None:
    text = "RAG can still hallucinate <script>alert(1)</script> when retrieval is noisy."
    snippet = _snippet(text, ["rag", "hallucination"])
    highlighted = _highlight(snippet, ["rag", "hallucination"])
    assert "<mark>RAG</mark>" in highlighted
    assert "<script>" not in highlighted
    assert "&lt;script&gt;" in highlighted


def sample_brief() -> dict:
    return {
        "question": "RAG 真的能让大模型更可靠吗？",
        "scope": "聚焦 RAG 与幻觉评测。",
        "criteria": ["有实验或基准", "讨论事实性"],
        "stage": "证据筛选",
        "next_action": "补一条检索噪声的反方证据",
    }


def sample_evidence() -> list[dict]:
    return [
        {
            "evidence_id": 1,
            "paper_id": 10,
            "stance": "challenge",
            "note": "检索噪声会显著影响结论。",
            "title": "The Power of Noise",
            "authors": "Cuconasu et al.",
            "year": 2024,
            "venue": "SIGIR",
            "url": "https://arxiv.org/abs/2401.14887",
            "topic": "信息检索",
        },
        {
            "evidence_id": 2,
            "paper_id": 20,
            "stance": "support",
            "note": "RAG 在开放域问答上提升事实性。",
            "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
            "authors": "Lewis et al.",
            "year": 2020,
            "venue": "NeurIPS",
            "url": "https://arxiv.org/abs/2005.11401",
            "topic": "自然语言处理",
        },
    ]


def test_review_contains_sections_citations_and_references() -> None:
    draft = synthesis.generate(sample_brief(), sample_evidence(), "review")
    markdown = draft["markdown"]
    assert draft["title"].startswith("证据综述：")
    for heading in ("## 0. 一句话结论", "## 3. 支持证据", "## 4. 挑战与限定", "## 6. 矛盾点与研究空白", "## 参考"):
        assert heading in markdown
    # Evidence is sorted support -> challenge before citation numbering.
    assert markdown.index("### [1] Retrieval-Augmented") < markdown.index("### [2] The Power of Noise")
    assert "[1] Lewis et al." in markdown
    assert "[2] Cuconasu et al." in markdown
    assert "未调用外部大模型" in markdown
    assert draft["counts"] == {"challenge": 1, "support": 1}


def test_weekly_template_has_discussion_section() -> None:
    draft = synthesis.generate(sample_brief(), sample_evidence(), "weekly")
    assert draft["template"] == "weekly"
    assert "## 3. 需要组会讨论的分歧" in draft["markdown"]
    assert "## 4. 下周计划" in draft["markdown"]


def test_dataset_shape() -> None:
    payload = json.loads((ROOT / "data" / "papers.json").read_text(encoding="utf-8"))
    assert payload["count"] == 508
    assert len(payload["papers"]) == 508
    assert all({"arxiv_id", "title", "abstract", "year"} <= set(paper) for paper in payload["papers"][:20])

    demo = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))
    assert demo["brief"]["question"]
    assert len(demo["evidence"]) == 9
    assert {item["stance"] for item in demo["evidence"]} == {"support", "challenge", "mixed"}


def test_static_app_shell_exists() -> None:
    html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    assert "研脉" in html
    assert "/assets/app.js" in html
    assert "/assets/styles.css" in html


def test_fastapi_routes_are_registered() -> None:
    from app.main import app

    paths = {route.path for route in app.routes}
    assert "/api/bootstrap" in paths
    assert "/api/search" in paths
    assert "/api/evidence" in paths
    assert "/api/synthesis" in paths
    assert "/api/session/new" in paths
