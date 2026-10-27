# OrionAI API 接口文档

## 通用约定

- **默认前缀：** `/api`
- **请求与响应：** JSON；请求体不接受未定义字段。
- **Snowflake ID：** 会话、消息和技能响应中的 ID 以十进制字符串返回，避免 JavaScript 整数精度损失；技能添加请求的 `skill_id` 也使用十进制字符串，路径参数使用十进制 ID。
- **邮箱：** 去除首尾空格并转为小写，最多 254 个字符。
- **密码：** 注册和重置为 8–128 个字符；登录为 1–128 个字符；已登录用户修改密码为 8–64 个字符，不能仅由空格组成，前后空格会作为密码内容保留。
- **认证：** 登录或注册成功后，服务端设置 `orionai_session` Cookie。Cookie 为 `HttpOnly`、`SameSite=Lax`、`Path=/`，默认有效 7 天；production 环境默认启用 `Secure`。客户端请求需携带 Cookie。
- **来源校验：** `POST`、`PATCH` 等状态变更接口若收到 `Origin`，其主机必须与请求 `Host` 一致，否则返回 `403`。
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
| `POST` | `/api/conversations/{id}/messages/stream` | 流式发送文本并获取回答或题卡 | Cookie |
| `POST` | `/api/conversations/{id}/answers` | 提交题卡选项并恢复对话 | Cookie |
| `POST` | `/api/conversations/{id}/answers/stream` | 提交题卡选项并流式恢复对话 | Cookie |
| `GET` | `/api/v1/skills` | 分页查询技能市场 | Cookie |
| `GET` | `/api/v1/skills/{skill_id}` | 查询已发布技能详情 | Cookie |
| `GET` | `/api/v1/users/me/skills` | 查询当前用户已添加技能 | Cookie |
| `POST` | `/api/v1/users/me/skills` | 添加已发布技能 | Cookie |
| `DELETE` | `/api/v1/users/me/skills/{skill_id}` | 移除当前用户的技能 | Cookie |
| `GET` | `/api/v1/users/me` | 读取当前用户个人资料 | Cookie |
| `PATCH` | `/api/v1/users/me` | 更新当前用户昵称和头像 | Cookie |
| `POST` | `/api/v1/users/me/password/code` | 向当前用户绑定邮箱发送修改密码验证码 | Cookie |
| `PUT` | `/api/v1/users/me/password` | 验证验证码并修改当前用户密码 | Cookie |
| `GET` | `/api/v1/task-results/{task_result_id}/image` | 读取本人已完成的私有图片结果 | Cookie |

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

### 当前用户个人资料 API

以下接口要求有效的 `orionai_session` Cookie。资料只针对当前登录用户，不接受用户 ID。新账号和已有账号未设置头像时返回项目静态资源 `/avatar/default_avatar.png`；默认头像地址不写入用户记录。用户上传头像后，`avatar_url` 为根据数据库中的 OSS 对象键生成的公开访问 URL。

`GET /api/v1/users/me` 返回当前个人资料：

```json
{
  "nickname": "示例用户",
  "account": "person@example.com",
  "avatar_url": "/avatar/default_avatar.png",
  "created_at": "2025-03-10T06:26:08Z",
  "last_login_at": "2026-01-26T01:17:34Z"
}
```

`PATCH /api/v1/users/me` 使用 `multipart/form-data`，字段为 `nickname`（必填，去除首尾空格后 1–20 个字符）和可选 `avatar` 文件。头像支持 PNG、JPEG、WebP，最大 2 MiB；服务端会重新检查文件签名、MIME 和大小。成功返回更新后的同一资料结构。上传头像会写入当前用户独立目录下的 OSS，并设置对象级公共读；数据库仅保存 `avatar_key`，响应中的 `avatar_url` 根据该键生成。头像上传和昵称保存在同一请求中，数据库提交失败时会尝试删除新对象；替换成功后会尽力清理旧对象。没有上传新头像时，现有头像保持不变；未设置头像时使用项目默认图片。

PATCH 请求沿用 `Origin` 与 `Host` 同源校验。错误：`401` 未登录；`403` 请求来源无效；`422` 昵称或头像不符合约束；`503` 数据库或 OSS 服务不可用。

### 当前用户修改密码 API

`POST /api/v1/users/me/password/code` 不接收邮箱参数，只向 Cookie 当前用户绑定的邮箱发送验证码。验证码为 6 位数字，有效期 5 分钟，同用途 60 秒内不可重发，最多输错 5 次；新验证码保存成功后旧验证码立即失效。Redis 只保存验证码摘要，验证由原子 Lua 脚本消费。邮件或 Redis 服务错误返回 `503`，限流返回 `429`。

