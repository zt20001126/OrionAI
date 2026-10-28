"""将已停写的 Checkpointer 表从 orionai 迁移到 checkpoint。"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from psycopg import sql

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from checkpointer_migration_utils import (  # noqa: E402
    MigrationError,
    active_source_connections,
    compare_databases,
    configured_urls,
    connect,
    copy_archive_into_postgres_container,
    discover_checkpointer_tables,
    has_only_empty_target_database,
    require_core_tables,
    run_pg_dump_to_file,
    run_postgres_container_tool,
    verify_backup_matches_source,
    verify_full_backup_archive,
)


def _target_database_exists(admin_connection, database_name: str) -> bool:
    return (
        admin_connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (database_name,)
        ).fetchone()
        is not None
    )


def _source_table_counts(connection, tables: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table_name in tables:
        count = connection.execute(
            sql.SQL("SELECT count(*) FROM {}.{}").format(
                sql.Identifier("public"), sql.Identifier(table_name)
            )
        ).fetchone()[0]
        counts[table_name] = count
    return counts


def migrate(
    backup: Path | None,
    *,
    execute: bool,
    writers_stopped: bool,
    skip_backup: bool,
    drop_source_tables: bool,
) -> dict[str, object]:
    source_url, target_url = configured_urls()
    if skip_backup and backup is not None:
        raise MigrationError("--skip-backup 不能与 --backup 同时使用。")
    if not skip_backup and (backup is None or not backup.is_file()):
        raise MigrationError("请提供全库备份，或明确传入 --skip-backup。")
    if backup is not None:
        verify_full_backup_archive(backup)

    with connect(source_url) as source:
        source_tables = discover_checkpointer_tables(source)
        require_core_tables(source_tables)
        source_counts = _source_table_counts(source, source_tables)

    with connect(source_url, database="postgres", autocommit=True) as admin:
        target_exists = _target_database_exists(admin, "checkpoint")
        if target_exists:
            with connect(target_url) as target:
                if not has_only_empty_target_database(target):
                    raise MigrationError(
                        "checkpoint 数据库已包含用户对象或数据；为避免覆盖，迁移已停止。"
                    )

        connection_count = active_source_connections(admin, "orionai")

        plan: dict[str, object] = {
            "source_database": "orionai",
            "target_database": "checkpoint",
            "target_will_be_created": not target_exists,
            "backup": str(backup.resolve()) if backup is not None else None,
            "backup_readable": backup is not None,
            "backup_skipped": skip_backup,
            "source_connections": connection_count,
            "tables": source_counts,
            "execute": execute,
            "backup_matches_current_source": None,
            "drop_source_tables": drop_source_tables,
        }
        if drop_source_tables and not execute:
            raise MigrationError("--drop-source-tables 只能与 --execute 一起使用。")
        if execute and not writers_stopped:
            raise MigrationError("正式迁移必须显式传入 --writers-stopped。")
        if execute and connection_count:
            raise MigrationError(
                f"业务数据库仍有 {connection_count} 个连接；"
                "请先停止 API 和所有 Checkpointer 写入方。"
            )
        if backup is not None and not connection_count:
            verify_backup_matches_source(backup, source_url)
            plan["backup_matches_current_source"] = True
        if not execute:
            return plan
        if backup is not None and plan["backup_matches_current_source"] is not True:
            verify_backup_matches_source(backup, source_url)
            plan["backup_matches_current_source"] = True

        if not target_exists:
            if not target_url.username:
                raise MigrationError("CHECKPOINT_DATABASE_URL 必须包含数据库所有者用户名。")
            admin.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier("checkpoint"), sql.Identifier(target_url.username)
                )
            )
            target_exists = True

    # pg_dump 和 pg_restore 直接使用现有 postgres:17 服务里的官方工具，
    # 避免误用宿主机上不同主版本的客户端，也不增加容器或修改 Volume。
    with tempfile.TemporaryDirectory(prefix="orionai-checkpointer-") as temporary_directory:
        archive = Path(temporary_directory) / "checkpointer.dump"
        dump_arguments = [
            "--format=custom",
            "--no-owner",
            "--no-acl",
            "--username",
            source_url.username or "orionai",
            "--dbname",
            "orionai",
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
                    target_url.username or "orionai",
                    "--dbname",
                    "checkpoint",
                    container_archive,
                ]
            )
        finally:
            run_postgres_container_tool(["rm", "-f", container_archive])

    with connect(source_url) as source, connect(target_url) as target:
        verified_tables = compare_databases(source, target)

    if drop_source_tables:
        with connect(source_url, database="postgres", autocommit=True) as admin:
            connection_count = active_source_connections(admin, "orionai")
            if connection_count:
                raise MigrationError(
                    f"校验成功，但 orionai 仍有 {connection_count} 个连接；旧表暂时保留。"
                )
        with connect(source_url) as source:
            with source.transaction():
                source.execute("SET LOCAL lock_timeout = '5s'")
                source.execute(
                    sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE NOWAIT").format(
                        sql.SQL(", ").join(
                            sql.Identifier("public", table_name) for table_name in source_tables
                        )
                    )
                )
                source.execute(
                    sql.SQL("DROP TABLE {}").format(
                        sql.SQL(", ").join(
                            sql.Identifier("public", table_name) for table_name in source_tables
                        )
                    )
                )
    return {
        **plan,
        "status": "complete",
        "tables": verified_tables,
        "source_tables_dropped": drop_source_tables,
        "source_tables_retained": not drop_source_tables,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backup",
        type=Path,
        help="迁移前生成并验证的 orionai 全库备份；如明确跳过，使用 --skip-backup。",
    )
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="按运维指示跳过全库备份；迁移归档仍只在临时目录中用于传输。",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="执行数据库创建与 Checkpointer 表迁移；默认仅检查并输出计划。",
    )
    parser.add_argument(
        "--writers-stopped",
        action="store_true",
        help="确认所有 API、Worker 和其他 Checkpointer 写入方均已停止。",
    )
    parser.add_argument(
        "--drop-source-tables",
        action="store_true",
        help="完整校验成功后删除 orionai 中的旧 Checkpointer 表。",
    )
    arguments = parser.parse_args()
    try:
        result = migrate(
            arguments.backup,
            execute=arguments.execute,
            writers_stopped=arguments.writers_stopped,
            skip_backup=arguments.skip_backup,
            drop_source_tables=arguments.drop_source_tables,
        )
    except MigrationError as error:
        print(f"迁移已停止：{error}", file=sys.stderr)
        print(
            "源数据库不会被清空；只有迁移校验成功后才会按参数删除旧 Checkpointer 表。",
            file=sys.stderr,
        )
        return 1
    except Exception as error:  # noqa: BLE001
        print(
            f"迁移失败（{type(error).__name__}）；源数据保留，目标数据库可能需要人工检查。",
            file=sys.stderr,
        )
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
