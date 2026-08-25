import csv
import json
from datetime import date
from pathlib import Path

import pytest

from ingest_ga4_raw import EXPECTED_COLUMNS, FULL_PAYLOAD_COLUMNS
from prepare_ga4_segmented_import import combine_segments


def write_segment(path: Path, event_date: str, *, full_payload: bool = False) -> None:
    with path.open("w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(
            file_handle, fieldnames=FULL_PAYLOAD_COLUMNS if full_payload else EXPECTED_COLUMNS
        )
        writer.writeheader()
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


def test_combine_segments_records_hashes_and_preserves_rows(tmp_path: Path) -> None:
    input_directory = tmp_path / "segments"
    input_directory.mkdir()
    write_segment(input_directory / "ga4_ecommerce_events_20201101_20201101.csv", "2020-11-01")
    write_segment(input_directory / "ga4_ecommerce_events_20201102_20201102.csv", "2020-11-02")
    output_path = tmp_path / "combined.csv"
    manifest_path = tmp_path / "manifest.json"

    manifest = combine_segments(
        input_directory,
        start_date=date(2020, 11, 1),
        end_date=date(2020, 11, 2),
        output_path=output_path,
        manifest_path=manifest_path,
    )

    assert manifest["combined_rows"] == 2
    assert len(manifest["segments"]) == 2
    assert json.loads(manifest_path.read_text())["combined_sha256"] == manifest["combined_sha256"]
    with output_path.open(newline="", encoding="utf-8") as file_handle:
        assert len(list(csv.DictReader(file_handle))) == 2


def test_combine_segments_rejects_gaps(tmp_path: Path) -> None:
    input_directory = tmp_path / "segments"
    input_directory.mkdir()
    write_segment(input_directory / "ga4_ecommerce_events_20201101_20201101.csv", "2020-11-01")
    write_segment(input_directory / "ga4_ecommerce_events_20201103_20201103.csv", "2020-11-03")

    with pytest.raises(ValueError, match="分段不连续"):
        combine_segments(
            input_directory,
            start_date=date(2020, 11, 1),
            end_date=date(2020, 11, 3),
            output_path=tmp_path / "combined.csv",
            manifest_path=tmp_path / "manifest.json",
        )


def test_combine_segments_keeps_full_payload_contract(tmp_path: Path) -> None:
    input_directory = tmp_path / "segments"
    input_directory.mkdir()
    write_segment(
        input_directory / "ga4_ecommerce_events_20201101_20201101.csv",
        "2020-11-01",
        full_payload=True,
    )

    manifest = combine_segments(
        input_directory,
        start_date=date(2020, 11, 1),
        end_date=date(2020, 11, 1),
        output_path=tmp_path / "combined.csv",
        manifest_path=tmp_path / "manifest.json",
    )

    assert manifest["payload_mode"] == "full_json"
    assert manifest["columns"] == FULL_PAYLOAD_COLUMNS
