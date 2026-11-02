# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Parse a complete PDF into page-level Sources and retrieve evidence pages.

Every physical page becomes one captured Source whose identity includes the
document digest, so a citation keeps pointing at the exact revision it was
retrieved from. Retrieval stays inside the public scoped-Memory API: the
question is expanded into focused lexical probes, the probes are fused by
concept coverage, and only really stored entries are returned as citations.
"""

from __future__ import annotations

import hashlib
import io
import re
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import quote

from pydantic import BaseModel, model_validator

from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources import TEXT_EVIDENCE_PROJECTION_KEY, AdapterSourceDefinition, TextEvidence
from powercontext.sources.models import Source, SourceMaterialization

if TYPE_CHECKING:
    from powercontext.builtin.artifacts.memory.models import MemoryCitation

PDF_PAGE_SOURCE_NAME = "pdf-page"
PDF_PAGE_SOURCE_VERSION = "1"
_MAX_CONCEPTS = 14
_MAX_CANDIDATES = 128
# Each probe is read deeper than the citation budget on purpose: a page that
# ranks just outside one probe's top-20 still deserves a vote when several other
# concepts also point at it.
_PROBE_DEPTH = 100
_RRF_K = 60
_QUERY_WORDS = frozenset({
    "a", "about", "above", "after", "all", "also", "an", "and", "any", "are", "as", "at", "be", "been",
    "before", "being", "below", "between", "both", "but", "by", "can", "could", "did", "do", "does",
    "during", "each", "further", "had", "has", "have", "having", "he", "her", "here", "his", "how",
    "i", "if", "in", "into", "is", "it", "its", "itself", "just", "me", "more", "most", "my", "no",
    "nor", "not", "of", "off", "on", "once", "only", "or", "other", "our", "out", "over", "own",
    "same", "she", "should", "so", "some", "such", "than", "that", "the", "their", "them", "then",
    "there", "these", "they", "this", "those", "through", "to", "too", "under", "until", "up", "very",
    "was", "we", "were", "what", "when", "where", "which", "while", "who", "whom", "why", "will",
    "with", "would", "you", "your", "please", "give", "respond", "answer", "state", "shown", "detail",
    "details", "question", "following", "based", "using", "use", "used", "note", "total",
})
_INSTRUCTION_PREFIXES = (
    "respond",
    "answer",
    "give a response",
    "give an answer",
    "reply",
    "assume",
    "you are",
    "you must",
    "use only",
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_TOKEN = re.compile(r"[a-z0-9]+")


class PDFDocumentInput(BaseModel):
    """One complete offline PDF document."""

    document_id: str
    content: bytes


class PDFPageInput(BaseModel):
    """One physical page of a PDF document."""

    document_id: str
    document_sha256: str
    page_number: int
    text: str


class PDFPageSource(Source):
    """Captured PDF page bound to one document revision and physical page."""

    materialization: Literal[SourceMaterialization.CAPTURED] = SourceMaterialization.CAPTURED
    source_id: str
    document_id: str
    document_sha256: str
    page_number: int
    text: str

    @model_validator(mode="after")
    def validate_page_identity(self) -> PDFPageSource:
        expected = pdf_page_source_id(self.document_id, self.document_sha256, self.page_number)
        if self.source_id != expected:
            raise ValueError("source_id must be the pdf page identity")  # noqa: TRY003
        if self.name != expected:
            raise ValueError("name must equal source_id")  # noqa: TRY003
        return self


def pdf_page_source_id(document_id: str, document_sha256: str, page_number: int) -> str:
    """Return the revision-scoped identity ``pdf:<document>:<digest>:<page>``."""

    if not isinstance(document_id, str):
        raise ValueError("document_id must be a string")  # noqa: TRY003
    if not document_id.strip():
        raise ValueError("document_id must not be blank")  # noqa: TRY003
    if not isinstance(page_number, int) or isinstance(page_number, bool) or page_number < 1:
        raise ValueError("page_number must be a positive integer")  # noqa: TRY003
    identity = f"pdf:{quote(document_id, safe='')}:{document_sha256}:{page_number}"
    if len(identity) > MAX_SOURCE_ID_LENGTH:
        raise ValueError(f"source_id must not exceed {MAX_SOURCE_ID_LENGTH} characters")  # noqa: TRY003
    return identity


def parse_pdf_document(value: PDFDocumentInput) -> tuple[PDFPageInput, ...]:
    """Return every physical page of one PDF, ordered from page 1.

    The complete document is parsed before anything is returned, so a damaged
    or unreadable file never produces a partial page list.
    """

    document_id = _checked_document_id(value.document_id)
    content = _checked_content(value.content)
    digest = hashlib.sha256(content).hexdigest()
    texts = _extract_page_texts(content)
    return tuple(
        PDFPageInput(
            document_id=document_id,
            document_sha256=digest,
            page_number=page_number,
            text=text,
        )
        for page_number, text in enumerate(texts, start=1)
    )


def _checked_document_id(document_id: object) -> str:
    if not isinstance(document_id, str):
        raise ValueError("document_id must be a string")  # noqa: TRY003
    if not document_id.strip():
        raise ValueError("document_id must not be blank")  # noqa: TRY003
    return document_id


def _checked_content(content: object) -> bytes:
    if not isinstance(content, (bytes, bytearray, memoryview)):
        raise ValueError("PDF content must be bytes")  # noqa: TRY003
    raw = bytes(content)
    if not raw:
        raise ValueError("PDF content must not be empty")  # noqa: TRY003
    return raw


def _extract_page_texts(content: bytes) -> list[str]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("PDF requires a user password")  # noqa: TRY003
        return [_page_text(page) for page in reader.pages]
    except ValueError:
        raise
    except Exception as error:  # noqa: BLE001 - every unreadable document is one failure mode
        raise ValueError(f"PDF cannot be parsed completely: {error}") from error


def _page_text(page: Any) -> str:
    text = page.extract_text()
    return text if isinstance(text, str) else ""


class PDFPageSourceAdapter:
    """Resolve and read one captured PDF page."""

    input_class = PDFPageInput
    name = PDF_PAGE_SOURCE_NAME
    source_class = PDFPageSource

    async def resolve(self, value: PDFPageInput, /) -> PDFPageSource:
        source_id = pdf_page_source_id(value.document_id, value.document_sha256, value.page_number)
        return PDFPageSource(
            name=source_id,
            source_id=source_id,
            document_id=value.document_id,
            document_sha256=value.document_sha256,
            page_number=value.page_number,
            text=value.text,
        )

    async def read(self, source: PDFPageSource, /) -> PDFPageInput:
        return PDFPageInput(
            document_id=source.document_id,
            document_sha256=source.document_sha256,
            page_number=source.page_number,
            text=source.text,
        )


class PDFPageTextEvidenceProjection:
    """Expose one page as textual evidence prefixed by its document identity."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PDFPageSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: PDFPageSource, /) -> TextEvidence:
        return TextEvidence(
            source_type=PDF_PAGE_SOURCE_NAME,
            source_id=source.source_id,
            content=f"{source.document_id}\n{source.text}",
            metadata={
                "document_id": source.document_id,
                "document_sha256": source.document_sha256,
                "page_number": source.page_number,
            },
        )


