# OrionAI 数据库表结构

## 概览

- **关系型数据库：** PostgreSQL 17。
- **业务表：** `users`、`conversations`、`messages`、`skills`、`user_skills`、`task_results`。
- **验证码和登录状态：** 保存在 Redis；聊天会话和消息保存在 PostgreSQL。
- **迁移：** Alembic。Docker 后端启动时自动执行迁移；本地可在 `backend/` 目录运行 `python -m alembic upgrade head`。

## `users` — 用户账号

| 字段            | PostgreSQL 类型 | 可空 | 默认值  | 键/约束 | 说明                                                     |
| --------------- | --------------- | ---- | ------- | ------- | -------------------------------------------------------- |
| `id`            | `BIGINT`        | 否   | 应用侧 Snowflake | 主键 | 用户 Snowflake ID，供业务外键引用                        |
| `account`       | `VARCHAR(254)`  | 否   | —       | 唯一    | 规范化后的邮箱：去除首尾空格并转为小写                   |
| `password_hash` | `VARCHAR(256)`  | 否   | —       | —       | 使用 scrypt 和随机盐生成的密码哈希，不保存明文密码       |
| `nickname`      | `VARCHAR(20)`   | 是   | `NULL`  | —       | 用户昵称；未设置时资料接口使用邮箱本地部分作为显示值       |
| `avatar_key`    | `VARCHAR(1024)` | 是   | `NULL`  | — | 用户头像在 OSS 中的对象键，用于安全管理和替换旧对象 |
| `avatar_url`    | `VARCHAR(2048)` | 是   | `NULL`  | — | 兼容既有自定义头像地址；新头像使用 `avatar_key`，不在此列重复保存 OSS URL |
| `created_at`    | `TIMESTAMPTZ`   | 否   | `now()` | —       | 账号创建时间；注册时设置                                 |
| `last_login_at` | `TIMESTAMPTZ`   | 是   | `NULL`  | —       | 最近一次成功认证时间；新账号注册时初始化，成功登录时更新 |

`id` 是由后端应用生成的 Snowflake 主键，`account` 保持唯一约束。创建用户时由 SQLAlchemy client-side default 赋值；PostgreSQL 中不再使用 Identity 序列。

迁移 `0009_add_user_profile.py` 增加可空昵称和默认头像 URL。迁移 `0010_add_user_avatar_key.py` 增加可空 OSS 对象键，移除头像 URL 列默认值，并将旧默认头像路径置空；既有自定义头像 URL、用户和其他资料均保留。新用户未设置头像时两个头像字段为空，资料接口返回项目静态默认图片。新上传头像仅将 OSS 对象键写入 `avatar_key`；响应中的公开 URL 按需生成。头像字节不写入数据库。

### 建表迁移

迁移文件：[`backend/migrations/versions/0001_create_users.py`](../../backend/migrations/versions/0001_create_users.py)、[`0002_add_users_identity_id.py`](../../backend/migrations/versions/0002_add_users_identity_id.py)、[`0004_snowflake_primary_ids.py`](../../backend/migrations/versions/0004_snowflake_primary_ids.py)、[`0009_add_user_profile.py`](../../backend/migrations/versions/0009_add_user_profile.py) 与 [`0010_add_user_avatar_key.py`](../../backend/migrations/versions/0010_add_user_avatar_key.py)。数据库另有 Alembic 管理的 `alembic_version` 迁移版本表，它不存放业务数据。

## `conversations` — 会话

| 字段 | PostgreSQL 类型 | 可空 | 默认值 | 键/约束 | 说明 |
|---|---|---|---|---|---|
| `id` | `BIGINT` | 否 | 应用侧 Snowflake | 主键 | 会话 Snowflake ID |
| `user_id` | `BIGINT` | 否 | — | 外键 `users.id`，删除级联 | 所属用户 |
| `skill_code` | `VARCHAR(100)` | 否 | `general_chat` | 外键 `skills.code`，删除限制 | 固定本会话使用的 Agent 技能；旧会话迁移为 `general_chat` |
| `title` | `VARCHAR(255)` | 是 | `NULL` | — | 根据首条用户消息自动生成的会话标题；功能上线前已有消息的会话可能仍为空 |
| `created_at` | `TIMESTAMPTZ` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `TIMESTAMPTZ` | 否 | `now()` | — | 最近更新时间，由业务层在交互时更新 |