`PUT /api/v1/users/me/password` 请求体只接受以下字段，不接受用户 ID 或邮箱：

```json
{
  "code": "123456",
  "new_password": "new-example-password",
  "password_confirmation": "new-example-password"
}
```

密码长度为 8–64 个字符，两次输入必须完全一致；全空格密码无效，前后空格不会被清理。新密码不能与当前密码相同。成功时更新 scrypt 哈希并清除响应 Cookie；服务端会话同时因密码哈希指纹变化而失效，用户需要重新登录。错误：`400` 验证码无效、过期或已使用；`401` 未登录；`403` 来源无效；`422` 密码规则不符；`429` 验证码请求过于频繁；`503` 依赖服务不可用。

### 会话与消息 API

以下接口均要求有效的 `orionai_session` Cookie。写入接口沿用 `Origin` 与 `Host` 同源校验。会话查询始终限制在当前用户范围；不存在或不属于当前用户的会话统一返回 `404`。列表接口支持 `limit`（默认 50，范围 1–100）和 `offset`（默认 0）。

发送消息和恢复题卡前，当前用户必须已添加会话绑定的技能，且技能仍处于已发布状态；否则返回 `409`。旧客户端不传技能代码时，新会话仍绑定 `general_chat`。

`POST /api/conversations` 创建空会话，可选请求体 `{"skill_code":"image_agent"}`；不传时默认为 `general_chat`。请求的技能必须已添加到当前用户技能，且有已注册运行入口。成功响应及会话列表项包含 `skill_code`、字符串形式的 Snowflake `id`、`title`、`created_at`、`updated_at`。首条用户消息发送前标题为空；首条用户消息提交后，根据其内容自动生成标题；模型失败或超时时使用首条消息的简短摘要。`GET /api/conversations` 返回 `items`、`limit`、`offset`，会话按 `updated_at DESC` 排列。

`GET /api/conversations/{id}/messages` 按消息 `id` 升序返回 `items`，并返回会话的 `skill_code`。消息内容使用 JSON `parts` 数组，例如：

```json
{"parts":[{"type":"text","text":"你好"}]}
```

发送消息时请求 `POST /api/conversations/{id}/messages`，JSON 请求体为 `{"message":"请帮我写一份说明"}`。返回 `status` 为 `completed` 或 `waiting`，以及本轮助手 `message`。普通回答的内容部分为 `type: "text"`；等待选择时为 `type: "question"` 并包含结构化 `questions`。图片助手完成生图时，还会包含 `image_result` 内容块，其中提供 `task_result_id`、`generation_status` 和登录后可访问的 `image_url`；不包含 OSS 对象键或上游图片地址。如果当前会话正在等待题卡答案，发送新消息返回 `409`。

图片助手技能代码为 `image_agent`，市场名称为“图片助手”。本期支持文本生成商品主图和详情页图片，不支持参考图上传、图像编辑或图像分析。用户未在文本中给出尺寸/画幅时，助手会发送现有单选题卡询问画幅；提交答案后在同一会话线程继续生图。

标题生成是消息发送流程的内部行为，不改变请求或响应结构；只有首条用户消息用于命名，后续消息和题卡答案不会覆盖标题。

通过 `POST /api/conversations/{id}/answers` 提交选择并恢复同一对话线程，请求示例：

```json
{"answers":{"style":"简洁"}}
```

答案题目 ID 集合必须与当前题卡完全相同，选项值必须为该题的有效标签；无待答题卡返回 `409`，答案不匹配返回 `422`。模型或 Checkpointer 暂不可用时返回 `503`，错误文本不会包含底层服务异常。

### 流式对话接口

`POST /api/conversations/{id}/messages/stream` 与 `POST /api/conversations/{id}/answers/stream` 使用与对应 JSON 接口相同的请求体、Cookie 登录、Origin 校验、会话所有权和技能要求。原 JSON 接口保持不变。

两个流式接口返回 `Content-Type: text/event-stream`。帧外层复用通用 `StreamEvent`：SSE 的 `id`、`event`、`data` 字段中，`data` 是 JSON，包含 `event_id`、`event_type`、`timestamp` 和业务 `data`。连接按 `start`、零到多条 `message`、空闲时的 `heartbeat`，最后一条 `end` 发送。共享响应设置 `Cache-Control: no-cache, no-transform` 与 `X-Accel-Buffering: no`。

