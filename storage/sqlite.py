"""Low-level SQLite access: connection setup and schema bootstrap.

This is the direct replacement for the D1Database binding the original
Worker used (env.DB) — database/repository.py builds all of its queries
on top of the connection this module hands out.
"""
from __future__ import annotations

import asyncio
import logging
import os

import aiosqlite

logger = logging.getLogger(__name__)

_SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "schema.sql")


class Database:
    """Thin wrapper around a single shared aiosqlite connection.

    SQLite handles concurrent access from a single process well as long as
    writes are serialized; aiosqlite's connection already serializes
    operations onto one background thread, so a single shared connection
    (rather than a full pool) is sufficient here and avoids "database is
    locked" errors under concurrent asyncio tasks.
    """

    def __init__(self, path: str):
        self.path = path
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)) or ".", exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode = WAL;")
        await self._conn.execute("PRAGMA foreign_keys = ON;")
        await self._conn.commit()
        await self._apply_schema()
        logger.info("Connected to SQLite database at %s", self.path)

    async def _apply_schema(self) -> None:
        with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        assert self._conn is not None
        await self._conn.executescript(schema_sql)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database.connect() must be called before use")
        return self._conn

    def transaction(self):
        """Async context manager serializing writes through one lock, so a
        read-modify-write sequence (e.g. addCoinsToUser) can't race with
        another concurrent request. Wrap call sites that need atomicity in
        `async with db.transaction():`.
        """
        return self._lock
