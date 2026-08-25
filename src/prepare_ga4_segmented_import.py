"""Validate contiguous GA4 CSV segments and build one auditable compact import file."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from ingest_ga4_raw import FULL_PAYLOAD_COLUMNS, sha256_file, validate_columns

SEGMENT_NAME = re.compile(r"^ga4_ecommerce_events_(\d{8})_(\d{8})\.csv$")


def parse_segment_bounds(path: Path) -> tuple[date, date]:
    match = SEGMENT_NAME.fullmatch(path.name)
    if match is None:
        raise ValueError(
            f"分段文件名必须为 ga4_ecommerce_events_YYYYMMDD_YYYYMMDD.csv：{path.name}"
        )
    start_date = datetime_date(match.group(1))
    end_date = datetime_date(match.group(2))
    if end_date < start_date:
        raise ValueError(f"分段结束日期早于开始日期：{path.name}")
    return start_date, end_date


def datetime_date(value: str) -> date:
    return date(int(value[:4]), int(value[4:6]), int(value[6:]))


def inspect_segment(path: Path, start_date: date, end_date: date) -> tuple[int, list[str]]:
    row_count = 0
    with path.open("r", encoding="utf-8", newline="") as file_handle:
        reader = csv.DictReader(file_handle)
        columns = validate_columns(reader.fieldnames)
        for source_row_number, row in enumerate(reader, start=2):
            event_date = date.fromisoformat(row["event_date"])
            if event_date < start_date or event_date > end_date:
                raise ValueError(
                    f"{path.name}:{source_row_number} 的日期 {event_date} 超出分段范围"
                )
            row_count += 1
    if row_count == 0:
        raise ValueError(f"{path.name}: 分段没有事件行")
    return row_count, columns


def combine_segments(
    input_directory: Path,
    start_date: date,
    end_date: date,
    output_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    segment_paths = sorted(input_directory.glob("ga4_ecommerce_events_*.csv"))
    if not segment_paths:
        raise FileNotFoundError(f"未找到 GA4 分段 CSV：{input_directory}")

    segments: list[dict[str, Any]] = []
    columns: list[str] | None = None
    expected_start = start_date
    for segment_path in segment_paths:
        segment_start, segment_end = parse_segment_bounds(segment_path)
        if segment_start != expected_start:
            raise ValueError(
                f"分段不连续：期望从 {expected_start} 开始，实际为 {segment_path.name}"
            )
        rows, segment_columns = inspect_segment(segment_path, segment_start, segment_end)
        if columns is None:
            columns = segment_columns
        elif columns != segment_columns:
            raise ValueError(f"{segment_path.name}: 字段与首个分段不一致")
        segments.append(
            {
                "file_name": segment_path.name,
                "sha256": sha256_file(segment_path),
                "extract_start_date": segment_start.isoformat(),
                "extract_end_date": segment_end.isoformat(),
                "rows": rows,
            }
        )
        expected_start = segment_end + timedelta(days=1)
    if expected_start != end_date + timedelta(days=1):
        raise ValueError(f"分段覆盖止于 {expected_start - timedelta(days=1)}，期望止于 {end_date}")
    if columns is None:
        raise AssertionError("至少应有一个已验证的分段")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as output_handle:
        writer = csv.writer(output_handle)
        writer.writerow(columns)
        for segment in segments:
            with (input_directory / segment["file_name"]).open(
                "r", encoding="utf-8", newline=""
            ) as input_handle:
                reader = csv.DictReader(input_handle)
                writer.writerows([row[column] for column in columns] for row in reader)

    manifest = {
        "source_system": "GA4 BigQuery public sample",
        "extract_start_date": start_date.isoformat(),
        "extract_end_date": end_date.isoformat(),
        "combined_file": output_path.name,
        "combined_sha256": sha256_file(output_path),
        "combined_rows": sum(segment["rows"] for segment in segments),
        "columns": columns,
        "payload_mode": "full_json" if columns == FULL_PAYLOAD_COLUMNS else "compact",
        "segments": segments,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--end-date", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.end_date < arguments.start_date:
        raise ValueError("end-date 不能早于 start-date")
    manifest = combine_segments(
        arguments.input_dir,
        arguments.start_date,
        arguments.end_date,
        arguments.output,
        arguments.manifest,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
