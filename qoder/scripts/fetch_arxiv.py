"""Fetch the arXiv metadata snapshots used by the demo library.

Requires network access.  The app itself never calls arXiv at runtime; this
script is only for refreshing data/papers.json.

Usage:
    python scripts/fetch_arxiv.py
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
BASE = "https://export.arxiv.org/api/query"

QUERIES = {
    "rag": 'all:"retrieval augmented generation"',
    "agents": 'all:"large language model" AND all:"agent"',
    "hallucination": 'all:"hallucination" AND all:"language model"',
    "scidiscovery": 'all:"scientific discovery" AND all:"language model"',
    "litreview": 'all:"literature review" AND all:"large language model"',
}

CURATED_IDS = [
    "2005.11401",  # Lewis et al., RAG
    "2310.11511",  # Self-RAG
    "2307.03172",  # Lost in the Middle
    "2309.01431",  # Benchmarking LLMs in RAG (RGB)
    "2104.07567",  # Retrieval Augmentation Reduces Hallucination
    "2312.10997",  # RAG survey
    "2401.15884",  # Corrective RAG
    "2406.04744",  # CRAG benchmark
    "2401.05856",  # Seven Failure Points
    "2401.14887",  # The Power of Noise
    "2309.11495",  # Chain-of-Verification
    "2309.15217",  # Ragas
    "2401.00396",  # RAGTruth
    "2401.11817",  # Hallucination is Inevitable
]

HEADERS = {"User-Agent": "ResearchThread/0.1 (demo dataset refresh)"}


def fetch(client: httpx.Client, path: Path, params: dict[str, str]) -> None:
    response = client.get(BASE, params=params, headers=HEADERS)
    response.raise_for_status()
    path.write_bytes(response.content)
    print(f"wrote {path.name} ({len(response.content) / 1024:.1f} KiB)")


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=90, follow_redirects=True) as client:
        for name, query in QUERIES.items():
            fetch(
                client,
                RAW / f"arxiv-{name}.xml",
                {
                    "search_query": query,
                    "start": "0",
                    "max_results": "100",
                    "sortBy": "relevance",
                },
            )
            time.sleep(3)
        fetch(
            client,
            RAW / "arxiv-curated.xml",
            {"id_list": ",".join(CURATED_IDS), "start": "0", "max_results": "50"},
        )
    print("done. now run: python scripts/build_dataset.py")


if __name__ == "__main__":
    main()