索引：`(user_id, updated_at DESC)`。新会话只允许绑定当前用户已添加且仍发布的技能。Agent Checkpointer 线程 ID 包含技能代码，避免不同 Agent 共用状态。

## `messages` — 消息

| 字段 | PostgreSQL 类型 | 可空 | 默认值 | 键/约束 | 说明 |
|---|---|---|---|---|---|
| `id` | `BIGINT` | 否 | 应用侧 Snowflake | 主键 | 消息 Snowflake ID |
| `conversation_id` | `BIGINT` | 否 | — | 外键 `conversations.id`，删除级联 | 所属会话 |
| `role` | `VARCHAR(20)` | 否 | — | CHECK：`user` 或 `assistant` | 消息角色 |
| `content` | `JSONB` | 否 | — | — | `{"parts":[...]}` 结构化消息内容 |
| `created_at` | `TIMESTAMPTZ` | 否 | `now()` | — | 创建时间 |

索引：`(conversation_id, id)`。文本使用 `{"type":"text","text":"..."}` part；等待用户选择的助手消息使用 `{"type":"question","questions":[...]}` part；生成图片的助手消息使用 `image_result` part 保存结果 ID、状态和受登录保护的 API 路径。数据库不增加消息内容列或二进制图片列。

会话与消息迁移：[`0003_create_conversations_and_messages.py`](../../backend/migrations/versions/0003_create_conversations_and_messages.py)。`0004_snowflake_primary_ids.py` 将现有用户、会话和消息主键重新编号为 Snowflake ID，并同步更新业务外键；如果 LangGraph Checkpointer 表已存在，也会同步更新本项目格式的会话 `thread_id`。[`0008_add_image_agent.py`](../../backend/migrations/versions/0008_add_image_agent.py) 为已有会话回填 `general_chat` 并增加技能外键。升级或回滚 `0004` 都会改变这些表中的 ID，客户端应在迁移后重新获取 ID；执行迁移前应备份数据库。

Snowflake 生成器由 `SNOWFLAKE_WORKER_ID` 区分并发 backend 实例，范围为 `0`–`1022`，默认值为 `1`。同一时刻运行多个实例时必须为每个实例设置不同值，否则可能生成重复 ID。运行迁移使用独立保留的 worker ID `1023`。

## `skills` — 平台技能

| 字段 | PostgreSQL 类型 | 可空 | 默认值 | 键/约束 | 说明 |
|---|---|---|---|---|---|
| `id` | `BIGINT` | 否 | 应用侧 Snowflake | 主键 | 技能 Snowflake ID |
| `code` | `VARCHAR(100)` | 否 | — | 唯一 | 稳定的技能代码 |
| `name` | `VARCHAR(100)` | 否 | — | — | 技能名称 |
| `description` | `TEXT` | 是 | `NULL` | — | 技能说明 |
| `type` | `VARCHAR(20)` | 否 | — | CHECK：`agent` 或 `tool` | 技能类型 |
| `status` | `VARCHAR(20)` | 否 | `published` | CHECK：`published` 或 `disabled` | 技能发布状态 |
| `created_at` | `TIMESTAMPTZ` | 否 | `now()` | — | 创建时间 |

索引：`(status, type, created_at)`。技能 ID 由应用侧 Snowflake 生成；手工执行 SQL 插入时需要显式提供 Snowflake `id`。应用启动时幂等注册 `general_chat` 和已发布的 `image_agent`（名称“图片助手”）；技能记录是技能市场数据源。

