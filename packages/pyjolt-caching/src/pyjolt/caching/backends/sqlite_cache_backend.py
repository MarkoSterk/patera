"""
SQLite cache backend

Indicated values are defaults
CACHE_SQLITE_PATH: str = "./pyjolt_cache.sqlite3" # file path (required for persistence)
CACHE_SQLITE_TABLE: str = "cache_entries" # table name
CACHE_KEY_PREFIX: str = "pyjolt:cache:" # optional key namespace
CACHE_DURATION: int = 300 # default TTL seconds
CACHE_SQLITE_WAL_CHECKPOINT_MODE: str = "PASSIVE" #PASSIVE|FULL|RESTART|TRUNCATE
CACHE_SQLITE_WAL_CHECKPOINT_EVERY: int = 100 #run checkpoint every N write ops
"""

from __future__ import annotations

import os
import pickle
import time
from typing import Optional, TYPE_CHECKING, Tuple, cast, Any
from pydantic import BaseModel, Field

import aiosqlite

from .base_cache_backend import BaseCacheBackend

if TYPE_CHECKING:
    from pyjolt import PyJolt


class SQLiteCacheConfig(BaseModel):
    CACHE_SQLITE_PATH: str = Field(
        "./pyjolt_cache.db",
        description="SQLite DB file path (use ':memory:' for in-memory)",
    )
    CACHE_SQLITE_TABLE: str = Field(
        "cache_entries", description="Table name for cache entries"
    )
    CACHE_DURATION: int = Field(300, description="Cache default TTL in seconds")
    CACHE_KEY_PREFIX: str = Field("", description="Cache key prefix/namespace")
    CACHE_SQLITE_WAL_CHECKPOINT_MODE: str = Field(
        "PASSIVE",
        description="Mode for WAL checkpointing: PASSIVE|FULL|RESTART|TRUNCATE",
    )
    CACHE_SQLITE_WAL_CHECKPOINT_EVERY: int = Field(
        100, description="Insert WAL checkpoint every N write operations"
    )


