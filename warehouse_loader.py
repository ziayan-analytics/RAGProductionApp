import hashlib
import json
import os
from typing import Any
import uuid

from dotenv import load_dotenv
from llama_index.core.node_parser import SentenceSplitter
from sqlalchemy import create_engine, text

from custom_types import WarehouseChunk

load_dotenv()

DEFAULT_CHUNK_SIZE = int(os.getenv("WAREHOUSE_CHUNK_SIZE", "1000"))
DEFAULT_CHUNK_OVERLAP = int(os.getenv("WAREHOUSE_CHUNK_OVERLAP", "150"))


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _clean_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _row_identity(row: dict[str, Any], primary_key_columns: list[str]) -> str:
    if primary_key_columns:
        return ":".join(_clean_value(row.get(col)) for col in primary_key_columns)
    serialized = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _row_to_text(row: dict[str, Any], text_columns: list[str]) -> str:
    columns = text_columns or list(row.keys())
    lines = []
    for col in columns:
        value = _clean_value(row.get(col))
        if value:
            lines.append(f"{col}: {value}")
    return "\n".join(lines)


def load_and_chunk_warehouse(
    query: str | None = None,
    source_id: str | None = None,
    primary_key_columns: list[str] | None = None,
    text_columns: list[str] | None = None,
    metadata_columns: list[str] | None = None,
) -> list[WarehouseChunk]:
    database_url = os.getenv("WAREHOUSE_DATABASE_URL")
    if not database_url:
        raise ValueError("Set WAREHOUSE_DATABASE_URL before syncing warehouse data.")

    sync_query = query or os.getenv("WAREHOUSE_SYNC_QUERY")
    if not sync_query:
        table = os.getenv("WAREHOUSE_TABLE")
        if not table:
            raise ValueError("Set WAREHOUSE_SYNC_QUERY or WAREHOUSE_TABLE before syncing warehouse data.")
        sync_query = f"SELECT * FROM {table}"

    source = source_id or os.getenv("WAREHOUSE_SOURCE_ID") or os.getenv("WAREHOUSE_TABLE") or "warehouse"
    primary_keys = primary_key_columns or _csv(os.getenv("WAREHOUSE_PRIMARY_KEY_COLUMNS"))
    text_cols = text_columns or _csv(os.getenv("WAREHOUSE_TEXT_COLUMNS"))
    metadata_cols = metadata_columns or _csv(os.getenv("WAREHOUSE_METADATA_COLUMNS"))

    splitter = SentenceSplitter(
        chunk_size=DEFAULT_CHUNK_SIZE,
        chunk_overlap=DEFAULT_CHUNK_OVERLAP,
    )

    engine = create_engine(database_url)
    chunks: list[WarehouseChunk] = []

    with engine.connect() as conn:
        result = conn.execute(text(sync_query))
        for row in result.mappings():
            row_dict = dict(row)
            row_id = _row_identity(row_dict, primary_keys)
            row_text = _row_to_text(row_dict, text_cols)
            if not row_text.strip():
                continue

            metadata = {
                "source": source,
                "warehouse_row_id": row_id,
            }
            for col in metadata_cols:
                if col in row_dict:
                    metadata[col] = _clean_value(row_dict.get(col))

            for index, chunk_text in enumerate(splitter.split_text(row_text)):
                point_id = str(
                    uuid.uuid5(uuid.NAMESPACE_URL, f"{source}:{row_id}:{index}")
                )
                chunks.append(
                    WarehouseChunk(
                        id=point_id,
                        text=chunk_text,
                        source_id=source,
                        metadata={**metadata, "chunk_index": index},
                    )
                )

    return chunks
