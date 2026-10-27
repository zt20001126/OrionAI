# OrionAI API 接口文档

## 通用约定

- **默认前缀：** `/api`
- **请求与响应：** JSON；请求体不接受未定义字段。
- **Snowflake ID：** 会话、消息和技能响应中的 ID 以十进制字符串返回，避免 JavaScript 整数精度损失；技能添加请求的 `skill_id` 也使用十进制字符串，路径参数使用十进制 ID。
- **邮箱：** 去除首尾空格并转为小写，最多 254 个字符。
- **密码：** 注册和重置为 8–128 个字符；登录为 1–128 个字符。
- **认证：** 登录或注册成功后，服务端设置 `orionai_session` Cookie。Cookie 为 `HttpOnly`、`SameSite=Lax`、`Path=/`，默认有效 7 天；production 环境默认启用 `Secure`。客户端请求需携带 Cookie。
- **来源校验：** `POST` 状态变更接口若收到 `Origin`，其主机必须与请求 `Host` 一致，否则返回 `403`。
- **错误格式：** 业务错误为 `{"detail":"错误说明"}`；请求字段校验失败返回 FastAPI 的 `422` 校验详情。

## 接口列表

| 方法   | 路径                       | 用途                     | 认证                           |
| ------ | -------------------------- | ------------------------ | ------------------------------ |
| `GET`  | `/api/health`              | 检查 API 服务            | 否                             |
| `POST` | `/api/auth/email-codes`    | 请求注册或重置密码验证码 | 否                             |
| `POST` | `/api/auth/register`       | 验证邮箱并创建账号       | 否                             |
| `POST` | `/api/auth/login`          | 邮箱和密码登录           | 否                             |
| `GET`  | `/api/auth/session`        | 检查并恢复当前会话       | Cookie                         |
| `POST` | `/api/auth/logout`         | 撤销当前会话             | Cookie（无 Cookie 时也可调用） |
| `POST` | `/api/auth/password-reset` | 验证邮箱并更新密码       | 否                             |
| `POST` | `/api/conversations` | 创建当前用户的空会话 | Cookie |
| `GET` | `/api/conversations` | 列出当前用户会话 | Cookie |
| `GET` | `/api/conversations/{id}/messages` | 分页读取会话消息 | Cookie |
| `POST` | `/api/conversations/{id}/messages` | 发送文本并获取回答或题卡 | Cookie |
| `POST` | `/api/conversations/{id}/answers` | 提交题卡选项并恢复对话 | Cookie |

## 接口详情

### `GET /api/health`

无需参数。健康时返回 `200`：

```json
{
  "status": "ok",
  "service": "OrionAI"
}
```

### `POST /api/auth/email-codes`

请求验证码。验证码为 6 位数字，有效期 10 分钟；同一邮箱、同一用途 60 秒内不可重发，最多输错 5 次。用途之间相互独立。

```json
{
  "email": "person@example.com",
  "purpose": "register"
}
```

`purpose` 只能是 `register` 或 `password_reset`。成功返回 `202`：

```json
{ "message": "验证码已发送。" }
```

重置密码用途对未知邮箱返回 `202` 和通用提示 `如果邮箱已注册，验证码将发送到邮箱。`，不会发送邮件；已注册邮箱正常发送时返回相同提示。已注册邮箱遇到邮件或 Redis 服务错误时返回 `503`。

错误：`409` 注册邮箱已存在；`429` 重发过于频繁；`503` 数据库、pepper、Redis 或邮件服务不可用。

### `POST /api/auth/register`

```json
{
  "email": "person@example.com",
  "code": "123456",
  "password": "example-password",
  "password_confirmation": "example-password"
}
```

密码必须为 8–128 个字符，两次密码必须一致。成功返回 `200`，同时设置会话 Cookie：

```json
{ "account": "person@example.com" }
```

错误：`400` 验证码无效或过期；`409` 邮箱已注册；`422` 请求字段无效；`503` 数据库或认证状态服务不可用。

### `POST /api/auth/login`

