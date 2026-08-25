"""Append the UCI Online Retail XLSX to the MySQL Raw layer."""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import uuid
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pymysql
from dotenv import load_dotenv

COLUMNS = [
    "InvoiceNo",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "UnitPrice",
    "CustomerID",
    "Country",
]
SQL = """INSERT INTO insightops_raw.uci_retail_line_raw
(batch_id,source_row_number,invoice_no,stock_code,description_text,quantity,invoice_ts,unit_price,customer_id,country_name)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""


def sha(path):
    d = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1048576), b""):
            d.update(chunk)
    return d.hexdigest()


def val(v):
    return None if pd.isna(v) else str(v)


def customer(v):
    return None if pd.isna(v) else str(int(v))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--batch-id", default=str(uuid.uuid4()))
    a = p.parse_args()
    path = a.input.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    load_dotenv(".env")
    password = os.environ["MYSQL_ROOT_PASSWORD"]
    df = pd.read_excel(path, engine="openpyxl")
    if list(df.columns) != COLUMNS:
        raise ValueError(f"XLSX 字段不符合预期：{list(df.columns)}")
    conn = pymysql.connect(
        host="127.0.0.1",
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user="root",
        password=password,
        charset="utf8mb4",
        autocommit=False,
    )
    loaded = 0
    try:
        with conn.cursor() as c:
            c.execute(
                """
                INSERT INTO insightops_ops.ingestion_batch (
                    batch_id, source_system, source_file, source_sha256,
                    extract_start_date, extract_end_date, status
                ) VALUES (%s, 'UCI', %s, %s, %s, %s, 'RUNNING')
                """,
                (
                    a.batch_id,
                    path.name,
                    sha(path),
                    df.InvoiceDate.min().date(),
                    df.InvoiceDate.max().date(),
                ),
            )
        conn.commit()
        rows = []
        for n, r in enumerate(df.itertuples(index=False, name=None), start=2):
            rows.append(
                (
                    a.batch_id,
                    n,
                    val(r[0]),
                    val(r[1]),
                    val(r[2]),
                    int(r[3]),
                    r[4].to_pydatetime(),
                    Decimal(str(r[5])),
                    customer(r[6]),
                    val(r[7]),
                )
            )
            if len(rows) == 5000:
                with conn.cursor() as c:
                    c.executemany(SQL, rows)
                conn.commit()
                loaded += len(rows)
                rows = []
        if rows:
            with conn.cursor() as c:
                c.executemany(SQL, rows)
            conn.commit()
            loaded += len(rows)
        with conn.cursor() as c:
            c.execute(
                """
                UPDATE insightops_ops.ingestion_batch
                SET status = 'SUCCEEDED', rows_loaded = %s, finished_at = UTC_TIMESTAMP(6)
                WHERE batch_id = %s
                """,
                (loaded, a.batch_id),
            )
        conn.commit()
    finally:
        conn.close()
    print(f"UCI Raw 导入完成：batch_id={a.batch_id}，rows_loaded={loaded}")


if __name__ == "__main__":
    sys.exit(main())
