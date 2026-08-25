"""Append a validated compact GA4 CSV into the MySQL Raw layer."""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sys
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterator

import pymysql
from dotenv import load_dotenv

EXPECTED_COLUMNS = [
    "event_date",
    "event_ts",
    "user_pseudo_id",
    "event_name",
    "ga_session_id",
    "page_location",
    "device_category",
    "country_name",
    "first_acquisition_source_name",
    "first_acquisition_medium_name",
    "transaction_id",
    "purchase_revenue_usd",
]
FULL_PAYLOAD_COLUMNS = [*EXPECTED_COLUMNS, "event_params_json", "items_json"]

INSERT_EVENT_SQL = """
INSERT INTO insightops_raw.ga4_event_raw (
  batch_id, source_row_number, event_date, event_ts, user_pseudo_id, event_name,
  ga_session_id, page_location, device_category, country_name,
  first_acquisition_source_name, first_acquisition_medium_name, transaction_id,
  purchase_revenue_usd, event_params_json, items_json
) VALUES (
  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
)
"""


def validate_columns(fieldnames: list[str] | None) -> list[str]:
    if fieldnames == EXPECTED_COLUMNS or fieldnames == FULL_PAYLOAD_COLUMNS:
        return fieldnames
    raise ValueError(f"CSV 字段不符合支持的轻量或完整载荷契约：{fieldnames}")


def inspect_csv(path: Path) -> tuple[int, date, date]:
    """Validate the compact CSV contract and derive its actual date coverage."""

    row_count = 0
    first_date: date | None = None
    last_date: date | None = None
    with path.open("r", encoding="utf-8", newline="") as file_handle:
        reader = csv.DictReader(file_handle)
        validate_columns(reader.fieldnames)
        for row in reader:
            event_date = date.fromisoformat(row["event_date"])
            first_date = event_date if first_date is None else min(first_date, event_date)
            last_date = event_date if last_date is None else max(last_date, event_date)
            row_count += 1
    if row_count == 0 or first_date is None or last_date is None:
        raise ValueError("CSV 没有事件行，不能创建接入批次")
    return row_count, first_date, last_date


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.removesuffix(" UTC"))


def empty_to_none(value: str) -> str | None:
    return value if value != "" else None


def iter_rows(path: Path, batch_id: str) -> Iterator[tuple[object, ...]]:
    with path.open("r", encoding="utf-8", newline="") as file_handle:
        reader = csv.DictReader(file_handle)
        columns = validate_columns(reader.fieldnames)
        has_full_payload = columns == FULL_PAYLOAD_COLUMNS
        for source_row_number, row in enumerate(reader, start=2):
            yield (
                batch_id,
                source_row_number,
                date.fromisoformat(row["event_date"]),
                parse_timestamp(row["event_ts"]),
                row["user_pseudo_id"],
                row["event_name"],
                row["ga_session_id"],
                row["page_location"],
                row["device_category"],
                row["country_name"],
                row["first_acquisition_source_name"],
                row["first_acquisition_medium_name"],
                empty_to_none(row["transaction_id"]),
                Decimal(row["purchase_revenue_usd"]) if row["purchase_revenue_usd"] != "" else None,
                empty_to_none(row["event_params_json"]) if has_full_payload else None,
                empty_to_none(row["items_json"]) if has_full_payload else None,
            )


def chunked(rows: Iterator[tuple[object, ...]], size: int) -> Iterator[list[tuple[object, ...]]]:
    chunk: list[tuple[object, ...]] = []
    for row in rows:
        chunk.append(row)
        if len(chunk) == size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Validated GA4 compact CSV path")
    parser.add_argument(
        "--batch-id", default=str(uuid.uuid4()), help="UUID for this append-only batch"
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--chunk-size", type=int, default=5_000)
    arguments = parser.parse_args()

    input_path = arguments.input.resolve()
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    if arguments.chunk_size < 1:
        raise ValueError("chunk-size 必须大于 0")

    load_dotenv(arguments.env_file)
    password = os.environ.get("MYSQL_ROOT_PASSWORD")
    if not password:
        raise RuntimeError("未找到 MYSQL_ROOT_PASSWORD；请提供 .env 文件")

    source_sha256 = sha256_file(input_path)
    expected_rows, extract_start_date, extract_end_date = inspect_csv(input_path)
    connection = pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ.get("MYSQL_USER", "root"),
        password=password,
        charset="utf8mb4",
        autocommit=False,
    )
    rows_loaded = 0
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO insightops_ops.ingestion_batch (
                  batch_id, source_system, source_file, source_sha256,
                  extract_start_date, extract_end_date, status
                ) VALUES (%s, 'GA4', %s, %s, %s, %s, 'RUNNING')
                """,
                (
                    arguments.batch_id,
                    input_path.name,
                    source_sha256,
                    extract_start_date,
                    extract_end_date,
                ),
            )
        connection.commit()

        for row_chunk in chunked(iter_rows(input_path, arguments.batch_id), arguments.chunk_size):
            with connection.cursor() as cursor:
                cursor.executemany(INSERT_EVENT_SQL, row_chunk)
            connection.commit()
            rows_loaded += len(row_chunk)

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE insightops_ops.ingestion_batch
                SET status = 'SUCCEEDED', rows_loaded = %s, finished_at = UTC_TIMESTAMP(6)
                WHERE batch_id = %s
                """,
                (rows_loaded, arguments.batch_id),
            )
        connection.commit()
    except Exception as exc:
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE insightops_ops.ingestion_batch
                SET status = 'FAILED', rows_loaded = %s, finished_at = UTC_TIMESTAMP(6),
                    error_message = %s
                WHERE batch_id = %s
                """,
                (rows_loaded, str(exc)[:65_535], arguments.batch_id),
            )
        connection.commit()
        raise
    finally:
        connection.close()

    if rows_loaded != expected_rows:
        raise AssertionError(f"导入行数不一致：expected={expected_rows}, loaded={rows_loaded}")
    print(f"GA4 Raw 导入完成：batch_id={arguments.batch_id}，rows_loaded={rows_loaded}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
