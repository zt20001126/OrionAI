# Checkpointer 独立数据库迁移手册

## 目标与边界

同一个 PostgreSQL Docker 服务继续承载两个数据库：`orionai` 保存业务数据，`checkpoint` 保存 LangGraph Checkpointer 数据。业务 Alembic 仍只读取 `DATABASE_URL`。迁移不会删除 `orionai` 中的 Checkpointer 表，也不会重建 Docker Volume。

迁移脚本在仓库根目录运行，使用现有 PostgreSQL 容器内与 PostgreSQL 17 同版本的 `pg_dump`、`pg_restore`。脚本不打印连接字符串或密码。请不要运行 `docker compose down -v`。

## 当前检查记录

2026-10-28 的检查结果：

- Compose 服务为 `backend`、`postgres` 和 `redis`；PostgreSQL 为 `postgres:17-alpine`，数据保存在 `postgres_data` Volume。
- 当前只存在 `orionai` 一个业务数据库，`checkpoint` 尚不存在。
- 当前 LangGraph Postgres Checkpointer 包版本为 3.2.0，使用异步 `AsyncPostgresSaver`。
- `orionai` 中发现 `checkpoints`、`checkpoint_blobs`、`checkpoint_writes` 和 `checkpoint_migrations` 四张表；记录数分别为 263、179、410、10。`checkpoints` 中有 13 个不同的 `thread_id`，迁移版本为 0–9。
- 全库备份 `backups/checkpointer_migration/orionai_full_20261028_093338.dump` 大小为 425,496 字节。PostgreSQL 17 的 `pg_restore --list` 可正常读取；该归档已恢复到隔离的临时验证库，12 张 public 表均成功恢复，备份时四张 Checkpointer 表的行数与源库一致。临时验证库已清理。
- 后续只读预检观察到源库增长为 268 checkpoints、182 blobs、420 writes、10 条 migrations。用户随后明确要求本次不生成备份，并在迁移验证成功后删除原有 Checkpointer 表。

本阶段没有创建 `checkpoint`、没有切换服务连接，也没有停止现有服务。数据库检查和完整恢复验证都未改动 `orionai`。

## 正式迁移步骤

本次按用户明确指示跳过全库备份。先停止所有可能写入 Checkpointer 的后端实例和 Worker。Redis 与 PostgreSQL 无需停止；如果有 Compose 外运行的 Worker，也必须一并停止。

```powershell
docker compose stop backend
python backend/scripts/migrate_checkpointer_db.py --skip-backup --execute --writers-stopped --drop-source-tables
```

迁移会使用 PostgreSQL 官方工具创建仅用于传输的临时表级归档，并在迁移结束后删除临时文件；不会生成或保留全库备份。

只有显式提供 `--execute --writers-stopped` 才会迁移。脚本要求 `orionai` 没有其他数据库连接、目标库不存在或完全没有用户对象。它动态识别 `checkpoint%` 表，使用 PostgreSQL 官方归档工具复制结构和数据，然后逐表比较列定义、主键/约束、索引、记录数及完整行内容摘要。提供 `--drop-source-tables` 时，只有全部数据校验通过才会锁定并删除 `orionai` 中的旧表；迁移或校验失败时旧表保留。

迁移命令成功后启动 backend：

```powershell
docker compose up --no-deps -d backend
docker compose ps
```

新入口会在 Checkpointer 数据库上执行 LangGraph 自身的 `setup()`。调用受 PostgreSQL advisory lock 串行保护；脚本本身不会在迁移校验前运行 `setup()`。连接生命周期与 FastAPI lifespan 相同，应用退出时会关闭异步连接。多轮会话及现有 `thread_id` 不做转换。

## 环境变量

数据库连接只使用 `.env` 中的 `DATABASE_URL` 和 `CHECKPOINT_DATABASE_URL` 两项。两项都写宿主机的 `localhost:5434` 地址；Settings 在 Docker 容器内将其转换为 Compose 服务地址 `postgres:5432`，宿主机脚本则继续使用 localhost。PostgreSQL 容器启动脚本从 `DATABASE_URL` 解析初始化用户和密码，因此不需要额外维护 `POSTGRES_USER`、`POSTGRES_PASSWORD` 或 `_DOCKER` 变量。密码请使用 URL 安全字符。`.env` 已被 Git 忽略，`.env.example` 只放密码占位符。

Compose 继续使用原有 `postgres_data` Volume，`POSTGRES_DB=orionai` 只描述首次初始化数据库。现有 Volume 上的 `checkpoint` 数据库由迁移脚本用 SQL 创建，不依赖修改 `POSTGRES_DB`。

## 回滚

旧表删除后，如需回滚，停止 backend 并使用 `rollback_checkpointer_db.py` 从 `checkpoint` 重新创建 `orionai` 中的 Checkpointer 表和当前数据；业务表保持不动。恢复完成后将 `.env` 中 `CHECKPOINT_DATABASE_URL` 的数据库名改为 `orionai` 并启动 backend。若结构校验失败，保持维护状态并保留 `checkpoint`。

## 验收范围与限制

迁移前后的数据库结构和数据可以由脚本完整验证。历史会话恢复、新会话写入、SSE、多轮对话及外部模型/工具调用需要在连接切换并启动应用后实际验证；本手册编写阶段尚未切换，因而没有声称这些运行时验收已通过。`pg_stat_activity` 的连接检查会在服务停止后再次确认 `orionai` 没有遗留连接。
