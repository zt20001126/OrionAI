# OrionAI 数据库表结构

## 概览

- **关系型数据库：** PostgreSQL 17。
- **业务表：** `users`。
- **验证码和会话：** 保存在 Redis，不建立验证码表或会话表。
- **迁移：** Alembic。Docker 后端启动时自动执行迁移；本地可在 `backend/` 目录运行 `python -m alembic upgrade head`。

## `users` — 用户账号

| 字段            | PostgreSQL 类型 | 可空 | 默认值  | 键/约束 | 说明                                                     |
| --------------- | --------------- | ---- | ------- | ------- | -------------------------------------------------------- |
| `account`       | `VARCHAR(254)`  | 否   | —       | 主键    | 规范化后的邮箱：去除首尾空格并转为小写                   |
| `password_hash` | `VARCHAR(256)`  | 否   | —       | —       | 使用 scrypt 和随机盐生成的密码哈希，不保存明文密码       |
| `created_at`    | `TIMESTAMPTZ`   | 否   | `now()` | —       | 账号创建时间；注册时设置                                 |
| `last_login_at` | `TIMESTAMPTZ`   | 是   | `NULL`  | —       | 最近一次成功认证时间；新账号注册时初始化，成功登录时更新 |

`account` 是主键，因此同时保证唯一；当前没有其他业务索引或外键。

### 建表迁移

迁移文件：[`backend/migrations/versions/0001_create_users.py`](../../backend/migrations/versions/0001_create_users.py)。数据库另有 Alembic 管理的 `alembic_version` 迁移版本表，它不存放业务数据。

## Redis 认证状态

以下状态由 [`backend/app/infrastructure/redis/auth_state.py`](../../backend/app/infrastructure/redis/auth_state.py) 管理，不属于 PostgreSQL 表。

| 状态     | Redis 键格式                                        | 保存内容                   | TTL                    |
| -------- | --------------------------------------------------- | -------------------------- | ---------------------- |
| 验证码   | `orionai:auth:code:{purpose}:{sha256(account)}`     | HMAC-SHA256 摘要、失败次数 | 600 秒                 |
| 重发冷却 | `orionai:auth:cooldown:{purpose}:{sha256(account)}` | 冷却标记                   | 60 秒                  |
| 登录会话 | `orionai:auth:session:{sha256(cookie_token)}`       | 规范化账号、密码哈希指纹   | 默认 604800 秒（7 天） |

验证码摘要使用 `HMAC-SHA256(AUTH_CODE_PEPPER, purpose + ":" + account + ":" + code)` 计算。Redis 不保存原始验证码；会话键使用 Cookie 令牌的 SHA-256 摘要，密码更新后通过密码哈希指纹使旧会话失效。
