# OrionAI 数据库表结构

## 概览

- **关系型数据库：** PostgreSQL 17。
- **业务表：** `users`、`conversations`、`messages`。
- **验证码和登录状态：** 保存在 Redis；聊天会话和消息保存在 PostgreSQL。
- **迁移：** Alembic。Docker 后端启动时自动执行迁移；本地可在 `backend/` 目录运行 `python -m alembic upgrade head`。

## `users` — 用户账号

| 字段            | PostgreSQL 类型 | 可空 | 默认值  | 键/约束 | 说明                                                     |
| --------------- | --------------- | ---- | ------- | ------- | -------------------------------------------------------- |
| `id`            | `BIGINT`        | 否   | 应用侧 Snowflake | 主键 | 用户 Snowflake ID，供业务外键引用                        |
| `account`       | `VARCHAR(254)`  | 否   | —       | 唯一    | 规范化后的邮箱：去除首尾空格并转为小写                   |
| `password_hash` | `VARCHAR(256)`  | 否   | —       | —       | 使用 scrypt 和随机盐生成的密码哈希，不保存明文密码       |
| `created_at`    | `TIMESTAMPTZ`   | 否   | `now()` | —       | 账号创建时间；注册时设置                                 |
| `last_login_at` | `TIMESTAMPTZ`   | 是   | `NULL`  | —       | 最近一次成功认证时间；新账号注册时初始化，成功登录时更新 |

`id` 是由后端应用生成的 Snowflake 主键，`account` 保持唯一约束。创建用户时由 SQLAlchemy client-side default 赋值；PostgreSQL 中不再使用 Identity 序列。

### 建表迁移

迁移文件：[`backend/migrations/versions/0001_create_users.py`](../../backend/migrations/versions/0001_create_users.py)、[`0002_add_users_identity_id.py`](../../backend/migrations/versions/0002_add_users_identity_id.py) 与 [`0004_snowflake_primary_ids.py`](../../backend/migrations/versions/0004_snowflake_primary_ids.py)。数据库另有 Alembic 管理的 `alembic_version` 迁移版本表，它不存放业务数据。

## `conversations` — 会话

| 字段 | PostgreSQL 类型 | 可空 | 默认值 | 键/约束 | 说明 |
|---|---|---|---|---|---|
| `id` | `BIGINT` | 否 | 应用侧 Snowflake | 主键 | 会话 Snowflake ID |
| `user_id` | `BIGINT` | 否 | — | 外键 `users.id`，删除级联 | 所属用户 |
| `title` | `VARCHAR(255)` | 是 | `NULL` | — | 会话标题，首版不自动生成 |
| `created_at` | `TIMESTAMPTZ` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `TIMESTAMPTZ` | 否 | `now()` | — | 最近更新时间，由业务层在交互时更新 |

索引：`(user_id, updated_at DESC)`。

## `messages` — 消息

| 字段 | PostgreSQL 类型 | 可空 | 默认值 | 键/约束 | 说明 |
|---|---|---|---|---|---|
| `id` | `BIGINT` | 否 | 应用侧 Snowflake | 主键 | 消息 Snowflake ID |
| `conversation_id` | `BIGINT` | 否 | — | 外键 `conversations.id`，删除级联 | 所属会话 |
| `role` | `VARCHAR(20)` | 否 | — | CHECK：`user` 或 `assistant` | 消息角色 |
| `content` | `JSONB` | 否 | — | — | `{"parts":[...]}` 结构化消息内容 |
| `created_at` | `TIMESTAMPTZ` | 否 | `now()` | — | 创建时间 |

索引：`(conversation_id, id)`。文本使用 `{"type":"text","text":"..."}` part；等待用户选择的助手消息使用 `{"type":"question","questions":[...]}` part。数据库不增加 JSON Schema 校验或额外内容表。

会话与消息迁移：[`0003_create_conversations_and_messages.py`](../../backend/migrations/versions/0003_create_conversations_and_messages.py)。`0004_snowflake_primary_ids.py` 将现有用户、会话和消息主键重新编号为 Snowflake ID，并同步更新业务外键；如果 LangGraph Checkpointer 表已存在，也会同步更新本项目格式的会话 `thread_id`。升级或回滚都会改变这些表中的 ID，客户端应在迁移后重新获取 ID；执行迁移前应备份数据库。

Snowflake 生成器由 `SNOWFLAKE_WORKER_ID` 区分并发 backend 实例，范围为 `0`–`1022`，默认值为 `1`。同一时刻运行多个实例时必须为每个实例设置不同值，否则可能生成重复 ID。运行迁移使用独立保留的 worker ID `1023`。

LangGraph PostgreSQL Checkpointer 使用其依赖管理的内部表保存图执行状态；这些表不属于业务表，也不通过业务 Alembic 迁移维护。应用首次启动会调用 Checkpointer `setup()`，数据库账号需要具备相应建表/升级权限。

## Redis 认证状态

以下状态由 [`backend/app/infrastructure/redis/auth_state.py`](../../backend/app/infrastructure/redis/auth_state.py) 管理，不属于 PostgreSQL 表。

| 状态     | Redis 键格式                                        | 保存内容                   | TTL                    |
| -------- | --------------------------------------------------- | -------------------------- | ---------------------- |
| 验证码   | `orionai:auth:code:{purpose}:{sha256(account)}`     | HMAC-SHA256 摘要、失败次数 | 600 秒                 |
| 重发冷却 | `orionai:auth:cooldown:{purpose}:{sha256(account)}` | 冷却标记                   | 60 秒                  |
| 登录会话 | `orionai:auth:session:{sha256(cookie_token)}`       | 规范化账号、密码哈希指纹   | 默认 604800 秒（7 天） |

验证码摘要使用 `HMAC-SHA256(AUTH_CODE_PEPPER, purpose + ":" + account + ":" + code)` 计算。Redis 不保存原始验证码；会话键使用 Cookie 令牌的 SHA-256 摘要，密码更新后通过密码哈希指纹使旧会话失效。
