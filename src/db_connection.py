"""Central, explicit MySQL connection factories for reads and transactional writes."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pymysql
from dotenv import load_dotenv
from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class DatabaseSettings:
    host: str
    port: int
    user: str
    password: str


def settings_from_env(env_file: Path) -> DatabaseSettings:
    """Load the local MySQL settings without printing or serializing the password."""

    load_dotenv(env_file)
    password = os.environ.get("MYSQL_ROOT_PASSWORD")
    if not password:
        raise RuntimeError("未找到 MYSQL_ROOT_PASSWORD；请提供 .env 文件")
    return DatabaseSettings(
        host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ.get("MYSQL_USER", "root"),
        password=password,
    )


def sqlalchemy_url(settings: DatabaseSettings) -> URL:
    """Build a safe SQLAlchemy URL for pandas read queries."""

    return URL.create(
        "mysql+pymysql",
        username=settings.user,
        password=settings.password,
        host=settings.host,
        port=settings.port,
        database="insightops_mart",
        query={"charset": "utf8mb4"},
    )


def sqlalchemy_engine_from_env(env_file: Path) -> Engine:
    """Return a pre-ping Engine for short, explicit read-only DataFrame queries."""

    return create_engine(sqlalchemy_url(settings_from_env(env_file)), pool_pre_ping=True)


def pymysql_transaction_connection_from_env(env_file: Path) -> pymysql.Connection:
    """Keep existing transactional writes on explicit PyMySQL DBAPI connections."""

    settings = settings_from_env(env_file)
    return pymysql.connect(
        host=settings.host,
        port=settings.port,
        user=settings.user,
        password=settings.password,
        charset="utf8mb4",
        autocommit=False,
    )
