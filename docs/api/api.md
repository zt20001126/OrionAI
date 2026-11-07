# OrionAI API 接口文档

本文为接口概览；实时完整契约以 FastAPI OpenAPI（`/docs`、`/openapi.json`）及路由源码为准。

## 通用约定

- **默认前缀：** `/api`
- **请求与响应：** 多数接口使用 JSON；文件上传、音视频、PDF 和 SSE 接口使用对应的媒体类型。字段约束以各接口模型和 OpenAPI 为准。
- **Snowflake ID：** 会话、消息和技能响应中的 ID 以十进制字符串返回，避免 JavaScript 整数精度损失；技能添加请求的 `skill_id` 也使用十进制字符串，路径参数使用十进制 ID。
- **邮箱：** 去除首尾空格并转为小写，最多 254 个字符。
- **密码：** 注册和重置为 8–128 个字符；登录为 1–128 个字符；已登录用户修改密码为 8–64 个字符，不能仅由空格组成，前后空格会作为密码内容保留。
- **认证：** 登录或注册成功后，服务端设置 `orionai_session` Cookie。Cookie 为 `HttpOnly`、`SameSite=Lax`、`Path=/`，默认有效 7 天；production 环境默认启用 `Secure`。客户端请求需携带 Cookie。
- **来源校验：** `POST`、`PATCH` 等状态变更接口若收到 `Origin`，其主机必须与请求 `Host` 一致，否则返回 `403`。
- **错误格式：** 业务错误为 `{"detail":"错误说明"}`；请求字段校验失败返回 FastAPI 的 `422` 校验详情。

## 简历接口

