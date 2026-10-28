"""将 checkpoint 中新增的 Checkpointer 行安全合并回 orionai。"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from psycopg import sql

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from checkpointer_migration_utils import (  # noqa: E402
    MigrationError,
    active_source_connections,
    catalog_snapshot,
    compare_databases,
    configured_urls,
    connect,
    copy_archive_into_postgres_container,
    discover_checkpointer_tables,
    primary_key_columns,
    require_core_tables,
    run_pg_dump_to_file,
    run_postgres_container_tool,
)


def _columns(connection, table_name: str) -> list[str]:
    rows = connection.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table_name,),
    ).fetchall()
    return [row[0] for row in rows]


def _row_count(connection, table_name: str) -> int:
    return connection.execute(
        sql.SQL("SELECT count(*) FROM {}.{}").format(
            sql.Identifier("public"), sql.Identifier(table_name)
        )
    ).fetchone()[0]


def _copy_to_staging(
    source, destination, table_name: str, columns: list[str], staging_name: str
) -> None:
    destination.execute(
        sql.SQL("CREATE TEMP TABLE {} (LIKE {}.{} INCLUDING DEFAULTS) ON COMMIT DROP").format(
            sql.Identifier(staging_name), sql.Identifier("public"), sql.Identifier(table_name)
        )
    )
    select_query = sql.SQL("SELECT {} FROM {}.{} ORDER BY {}").format(
        sql.SQL(", ").join(sql.Identifier(column) for column in columns),
        sql.Identifier("public"),
        sql.Identifier(table_name),
        sql.SQL(", ").join(
            sql.Identifier(column) for column in primary_key_columns(source, table_name)
        ),
    )
    copy_query = sql.SQL("COPY {} ({}) FROM STDIN").format(
        sql.Identifier("pg_temp", staging_name),
        sql.SQL(", ").join(sql.Identifier(column) for column in columns),
    )
    with source.cursor(name=f"rollback_{table_name}") as source_cursor:
        source_cursor.execute(select_query)
        with destination.copy(copy_query) as copy:
            while rows := source_cursor.fetchmany(1000):
                for row in rows:
                    copy.write_row(row)


def _find_conflicts(
    destination, table_name: str, columns: list[str], primary_key: list[str], staging_name: str
) -> int:
    key_clause = sql.SQL(", ").join(sql.Identifier(column) for column in primary_key)
    existing_row = sql.SQL(", ").join(sql.Identifier("existing", column) for column in columns)
    incoming_row = sql.SQL(", ").join(sql.Identifier("incoming", column) for column in columns)
    query = sql.SQL(
        "SELECT count(*) FROM {}.{} AS existing "
        "JOIN {}.{} AS incoming USING ({}) "
        "WHERE ROW(existing.{}) IS DISTINCT FROM ROW(incoming.{})"
    ).format(
        sql.Identifier("public"),
        sql.Identifier(table_name),
        sql.Identifier("pg_temp"),
        sql.Identifier(staging_name),
        key_clause,
        existing_row,
        incoming_row,
    )
    return destination.execute(query).fetchone()[0]


def _merge_staging(
    destination, table_name: str, columns: list[str], primary_key: list[str], staging_name: str
) -> int:
    column_clause = sql.SQL(", ").join(sql.Identifier(column) for column in columns)
    key_clause = sql.SQL(", ").join(sql.Identifier(column) for column in primary_key)
    query = sql.SQL(
        "INSERT INTO {}.{} ({}) SELECT {} FROM {}.{} ON CONFLICT ({}) DO NOTHING"
    ).format(
        sql.Identifier("public"),
        sql.Identifier(table_name),
        column_clause,
        column_clause,
        sql.Identifier("pg_temp"),
        sql.Identifier(staging_name),
        key_clause,
    )
    cursor = destination.execute(query)
    return cursor.rowcount


def _restore_removed_source_tables(
    source_url, original_url, source_tables: list[str], source_counts: dict[str, int]
) -> dict[str, Any]:
    """旧表已删除时，从 checkpoint 归档恢复结构和全部当前记录。"""

    with tempfile.TemporaryDirectory(prefix="orionai-checkpointer-rollback-") as directory:
        archive = Path(directory) / "checkpointer-rollback.dump"
        dump_arguments = [
            "--format=custom",
            "--no-owner",
            "--no-acl",
            "--username",
            source_url.username or "orionai",
            "--dbname",
            "checkpoint",
        ]
        for table_name in source_tables:
            dump_arguments.extend(["--table", f"public.{table_name}"])
        run_pg_dump_to_file(dump_arguments, archive)
        container_archive = copy_archive_into_postgres_container(archive)
        try:
            run_postgres_container_tool(
                [
                    "pg_restore",
                    "--exit-on-error",
                    "--no-owner",
                    "--no-acl",
                    "--username",
                    original_url.username or "orionai",
                    "--dbname",
                    "orionai",
                    container_archive,
                ]
            )
        finally:
            run_postgres_container_tool(["rm", "-f", container_archive])

    with connect(source_url) as checkpoint_source, connect(original_url) as original:
        results = compare_databases(checkpoint_source, original)
    return {
        "status": "restored",
        "source_database": "checkpoint",
        "target_database": "orionai",
        "checkpoint_rows": source_counts,
        "tables": results,
        "source_database_retained": True,
    }


def rollback(*, execute: bool, writers_stopped: bool) -> dict[str, Any]:
    source_url, original_url = configured_urls()
    with connect(source_url) as checkpointer_source:
        source_tables = discover_checkpointer_tables(checkpointer_source)
        require_core_tables(source_tables)
        source_counts = {table: _row_count(checkpointer_source, table) for table in source_tables}

    with connect(original_url) as original:
        original_tables = discover_checkpointer_tables(original)
        original_counts = {table: _row_count(original, table) for table in original_tables}
        if original_tables and source_tables != original_tables:
            raise MigrationError("两套数据库的 Checkpointer 表集合不同，无法自动回滚。")
        if original_tables:
            with connect(source_url) as checkpointer_source:
                if catalog_snapshot(checkpointer_source, source_tables) != catalog_snapshot(
                    original, original_tables
                ):
                    raise MigrationError("两套数据库的表结构、约束或索引不同，无法自动回滚。")

    with connect(original_url, database="postgres", autocommit=True) as admin:
        open_connections = {
            database: active_source_connections(admin, database)
            for database in ("orionai", "checkpoint")
        }
    if not execute:
        return {
            "execute": False,
            "source_database": "checkpoint",
            "target_database": "orionai",
            "open_connections": open_connections,
            "checkpoint_rows": source_counts,
            "original_rows": original_counts,
            "source_tables_missing": not original_tables,
            "schema_match": bool(original_tables),
        }
    if not writers_stopped:
        raise MigrationError("正式回滚必须显式传入 --writers-stopped。")
    if any(open_connections.values()):
        raise MigrationError("orionai 或 checkpoint 仍有连接；请先停止后端和所有 Worker。")
    if not original_tables:
        return _restore_removed_source_tables(
            source_url,
            original_url,
            source_tables,
            source_counts,
        )

    merged_rows: dict[str, int] = {}
    with connect(source_url) as checkpointer_source, connect(original_url) as original:
        with original.transaction():
            staged: dict[str, tuple[list[str], list[str], str]] = {}
            for table_name in source_tables:
                columns = _columns(original, table_name)
                primary_key = primary_key_columns(original, table_name)
                if not primary_key:
                    raise MigrationError(f"表 public.{table_name} 缺少主键，停止回滚。")
                staging_name = f"rollback_{table_name}"
                _copy_to_staging(
                    checkpointer_source,
                    original,
                    table_name,
                    columns,
                    staging_name,
                )
                staged[table_name] = (columns, primary_key, staging_name)

            conflicts = {
                table_name: _find_conflicts(
                    original, table_name, columns, primary_key, staging_name
                )
                for table_name, (columns, primary_key, staging_name) in staged.items()
            }
            conflicting_tables = [name for name, count in conflicts.items() if count]
            if conflicting_tables:
                raise MigrationError(
                    "相同主键对应不同内容，未写入任何回滚数据："
                    + ", ".join(conflicting_tables)
                    + "。"
                )

            for table_name, (columns, primary_key, staging_name) in staged.items():
                merged_rows[table_name] = _merge_staging(
                    original, table_name, columns, primary_key, staging_name
                )
                if _find_conflicts(original, table_name, columns, primary_key, staging_name):
                    raise MigrationError(f"表 public.{table_name} 合并后内容校验失败。")

    with connect(original_url) as original:
        final_counts = {table: _row_count(original, table) for table in source_tables}
        for table_name, source_count in source_counts.items():
            if final_counts[table_name] < source_count:
                raise MigrationError(f"表 public.{table_name} 合并后记录数不足。")
    return {
        "status": "merged",
        "source_database": "checkpoint",
        "target_database": "orionai",
        "checkpoint_rows": source_counts,
        "inserted_rows": merged_rows,
        "original_rows_after_merge": final_counts,
        "source_database_retained": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="执行事务性缺失行合并；默认只读检查。",
    )
    parser.add_argument(
        "--writers-stopped",
        action="store_true",
        help="确认后端、Worker 和其他 Checkpointer 写入方均已停止。",
    )
    arguments = parser.parse_args()
    try:
        result = rollback(
            execute=arguments.execute,
            writers_stopped=arguments.writers_stopped,
        )
    except MigrationError as error:
        print(f"回滚已停止：{error}", file=sys.stderr)
        print("orionai 与 checkpoint 两个数据库都会保留。", file=sys.stderr)
        return 1
    except Exception as error:  # noqa: BLE001
        print(f"回滚失败（{type(error).__name__}）；两个数据库均保留。", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
