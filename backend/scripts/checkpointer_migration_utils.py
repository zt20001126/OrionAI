"""Checkpointer 迁移脚本共用的连接、目录检查和完整性校验工具。"""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
import uuid
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from sqlalchemy.engine import URL, make_url

from app.core.config import get_settings

CHECKPOINTER_CORE_TABLES = frozenset(
    {"checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations"}
)
COMPOSE_ROOT = Path(__file__).resolve().parents[2]


class MigrationError(RuntimeError):
    """迁移前置条件或完整性校验不满足。"""


def configured_urls() -> tuple[URL, URL]:
    """读取并校验业务库与 Checkpointer 库连接，不输出任何凭据。"""

    settings = get_settings()
    if not settings.checkpoint_database_url.strip():
        raise MigrationError("必须设置 CHECKPOINT_DATABASE_URL。")
    source_url = make_url(settings.database_url)
    target_url = make_url(settings.checkpoint_database_url)
    if source_url.drivername not in {"postgresql", "postgresql+psycopg"}:
        raise MigrationError("DATABASE_URL 必须使用 PostgreSQL psycopg。")
    if target_url.drivername not in {"postgresql", "postgresql+psycopg"}:
        raise MigrationError("CHECKPOINT_DATABASE_URL 必须使用 PostgreSQL psycopg。")
    if source_url.database != "orionai":
        raise MigrationError("DATABASE_URL 必须指向业务数据库 orionai。")
    if target_url.database != "checkpoint":
        raise MigrationError("CHECKPOINT_DATABASE_URL 必须指向 checkpoint 数据库。")
    return source_url.set(drivername="postgresql"), target_url.set(drivername="postgresql")


def connect(
    url: URL, *, database: str | None = None, autocommit: bool = False
) -> psycopg.Connection[Any]:
    """使用 psycopg 连接目标数据库或 PostgreSQL 管理数据库。"""

    connection_url = url.set(database=database) if database is not None else url
    dsn = connection_url.render_as_string(hide_password=False)
    return psycopg.connect(dsn, autocommit=autocommit)