简历接口均要求当前登录 Cookie。服务器按当前用户 ID 读写，客户端不能指定简历所有者。

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/resume` | 获取简历；尚未保存时返回算法工程师示例内容和 `exists: false`，不创建记录。 |
| `PUT` | `/api/resume` | 校验并保存完整简历及排版设置；已有简历需携带 `expected_updated_at`，版本不匹配返回 `409`。 |
| `POST` | `/api/resume/photo` | 上传 PNG/JPEG 照片，最大 5 MiB，返回暂存 `photo_id`。 |
| `GET` | `/api/resume/photo` | 读取当前用户已保存简历引用的私有照片。 |
| `DELETE` | `/api/resume/photo?photo_id={id}` | 删除当前用户未引用的暂存照片。 |
| `GET` | `/api/resume/export/pdf` | 导出当前用户已保存简历的 PDF。 |

AI 优化沿用 `/api/conversations` 的消息和题卡接口；候选在用户确认前不会写入简历。

## 当前路由目录

以下目录由当前 Router 声明整理；请求字段、响应模型、状态码及逐接口认证要求以运行服务的 `/docs` 或 `/openapi.json` 和源码为准。部分写操作需要会员，注册用户专属操作不接受访客；Webhook 使用 Stripe 签名。

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/health` | 检查服务健康状态。 |
| `GET` | `/api/auth/session` | 查询当前会话。 |
| `POST` | `/api/auth/email-codes` | 请求邮箱验证码。 |
| `POST` | `/api/auth/guest` | 创建访客会话。 |
| `POST` | `/api/auth/login` | 邮箱密码登录。 |
| `POST` | `/api/auth/logout` | 退出当前会话。 |
| `POST` | `/api/auth/password-reset` | 重置密码。 |
| `POST` | `/api/auth/register` | 注册账号。 |
| `GET` | `/api/conversations` | 按最近更新时间倒序列出当前用户会话。 |
| `GET` | `/api/conversations/{conversation_id}/messages` | 读取当前用户会话中的消息记录。 |
| `GET` | `/api/conversations/{conversation_id}/runs/active` | 查询当前用户会话中的活动任务，供页面重新进入时恢复监听。 |
| `GET` | `/api/conversations/{conversation_id}/runs/{run_id}/listen` | 监听并回放任务事件；客户端断开只关闭监听。 |
| `POST` | `/api/conversations` | 为当前用户创建空会话。 |
| `POST` | `/api/conversations/{conversation_id}/answers` | 校验当前待答题卡选项并恢复原对话线程。 |
| `POST` | `/api/conversations/{conversation_id}/answers/stream` | 预检并保存题卡答案，再以 SSE 返回恢复后的 Agent 回答。 |
| `POST` | `/api/conversations/{conversation_id}/messages` | 存储用户文本并同步返回助手回答或题卡。 |
| `POST` | `/api/conversations/{conversation_id}/messages/stream` | 先完成消息预检，再以 SSE 返回 Agent 的逐段回答。 |
| `POST` | `/api/conversations/{conversation_id}/runs/answers` | 保存题卡答案并启动可重连的 Agent 恢复任务。 |
| `POST` | `/api/conversations/{conversation_id}/runs/messages` | 保存用户消息并启动独立于监听连接的 Agent 生成任务。 |
| `POST` | `/api/conversations/{conversation_id}/runs/{run_id}/interrupt` | 停止本轮 Agent 生成并保留已输出内容。 |
| `GET` | `/api/digital-human/conversations` | 只返回当前用户的数字人技能会话。 |
| `GET` | `/api/digital-human/task-results/{task_result_id}/video` | 返回当前用户的私有视频；输入任务 ID，输出 MP4；调用方：数字人播放器。 |
| `POST` | `/api/digital-human/speech/recognitions` | 将短录音转成文本；音频仅在本次请求中暂存。 |
| `POST` | `/api/digital-human/speech/syntheses` | 返回临时 MPEG 音频，不持久化音频或返回上游下载 URL。 |
| `POST` | `/api/payments/stripe/webhook` | 读取有大小限制的原始请求体并交由支付服务验签处理。 |
| `DELETE` | `/api/resume/photo` | 删除未引用的暂存照片。 |
| `GET` | `/api/resume` | 读取当前用户简历。 |
| `GET` | `/api/resume/export/pdf` | 导出简历 PDF。 |
| `GET` | `/api/resume/photo` | 读取简历照片。 |
| `POST` | `/api/resume/photo` | 上传简历照片。 |
| `PUT` | `/api/resume` | 保存简历。 |
| `GET` | `/api/tourism-insight/comments` | 分页查询评论。 |
| `GET` | `/api/tourism-insight/results` | 分页查询分析结果。 |
| `GET` | `/api/tourism-insight/summary` | 查询导入与分析概况。 |
| `POST` | `/api/tourism-insight/analyses` | 分析指定评论。 |
| `POST` | `/api/tourism-insight/comments/import` | 读取并导入 UGC 评论 CSV 文件。 |
| `POST` | `/api/tourism-insight/rules/import` | 读取并导入评分规则文件。 |
| `DELETE` | `/api/v1/users/me/skills/{skill_id}` | 移除当前用户与技能的关联。 |
| `GET` | `/api/v1/skills` | 分页查询已发布技能市场。 |
| `GET` | `/api/v1/skills/{skill_id}` | 读取已发布技能详情。 |
| `GET` | `/api/v1/users/me/skills` | 查询当前用户已添加且仍发布的技能。 |
| `POST` | `/api/v1/users/me/skills` | 将已发布技能添加到当前用户列表。 |
| `POST` | `/api/v1/feedback` | 验证当前会话并将反馈交由业务 Service 处理。 |
| `GET` | `/api/v1/membership/orders/{order_id}` | 查询当前注册用户自己的会员订单。 |
| `GET` | `/api/v1/membership/plans` | 公开读取启用中的会员套餐。 |
| `POST` | `/api/v1/membership/orders` | 为当前注册用户创建会员订单并快照套餐价格和期限。 |
| `GET` | `/api/v1/memory-training/prepare` | 返回训练规则，不在准备阶段获取图片。 |
| `GET` | `/api/v1/memory-training/sessions/{session_id}` | 查询本人会话阶段，以服务端时间推进观察结束状态。 |
| `GET` | `/api/v1/memory-training/sessions/{session_id}/questions` | 仅在观察窗口结束且题目生成成功后返回不含答案的题目。 |
| `GET` | `/api/v1/memory-training/sessions/{session_id}/result` | 读取本人已完成的训练结果和本次原图公开链接。 |
| `POST` | `/api/v1/memory-training/sessions` | 随机抽取一张启用图片并创建短期训练会话。 |
| `POST` | `/api/v1/memory-training/sessions/{session_id}/answers` | 提交全部答案并由后端评分。 |
| `POST` | `/api/v1/memory-training/sessions/{session_id}/observation/start` | 在前端确认图片加载后启动服务端观察计时。 |
| `GET` | `/api/v1/payments/methods` | 返回当前环境已完整配置的支付渠道。 |
| `POST` | `/api/v1/payments/checkout-sessions` | 按客户端选中的可用支付方式创建或恢复支付会话。 |
| `POST` | `/api/v1/payments/stripe/checkout-sessions` | 提供方案中 Stripe 专用的 Checkout Session API。 |
| `GET` | `/api/v1/reminders` | 分页读取当前用户自己的提醒。 |
| `GET` | `/api/v1/reminders/{reminder_id}` | 读取当前用户的一条提醒；跨用户 ID 与不存在 ID 使用同一 404。 |
| `GET` | `/api/v1/reminders/{reminder_id}/executions` | 读取本人提醒的执行历史，并只返回脱敏后的收件邮箱。 |
| `POST` | `/api/v1/reminders` | 为当前登录用户创建一个单次或周期提醒。 |
| `POST` | `/api/v1/reminders/{reminder_id}/cancel` | 软取消提醒，保留所有已经创建的执行历史。 |
| `POST` | `/api/v1/reminders/{reminder_id}/pause` | 暂停周期提醒，已开始的 SMTP 调用无法撤回。 |
| `POST` | `/api/v1/reminders/{reminder_id}/resume` | 恢复暂停的周期提醒并计算下一次未来计划。 |
| `PUT` | `/api/v1/reminders/{reminder_id}` | 用完整规则更新提醒，并以 expected_version 拒绝过期表单。 |
| `GET` | `/api/v1/task-results/{task_result_id}/image` | 只向任务所属用户返回完成状态的图片字节。 |
| `GET` | `/api/v1/users/me` | 读取当前登录用户资料。 |
| `GET` | `/api/v1/users/me/membership` | 读取当前、未来和最近过期的会员期限。 |
| `GET` | `/api/v1/users/me/membership/access` | 从 Redis 准入缓存读取当前用户是否可使用技能。 |
| `GET` | `/api/v1/users/me/membership/orders` | 分页读取当前注册用户的会员订单历史。 |
| `PATCH` | `/api/v1/users/me` | 一次提交当前用户昵称和可选头像文件。 |
| `POST` | `/api/v1/users/me/password/code` | 向当前登录用户绑定的邮箱发送修改密码验证码。 |
| `PUT` | `/api/v1/users/me/password` | 修改当前用户密码并清除当前浏览器会话 Cookie。 |

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

