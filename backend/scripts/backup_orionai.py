"""使用现有 PostgreSQL 容器生成并完整恢复验证 orionai 全库备份。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

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
    require_core_tables,
    run_pg_dump_to_file,
    run_postgres_container_tool,
    safe_archive_path,
    verify_full_backup_archive,
)


def _public_table_counts(connection) -> dict[str, int]:
    table_rows = connection.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """
    ).fetchall()
    counts: dict[str, int] = {}
    for (table_name,) in table_rows:
        counts[table_name] = connection.execute(
            sql.SQL("SELECT count(*) FROM {}.{}").format(
                sql.Identifier("public"), sql.Identifier(table_name)
            )
        ).fetchone()[0]
    return counts


def create_verified_backup(*, writers_stopped: bool) -> dict[str, object]:
    if not writers_stopped:
        raise MigrationError("生成迁移前最终备份时必须显式确认 --writers-stopped。")

    source_url, _target_url = configured_urls()
    with connect(source_url) as source:
        source_tables = discover_checkpointer_tables(source)
        require_core_tables(source_tables)
        source_counts = _public_table_counts(source)
        source_catalog = catalog_snapshot(source, sorted(source_counts))

    with connect(source_url, database="postgres", autocommit=True) as admin:
        connection_count = active_source_connections(admin, "orionai")
        if connection_count:
            raise MigrationError(
                f"业务数据库仍有 {connection_count} 个连接；备份前请停止所有 API 和 Worker。"
            )

        backup_directory = BACKEND_ROOT.parent / "backups" / "checkpointer_migration"
        backup_path = safe_archive_path(backup_directory, "orionai_full")
        run_pg_dump_to_file(
            [
                "--format=custom",
                "--no-owner",
                "--no-acl",
                "--username",
                source_url.username or "orionai",
                "--dbname",
                "orionai",
            ],
            backup_path,
        )
        verify_full_backup_archive(backup_path)

        verify_database = f"orionai_backup_verify_{backup_path.stem.rsplit('_', 1)[-1]}"
        if admin.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (verify_database,)
        ).fetchone():
            raise MigrationError("备份验证数据库名称已存在；拒绝覆盖。")
        admin.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(verify_database),
                sql.Identifier(source_url.username or "orionai"),
            )
        )

        container_archive = copy_archive_into_postgres_container(backup_path)
        try:
            run_postgres_container_tool(
                [
                    "pg_restore",
                    "--exit-on-error",
                    "--no-owner",
                    "--no-acl",
                    "--username",
                    source_url.username or "orionai",
                    "--dbname",
                    verify_database,
                    container_archive,
                ]
            )
        finally:
            run_postgres_container_tool(["rm", "-f", container_archive])

        with (
            connect(source_url) as source,
            connect(source_url, database=verify_database) as restored,
        ):
            restored_counts = _public_table_counts(restored)
            restored_catalog = catalog_snapshot(restored, sorted(restored_counts))
            if source_counts != restored_counts:
                raise MigrationError("全库备份恢复后的表记录数与源库不一致。")
            if source_catalog != restored_catalog:
                raise MigrationError("全库备份恢复后的列、约束或索引定义与源库不一致。")
            checkpoint_results = compare_databases(source, restored)

        admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(verify_database)))

    return {
        "status": "verified",
        "backup": str(backup_path.resolve()),
        "bytes": backup_path.stat().st_size,
        "full_restore": True,
        "public_tables": len(source_counts),
        "checkpointer_tables": checkpoint_results,
        "restore_verification_database_removed": True,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--writers-stopped",
        action="store_true",
        help="确认所有 API、Worker 和其他数据库写入方均已停止。",
    )
    arguments = parser.parse_args()
    try:
        result = create_verified_backup(writers_stopped=arguments.writers_stopped)
    except MigrationError as error:
        print(f"备份未通过验证：{error}", file=sys.stderr)
        return 1
    except Exception as error:  # noqa: BLE001
        print(f"备份验证失败（{type(error).__name__}）；保留已生成文件供检查。", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
