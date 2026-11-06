"""Build data/papers.json from the arXiv API snapshots in data/raw.

The app ships the resulting JSON so it can run offline. Re-run this script only
when refreshing the demo library.

Usage:
    python scripts/build_dataset.py
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "papers.json"

ATOM = "http://www.w3.org/2005/Atom"
ARXIV = "http://arxiv.org/schemas/atom"
NS = {"a": ATOM, "arxiv": ARXIV}

QUERY_LABELS = {
    "rag": "RAG",
    "agents": "LLM Agent",
    "hallucination": "幻觉与事实性",
    "scidiscovery": "AI for Science",
    "litreview": "文献综述自动化",
    "curated": "经典与评测基准",
}

TOPIC_MAP = {
    "cs.CL": "自然语言处理",
    "cs.AI": "人工智能",
    "cs.LG": "机器学习",
    "cs.IR": "信息检索",
    "cs.CV": "计算机视觉",
    "cs.SE": "软件工程",
    "cs.HC": "人机交互",
    "cs.CY": "计算与社会",
    "cs.RO": "机器人",
    "cs.MA": "多智能体",
    "cs.NE": "神经计算",
    "cs.DL": "数字图书馆",
    "cs.GL": "通用文献",
    "stat.ML": "统计机器学习",
    "q-bio": "生物信息",
    "physics": "物理",
    "eess": "电子工程",
    "math": "数学",
}


def clean(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def strip_version(arxiv_id: str) -> str:
    return re.sub(r"v\d+$", "", arxiv_id)


def main() -> None:
    if not RAW.exists():
        raise SystemExit(f"missing raw data directory: {RAW}")

    records: dict[str, dict] = {}
    per_query: dict[str, int] = {}

    for path in sorted(RAW.glob("arxiv-*.xml")):
        group = path.stem.removeprefix("arxiv-")
        root = ET.parse(path).getroot()
        count = 0
        for entry in root.findall("a:entry", NS):
            abs_url = clean(entry.findtext("a:id", default="", namespaces=NS))
            match = re.search(r"abs/([^/]+)$", abs_url)
            if not match:
                continue
            arxiv_id = strip_version(match.group(1))
            title = clean(entry.findtext("a:title", default="", namespaces=NS))
            abstract = clean(entry.findtext("a:summary", default="", namespaces=NS))
            if not title or len(abstract) < 250:
                continue

            categories = [
                node.attrib.get("term", "")
                for node in entry.findall("a:category", NS)
                if node.attrib.get("term")
            ]
            primary = categories[0] if categories else "cs.AI"
            topic = TOPIC_MAP.get(primary) or TOPIC_MAP.get(primary.split(".")[0]) or "交叉学科"
            authors = [
                clean(node.findtext("a:name", default="", namespaces=NS))
                for node in entry.findall("a:author", NS)
            ]
            authors = [name for name in authors if name]
            author_text = ", ".join(authors[:6])
            if len(authors) > 6:
                author_text += " 等"

            published = clean(entry.findtext("a:published", default="", namespaces=NS))
            year = int(published[:4]) if published[:4].isdigit() else 0
            journal_ref = clean(entry.findtext("arxiv:journal_ref", default="", namespaces=NS))
            doi = clean(entry.findtext("arxiv:doi", default="", namespaces=NS))

            record = {
                "arxiv_id": arxiv_id,
                "title": title,
                "abstract": abstract,
                "authors": author_text,
                "year": year,
                "venue": journal_ref or "arXiv 预印本",
                "topic": topic,
                "categories": categories[:4],
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                "doi": doi,
                "open_access": 1,
                "citation_count": 0,
                "source": "arXiv",
                "query_group": group,
            }
            existing = records.get(arxiv_id)
            if existing:
                # Keep the first ranking but merge provenance.
                existing["query_group"] = existing["query_group"] + "+" + group
                continue
            records[arxiv_id] = record
            count += 1
        per_query[group] = count
        print(f"{path.name}: {count} usable entries")

    papers = sorted(records.values(), key=lambda item: (-item["year"], item["title"].lower()))
    payload = {
        "dataset": "ResearchThread arXiv demo library",
        "description": "A bundled metadata snapshot of arXiv papers used by the demo research project. "
        "Titles and abstracts are fetched from the public arXiv API; original papers remain the "
        "property of their authors.",
        "license": "arXiv API metadata; abstracts are quoted for research/demo purposes. See data/README.md.",
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "queries": {QUERY_LABELS.get(key, key): {"file": f"arxiv-{key}.xml", "usable": value} for key, value in per_query.items()},
        "count": len(papers),
        "papers": papers,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(papers)} unique papers)")


if __name__ == "__main__":
    main()
