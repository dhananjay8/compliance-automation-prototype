import os
import uuid
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg import rows
from psycopg_pool import ConnectionPool

_MIN_CONNECTIONS = int(os.getenv("DB_POOL_MIN", "1"))
_MAX_CONNECTIONS = int(os.getenv("DB_POOL_MAX", "10"))


def _build_dsn() -> str:
    host = os.getenv("PGHOST", "localhost")
    port = os.getenv("PGPORT", "5432")
    dbname = os.getenv("PGDATABASE", "compliance_test")
    user = os.getenv("PGUSER", "test")
    password = os.getenv("PGPASSWORD", "testpass")
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


class Database:
    def __init__(self) -> None:
        self._pool: ConnectionPool | None = None

    def configure(self, dsn: str | None = None) -> None:
        if dsn is None:
            dsn = _build_dsn()
        self._pool = ConnectionPool(
            dsn,
            min_size=_MIN_CONNECTIONS,
            max_size=_MAX_CONNECTIONS,
        )
        self._pool.wait()

    @contextmanager
    def get_conn(self, row_factory=rows.dict_row):
        if self._pool is None:
            raise RuntimeError("Database not configured")
        conn = self._pool.getconn()
        try:
            conn.row_factory = row_factory
            yield conn
        finally:
            self._pool.putconn(conn)

    @contextmanager
    def get_cursor(self, row_factory=rows.dict_row):
        with self.get_conn(row_factory=row_factory) as conn:
            cur = conn.cursor()
            try:
                yield cur
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cur.close()

    def execute(
        self,
        sql: str,
        params: tuple | dict | list | None = None,
        many: bool = False,
    ) -> list[dict[str, Any]]:
        with self.get_cursor() as cur:
            if many:
                cur.executemany(sql, params or [])
            else:
                cur.execute(sql, params)
            if cur.description:
                return _stringify_uuids(list(cur.fetchall()))
            return []

    def fetchone(
        self, sql: str, params: tuple | dict | list | None = None
    ) -> dict[str, Any] | None:
        rows_list = self.execute(sql, params)
        return rows_list[0] if rows_list else None

    def init_schema(self, schema_path: str = "prototype/schema.sql") -> None:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = f.read()
        statements = _split_statements(schema)
        with self.get_cursor() as cur:
            for stmt in statements:
                cur.execute(stmt)


def _stringify_uuids(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: _stringify_uuids(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_stringify_uuids(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_stringify_uuids(v) for v in value)
    return value


def _split_statements(schema: str) -> list[str]:
    raw_parts = schema.split(";")
    cleaned: list[str] = []
    for part in raw_parts:
        lines = [
            line.strip()
            for line in part.splitlines()
            if line.strip() and not line.strip().startswith("--")
        ]
        if lines:
            cleaned.append("\n".join(lines))
    return cleaned


db = Database()