async def search_pdf_pages(memory: Any, question: str, limit: int = 10) -> tuple[MemoryCitation, ...]:
    """Return up to ``limit`` distinct page citations for one finance question.

    Only pages that really exist in Memory are returned. The question is probed
    first with its whole lexical content, then with focused per-concept probes;
    both candidate sets are fused so a page matching many distinct concepts
    outranks a page that merely repeats one.
    """

    if limit < 1 or not isinstance(question, str) or not question.strip():
        return ()

    probes = _question_probes(question)
    if probes is None or not probes.probes:
        return ()

    from powercontext.builtin.artifacts.memory.models import MemoryCitation
    from powercontext.builtin.runtime import GetMemoryEntryRequest, SearchMemoryRequest

    hits_by_key: dict[tuple[str, str, str], Any] = {}
    fused: dict[tuple[str, str, str], float] = {}

    for queries in probes.probes:
        best: dict[tuple[str, str, str], float] = {}
        for query in queries:
            page = await memory.search(
                SearchMemoryRequest(query=query, mode="fts", limit=_PROBE_DEPTH)
            )
            for rank, hit in enumerate(page.hits):
                key = _hit_key(hit)
                hits_by_key.setdefault(key, hit)
                score = 1.0 / (_RRF_K + rank)
                if score > best.get(key, 0.0):
                    best[key] = score
        for key, score in best.items():
            fused[key] = fused.get(key, 0.0) + score

    # Reciprocal-rank fusion: a page that ranks well for several independent
    # concepts beats a page that merely repeats one concept's vocabulary.
    ordered = sorted(fused, key=lambda key: fused[key], reverse=True)
    ranked = [hits_by_key[key] for key in ordered[:_MAX_CANDIDATES]]

    citations: list[MemoryCitation] = []
    seen_pages: set[str] = set()
    for hit in ranked:
        if len(citations) >= limit:
            break
        citation = MemoryCitation(
            memory_ref=hit.memory_ref,
            entry_id=hit.entry_id,
            entry_version_id=hit.entry_version_id,
        )
        try:
            entry = (await memory.get(GetMemoryEntryRequest(citation=citation))).entry
        except Exception:  # noqa: BLE001 - a stale hit is simply not a usable citation
            continue
        page_keys = {
            reference.source_id
            for reference in entry.sources
            if reference.source_type == PDF_PAGE_SOURCE_NAME
        }
        if not page_keys or page_keys & seen_pages:
            continue
        seen_pages |= page_keys
        citations.append(citation)
    return tuple(citations)


