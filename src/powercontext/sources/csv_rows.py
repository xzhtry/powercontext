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

"""Row-level CSV Sources that keep every record verifiable by primary key.

Each data record becomes its own captured Source whose identity is derived from
the document and the primary-key value, so a citation can be resolved back to
the complete original row after reordering or a process restart.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Literal
from urllib.parse import quote

from pydantic import BaseModel, model_validator

from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources import TEXT_EVIDENCE_PROJECTION_KEY, AdapterSourceDefinition, TextEvidence
from powercontext.sources.models import Source, SourceMaterialization

CSV_ROW_SOURCE_NAME = "csv-row"
CSV_ROW_SOURCE_VERSION = "1"
_UTF8_BOM = b"\xef\xbb\xbf"


class CSVDocumentInput(BaseModel):
    """Offline CSV bytes to split into one Source per data record."""

    document_id: str
    primary_key: str
    content: bytes


class CSVRowInput(BaseModel):
    """One data record described by its header order and exact field strings."""

    document_id: str
    primary_key: str
    primary_key_value: str
    columns: tuple[str, ...]
    values: tuple[str, ...]


class CSVRowSource(Source):
    """Captured CSV record whose identity is the document and primary key."""

    materialization: Literal[SourceMaterialization.CAPTURED] = SourceMaterialization.CAPTURED
    source_id: str
    document_id: str
    primary_key: str
    primary_key_value: str
    columns: tuple[str, ...]
    values: tuple[str, ...]

    @model_validator(mode="after")
    def validate_record_identity(self) -> CSVRowSource:
        if len(self.columns) != len(self.values):
            raise ValueError("row must hold one value per header column")  # noqa: TRY003
        expected = csv_row_source_id(self.document_id, self.primary_key_value)
        if self.source_id != expected:
            raise ValueError("source_id must be the csv row identity")  # noqa: TRY003
        if self.name != expected:
            raise ValueError("name must equal source_id")  # noqa: TRY003
        return self


def csv_row_source_id(document_id: str, primary_key_value: str) -> str:
    """Return the delimiter-safe identity ``csv:<document>:<value>``."""

    checked_document = _checked_document_id(document_id)
    if not isinstance(primary_key_value, str):
        raise ValueError("primary_key_value must be a string")  # noqa: TRY003
    if not primary_key_value.strip():
        raise ValueError("primary_key_value must not be blank")  # noqa: TRY003
    identity = f"csv:{quote(checked_document, safe='')}:{quote(primary_key_value, safe='')}"
    if len(identity) > MAX_SOURCE_ID_LENGTH:
        raise ValueError(f"source_id must not exceed {MAX_SOURCE_ID_LENGTH} characters")  # noqa: TRY003
    return identity


def parse_csv_document(value: CSVDocumentInput) -> tuple[CSVRowInput, ...]:
    """Split one offline CSV document into validated row inputs.

    The whole document is decoded, parsed and validated before any row is
    returned, so an invalid input never yields a partial result.
    """

    document_id = _checked_document_id(value.document_id)
    primary_key = _checked_primary_key(value.primary_key)
    records = _read_records(_decode_utf8(value.content))

    if not records:
        raise ValueError("CSV document must contain a header record")  # noqa: TRY003
    columns = _checked_header(records[0])
    if primary_key not in columns:
        raise ValueError(f"primary key {primary_key!r} is not a header column")  # noqa: TRY003
    key_index = columns.index(primary_key)

    rows: list[CSVRowInput] = []
    seen: set[str] = set()
    for record in records[1:]:
        if not record:
            continue  # a fully empty physical record carries no data
        if len(record) != len(columns):
            raise ValueError(  # noqa: TRY003
                f"record has {len(record)} fields, header has {len(columns)}"
            )
        primary_key_value = record[key_index]
        if not primary_key_value.strip():
            raise ValueError("primary key value must not be blank")  # noqa: TRY003
        if primary_key_value in seen:
            raise ValueError(f"duplicate primary key value {primary_key_value!r}")  # noqa: TRY003
        seen.add(primary_key_value)
        rows.append(
            CSVRowInput(
                document_id=document_id,
                primary_key=primary_key,
                primary_key_value=primary_key_value,
                columns=columns,
                values=tuple(record),
            )
        )
    return tuple(rows)


def _checked_document_id(document_id: str) -> str:
    if not isinstance(document_id, str):
        raise ValueError("document_id must be a string")  # noqa: TRY003
    if not document_id.strip():
        raise ValueError("document_id must not be blank")  # noqa: TRY003
    if document_id != document_id.strip():
        raise ValueError("document_id must not contain leading or trailing whitespace")  # noqa: TRY003
    return document_id


def _checked_primary_key(primary_key: str) -> str:
    if not isinstance(primary_key, str):
        raise ValueError("primary_key must be a string")  # noqa: TRY003
    if not primary_key.strip():
        raise ValueError("primary_key must not be blank")  # noqa: TRY003
    return primary_key


def _decode_utf8(content: bytes) -> str:
    if not isinstance(content, (bytes, bytearray, memoryview)):
        raise ValueError("CSV content must be bytes")  # noqa: TRY003
    raw = bytes(content)
    if raw.startswith(_UTF8_BOM):
        raw = raw[len(_UTF8_BOM) :]
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("CSV content must be valid UTF-8") from error  # noqa: TRY003


def _read_records(text: str) -> list[list[str]]:
    """Read every record with the stdlib semantics the contract pins down."""

    records: list[list[str]] = []
    try:
        for record in csv.reader(io.StringIO(text, newline=""), strict=True):
            records.append(record)
    except csv.Error as error:
        raise ValueError(f"malformed CSV content: {error}") from error  # noqa: TRY003
    return records


def _checked_header(header: list[str]) -> tuple[str, ...]:
    if not header:
        raise ValueError("CSV header record must not be empty")  # noqa: TRY003
    for column in header:
        if not column.strip():
            raise ValueError("CSV header fields must not be blank")  # noqa: TRY003
    if len(set(header)) != len(header):
        raise ValueError("CSV header fields must be unique")  # noqa: TRY003
    return tuple(header)


def _row_object(columns: tuple[str, ...], values: tuple[str, ...]) -> dict[str, str]:
    return dict(zip(columns, values, strict=True))


class CSVRowSourceAdapter:
    """Resolve and read one captured CSV record."""

    input_class = CSVRowInput
    name = CSV_ROW_SOURCE_NAME
    source_class = CSVRowSource

    async def resolve(self, value: CSVRowInput, /) -> CSVRowSource:
        source_id = csv_row_source_id(value.document_id, value.primary_key_value)
        return CSVRowSource(
            name=source_id,
            source_id=source_id,
            document_id=value.document_id,
            primary_key=value.primary_key,
            primary_key_value=value.primary_key_value,
            columns=value.columns,
            values=value.values,
        )

    async def read(self, source: CSVRowSource, /) -> CSVRowInput:
        return CSVRowInput(
            document_id=source.document_id,
            primary_key=source.primary_key,
            primary_key_value=source.primary_key_value,
            columns=source.columns,
            values=source.values,
        )


class CSVRowTextEvidenceProjection:
    """Expose one row as canonical textual evidence without reordering fields."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = CSVRowSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: CSVRowSource, /) -> TextEvidence:
        row = _row_object(source.columns, source.values)
        return TextEvidence(
            source_type=CSV_ROW_SOURCE_NAME,
            source_id=source.source_id,
            content=json.dumps(row, ensure_ascii=False, separators=(",", ":")),
            metadata={
                "document_id": source.document_id,
                "primary_key": source.primary_key,
                "primary_key_value": source.primary_key_value,
                "columns": list(source.columns),
                "row": row,
            },
        )


CSV_ROW_SOURCE_ADAPTER = CSVRowSourceAdapter()
CSV_ROW_SOURCE_DEFINITION: AdapterSourceDefinition[CSVRowInput, CSVRowSource, CSVRowInput] = AdapterSourceDefinition(
    CSV_ROW_SOURCE_ADAPTER,
    version=CSV_ROW_SOURCE_VERSION,
    projections=(CSVRowTextEvidenceProjection(),),
)

__all__ = [
    "CSV_ROW_SOURCE_DEFINITION",
    "CSV_ROW_SOURCE_NAME",
    "CSV_ROW_SOURCE_VERSION",
    "CSVDocumentInput",
    "CSVRowInput",
    "CSVRowSource",
    "csv_row_source_id",
    "parse_csv_document",
]
