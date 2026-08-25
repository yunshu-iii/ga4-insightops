import csv
from pathlib import Path

import pytest

from ingest_ga4_raw import (
    EXPECTED_COLUMNS,
    FULL_PAYLOAD_COLUMNS,
    inspect_csv,
    iter_rows,
    parse_timestamp,
)


def write_compact_csv(path: Path, dates: list[str], *, full_payload: bool = False) -> None:
    with path.open("w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(
            file_handle, fieldnames=FULL_PAYLOAD_COLUMNS if full_payload else EXPECTED_COLUMNS
        )
        writer.writeheader()
        for event_date in dates:
            row = {
                "event_date": event_date,
                "event_ts": f"{event_date} 00:00:00.000000 UTC",
                "user_pseudo_id": "user-1",
                "event_name": "page_view",
                "ga_session_id": "123",
                "page_location": "https://example.com/",
                "device_category": "desktop",
                "country_name": "US",
                "first_acquisition_source_name": "google",
                "first_acquisition_medium_name": "organic",
                "transaction_id": "",
                "purchase_revenue_usd": "",
            }
            if full_payload:
                row.update({"event_params_json": "[]", "items_json": "[]"})
            writer.writerow(row)


def test_inspect_csv_derives_input_date_range(tmp_path: Path) -> None:
    input_path = tmp_path / "ga4.csv"
    write_compact_csv(input_path, ["2020-11-03", "2020-11-01", "2020-11-02"])

    row_count, start_date, end_date = inspect_csv(input_path)

    assert row_count == 3
    assert start_date.isoformat() == "2020-11-01"
    assert end_date.isoformat() == "2020-11-03"


def test_inspect_csv_rejects_empty_event_file(tmp_path: Path) -> None:
    input_path = tmp_path / "empty.csv"
    write_compact_csv(input_path, [])

    with pytest.raises(ValueError, match="没有事件行"):
        inspect_csv(input_path)


def test_full_payload_csv_preserves_json_columns_for_raw_import(tmp_path: Path) -> None:
    input_path = tmp_path / "full.csv"
    write_compact_csv(input_path, ["2020-11-01"], full_payload=True)

    imported_row = next(iter_rows(input_path, "test-batch"))

    assert imported_row[-2:] == ("[]", "[]")


def test_parse_timestamp_accepts_bigquery_fractional_and_whole_seconds() -> None:
    assert parse_timestamp("2020-12-08 04:01:48 UTC").microsecond == 0
    assert parse_timestamp("2020-12-08 04:01:48.123456 UTC").microsecond == 123456