普通回答按增量发送：

```json
{"type":"text_delta","content":"你好"}
```

Agent 需要用户选择时，发送完整且已保存的题卡消息：

```json
{"type":"question","message":{"id":"...","conversation_id":"...","role":"assistant","content":{"parts":[{"type":"question","questions":[...]}]},"created_at":"..."}}
```

`end.data.status` 为 `completed` 表示传输成功结束；若上游 Agent 或最终持久化在 SSE 开始后失败，则为 `failed`，且不带异常详情。登录、权限、请求校验、当前题卡状态等可在发送响应头前判断的错误仍返回原 HTTP 状态码及 JSON 错误格式。对于题卡等待结果，客户端根据此前的 `question` 事件进入待答状态。

用户消息在模型调用前提交；只有 Agent 完成后，完整文本或题卡才写入消息表。中途断连或生成失败时不会保存部分助手回答，已提交的用户消息可能仍在历史中。浏览器客户端使用带 Cookie 的 Fetch POST 和 `ReadableStream` 读取事件，不自动重发失败消息。

图片生成通过 TokenHub 执行，图片下载后保存到私有 OSS。缺少 TokenHub 或 OSS 配置时，对应调用会返回受控失败提示；对象存储凭据不会在应用启动时用于创建 Bucket。`image_url` 的图片读取接口要求会话 Cookie，且只返回当前用户拥有、状态为 `succeeded` 的结果。

### 技能市场 API

以下接口要求有效的 `orionai_session` Cookie。`GET /api/v1/skills` 支持 `type`、`keyword`、`page`、`page_size` 和 `include_disabled`；默认只返回已发布技能，传 `include_disabled=true` 时也返回已停用技能。停用技能可查看列表说明，但详情接口仍返回 `404`，且不能添加到用户技能列表。技能响应中的 Snowflake `id` 使用十进制字符串。

`GET /api/v1/users/me/skills` 只返回当前用户已添加且仍发布的技能。添加技能时，`POST /api/v1/users/me/skills` 的请求体使用 `{"skill_id":"十进制 Snowflake ID"}`；重复添加返回 `409`，不存在或已停用的技能返回 `404`。删除当前用户自己的关联使用 `DELETE /api/v1/users/me/skills/{skill_id}`。

### 私有图片结果 API

`GET /api/v1/task-results/{task_result_id}/image` 返回 `image/png` 或 `image/jpeg` 图片字节，仅当任务结果属于当前登录用户且状态为 `succeeded` 时可读取。其他用户的 ID、不存在的 ID、失败或尚未完成的任务统一返回 `404`。响应设置 `Cache-Control: private, no-store`，图片保存在私有 OSS，不向客户端公开 OSS Key 或签名 URL。

运行图片助手需配置 `TOKENHUB_API_KEY`（兼容 `TENCENT_TOKENHUB_API_KEY`）；可选配置项 `TOKENHUB_BASE_URL`（兼容 `TENCENT_TOKENHUB_BASE_URL`）、`TENCENT_HY_IMAGE_MODEL`、`TENCENT_HY_IMAGE_ENDPOINT`、`TOKENHUB_TIMEOUT_SECONDS` 和 `IMAGE_RESULT_MAX_BYTES` 控制服务地址、模型、超时与下载上限。结果持久化还需配置 `ALIYUN_OSS_ACCESS_KEY_ID`、`ALIYUN_OSS_ACCESS_KEY_SECRET`、`ALIYUN_OSS_ENDPOINT`、`ALIYUN_OSS_BUCKET` 和可选 `ALIYUN_OSS_OBJECT_PREFIX`。

## 实现位置

- 路由与 Cookie：[`backend/app/modules/auth/router.py`](../../backend/app/modules/auth/router.py)
- 请求与响应模型：[`backend/app/modules/auth/schemas.py`](../../backend/app/modules/auth/schemas.py)
- 认证业务：[`backend/app/modules/auth/service.py`](../../backend/app/modules/auth/service.py)
- 会话路由与业务：[`backend/app/modules/conversations/router.py`](../../backend/app/modules/conversations/router.py)、[`backend/app/modules/conversations/service.py`](../../backend/app/modules/conversations/service.py)
- 技能路由与业务：[`backend/app/modules/skills/router.py`](../../backend/app/modules/skills/router.py)、[`backend/app/modules/skills/service.py`](../../backend/app/modules/skills/service.py)