def _hit_key(hit: Any) -> tuple[str, str, str]:
    return (hit.memory_ref.artifact_id, hit.entry_id, hit.entry_version_id)


class _QuestionProbes:
    """Ordered probe groups: the whole question first, then one group per concept."""

    def __init__(self, probes: list[list[str]]) -> None:
        self.probes = probes


def _question_probes(question: str) -> _QuestionProbes | None:
    sentences = [sentence for sentence in _SENTENCE_SPLIT.split(question) if sentence.strip()]
    content = [sentence for sentence in sentences if not _is_instruction(sentence)] or sentences
    terms = _content_terms(" ".join(content)) or _content_terms(question)
    if not terms:
        return None
    selected = terms[:_MAX_CONCEPTS]
    return _QuestionProbes([[" ".join(selected)], *[_variant_queries(term) for term in selected]])


def _is_instruction(sentence: str) -> bool:
    folded = " ".join(sentence.split()).casefold()
    return any(folded.startswith(prefix) for prefix in _INSTRUCTION_PREFIXES)


def _content_terms(text: str) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for token in _TOKEN.findall(text.casefold()):
        if len(token) < 2 or token in _QUERY_WORDS or token in seen:
            continue
        if token.isdigit() and len(token) < 4:
            continue
        seen.add(token)
        terms.append(token)
    return terms


def _variant_queries(term: str) -> list[str]:
    """Group a term with its common inflections into <=2-term probes.

    The backend admits a candidate on one matched term only while a probe holds
    at most two terms, so pairing inflections keeps morphology recall without
    tightening the admission floor.
    """

    variants = [term]
    if len(term) > 4 and term.endswith("ies"):
        variants.append(term[:-3] + "y")
    elif len(term) > 4 and term.endswith("es"):
        variants.extend((term[:-2], term[:-1]))
    elif len(term) > 3 and term.endswith("s"):
        variants.append(term[:-1])
    if len(term) > 5 and term.endswith("ing"):
        variants.append(term[:-3])
    if len(term) > 4 and term.endswith("ed"):
        variants.append(term[:-2])
    unique: list[str] = []
    for variant in variants:
        if variant and len(variant) > 1 and variant not in unique:
            unique.append(variant)
    return [" ".join(unique[index : index + 2]) for index in range(0, len(unique), 2)] or [term]


PDF_PAGE_SOURCE_ADAPTER = PDFPageSourceAdapter()
PDF_PAGE_SOURCE_DEFINITION: AdapterSourceDefinition[PDFPageInput, PDFPageSource, PDFPageInput] = (
    AdapterSourceDefinition(
        PDF_PAGE_SOURCE_ADAPTER,
        version=PDF_PAGE_SOURCE_VERSION,
        projections=(PDFPageTextEvidenceProjection(),),
    )
)

__all__ = [
    "PDF_PAGE_SOURCE_DEFINITION",
    "PDF_PAGE_SOURCE_NAME",
    "PDFDocumentInput",
    "PDFPageInput",
    "PDFPageSource",
    "parse_pdf_document",
    "pdf_page_source_id",
    "search_pdf_pages",
]
