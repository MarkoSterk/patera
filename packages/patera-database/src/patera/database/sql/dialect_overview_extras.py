"""Overview extras for different db dialects"""

from typing import Any, Dict, List, Tuple
from sqlalchemy import text
from sqlalchemy.inspection import inspect


def _portable_schema_stats(sync_conn, schema: str | None) -> Dict[str, Any]:
    insp = inspect(sync_conn)

    # pick schemas
    schemas = [schema] if schema else insp.get_schema_names()

    total_tables = 0
    total_views = 0
    total_indexes = 0
    total_foreign_keys = 0
    total_columns = 0
    tables_seen: List[Tuple[str, str]] = []  # (schema, table)

    # collect per-table info
    for sch in schemas:
        tables = insp.get_table_names(schema=sch)
        views = insp.get_view_names(schema=sch)
        total_tables += len(tables)
        total_views += len(views)

        for t in tables:
            tables_seen.append((sch, t))
            # columns
            cols = insp.get_columns(t, schema=sch)
            total_columns += len(cols)
            # indexes
            idxs = insp.get_indexes(t, schema=sch)
            total_indexes += len(idxs)
            # fks
            fks = insp.get_foreign_keys(t, schema=sch)
            total_foreign_keys += len(fks)

    avg_cols_per_table = (total_columns / total_tables) if total_tables else 0.0

    # Detect unindexed FKs (heuristic, portable)
    # For each FK on child table, check if any index covers exactly the fk column set (order-insensitive).
    unindexed_fk_count = 0
    for sch, t in tables_seen:
        fks = insp.get_foreign_keys(t, schema=sch)
        if not fks:
            continue
        idxs = insp.get_indexes(t, schema=sch)
        indexed_sets = {
            tuple(sorted(ix["column_names"])) for ix in idxs if ix.get("column_names")
        }
        for fk in fks:
            cols = fk.get("constrained_columns") or []
            if not cols:
                continue
            if tuple(sorted(cols)) not in indexed_sets:
                unindexed_fk_count += 1

    return {
        "schemas_count": len(schemas),
        "tables_count": total_tables,
        "views_count": total_views,
        "indexes_count": total_indexes,
        "foreign_keys_count": total_foreign_keys,
        "columns_count": total_columns,
        "avg_columns_per_table": avg_cols_per_table,
        "unindexed_foreign_keys": unindexed_fk_count,
    }


def _extras_postgres(sync_conn) -> Dict[str, Any]:
    # db size
    size = sync_conn.execute(
        text("SELECT pg_database_size(current_database())")
    ).scalar()
    # fast row estimates per table
    rows = (
        sync_conn.execute(
            text("""
        SELECT n.nspname AS schema, c.relname AS table, c.reltuples::bigint AS est_rows
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'  -- ordinary tables
          AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
          AND n.nspname NOT LIKE 'pg_%'
    """)
        )
        .mappings()
        .all()
    )
    per_table_est = {f"{r['schema']}.{r['table']}": int(r["est_rows"]) for r in rows}
    return {
        "db_size_bytes": int(size or 0),
        "row_estimates": per_table_est,
        "row_estimates_total": sum(per_table_est.values()),
        "notes": "Row counts are estimates from pg_class.reltuples.",
    }


def _extras_sqlite(sync_conn) -> Dict[str, Any]:
    # PRAGMAs return page size and page count; multiply for file size bytes
    page_size = sync_conn.execute(text("PRAGMA page_size;")).scalar()
    page_count = sync_conn.execute(text("PRAGMA page_count;")).scalar()
    freelist = sync_conn.execute(text("PRAGMA freelist_count;")).scalar()
    size_bytes = int((page_size or 0) * (page_count or 0))
    return {
        "db_size_bytes": size_bytes,
        "sqlite_page_size": page_size,
        "sqlite_page_count": page_count,
        "sqlite_freelist_pages": freelist,
    }


def _extras_mysql(sync_conn) -> Dict[str, Any]:
    # Use current database()
    db = sync_conn.execute(text("SELECT DATABASE()")).scalar()
    if not db:
        return {}
    rows = (
        sync_conn.execute(
            text("""
        SELECT
          TABLE_SCHEMA, TABLE_NAME,
          COALESCE(TABLE_ROWS,0) AS table_rows,
          COALESCE(DATA_LENGTH,0) + COALESCE(INDEX_LENGTH,0) AS total_bytes
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = :db AND TABLE_TYPE='BASE TABLE'
    """),
            {"db": db},
        )
        .mappings()
        .all()
    )
    size_total = sum(int(r["total_bytes"]) for r in rows)
    row_est_total = sum(int(r["table_rows"]) for r in rows)
    per_table_est = {
        f"{r['TABLE_SCHEMA']}.{r['TABLE_NAME']}": int(r["table_rows"]) for r in rows
    }
    return {
        "db_size_bytes": size_total,
        "row_estimates": per_table_est,
        "row_estimates_total": row_est_total,
        "notes": "Row counts are estimates from information_schema.TABLES.TABLE_ROWS.",
    }


def _extras_mssql(sync_conn) -> Dict[str, Any]:
    # total database size (approx) and row counts
    # size in 8KB pages
    db = sync_conn.execute(text("SELECT DB_NAME()")).scalar()
    if not db:
        return {}
    size_pages = sync_conn.execute(
        text("""
        SELECT SUM(size) FROM sys.master_files WHERE database_id = DB_ID()
    """)
    ).scalar()
    size_bytes = int((size_pages or 0) * 8 * 1024)

    # row counts via sys.dm_db_partition_stats (user tables only)
    rows = (
        sync_conn.execute(
            text("""
        SELECT s.name AS schema_name, t.name AS table_name,
               SUM(p.row_count) AS row_count
        FROM sys.tables t
        JOIN sys.schemas s ON t.schema_id = s.schema_id
        JOIN sys.dm_db_partition_stats p ON t.object_id = p.object_id
        WHERE p.index_id IN (0,1) -- heap or clustered index
        GROUP BY s.name, t.name
    """)
        )
        .mappings()
        .all()
    )
    per = {f"{r['schema_name']}.{r['table_name']}": int(r["row_count"]) for r in rows}
    return {
        "db_size_bytes": size_bytes,
        "row_counts": per,
        "row_counts_total": sum(per.values()),
        "notes": "Row counts from sys.dm_db_partition_stats; size from sys.master_files.",
    }


def _extras_oracle(sync_conn) -> Dict[str, Any]:
    # NUM_ROWS in ALL_TABLES are stats-based estimates (ANALYZE needed).
    rows = (
        sync_conn.execute(
            text("""
        SELECT owner AS schema, table_name, COALESCE(num_rows,0) AS est_rows
        FROM ALL_TABLES
    """)
        )
        .mappings()
        .all()
    )
    per = {f"{r['SCHEMA']}.{r['TABLE_NAME']}": int(r["EST_ROWS"]) for r in rows}
    # segment sizes
    seg = (
        sync_conn.execute(
            text("""
        SELECT owner AS schema, segment_name, SUM(bytes) AS bytes
        FROM ALL_SEGMENTS
        GROUP BY owner, segment_name
    """)
        )
        .mappings()
        .all()
    )
    size_total = sum(int(r["BYTES"]) for r in seg)
    return {
        "db_size_bytes": size_total,
        "row_estimates": per,
        "row_estimates_total": sum(per.values()),
        "notes": "Row counts are estimates from ALL_TABLES.NUM_ROWS; size from ALL_SEGMENTS.",
    }