## `user_skills` — 用户技能关联

| 字段 | PostgreSQL 类型 | 可空 | 默认值 | 键/约束 | 说明 |
|---|---|---|---|---|---|
| `id` | `BIGINT` | 否 | 应用侧 Snowflake | 主键 | 关联记录 Snowflake ID |
| `user_id` | `BIGINT` | 否 | — | 外键 `users.id`，删除级联 | 用户 ID |
| `skill_id` | `BIGINT` | 否 | — | 外键 `skills.id`，删除级联 | 技能 Snowflake ID |
| `skill_name` | `VARCHAR(100)` | 否 | — | — | 添加时保存的技能名称快照 |
| `created_at` | `TIMESTAMPTZ` | 否 | `now()` | — | 添加时间 |

唯一约束：`(user_id, skill_id)`；索引：`(user_id, created_at)`。所有业务表主键及引用主键的外键统一使用 Snowflake `BIGINT`。`0006_snowflake_skill_ids.py` 将技能及关联表中已有 UUID 重映射为 Snowflake ID，并幂等注册 `resume_assistant` 和 `literature_assistant`；升级后客户端应重新获取技能 ID。

LangGraph PostgreSQL Checkpointer 使用其依赖管理的内部表保存图执行状态；这些表不属于业务表，也不通过业务 Alembic 迁移维护。应用首次启动会调用 Checkpointer `setup()`，数据库账号需要具备相应建表/升级权限。

## `task_results` — 技能任务结果

| 字段 | PostgreSQL 类型 | 可空 | 默认值 | 键/约束 | 说明 |
|---|---|---|---|---|---|
| `id` | `BIGINT` | 否 | 应用侧 Snowflake | 主键 | 任务结果唯一标识 |
| `user_id` | `BIGINT` | 否 | — | 外键 `users.id`，删除级联 | 所属用户 ID |
| `conversation_id` | `BIGINT` | 是 | `NULL` | 外键 `conversations.id`，删除时设为 NULL | 关联会话 ID |
| `skill_code` | `VARCHAR(100)` | 否 | — | 外键 `skills.code`，删除限制 | 对应技能代码 |
| `result` | `JSONB` | 否 | — | — | 技能执行产生的结果；图片助手在其中保存运行状态及 OSS 结果元数据 |
| `created_at` | `TIMESTAMPTZ` | 否 | `now()` | — | 创建时间 |

索引：`(user_id, created_at)`、`(conversation_id)`、`(skill_code)`。所有主键和用户/会话外键沿用项目 BIGINT Snowflake ID。图片字节只保存在私有 OSS，不存入 PostgreSQL；对话消息只保留结果 ID 和授权接口路径。图片读取需校验当前用户与结果所有权。

## Redis 认证状态

以下状态由 [`backend/app/infrastructure/redis/auth_state.py`](../../backend/app/infrastructure/redis/auth_state.py) 管理，不属于 PostgreSQL 表。

| 状态     | Redis 键格式                                        | 保存内容                   | TTL                    |
| -------- | --------------------------------------------------- | -------------------------- | ---------------------- |
| 验证码   | `orionai:auth:code:{purpose}:{sha256(account)}`     | HMAC-SHA256 摘要、失败次数 | 默认 600 秒；修改密码 300 秒 |
| 重发冷却 | `orionai:auth:cooldown:{purpose}:{sha256(account)}` | 冷却标记                   | 60 秒                  |
| 登录会话 | `orionai:auth:session:{sha256(cookie_token)}`       | 规范化账号、密码哈希指纹   | 默认 604800 秒（7 天） |

验证码摘要使用 `HMAC-SHA256(AUTH_CODE_PEPPER, purpose + ":" + account + ":" + code)` 计算。Redis 不保存原始验证码；会话键使用 Cookie 令牌的 SHA-256 摘要，密码更新后通过密码哈希指纹使旧会话失效。验证码按用途和规范化账号隔离，验证错误最多允许 5 次。