class SQLiteCacheBackend(BaseCacheBackend):
    """SQLite-backed cache using pickled payloads (async via aiosqlite)."""

    def __init__(
        self,
        db_path: str,
        table: str = "cache_entries",
        default_ttl: int = 300,
        key_prefix: str = "",
        checkpoint_mode: str = "PASSIVE",
        checkpoint_every: int = 100,
    ) -> None:
        if not db_path:
            raise ValueError(
                "CACHE_SQLITE_PATH must be provided for SQLiteCacheBackend"
            )
        self._db_path = db_path
        self._table = table
        self.default_ttl = int(default_ttl)
        self._conn: Optional[aiosqlite.Connection] = None
        if key_prefix and not key_prefix.endswith(":"):
            key_prefix = key_prefix + ":"
        self._prefix = key_prefix
        # WAL checkpoint settings
        self._checkpoint_mode = checkpoint_mode.upper()
        if self._checkpoint_mode not in {"PASSIVE", "FULL", "RESTART", "TRUNCATE"}:
            raise ValueError(
                "CACHE_SQLITE_WAL_CHECKPOINT_MODE must be one of PASSIVE|FULL|RESTART|TRUNCATE"
            )
        self._checkpoint_every = max(1, int(checkpoint_every))
        self._write_ops = 0

    @classmethod
    def configure_from_app(
        cls, app: "PyJolt", configs: dict[str, Any]
    ) -> "SQLiteCacheBackend":
        db_path = cast(str, configs.get("SQLITE_PATH", "./pyjolt_cache.db"))
        table = cast(str, configs.get("SQLITE_TABLE", "cache_entries"))
        default_ttl = int(configs.get("DURATION", 300))
        key_prefix = cast(str, configs.get("KEY_PREFIX", ""))
        checkpoint_mode = cast(
            str, configs.get("SQLITE_WAL_CHECKPOINT_MODE", "PASSIVE")
        )
        checkpoint_every = int(configs.get("SQLITE_WAL_CHECKPOINT_EVERY", 100))
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        return cls(
            db_path=db_path,
            table=table,
            default_ttl=default_ttl,
            key_prefix=key_prefix,
            checkpoint_mode=checkpoint_mode,
            checkpoint_every=checkpoint_every,
        )

    async def connect(self) -> None:
        if self._conn:
            return
        self._conn = await aiosqlite.connect(self._db_path)
        # Pragmas tuned for app caches (good perf/safety tradeoffs)
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA synchronous=NORMAL;")
        await self._conn.execute("PRAGMA foreign_keys=ON;")
        await self._conn.execute(
            "PRAGMA busy_timeout=3000;"
        )  # 3s wait instead of immediate 'database is locked'. Useful for WAL mode with concurrent readers/writers (multiple app workers)
        await self._conn.execute(
            "PRAGMA wal_autocheckpoint=1000;"
        )  # checkpoint every ~1000 pages (~4MB)
        await self._ensure_schema()
        await self._conn.commit()

    async def disconnect(self) -> None:
        if self._conn is None:
            return
        await self._conn.close()
        self._conn = None

    async def _ensure_schema(self) -> None:
        assert self._conn is not None
        t = self._table
        await self._conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS {t} (
                k TEXT PRIMARY KEY,
                v BLOB NOT NULL,
                expire REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_{t}_expire ON {t}(expire);
            CREATE INDEX IF NOT EXISTS idx_{t}_k_pref ON {t}(k);
            """
        )

    def _k(self, key: str) -> str:
        return f"{self._prefix}{key}" if self._prefix else key

    async def _cleanup_expired(self) -> None:
        assert self._conn is not None
        now = time.time()
        await self._conn.execute(f"DELETE FROM {self._table} WHERE expire <= ?", (now,))
        await self._conn.commit()

    async def _maybe_checkpoint(self) -> None:
        """Run WAL checkpoint every N write operations."""
        assert self._conn is not None
        self._write_ops += 1
        if (self._write_ops % self._checkpoint_every) == 0:
            # PRAGMA wal_checkpoint(PASSIVE)
            await self._conn.execute(f"PRAGMA wal_checkpoint({self._checkpoint_mode});")
            await self._conn.commit()

    async def get(self, key: str) -> Optional[dict]:
        if self._conn is None:
            await self.connect()
        assert self._conn is not None
        k = self._k(key)
        async with self._conn.execute(
            f"SELECT v, expire FROM {self._table} WHERE k = ?",
            (k,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        raw, expire = cast(Tuple[bytes, float], row)
        now = time.time()
        if expire <= now:
            await self._conn.execute(f"DELETE FROM {self._table} WHERE k = ?", (k,))
            await self._conn.commit()
            # count deletion as a write op for checkpoint cadence
            await self._maybe_checkpoint()
            return None
        try:
            return cast(dict, pickle.loads(raw))
        except Exception:
            # Drop corrupt entry
            await self._conn.execute(f"DELETE FROM {self._table} WHERE k = ?", (k,))
            await self._conn.commit()
            await self._maybe_checkpoint()
            return None

    async def set(self, key: str, value: dict, duration: Optional[int] = None) -> None:
        if self._conn is None:
            await self.connect()
        assert self._conn is not None
        ttl = int(duration) if duration is not None else self.default_ttl
        expire = time.time() + ttl
        k = self._k(key)
        raw = pickle.dumps(value)
        # Upsert with ON CONFLICT
        await self._conn.execute(
            f"""
            INSERT INTO {self._table}(k, v, expire, updated_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(k) DO UPDATE SET
                v=excluded.v,
                expire=excluded.expire,
                updated_at=excluded.updated_at
            """,
            (k, raw, expire, time.time()),
        )
        await self._conn.commit()
        # count insertion as a write op for checkpoint cadence
        await self._cleanup_expired()
        await self._maybe_checkpoint()

    async def delete(self, key: str) -> None:
        if self._conn is None:
            await self.connect()
        assert self._conn is not None
        await self._conn.execute(
            f"DELETE FROM {self._table} WHERE k = ?", (self._k(key),)
        )
        await self._conn.commit()
        await self._maybe_checkpoint()

    async def clear(self) -> None:
        if self._conn is None:
            await self.connect()
        assert self._conn is not None
        if self._prefix:
            like = f"{self._prefix}%"
            await self._conn.execute(
                f"DELETE FROM {self._table} WHERE k LIKE ?", (like,)
            )
        else:
            await self._conn.execute(f"DELETE FROM {self._table}")
        # Checkpoint after full clear to truncate WAL
        await self._conn.execute(f"PRAGMA wal_checkpoint({self._checkpoint_mode});")
        await self._conn.commit()
        # reset write op count after full clear
        self._write_ops = 0