### `POST /api/auth/guest`

创建访客身份并设置会话 Cookie；访客身份与业务数据关联到新的用户 ID，Cookie 丢失或过期后不能恢复。访客无法使用仅限注册用户的操作；具体会员准入要求见路由依赖。

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

访客会话返回 `{"authenticated":true,"account":null,"is_guest":true}`。注册用户和未登录响应继续使用原有字段；客户端可通过 `is_guest` 区分访客。

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

创建会话、发送消息、流式发送、提交答案和流式提交答案还要求当前用户拥有有效会员资格；不满足时返回 `403`。会话及消息历史仍可读取。前端每次从“我的技能”点击使用前都会请求会员准入接口，后端仍独立校验实际执行请求。

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

### 会员准入与技能使用

`GET /api/v1/users/me/membership/access` 使用当前 Cookie 用户身份，不接受用户 ID，响应只包含准入布尔值：

```json
{"is_member": true}
```

每次检查先读取 Redis 中按用户隔离的会员状态；缓存未命中时由服务端根据现有会员期限计算并回填。会员数据库是状态权威来源，支付 Webhook 成功入账后会删除该用户缓存。Redis 或缓存未命中时的数据库查询不可用时返回 `503`。访客的 `is_member` 为 `false`。

非会员可以继续浏览技能市场和添加/移除技能。点击“使用”时会显示“关闭”和“去充值”两个选项；充值跳转到现有 `/membership` 页面。后端执行接口也会重复校验会员，未开通时返回 `403`。

以下操作要求会员：对话/Agent 会话创建、消息和题卡提交；记忆训练会话创建、观察启动和答案提交；提醒创建、更新和恢复。只读历史、简历查看与管理、图片结果读取、提醒读取、暂停及取消不要求会员。会员到期后已创建的周期提醒仍会执行，用户仍可暂停或取消。

### 私有图片结果 API

`GET /api/v1/task-results/{task_result_id}/image` 返回 `image/png` 或 `image/jpeg` 图片字节，仅当任务结果属于当前登录用户且状态为 `succeeded` 时可读取。其他用户的 ID、不存在的 ID、失败或尚未完成的任务统一返回 `404`。响应设置 `Cache-Control: private, no-store`，图片保存在私有 OSS，不向客户端公开 OSS Key 或签名 URL。

运行图片助手需配置 `TOKENHUB_API_KEY`（兼容 `TENCENT_TOKENHUB_API_KEY`）；可选配置项 `TOKENHUB_BASE_URL`（兼容 `TENCENT_TOKENHUB_BASE_URL`）、`TENCENT_HY_IMAGE_MODEL`、`TENCENT_HY_IMAGE_ENDPOINT`、`TOKENHUB_TIMEOUT_SECONDS` 和 `IMAGE_RESULT_MAX_BYTES` 控制服务地址、模型、超时与下载上限。结果持久化还需配置 `ALIYUN_OSS_ACCESS_KEY_ID`、`ALIYUN_OSS_ACCESS_KEY_SECRET`、`ALIYUN_OSS_ENDPOINT`、`ALIYUN_OSS_BUCKET` 和可选 `ALIYUN_OSS_OBJECT_PREFIX`。

## 实现位置

- 路由与 Cookie：[`backend/app/modules/auth/router.py`](../../backend/app/modules/auth/router.py)
- 请求与响应模型：[`backend/app/modules/auth/schemas.py`](../../backend/app/modules/auth/schemas.py)
- 认证业务：[`backend/app/modules/auth/service.py`](../../backend/app/modules/auth/service.py)
- 会话路由与业务：[`backend/app/modules/conversations/router/router.py`](../../backend/app/modules/conversations/router/router.py)、[`backend/app/modules/conversations/service/service.py`](../../backend/app/modules/conversations/service/service.py)
- 技能路由与业务：[`backend/app/modules/skills/router.py`](../../backend/app/modules/skills/router.py)、[`backend/app/modules/skills/service.py`](../../backend/app/modules/skills/service.py)