```json
{
  "email": "person@example.com",
  "password": "example-password"
}
```

成功返回 `200`，同时设置会话 Cookie，响应只包含规范化后的账号：

```json
{ "account": "person@example.com" }
```

账号不存在和密码错误均返回相同的 `401` 响应：`{"detail":"邮箱或密码错误。"}`。

当前没有独立的登录失败次数或 IP 限流。

### `GET /api/auth/session`

通过 Cookie 检查会话。有效会话返回 `200`：

```json
{ "authenticated": true, "account": "person@example.com" }
```

没有会话或会话无效时返回 `200`：

```json
{ "authenticated": false, "account": null }
```

无效 Cookie 会被清除。会话状态服务不可用时返回 `503`。

### `POST /api/auth/logout`

无需请求体。撤销当前 Redis 会话并清除 Cookie，返回 `200`：

```json
{ "message": "已退出登录。" }
```

当前会话需要访问 Redis；Redis 不可用且请求带有会话 Cookie 时返回 `503`。

### `POST /api/auth/password-reset`

```json
{
  "email": "person@example.com",
  "code": "123456",
  "new_password": "new-example-password",
  "password_confirmation": "new-example-password"
}
```

密码长度为 8–128 个字符，两次密码必须一致。成功返回 `200`：

```json
{ "message": "密码已更新，请使用新密码登录。" }
```

密码更新后，先前签发的会话失效。错误：`400` 验证码无效或过期；`422` 请求字段无效；`503` 数据库或认证状态服务不可用。

### 会话与消息 API

以下接口均要求有效的 `orionai_session` Cookie。写入接口沿用 `Origin` 与 `Host` 同源校验。会话查询始终限制在当前用户范围；不存在或不属于当前用户的会话统一返回 `404`。列表接口支持 `limit`（默认 50，范围 1–100）和 `offset`（默认 0）。

`POST /api/conversations` 创建空会话，成功返回 `201`，字段包含字符串形式的 Snowflake `id`、`title`、`created_at`、`updated_at`；首条用户消息发送前标题为空；首条用户消息提交后，根据其内容自动生成标题；模型失败或超时时使用首条消息的简短摘要。`GET /api/conversations` 返回 `items`、`limit`、`offset`，会话按 `updated_at DESC` 排列。

`GET /api/conversations/{id}/messages` 按消息 `id` 升序返回 `items`。消息内容使用 JSON `parts` 数组，例如：

```json
{"parts":[{"type":"text","text":"你好"}]}
```

发送消息时请求 `POST /api/conversations/{id}/messages`，JSON 请求体为 `{"message":"请帮我写一份说明"}`。返回 `status` 为 `completed` 或 `waiting`，以及本轮助手 `message`。普通回答的内容部分为 `type: "text"`；等待选择时为 `type: "question"` 并包含结构化 `questions`。如果当前会话正在等待题卡答案，发送新消息返回 `409`。

标题生成是消息发送流程的内部行为，不改变请求或响应结构；只有首条用户消息用于命名，后续消息和题卡答案不会覆盖标题。

通过 `POST /api/conversations/{id}/answers` 提交选择并恢复同一对话线程，请求示例：

```json
{"answers":{"style":"简洁"}}
```

答案题目 ID 集合必须与当前题卡完全相同，选项值必须为该题的有效标签；无待答题卡返回 `409`，答案不匹配返回 `422`。模型或 Checkpointer 暂不可用时返回 `503`，错误文本不会包含底层服务异常。

## 实现位置

- 路由与 Cookie：[`backend/app/modules/auth/router.py`](../../backend/app/modules/auth/router.py)
- 请求与响应模型：[`backend/app/modules/auth/schemas.py`](../../backend/app/modules/auth/schemas.py)
- 认证业务：[`backend/app/modules/auth/service.py`](../../backend/app/modules/auth/service.py)
- 会话路由与业务：[`backend/app/modules/conversations/router.py`](../../backend/app/modules/conversations/router.py)、[`backend/app/modules/conversations/service.py`](../../backend/app/modules/conversations/service.py)
