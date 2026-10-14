"""
SQLite cache backend

Settings of the cache extension that uses it (defaults shown):
SQLITE_PATH = "./patera_cache.db"            # file path
SQLITE_TABLE = "cache_entries"               # table name
KEY_PREFIX = "patera:<app>:<cache>:"         # key namespace ("" for none)
DURATION = 300                               # default TTL in seconds
SQLITE_WAL_CHECKPOINT_MODE = "PASSIVE"       # PASSIVE|FULL|RESTART|TRUNCATE
SQLITE_WAL_CHECKPOINT_EVERY = 100            # checkpoint every N writes
"""

from __future__ import annotations

import os
import re
import time
from fnmatch import fnmatchcase
from typing import Generic, Optional, TYPE_CHECKING, Tuple, TypeVar, cast, Any
from pydantic import BaseModel

import aiosqlite

from .base_cache_backend import BaseCacheBackend

if TYPE_CHECKING:
    from patera import Patera

AppT = TypeVar("AppT", bound="Patera", default="Patera")


class SQLiteCacheBackend(BaseCacheBackend[AppT], Generic[AppT]):
    """SQLite-backed cache storing JSON payloads (async via aiosqlite)."""

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
            raise ValueError("SQLITE_PATH must be provided for SQLiteCacheBackend")
        self._db_path = db_path
        self._table = table
        self.default_ttl = int(default_ttl)
        self._conn: Optional[aiosqlite.Connection] = None
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
            # The table name is interpolated into SQL statements.
            raise ValueError(f"Invalid SQLite cache table name: {table!r}")
        key_prefix = key_prefix or ""
        if key_prefix and not key_prefix.endswith(":"):
            key_prefix = key_prefix + ":"
        self._prefix = key_prefix
        # WAL checkpoint settings
        self._checkpoint_mode = checkpoint_mode.upper()
        if self._checkpoint_mode not in {"PASSIVE", "FULL", "RESTART", "TRUNCATE"}:
            raise ValueError(
                "SQLITE_WAL_CHECKPOINT_MODE must be one of PASSIVE|FULL|RESTART|TRUNCATE"
            )
        self._checkpoint_every = max(1, int(checkpoint_every))
        self._write_ops = 0

    @classmethod
    def from_configs(
        cls,
        app: AppT,
        configs: dict[str, Any] | BaseModel,
        namespace: str = "cache",
    ) -> "SQLiteCacheBackend[AppT]":
        """
        Creates a backend from a config mapping or a CachingConfig
        (SQLITE_PATH, SQLITE_TABLE, DURATION, KEY_PREFIX, ...). KEY_PREFIX
        defaults to "patera:<application>:<namespace>:", so caches sharing
        one file and table stay apart; set it to "" explicitly for none.
        """
        configs = cls._config_values(configs)
        db_path = cast(str, configs.get("SQLITE_PATH") or "./patera_cache.db")
        table = cast(str, configs.get("SQLITE_TABLE") or "cache_entries")
        default_ttl = int(configs.get("DURATION") or 300)
        configured_prefix = configs.get("KEY_PREFIX")
        key_prefix = (
            cls.default_key_prefix(app, namespace)
            if configured_prefix is None
            else str(configured_prefix)
        )
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
        payload = self.decode_payload(raw)
        if payload is not None:
            return payload
        # Drop an entry that cannot be read (corrupt, or written by an older
        # version).
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
        raw = self.encode_payload(value)
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

    async def delete(
        self, key: str, *, regex: bool = False, wildcard: bool = False
    ) -> int:
        """
        Deletes entries (exact key, wildcard pattern or regex) in this
        backend's namespace and returns the number of deleted entries.
        """
        if regex and wildcard:
            raise ValueError("Use either regex=True or wildcard=True, not both.")
        if self._conn is None:
            await self.connect()
        assert self._conn is not None

        if not regex and not wildcard:
            keys = [self._k(key)]
        else:
            async with self._conn.execute(f"SELECT k FROM {self._table}") as cur:
                rows = await cur.fetchall()
            pattern = re.compile(key) if regex else None
            keys = []
            for (full_key,) in rows:
                if self._prefix and not full_key.startswith(self._prefix):
                    continue
                short_key = full_key[len(self._prefix) :]
                if pattern is not None:
                    if pattern.search(short_key):
                        keys.append(full_key)
                elif fnmatchcase(short_key, key):
                    keys.append(full_key)

        deleted = 0
        for full_key in keys:
            cursor = await self._conn.execute(
                f"DELETE FROM {self._table} WHERE k = ?", (full_key,)
            )
            deleted += max(cursor.rowcount, 0)
        await self._conn.commit()
        await self._maybe_checkpoint()
        return deleted

    async def clear(self) -> None:
        if self._conn is None:
            await self.connect()
        assert self._conn is not None
        if self._prefix:
            # Escape LIKE wildcards: "_" in a prefix must match only "_".
            escaped = (
                self._prefix.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            await self._conn.execute(
                f"DELETE FROM {self._table} WHERE k LIKE ? ESCAPE '\\'",
                (f"{escaped}%",),
            )
        else:
            await self._conn.execute(f"DELETE FROM {self._table}")
        # Commit first: a checkpoint cannot run inside the open transaction.
        await self._conn.commit()
        # Checkpoint after full clear to truncate WAL
        await self._conn.execute(f"PRAGMA wal_checkpoint({self._checkpoint_mode});")
        await self._conn.commit()
        # reset write op count after full clear
        self._write_ops = 0