def discover_checkpointer_tables(connection: psycopg.Connection[Any]) -> list[str]:
    """识别 public schema 下所有 LangGraph Checkpointer 专属表。"""

    rows = connection.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
          AND table_name LIKE 'checkpoint%'
        ORDER BY table_name
        """
    ).fetchall()
    return [row[0] for row in rows]


def require_core_tables(tables: list[str]) -> None:
    missing = sorted(CHECKPOINTER_CORE_TABLES.difference(tables))
    if missing:
        raise MigrationError(f"源数据库缺少 Checkpointer 核心表：{', '.join(missing)}。")


def catalog_snapshot(
    connection: psycopg.Connection[Any], tables: list[str]
) -> dict[str, list[tuple[Any, ...]]]:
    """读取列、约束和索引定义，比较数据迁移前后的结构。"""

    columns = connection.execute(
        """
        SELECT table_name, ordinal_position, column_name, data_type, udt_name,
               is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = ANY(%s)
        ORDER BY table_name, ordinal_position
        """,
        (tables,),
    ).fetchall()
    constraints = connection.execute(
        """
        SELECT relation.relname, constraint_row.conname, constraint_row.contype,
               pg_get_constraintdef(constraint_row.oid)
        FROM pg_constraint AS constraint_row
        JOIN pg_class AS relation ON relation.oid = constraint_row.conrelid
        JOIN pg_namespace AS schema_row ON schema_row.oid = relation.relnamespace
        WHERE schema_row.nspname = 'public' AND relation.relname = ANY(%s)
        ORDER BY relation.relname, constraint_row.conname
        """,
        (tables,),
    ).fetchall()
    indexes = connection.execute(
        """
        SELECT tablename, indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public' AND tablename = ANY(%s)
        ORDER BY tablename, indexname
        """,
        (tables,),
    ).fetchall()
    return {"columns": columns, "constraints": constraints, "indexes": indexes}


def _normalize_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"__bytes_base64__": base64.b64encode(value).decode("ascii")}
    if isinstance(value, Decimal):
        return {"__decimal__": str(value)}
    if isinstance(value, (datetime, date, time)):
        return {"__datetime__": value.isoformat()}
    if isinstance(value, UUID):
        return {"__uuid__": str(value)}
    if isinstance(value, dict):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return {"__string__": str(value)}


def primary_key_columns(connection: psycopg.Connection[Any], table_name: str) -> list[str]:
    """按主键定义顺序返回列名。"""

    rows = connection.execute(
        """
        SELECT attribute.attname
        FROM pg_index AS index_row
        JOIN pg_class AS relation ON relation.oid = index_row.indrelid
        JOIN pg_namespace AS schema_row ON schema_row.oid = relation.relnamespace
        JOIN LATERAL unnest(index_row.indkey) WITH ORDINALITY
            AS key_column(attnum, ordinal_position) ON true
        JOIN pg_attribute AS attribute
            ON attribute.attrelid = relation.oid AND attribute.attnum = key_column.attnum
        WHERE schema_row.nspname = 'public'
          AND relation.relname = %s
          AND index_row.indisprimary
        ORDER BY key_column.ordinal_position
        """,
        (table_name,),
    ).fetchall()
    return [row[0] for row in rows]


def table_content_digest(connection: psycopg.Connection[Any], table_name: str) -> tuple[int, str]:
    """按主键顺序计算整表内容摘要，覆盖 JSON/JSONB 与二进制列。"""

    primary_key = primary_key_columns(connection, table_name)
    if not primary_key:
        raise MigrationError(f"表 public.{table_name} 没有主键，无法安全地比较内容。")

    query = sql.SQL("SELECT * FROM {}.{} ORDER BY {}").format(
        sql.Identifier("public"),
        sql.Identifier(table_name),
        sql.SQL(", ").join(sql.Identifier(column) for column in primary_key),
    )
    digest = hashlib.sha256()
    row_count = 0
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query)
        for row in cursor:
            encoded = json.dumps(
                _normalize_value(row),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            digest.update(encoded)
            digest.update(b"\n")
            row_count += 1
    return row_count, digest.hexdigest()


def compare_databases(
    source: psycopg.Connection[Any], target: psycopg.Connection[Any]
) -> list[dict[str, Any]]:
    """验证 Checkpointer 表集合、结构、约束、索引和逐行内容摘要。"""

    source_tables = discover_checkpointer_tables(source)
    target_tables = discover_checkpointer_tables(target)
    require_core_tables(source_tables)
    if source_tables != target_tables:
        missing = sorted(set(source_tables).difference(target_tables))
        extra = sorted(set(target_tables).difference(source_tables))
        raise MigrationError(f"目标表集合不一致；缺失：{missing or '无'}；额外：{extra or '无'}。")

    source_catalog = catalog_snapshot(source, source_tables)
    target_catalog = catalog_snapshot(target, target_tables)
    if source_catalog != target_catalog:
        differences = [
            section
            for section in source_catalog
            if source_catalog[section] != target_catalog[section]
        ]
        raise MigrationError(f"源和目标数据库结构不一致：{', '.join(differences)}。")

    results: list[dict[str, Any]] = []
    mismatched_tables: list[str] = []
    for table_name in source_tables:
        source_count, source_digest = table_content_digest(source, table_name)
        target_count, target_digest = table_content_digest(target, table_name)
        matches = source_count == target_count and source_digest == target_digest
        if not matches:
            mismatched_tables.append(table_name)
        results.append(
            {
                "table": table_name,
                "source_rows": source_count,
                "target_rows": target_count,
                "sha256_match": source_digest == target_digest,
                "match": matches,
            }
        )
    if mismatched_tables:
        raise MigrationError(f"源和目标数据库记录内容不一致：{', '.join(mismatched_tables)}。")
    return results


def copy_archive_into_postgres_container(archive: Path) -> str:
    """将本地 pg_dump 归档复制到现有 PostgreSQL 容器，不创建新容器。"""

    container_path = f"/tmp/orionai-checkpointer-{uuid.uuid4().hex}.dump"
    result = subprocess.run(
        ["docker", "compose", "cp", str(archive.resolve()), f"postgres:{container_path}"],
        cwd=COMPOSE_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise MigrationError("无法将迁移归档复制到现有 PostgreSQL 容器。")
    return container_path


def run_postgres_container_tool(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    """通过现有 postgres 服务调用同版本官方 pg_dump/pg_restore 工具。"""

    if shutil.which("docker") is None:
        raise MigrationError("找不到 Docker CLI；请在 Docker Compose 项目根目录运行脚本。")
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", *arguments],
        cwd=COMPOSE_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise MigrationError(
            f"PostgreSQL 工具执行失败（退出码 {result.returncode}）；"
            "详细错误已省略以避免泄露连接信息。"
        )
    return result


def run_pg_dump_to_file(arguments: list[str], archive: Path) -> None:
    """将现有 PostgreSQL 容器的 pg_dump 二进制输出保存至本地文件。"""

    if shutil.which("docker") is None:
        raise MigrationError("找不到 Docker CLI；无法调用 PostgreSQL 17 的 pg_dump。")
    command = ["docker", "compose", "exec", "-T", "postgres", "pg_dump", *arguments]
    with archive.open("wb") as archive_file:
        result = subprocess.run(
            command,
            cwd=COMPOSE_ROOT,
            stdout=archive_file,
            stderr=subprocess.PIPE,
            check=False,
        )
    if result.returncode or not archive.exists() or archive.stat().st_size == 0:
        raise MigrationError(f"pg_dump 执行失败（退出码 {result.returncode}）；未能生成有效归档。")


def verify_full_backup_archive(archive: Path) -> None:
    """确认完整数据库备份归档可读取且包含全部 Checkpointer 表。"""

    if not archive.is_file() or archive.stat().st_size == 0:
        raise MigrationError("备份文件不存在或为空。")
    container_archive = copy_archive_into_postgres_container(archive)
    try:
        output = run_postgres_container_tool(["pg_restore", "--list", container_archive]).stdout
        missing = [table for table in sorted(CHECKPOINTER_CORE_TABLES) if table not in output]
        if missing:
            raise MigrationError(f"备份归档未包含全部 Checkpointer 核心表：{', '.join(missing)}。")
    finally:
        run_postgres_container_tool(["rm", "-f", container_archive])


def verify_backup_matches_source(archive: Path, source_url: URL) -> list[dict[str, Any]]:
    """完整恢复备份到隔离临时库，并逐行确认 Checkpointer 快照与源库一致。"""

    container_archive = copy_archive_into_postgres_container(archive)
    verify_database = f"orionai_backupcheck_{uuid.uuid4().hex[:12]}"
    try:
        with connect(source_url, database="postgres", autocommit=True) as admin:
            if admin.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (verify_database,)
            ).fetchone():
                raise MigrationError("临时备份验证库名称已存在，拒绝覆盖。")
            admin.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(verify_database),
                    sql.Identifier(source_url.username or "orionai"),
                )
            )
            restore_succeeded = False
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
                restore_succeeded = True
                with (
                    connect(source_url) as source,
                    connect(source_url, database=verify_database) as restored,
                ):
                    results = compare_databases(source, restored)
            except MigrationError:
                if restore_succeeded:
                    admin.execute(
                        sql.SQL("DROP DATABASE {}").format(sql.Identifier(verify_database))
                    )
                raise
            except Exception:
                # 恢复失败时保留临时库，方便检查具体失败对象。
                raise
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(verify_database)))
    finally:
        run_postgres_container_tool(["rm", "-f", container_archive])

    return results


def has_only_empty_target_database(connection: psycopg.Connection[Any]) -> bool:
    """目标数据库没有任何用户表、视图或序列时才允许迁移写入。"""

    object_count = connection.execute(
        """
        SELECT count(*)
        FROM pg_class AS relation
        JOIN pg_namespace AS schema_row ON schema_row.oid = relation.relnamespace
        WHERE schema_row.nspname NOT IN ('pg_catalog', 'information_schema')
          AND schema_row.nspname NOT LIKE 'pg_toast%'
          AND relation.relkind IN ('r', 'p', 'v', 'm', 'S')
        """
    ).fetchone()[0]
    return object_count == 0


def active_source_connections(
    admin_connection: psycopg.Connection[Any], source_database: str
) -> int:
    """检查是否仍有连接停留在业务数据库，作为停止写入服务的安全门。"""

    return admin_connection.execute(
        "SELECT count(*) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
        (source_database,),
    ).fetchone()[0]


def safe_archive_path(directory: Path, prefix: str) -> Path:
    """生成不覆盖现有文件的时间戳备份路径。"""

    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{prefix}_{stamp}.dump"
    if path.exists():
        raise MigrationError("备份路径已存在，拒绝覆盖。")
    return path
