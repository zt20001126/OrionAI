# OrionAI 定时提醒工具需求与实现设计

- 文档日期：2026-10-28
- 文档状态：需求与技术方案；待决事项需在开发前确认
- 调研范围：当前工作区代码、项目文档与 Docker Compose 配置
- 本文仅为设计，不代表功能已实现

## 1. 功能背景与目标

在技能市场新增普通工具“提醒助手”（英文名 Reminder，技能编码 reminder，类型 tool）。登录用户可创建、查看和管理单次或周期提醒；系统根据提醒计划向用户账号邮箱发送通知邮件，并保留每次计划执行及 SMTP 处理结果。

本次只产出可供后续分阶段开发的需求与实现文档。本文不创建表、不执行迁移、不增加依赖、不改动应用或 Compose 配置，也不发送邮件。

### 1.1 目标

- 为提醒规则和每次执行保留 PostgreSQL 中的持久化记录。
- 使用现有 Cookie 登录身份和账号邮箱。
- 复用现有 Redis、SMTP 配置及技能市场元数据机制。
- 在 Celery 尚未集成的前提下，提出使用 Celery Beat、Worker 的最小新增方案。
- 在仅新增 reminders 与 reminder_executions 两张提醒业务表的限制下，提供可恢复、可幂等且诚实说明投递边界的调度流程。

### 1.2 非目标

- 不将 Reminder 实现为 AI Agent，不调用 LLM，不创建对话或 Agent Runtime。
- 不创建独立邮件日志表、通用任务表或第三张提醒业务表。
- 不在本阶段实际实现 API、前端、Celery 任务、数据库迁移或容器服务。
- 不承诺邮件必达、SMTP 端到端恰好一次投递或用户实际阅读。

## 2. 现有项目调研

调研依据是仓库当前文件；能力状态只按可见实现描述。

| 领域 | 实际情况 | 对本功能的影响 |
|---|---|---|
| 项目规范 | 根目录 AGENTS.md 规定 FastAPI 模块采用 Router / Service / Repository 分层、模块内组织、基础设施复用。没有发现其他 AGENTS.md。 | 新业务放入 backend/app/modules/reminders；应用组合与共享基础设施仍沿用 core、infrastructure。 |
| 技能市场 | backend/app/modules/skills/models.py 有 Skill、UserSkill；Skill.type 的 CHECK 允许 agent、tool，技能 code 唯一；用户关联有 user_id、skill_id 唯一约束。技能市场 API 位于 /api/v1/skills，需 Cookie 登录。repository.py 与 core/application.py 通过幂等 ensure_* 函数注册内置技能。 | 可复用技能元数据、类型和用户技能关联，不增加技能专属表。需要为 reminder 注册市场项。 |
| 工具运行入口 | frontend/src/features/platform/skillUsage.ts 只识别 general_chat、image_agent、resume_assistant；未知技能默认创建对话。backend/app/agent/tools/registry.py 是 Agent 内部工具注册能力，不是普通用户工具的调度或管理入口。 | Reminder 必须在前端技能启动分派中明确跳转管理页；不能把 Agent 工具注册当作 Reminder 执行机制。 |
| 用户与认证 | backend/app/modules/auth/models.py 的 User.id 为 BIGINT Snowflake，邮箱保存在 account VARCHAR(254)，唯一且非空。backend/app/modules/auth/dependencies.py 的 get_current_user 从 HttpOnly Cookie Session 验证并返回用户。当前用户资料更新不允许改 account，未发现邮箱变更流程。 | API 使用 CurrentUser，不接受客户端 user_id。执行收件邮箱从 users.account 读取并保存到执行快照。 |
| PostgreSQL / ORM | PostgreSQL 17、SQLAlchemy 2、Alembic 已使用。业务模型在 app/modules/<module>/models.py；常用 BIGINT Snowflake、TIMESTAMPTZ、server_default=now()、具名 CHECK 和索引。JSONB 在 SQLite 测试中用 JSON variant。 | 两张表沿用上述约定。执行 ID 使用项目 Snowflake 生成器；时间戳均存为 UTC aware timestamptz。 |
| 迁移 | Alembic 环境位于 backend/migrations；当前版本序列至 0013_rename_general_chat。env.py 显式导入各模块模型。 | 后续新增单个迁移版本（建议 0014_create_reminders.py），导入提醒模型并只创建这两张业务表。本文不运行迁移。 |
| Redis / Celery | Redis 7.4 已在 Compose 中运行；REDIS_URL 已由 Settings 读取，并由认证功能用于验证码和会话。pyproject.toml 未包含 Celery，代码和 Compose 中未发现 Celery Worker、Beat 或任务注册机制。 | Redis 可复用为 broker，但“已集成 Celery”不成立。需新增 Celery 依赖、应用配置、任务入口与 Worker、Beat 服务。 |
| SMTP | app/infrastructure/email/email_sender.py 已实现 SMTP_SSL 或 STARTTLS、10 秒 socket timeout、账号登录、EmailDeliveryError；目前唯一公开函数为验证码邮件发送，邮件内容与验证码流程绑定。Settings 已含 SMTP 主机、端口、用户名、密码、发件地址、发件名称、SSL 开关。 | SMTP 连接配置和传输代码可复用；需在同一基础设施模块扩展通用邮件发送接口，不能把验证码发送函数用于提醒邮件。 |
| 前端路由与 UI | 前端为 React、TypeScript、Vite；App.tsx 使用自定义 pathname 分派，platformData.ts 集中定义路径。SkillMarketPage、MySkillsPage 是现有技能入口；现有主导航固定为五项。docs/design/UI_DESIGN.md 规定浅色中性、克制品牌蓝、复用组件和令牌。 | 在技能启动分派中增加 /reminders 路由，不新增全局导航项；页面遵循现有浅色设计。已按要求阅读 UI_DESIGN.md。 |
| Compose | 根 docker-compose.yml 目前只有 backend、postgres、redis。backend 执行 Alembic upgrade head 后启动 Uvicorn，并注入 Redis、SMTP 配置；没有 Celery 服务。README 记载 Compose 启动时先运行迁移。Redis 开启 AOF。 | 后续 Worker/Beat 复用 backend 镜像、代码挂载和配置；仅增加必要服务和 Celery 命令。Beat 只能单实例。 |
| 文档命名 | docs/requirements 当前文件为 2026-10-26-001-general-conversation-assistant-frontend.md。 | 按“日期-当日序号-英文 kebab-case 名称”新建 2026-10-28-001-reminder-tool-requirements-and-implementation-design.md；不覆盖现有文档。 |

### 2.1 明确可复用能力

- get_current_user、CurrentUser 与 validate_origin：登录身份和状态变更来源校验。
- User.account：当前账号邮箱。
- Skill、UserSkill、市场列表和用户技能接口：普通工具元数据与用户关联。
- SQLAlchemy SessionLocal、Base、Snowflake ID 生成器、Alembic 元数据导入约定。
- Settings 中 Redis 与 SMTP 参数、Redis 客户端工厂。
- SMTP 的 SSL/STARTTLS 传输实现、邮件地址配置和 10 秒网络超时。
- PlatformLayout、PlatformIcon、按钮、Toast、ConfirmationDialog、全局 CSS tokens 与技能卡片。

### 2.2 不存在或不能直接复用的能力

- Celery 依赖、Celery app、Beat schedule、Worker、自动任务发现均不存在。
- SMTP sender 当前只生成验证码邮件，没有通用 subject/body 接口。
- 当前用户表没有时区字段；浏览器端需要检测并在创建请求中显式提交 IANA 时区。
- 技能的“普通工具”类型只是市场元数据；Reminder 专用页面和生命周期并不存在。
- 没有现成的提醒执行状态、通用业务错误码响应封装或提醒并发控制。

## 3. 业务范围与操作流程

### 3.1 支持的提醒

repeat_type 取值：once、daily、weekly、monthly。

- 单次：用户提供本地日期、时间及时区，数据库保存换算后的 UTC next_run_at；repeat_config 为 {}。
- 每天：在起始日期及之后每天使用指定本地时刻。
- 每周：已确认按创建日期的星期重复。例如从周三开始，则每周三重复；界面无需额外选择星期。
- 每月：已确认按创建日期的日号重复；某月没有该日时跳过该月，不滚动到月底。
- 周期任务可以设置结束日期。结束日期是用户时区内的日历日期，包含结束日当天计划的执行。

每个提醒保存独立时区，避免将用户资料表扩展为提醒所需的唯一时区来源。界面使用浏览器 Intl API 检测 IANA 名称并作为默认值，用户可在表单中调整。API 应要求提交 timezone，不在服务器猜测用户所在地。

### 3.2 创建流程

1. 用户从技能市场或“我的技能”打开 Reminder 管理页。
2. 页面加载本人提醒列表，并显示浏览器检测到的时区。
3. 用户填写标题、正文、类型、本地日期/时间、周期结束日期。
4. 前端与后端校验字段；后端基于 ZoneInfo 验证 IANA 时区并计算第一次执行时间。
5. 后端在事务中写入 active 提醒，返回提醒详情。
6. Beat 扫描器在到期后认领提醒、创建唯一执行记录并投递 Worker。

### 3.3 管理流程

- 列表和详情始终按当前用户 ID 过滤。
- 可编辑 active 或 paused 提醒，但不能编辑 cancelled、completed 提醒；执行正在发送时返回 409。
- 周期提醒可暂停/恢复。暂停阻止尚未开始发送的当前执行及新的周期执行；已经进入 SMTP 调用的邮件无法撤回。
- 恢复时保留将来的下次执行计划；若计划时间已过去，按已确认的停机补发规则处理。
- 取消采用软取消，保留执行历史；pending/retry_wait 执行标记 cancelled，正在发送的任务可能完成。
- 单次提醒成功或达到终态失败后变为 completed；执行结果由 execution 状态表达。

## 4. 校验规则与时间语义

以下长度和错误处理是可实施的推荐基线；如产品另有内容策略，应在开发前确认。

| 字段/规则 | 推荐校验 |
|---|---|
| title | 去除首尾空格后 1–120 个 Unicode 字符；不能为空。 |
| content | 去除首尾空格后 1–5000 个 Unicode 字符；纯空白不接受。邮件按纯文本安全发送；不将用户内容直接解释为 HTML。 |
| repeat_type | 仅 once、daily、weekly、monthly。 |
| timezone | 必须是系统可识别的 IANA 时区，例如 Asia/Shanghai；拒绝未知标识和固定偏移字符串。 |
| 本地日期/时间 | API 使用 date 与 HH:MM 的本地字段结合 timezone；不存在的日历日期和非法格式返回 422。 |
| 过去时间 | 创建/修改后第一次计划执行必须晚于服务端当前 UTC 时间；不接受过去的单次时间或已错过的首次周期时间。 |
| repeat_config | 只允许与 repeat_type 对应的键；未知键拒绝。JSON 根节点必须为 object。 |
| end_date | 仅周期任务允许；如设置，必须不早于第一次执行的本地日期。inclusive。 |
| 提醒 ID | JSON 响应以十进制字符串返回，匹配项目对 BIGINT Snowflake ID 的约定。 |
| 空值和未知字段 | Pydantic DTO 使用 extra=forbid；不允许客户端提交 user_id、status、recipient_email 或 next_run_at。 |

### 4.1 repeat_config JSONB 契约

- once：{}。
- daily：{"start_date":"2026-10-28","local_time":"09:30"}。
- weekly：{"start_date":"2026-10-28","local_time":"09:30","weekday":2}，weekday 采用 ISO 8601，周一为 1、周日为 7；该 weekday 必须与 start_date 的星期一致。
- monthly：{"start_date":"2026-10-28","local_time":"09:30","day_of_month":28}，day_of_month 由起始日期日号确定，范围 1–31。

repeat_config 只保存业务规则，不作为任意用户 JSON。timezone 单独保存，不重复写入配置。next_run_at 保存当前待执行计划的绝对 UTC instant；周期规则仍由 repeat_config 的本地时间与时区计算下一次。

### 4.2 时区、夏令时与每月规则

所有持久化时间使用 TIMESTAMPTZ，业务计算先在 reminder.timezone 转换为本地日历日期/墙上时间，再将计划转为 UTC 存储。夏令时会导致本地时间不存在或出现两次。建议：
- 周期提醒落在不存在的本地时间时，将该次计划顺延到该日第一个有效本地时刻。
- 本地时间出现两次时，选择较早的 instant（fold=0），每个本地日期最多生成一次执行。
- 单次提醒落在歧义或不存在的本地时间时，当前推荐由 API 422 拒绝并提示用户改选时间。

夏令时策略是实现前需确认的产品规则，尤其是单次提醒的行为。已确认的月末规则为跳过无该日的月份；例如 day_of_month=31 时，二月、四月不执行。

## 5. 提醒状态与允许操作

### 5.1 reminders.status

| 状态 | 含义 | 可允许操作 |
|---|---|---|
| active | 单次或周期提醒可执行 | 查看、编辑、取消；周期提醒可暂停 |
| paused | 周期提醒暂停，保留下一次规则位置 | 查看、编辑、恢复、取消 |
| cancelled | 用户取消，保留记录和执行历史 | 仅查看 |
| completed | 单次提醒已到终态，或周期规则结束 | 仅查看 |

系统使用 VARCHAR + named CHECK 维护有限状态，避免数据库原生 ENUM 的迁移耦合。active 且 next_run_at 为 NULL 允许短暂表示单次提醒已产生执行记录、仍在发送/重试；执行终态后 reminders 改为 completed。

### 5.2 reminder_executions.status

| 状态 | 含义 | 转移 |
|---|---|---|
| pending | 数据库中已有执行记录，待 Celery 投递/认领 | sending、cancelled |
| sending | 某 Worker 已认领，正在处理/调用 SMTP | accepted、retry_wait、failed；租约超时后恢复为 retry_wait |
| retry_wait | 本次可重试失败，等待 next_retry_at | sending、cancelled、failed |
| accepted | SMTP 接受了发送请求；不代表最终投递 | 终态 |
| failed | 永久错误或重试耗尽 | 终态 |
| cancelled | 提醒暂停/取消导致未发送执行被终止 | 终态 |

主要状态转移：

~~~text
pending -> sending -> accepted
                   -> retry_wait -> sending
                   -> failed
pending/retry_wait -> cancelled
sending(租约超时) -> retry_wait
~~~

Worker 使用数据库原子状态更新/行锁认领，只有一个 Worker 能将同一 pending/retry_wait 行切换为 sending。遇到用户取消、暂停或提醒已不允许发送时，Worker 在 SMTP 调用前将执行标记 cancelled。

## 6. 数据库设计

只新增 reminders 与 reminder_executions 两张提醒业务表，不增加 outbox、邮件日志、排程或审计第三表。技能元数据仍使用既有 skills 表。

### 6.1 reminders 字段

| 字段 | PostgreSQL 类型 | 可空 | 默认/约束 | 说明 |
|---|---|---:|---|---|
| id | BIGINT | 否 | 应用 Snowflake 主键 | 提醒 ID。 |
| user_id | BIGINT | 否 | FK users.id ON DELETE CASCADE | 所属用户。 |
| title | VARCHAR(120) | 否 | CHECK trim 后 1–120 | 提醒标题。 |
| content | TEXT | 否 | CHECK trim 后 1–5000 | 提醒正文。 |
| repeat_type | VARCHAR(16) | 否 | CHECK once/daily/weekly/monthly | 单次或周期类型。 |
| repeat_config | JSONB | 否 | DEFAULT {}；CHECK 根节点为 object | 规则契约见 4.1。 |
| timezone | VARCHAR(64) | 否 | IANA 名称由 Service 校验 | 该提醒显示和重复计算所用时区。 |
| next_run_at | TIMESTAMPTZ | 是 | 无 | 当前下一个计划 instant，暂停时保留；终态可为空。 |
| end_date | DATE | 是 | 无 | 周期提醒本地结束日期，包含当日；不适用于 once。 |
| status | VARCHAR(16) | 否 | DEFAULT active；CHECK 状态集合 | 提醒生命周期。 |
| version | INTEGER | 否 | DEFAULT 1；CHECK > 0 | 编辑的乐观并发版本；每次成功修改加一。 |
| created_at | TIMESTAMPTZ | 否 | DEFAULT now() | 创建时间。 |
| updated_at | TIMESTAMPTZ | 否 | DEFAULT now() | 每次业务修改更新；不是数据库自动更新触发器。 |

约束：repeat_config 必须是 JSON 对象；end_date 仅允许在周期提醒上设置；标题和内容使用数据库 CHECK 做基础防御，完整校验仍由 Pydantic/Service 完成。外键删除规则沿用项目：删除用户时提醒级联删除，提醒执行记录随提醒级联删除。

推荐索引：
- 部分索引 reminders(next_run_at, id)，条件 status='active' AND next_run_at IS NOT NULL，服务到期扫描。
- 索引 reminders(user_id, created_at DESC, id DESC)，查询用户列表与稳定排序。

### 6.2 reminder_executions 字段

| 字段 | PostgreSQL 类型 | 可空 | 默认/约束 | 说明 |
|---|---|---:|---|---|
| id | BIGINT | 否 | 应用 Snowflake 主键 | 执行记录 ID。 |
| reminder_id | BIGINT | 否 | FK reminders.id ON DELETE CASCADE | 所属提醒。 |
| scheduled_at | TIMESTAMPTZ | 否 | 唯一键组成部分 | 本次计划的 UTC instant；不是开始发送时间。 |
| status | VARCHAR(16) | 否 | DEFAULT pending；CHECK 状态集合 | 执行与投递处理结果。 |
| retry_count | INTEGER | 否 | DEFAULT 0；CHECK >= 0 | 已发生的失败重试次数；第一次 SMTP 尝试前为 0。 |
| next_retry_at | TIMESTAMPTZ | 是 | 无 | retry_wait 的下次可尝试时间。 |
| recipient_email | VARCHAR(254) | 是 | 无 | Worker 认领时从 users.account 读取并保存的收件邮箱快照。 |
| error_message | TEXT | 是 | 无 | 最近失败的安全摘要；不得存 SMTP 凭据或敏感响应全文。 |
| started_at | TIMESTAMPTZ | 是 | 无 | 最近一次认领/发送开始时间；用于执行历史及过期租约恢复。 |
| finished_at | TIMESTAMPTZ | 是 | 无 | accepted、failed、cancelled 等终态时间。 |
| created_at | TIMESTAMPTZ | 否 | DEFAULT now() | 执行记录创建时间。 |

唯一约束：(reminder_id, scheduled_at)，数据库约束是并发扫描去重的最终保障。推荐索引：
- (reminder_id, scheduled_at DESC, id DESC)：用户提醒执行历史。
- 部分索引 (next_retry_at, id)，条件 status='retry_wait'：到期重试。
- 部分索引 (started_at, id)，条件 status='sending'：超时恢复。

recipient_email 在执行第一次认领时复制当前 account；以后用户邮箱变更不改变已经开始处理的执行。项目目前没有邮箱变更入口，但该快照可明确历史收件地址。SMTP 发送成功只将状态写为 accepted。

### 6.3 SQLAlchemy 模型建议

- 模型分别放 reminders/models.py；继承 app.infrastructure.database.base.Base。
- id、user_id、reminder_id 使用 BigInteger().with_variant(Integer(), "sqlite")；id default=generate_snowflake_id。
- 时间字段使用 DateTime(timezone=True)；生产数据库为 PostgreSQL。
- repeat_config 使用 JSONB().with_variant(JSON(), "sqlite")，与现有 resumes、messages 模型一致。
- 使用具名 CheckConstraint、UniqueConstraint、Index；状态以 Literal DTO + DB CHECK 表达。
- Service 管理事务提交/回滚；Repository 只封装查询、锁定、插入和状态更新。
- 对外返回 DTO，不直接序列化 ORM。BIGINT ID 返回十进制字符串。

### 6.4 DDL 示例

以下示例仅描述目标结构，不会在本次执行：

~~~sql
CREATE TABLE reminders (
    id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(120) NOT NULL,
    content TEXT NOT NULL,
    repeat_type VARCHAR(16) NOT NULL
        CHECK (repeat_type IN ('once', 'daily', 'weekly', 'monthly')),
    repeat_config JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(repeat_config) = 'object'),
    timezone VARCHAR(64) NOT NULL,
    next_run_at TIMESTAMPTZ NULL,
    end_date DATE NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'cancelled', 'completed')),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_reminders_title_length
        CHECK (char_length(btrim(title)) BETWEEN 1 AND 120),
    CONSTRAINT ck_reminders_content_length
        CHECK (char_length(btrim(content)) BETWEEN 1 AND 5000),
    CONSTRAINT ck_reminders_end_date_repeat
        CHECK (end_date IS NULL OR repeat_type <> 'once')
);

CREATE INDEX ix_reminders_due
    ON reminders (next_run_at, id)
    WHERE status = 'active' AND next_run_at IS NOT NULL;

CREATE INDEX ix_reminders_user_created
    ON reminders (user_id, created_at DESC, id DESC);

CREATE TABLE reminder_executions (
    id BIGINT PRIMARY KEY,
    reminder_id BIGINT NOT NULL REFERENCES reminders(id) ON DELETE CASCADE,
    scheduled_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending', 'sending', 'retry_wait', 'accepted', 'failed', 'cancelled'
        )),
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    next_retry_at TIMESTAMPTZ NULL,
    recipient_email VARCHAR(254) NULL,
    error_message TEXT NULL,
    started_at TIMESTAMPTZ NULL,
    finished_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_reminder_executions_schedule
        UNIQUE (reminder_id, scheduled_at)
);

CREATE INDEX ix_reminder_executions_history
    ON reminder_executions (reminder_id, scheduled_at DESC, id DESC);

CREATE INDEX ix_reminder_executions_retry
    ON reminder_executions (next_retry_at, id)
    WHERE status = 'retry_wait';

CREATE INDEX ix_reminder_executions_stale
    ON reminder_executions (started_at, id)
    WHERE status = 'sending';
~~~

### 6.5 Alembic 迁移方案（未来执行）

1. 新增下一 Alembic revision，当前 head 为 0013_rename_general_chat；建议文件名 0014_create_reminders.py，实际 revision id 依生成器规则确定。
2. 在 migrations/env.py 导入 reminders.models。
3. 在一个 migration 中创建上述两张表、具名约束和索引；降级只删除这两张表及其索引。
4. 在已有 skills 注册机制中幂等注册 Reminder 市场元数据（code=reminder、name=提醒助手、type=tool、status=published）。不得改写已有技能或 user_skills 数据。
5. 部署时先备份，再执行 Alembic upgrade；API/Worker/Beat 在 schema 到位后启动。
6. 不把 LangGraph Checkpointer 管理的内部表计入这两张业务表；Reminder 不依赖 Checkpointer。

## 7. 调度与执行架构

### 7.1 组件职责

- FastAPI Router：登录保护、DTO 校验、调用 ReminderService、组织响应。
- ReminderService：业务规则、事务边界、状态校验、时区换算与并发策略。
- ReminderRepository：SQL 查询、行锁、唯一约束冲突和执行历史分页。
- Celery Beat：每 30 秒发送一次扫描任务；只允许一个活动 Beat 实例。
- Celery Worker：处理一条执行记录，完成 SMTP 调用并更新执行结果。
- PostgreSQL：提醒与执行的唯一事实来源。
- Redis：Celery broker；不能作为唯一任务事实来源。
- 邮件基础设施：复用 SMTP 配置和连接发送逻辑，提供通用邮件 API。

### 7.2 Beat 扫描算法与事务边界

每 30 秒运行一个短小的数据库扫描任务，批量上限建议 100 条；每次使用独立 Session。一个事务内：

1. 读取当前 UTC 时间。
2. 查询 status=active 且 next_run_at <= now 的提醒，按 next_run_at、id 排序，使用 FOR UPDATE SKIP LOCKED 和 LIMIT。
3. 对单次提醒，以其 next_run_at 作为 scheduled_at 插入 pending execution；发送进入终态后才清空 next_run_at。扫描重复命中时由唯一约束复用现有执行记录，不重复建行。保留当前计划可让尚未开始的单次提醒继续展示和编辑。
4. 对周期提醒，按本地规则计算不晚于 now 的计划，并依据“仅补发最近一次遗漏”折叠过期计划：最多为该提醒创建一条最近遗漏执行记录，next_run_at 更新为严格晚于 now 的下一次；结束日期后设置 completed、next_run_at=NULL。
5. 在同一轮扫描中，锁定 started_at 早于租约阈值的 sending executions，将其计入一次恢复尝试并转为 retry_wait；超过最大尝试次数则转 failed。Worker 崩溃与 SMTP 结果不明时不能当作确定发送失败处理，需保留重复窗口语义。
6. 插入 execution、更新 reminder.next_run_at/status、恢复过期 sending 必须在 PostgreSQL 事务中提交；不持有这些锁调用 Redis 或 SMTP。
7. 事务提交后，将 pending execution ID 和 next_retry_at <= now 的 retry_wait ID 投递给 Celery。投递失败只记录带 reminder_id/execution_id 的告警，不回滚已提交的业务事务。
8. 后续每轮扫描重新投递仍为 pending 的 execution 和到期 retry_wait，覆盖数据库提交成功但 Redis 投递失败、Redis 重启丢失消息的情况。重复消息由 Worker 的数据库认领保证无副作用。

提醒行锁使同一轮不会被另一个扫描 Worker 同时更新；execution 唯一约束保护重复 Beat 触发和异常重试。不要在持有数据库事务/行锁期间连接 SMTP 或执行 Redis 网络调用。

### 7.3 单次与周期 next_run_at

- 创建时计算首个有效未来计划，并设置 active。
- 单次计划在扫描创建执行记录后保留当前 next_run_at；执行 accepted/failed 终态时清空计划并将 reminder 标记 completed。数据库事务失败时执行状态与提醒状态都不生效。
- 周期计划扫描创建当前 execution，并在同一事务推进 next_run_at。
- 修改计划时重新计算 next_run_at，清除旧的未开始执行，并增加 version。
- 暂停保留当前下一次计划；恢复时按照当前时区和已确认的停机补发规则计算。
- 达到 end_date 后不再创建新执行；最后一个计划完成后 reminder 标记 completed。

### 7.4 Worker 执行步骤

1. 接收 reminder_execution_id，开启短事务，按固定锁顺序读取 Reminder 再读取 Execution。
2. 若 execution 不存在或状态不为 pending/到期 retry_wait，退出，不重复发送。
3. 若 Reminder 已 cancelled/paused，或计划已失效，将未开始 execution 标为 cancelled 并提交。
4. 若账号已不存在或 account 无有效邮箱，记录安全错误并按永久错误终止。
5. 在事务中将 execution 切换为 sending，记录 started_at、recipient_email=users.account，提交认领。
6. 事务外构造纯文本邮件并调用通用 SMTP sender。标题、正文作为数据处理；HTML 模板如提供必须转义用户字段。
7. SMTP 接受后，在短事务将状态写为 accepted、finished_at=now、清空 next_retry_at。
8. 发送失败时按失败类型决定重试或终止；失败摘要写到 error_message，不记录凭据或敏感 SMTP 原文。
9. 单次提醒在 accepted/failed 终态时更新为 completed；周期提醒保留 active/paused 状态及后续 next_run_at。

所有 API/扫描/Worker 操作使用相同锁顺序（Reminder → Execution），避免死锁。较长的 SMTP 调用不持有数据库行锁。

### 7.5 Celery 配置建议

- 新增 Celery（带 Redis transport）依赖；不需要 Celery result backend，执行状态由数据库记录。
- broker URL 复用 Settings.redis_url；配置 queue 名称如 reminders。
- Celery 任务参数只传 Snowflake execution ID，不传整段提醒正文或收件邮箱。
- worker 使用 late ack、worker lost 时 reject/requeue、prefetch 1；SMTP 客户端仍须有自己的 10 秒网络超时。
- Beat 的 30 秒 schedule 使用 Celery crontab/timedelta 配置，不把每个提醒注册为 Beat entry；用户提醒数量不能转化为动态 Beat 配置。
- 可设置任务级软/硬时限大于 SMTP 超时时间；任务实现只协调服务，不承载业务算法。
- Beat 必须单实例；Worker 可多实例。PostgreSQL 行锁/唯一约束负责并发正确性。

## 8. 邮件内容、重试与投递保证

### 8.1 邮件内容

主题建议为“OrionAI 提醒：{标题}”。正文至少包括：

- OrionAI 产品标识。
- 提醒标题和原始内容。
- 原计划提醒时间，按该提醒 timezone 显示，并附时区名称。
- 可选的“此邮件由 OrionAI 自动发送”说明。

计划时间使用 execution.scheduled_at 转换到提醒时区显示；不能用 Worker 实际发送时间替代计划时间。发件地址和显示名来自现有 Settings，默认产品名 OrionAI。

### 8.2 SMTP 复用改造建议

扩展 backend/app/infrastructure/email/email_sender.py，增加接收 recipient、subject、text body 和可选 HTML body 的通用发送函数；沿用 Settings、SMTP SSL/STARTTLS、认证、10 秒 timeout、EmailDeliveryError。验证码函数继续保留既有用途并可委托通用 sender。Reminder Service 只依赖邮件服务接口，不直接创建 SMTP 连接。

SMTP 服务端接受 message 仅代表传输层接受请求。远端退信、垃圾邮件过滤、邮箱不可达、用户未阅读均不能由当前 SMTP API 证明。execution.accepted 的用户可见文案应为“邮件服务已接受发送请求”，不能写“已送达”。

### 8.3 重试策略建议

- 最多 5 次 SMTP 尝试（初次 1 次，最多 4 次重试）。
- 网络超时、连接失败、SMTP 4xx 等暂时故障进入 retry_wait；延迟建议 30 秒、2 分钟、10 分钟、30 分钟，并加入少量随机抖动。
- SMTP 配置缺失、无法认证、明确永久 5xx、收件地址无效可直接 failed；需要邮件基础设施提供足够的错误分类，不能只依赖当前统一 EmailDeliveryError 文案。
- 每次重试前检查 reminder/execution 最新状态；暂停或取消后不再发新请求。
- retry_count 在一次失败后增加；到达最大尝试次数后 status=failed、finished_at=now、next_retry_at=NULL。
- 错误向用户显示简短原因；日志以 execution_id、reminder_id、错误类别关联，不写正文、密码或 SMTP 凭据。

失败分类和尝试上限是工程建议，可作为首版默认值；上线前应确认告警及用户可见错误文案。

### 8.4 幂等边界与异常恢复

两张表可以保证同一提醒同一计划时间最多只有一条 execution、同一 execution 同时只被一个 Worker 认领；不能保证 SMTP 端到端恰好一次。

不可消除的窗口：SMTP 已接受邮件，但 Worker 在写入 accepted 前崩溃或数据库不可用；租约超时后重试可能导致用户收到重复邮件。可使用稳定 Message-ID（例如由 execution ID 确定）协助追踪，但标准 SMTP 不保证收件方按 Message-ID 去重。因此系统按“至少一次尽力发送”设计，并明确存在极小重复窗口，不宣传绝对防重。

恢复策略：
- Beat 重启：恢复后扫描 PostgreSQL 中到期 reminders 与 pending executions。
- Redis 暂不可用：DB 执行记录不丢；投递失败后下一次 Beat 重试。
- Worker 崩溃：sending 且 started_at 超过建议租约阈值（例如 2 分钟）的记录被恢复任务锁定，按 retry 规则重排；阈值应大于 SMTP timeout 和正常处理时间。
- 容器重启：Redis AOF 有助于队列持久化，DB 是权威记录；重复/丢失 broker 消息由 pending 恢复流程吸收。
- 数据库提交成功但队列发布失败：保留 pending，后续 Beat 再发布。
- Redis 接收任务但 Worker 未消费：pending 扫描再发布。
- 邮件已接受但 DB 更新失败：根据过期 sending 恢复重试，可能重复；必须在运行手册和用户说明中承认。
- SMTP 接受但之后退信：当前无退信 Webhook/邮件服务 API，不可能仅凭 SMTP 结果确认；后续若需投递回执需独立评估，不能新增第三张表绕过约束。

## 9. REST API 设计

以下路由遵循现有 /api 前缀、技能模块 /v1 路由形式、Cookie 认证、Origin 校验、Snowflake 字符串返回、请求 JSON 禁止未定义字段。所有写接口增加 validate_origin。错误仍按项目现有 JSON 格式 {"detail":"..."}；文档中的 error key 是稳定业务错误标识，当前不额外改变所有 API 的错误 envelope。

### 9.1 路由清单

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | /api/v1/reminders | 创建提醒，返回 201。 |
| GET | /api/v1/reminders | 查询本人提醒列表。 |
| GET | /api/v1/reminders/{reminder_id} | 查询本人提醒详情。 |
| PUT | /api/v1/reminders/{reminder_id} | 完整替换可编辑规则，需 expected_version。 |
| POST | /api/v1/reminders/{reminder_id}/pause | 暂停周期提醒。 |
| POST | /api/v1/reminders/{reminder_id}/resume | 恢复周期提醒。 |
| POST | /api/v1/reminders/{reminder_id}/cancel | 软取消并保留历史。 |
| GET | /api/v1/reminders/{reminder_id}/executions | 分页查询执行历史。 |

ID 路径参数为 1 到有符号 BIGINT 最大值的十进制数字。不能从 body 接受 user_id 或 recipient_email。读取他人 ID 与不存在的 ID 均返回相同 404，降低资源枚举。

### 9.2 创建提醒

请求示例：

~~~json
{
  "title": "提交周报",
  "content": "整理本周完成事项并提交周报。",
  "repeat_type": "weekly",
  "timezone": "Asia/Shanghai",
  "start_date": "2026-10-28",
  "local_time": "09:30",
  "end_date": "2026-12-31"
}
~~~

成功返回 201：

~~~json
{
  "id": "812345678901234567",
  "title": "提交周报",
  "content": "整理本周完成事项并提交周报。",
  "repeat_type": "weekly",
  "repeat_config": {
    "start_date": "2026-10-28",
    "local_time": "09:30",
    "weekday": 3
  },
  "timezone": "Asia/Shanghai",
  "next_run_at": "2026-10-28T01:30:00Z",
  "end_date": "2026-12-31",
  "status": "active",
  "version": 1,
  "created_at": "2026-10-27T08:00:00Z",
  "updated_at": "2026-10-27T08:00:00Z"
}
~~~

周三的 ISO weekday 为 3。once 请求使用 repeat_type=once、date、local_time、timezone；daily/weekly/monthly 都使用 start_date、local_time 和可选 end_date。收件邮箱不由客户端填写。单次请求示例：

~~~json
{
  "title": "预约复诊",
  "content": "携带检查报告前往医院。",
  "repeat_type": "once",
  "timezone": "Asia/Shanghai",
  "date": "2026-11-02",
  "local_time": "14:00"
}
~~~

### 9.3 列表、详情、编辑和状态操作

- GET 列表支持 status、limit(1–100)、offset(>=0)；默认按 created_at DESC、id DESC。无请求 body。请求：GET /api/v1/reminders?status=active&limit=20&offset=0。响应示例：

~~~json
{
  "items": [
    {
      "id": "812345678901234567",
      "title": "提交周报",
      "content": "整理本周完成事项并提交周报。",
      "repeat_type": "weekly",
      "repeat_config": {"start_date": "2026-10-28", "local_time": "09:30", "weekday": 3},
      "timezone": "Asia/Shanghai",
      "next_run_at": "2026-10-28T01:30:00Z",
      "end_date": "2026-12-31",
      "status": "active",
      "version": 1,
      "created_at": "2026-10-27T08:00:00Z",
      "updated_at": "2026-10-27T08:00:00Z"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
~~~

- GET 详情无请求 body；例如 GET /api/v1/reminders/812345678901234567。成功响应与 9.2 创建成功的 Reminder JSON 对象相同；不存在或非本人资源返回 404。
- PUT 编辑请求示例：

~~~json
{
  "expected_version": 4,
  "title": "提交团队周报",
  "content": "汇总事项并提交。",
  "repeat_type": "weekly",
  "timezone": "Asia/Shanghai",
  "start_date": "2026-10-28",
  "local_time": "10:00",
  "end_date": "2026-12-31"
}
~~~

成功响应示例：

~~~json
{
  "id": "812345678901234567",
  "title": "提交团队周报",
  "content": "汇总事项并提交。",
  "repeat_type": "weekly",
  "repeat_config": {"start_date": "2026-10-28", "local_time": "10:00", "weekday": 3},
  "timezone": "Asia/Shanghai",
  "next_run_at": "2026-10-28T02:00:00Z",
  "end_date": "2026-12-31",
  "status": "active",
  "version": 5,
  "created_at": "2026-10-27T08:00:00Z",
  "updated_at": "2026-10-27T08:10:00Z"
}
~~~

客户端应传读取详情时拿到的版本。更新期间锁 Reminder；若执行正在 sending、状态已终结或 version 不符，返回 409，不覆盖并发更新。对尚未开始的旧 pending/retry_wait 执行置 cancelled，再按新规则计算 next_run_at。

- POST pause、resume、cancel 不需要 body，成功返回更新后的 Reminder DTO；响应结构与上述 PUT 成功 JSON 相同，只是 status、next_run_at、version、updated_at 反映新状态。例如 pause 返回 status=paused、version=5。pause/resume 仅对 weekly/monthly/daily 周期任务开放；cancel 对 active/paused 开放。重复状态操作按幂等设计：已 paused 再 pause、已 active 再 resume 可返回当前资源；已 cancelled/completed 的冲突操作返回 409。
- cancel 把未开始 pending/retry_wait execution 标记 cancelled，保留执行记录；sending 执行无法撤销，允许 SMTP 已开始的请求完成。

### 9.4 执行历史

请求示例：GET /api/v1/reminders/812345678901234567/executions?limit=20&offset=0。

成功响应：

~~~json
{
  "items": [
    {
      "id": "912345678901234567",
      "scheduled_at": "2026-10-28T01:30:00Z",
      "status": "accepted",
      "retry_count": 0,
      "next_retry_at": null,
      "recipient_email_masked": "p***@example.com",
      "error_message": null,
      "started_at": "2026-10-28T01:30:04Z",
      "finished_at": "2026-10-28T01:30:05Z",
      "created_at": "2026-10-28T01:30:00Z"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
~~~

历史按 scheduled_at DESC、id DESC。数据库保留 recipient_email 完整快照供发送与审计；API 只返回 recipient_email_masked，不返回完整地址。

### 9.5 权限、参数与错误码

所有路由依赖 get_current_user；Repository 查询始终包含 reminder.user_id=current_user.id。列表、详情、写操作和 execution 查询都不接受任意 owner ID。所有写操作增加 validate_origin。

| 业务错误 key | HTTP | 场景 |
|---|---:|---|
| reminder_validation_error | 422 | 字段、时区、过去时间、重复规则非法；沿用 FastAPI 校验格式。 |
| reminder_not_found | 404 | ID 不存在或不属于当前用户。 |
| reminder_state_conflict | 409 | 不允许的状态操作、编辑正在发送的计划。 |
| reminder_version_conflict | 409 | expected_version 落后于数据库版本。 |
| reminder_schedule_conflict | 409 | 当前执行进入不可编辑/取消的 SMTP 发送阶段。 |
| reminder_service_unavailable | 503 | 数据库或必要调度依赖短时不可用。 |
| unauthenticated | 401 | Cookie 缺失或失效，使用现有认证错误响应。 |
| invalid_origin | 403 | Origin/Host 不匹配，使用现有认证校验。 |

项目当前业务响应体只有 detail 字段，故错误 key 作为模块异常映射和文档契约；若前端必须依赖机器可读 code，应先在项目层统一错误 schema，不能让本模块悄悄改变其他 API 格式。邮件失败是异步结果，不回写创建/编辑接口错误；用户在执行历史看到 failed 和安全错误摘要。

## 10. 前端页面与交互

### 10.1 技能入口和路由

- skills 元数据注册 Reminder 普通工具；市场分类沿用现有“工具”筛选。
- frontend/src/features/platform/skillUsage.ts 对 reminder 显式跳转 platformPaths.reminders（建议 /reminders），不得走创建会话逻辑。
- frontend/src/app/App.tsx 与 platformData.ts 增加页面路径分派。
- 不新增、重排全局导航入口，遵守 UI_DESIGN.md；从市场卡片和我的技能入口打开管理页。
- 是否必须先将技能加入“我的技能”才能创建提醒，需遵循现有技能授权语义并在开发前确认；建议沿用添加技能流程。

### 10.2 管理页

页面标题“提醒助手”，简短说明“按计划将提醒发送到账号邮箱”。标题区域提供“新建提醒”主操作；列表使用简单表格/紧凑行，不堆叠多层卡片。推荐列：标题与内容摘要、类型、状态、下一次提醒（显示本地时区）、操作。行操作根据状态显示编辑、暂停、恢复、取消；历史入口在详情/展开视图中。

- 空状态：说明尚无提醒，提供创建入口。
- 加载状态：使用轻量骨架/文字提示；保留主内容结构。
- 错误状态：显示可重试提示，不伪造空列表。
- 取消使用现有 ConfirmationDialog，说明取消后的未开始计划不会发送。
- 列表分页或“加载更多”使用现有简单 API 风格，首版可 limit/offset。

### 10.3 创建与编辑表单

表单包括标题、内容、多选类型（单次/每天/每周/每月）、日期、时间、时区、可选结束日期。单次显示指定日期；周期显示开始日期，并清楚说明每周按开始日期星期、每月无该日时跳过。时区默认 Intl.DateTimeFormat().resolvedOptions().timeZone，提供可搜索的时区选择器仅在现有依赖支持时采用；不可为此引入大型日期/时区框架。

提交前显示“提醒将发送到当前账号邮箱”；不提供自定义收件邮箱。字段错误紧邻字段展示；服务端 409 保留用户输入并提示重新加载/合并。成功后返回列表并显示轻量 Toast。

### 10.4 执行历史

按计划时间倒序展示计划时间（本地时区）、实际开始/结束时间、状态、重试次数、安全失败摘要。accepted 文案为“邮件服务已接受”，不写“已送达”。默认不展示完整邮箱，可展示脱敏收件地址。

### 10.5 响应式与可访问性

沿用 PlatformLayout、按钮、Toast、图标、对话框、主题 tokens；不增加新的全局导航结构、字体或颜色。桌面端使用紧凑列表；窄屏将每条提醒改为纵向信息行，操作进入轻量菜单或换行，不允许横向页面溢出。标签关联表单控件，键盘焦点清楚，错误使用文字与语义状态共同表达。

## 11. 后端模块结构

建议按现有模块风格新增：

~~~text
backend/app/modules/reminders/
  __init__.py
  router.py          # 路由、认证依赖、状态码与响应组织
  dependencies.py    # DB Session、CurrentUser、Service 工厂
  schemas.py         # 创建/更新/响应/分页 DTO 与 Pydantic 校验
  models.py          # Reminder、ReminderExecution ORM
  repository.py      # 查询、FOR UPDATE、唯一约束、历史分页
  service.py         # CRUD、状态转换、事务边界、调用时区规则
  recurrence.py      # 本地计划计算、DST 与月末规则
  errors.py          # 提醒业务异常及 HTTP 映射
  tasks.py           # Celery 任务薄封装，只接收 execution ID
  scheduler.py       # 扫描、待投递和过期 sending 恢复
  email.py           # 邮件模板/应用级邮件协调；SMTP 连接仍在 infrastructure
~~~

实际文件可根据已有命名适度合并，避免为目录完整而拆出无实际职责的文件。Celery app 建议放在 backend/app/core/celery_app.py 或独立任务组合入口；不创建 bootstrap/ 目录。将 reminders router 注册到 backend/app/api/router.py；提醒模型加入 Alembic env.py；技能项注册沿用 skills.repository 与 core/application.py 的幂等机制。

依赖方向：Router → Service → Repository/领域函数；Service/Worker → infrastructure.email；Celery task → ReminderService/Scheduler。Infrastructure 不依赖 reminders 业务模块，不把复杂业务规则塞入 task 或 Router。

## 12. Docker 部署方案

### 12.1 服务现状与新增

现有 Compose 只有 backend、PostgreSQL、Redis；SMTP 参数由 backend 注入；没有 Celery 服务。建议未来增加：

- celery-worker：使用 backend 同一构建镜像、工作目录、源代码挂载、数据库/Redis/SMTP 环境变量；运行 Worker 命令并监听 reminders queue。
- celery-beat：同一镜像和配置，运行 Beat 命令；部署只能有一个副本。
- 不需增加新的数据库、Redis 实例或容器镜像。
- 若 Worker 不需要 LangGraph/API 服务启动副作用，应确保 Celery app 导入路径不触发 FastAPI lifespan、LLM 初始化或 Agent Checkpointer setup。

### 12.2 配置与启动

Celery 和 Beat 使用现有 REDIS_URL。队列名、扫描间隔、批量上限、重试策略、发送租约、SMTP 端口、SSL 模式和调用超时均使用代码中的默认配置，不要求添加到 .env；SMTP_HOST、SMTP_USERNAME、SMTP_PASSWORD、SMTP_FROM_EMAIL 等部署相关连接信息由 Compose 传递。Beat 扫描间隔默认为 30 秒；若需调整固定运行策略，直接修改 Settings 或 reminders 常量及相应测试。

建议启动顺序：
1. PostgreSQL、Redis healthcheck 通过。
2. 执行一次 Alembic upgrade head。现有 backend 命令会在启动 Uvicorn 前迁移；新增 Worker/Beat 不应各自并发跑迁移。
3. API、Worker、单实例 Beat 启动。
4. Worker 注册 reminder tasks，启动日志应明确队列和并发配置；Beat 日志显示 30 秒扫描任务。
5. 查看健康检查、数据库连接、Redis broker 连接、SMTP 配置状态；SMTP 缺失时 reminder 发信应在执行记录中失败，不应泄露秘密。

生产与开发部署需避免多副本 backend 同时运行相同迁移命令；可将迁移作为单独 release step。Compose 的 Worker/Beat 使用 restart policy；API 健康检查不能替代 Worker/Beat 运行监控。

### 12.3 容器重启与持久性

PostgreSQL 保存提醒与执行真相；Redis AOF 仅辅助保存 broker 队列。启动后 Beat 扫描到期提醒、pending execution 和过期 sending 记录。服务停机的周期提醒按“仅补发最近一次遗漏”规则追赶，并更新指针至未来计划；不能生成整段积压邮件洪峰。

## 13. 异常处理与可靠性矩阵

| 故障 | 处理方式 | 保证/限制 |
|---|---|---|
| Beat 重复触发 | reminders 行锁 + (reminder_id, scheduled_at) 唯一约束 | 同一计划不会产生两条业务执行记录。 |
| 多扫描 Worker | FOR UPDATE SKIP LOCKED + 批量上限 | 并行处理不同提醒。 |
| Worker 重复收到相同消息 | 原子认领 pending/retry_wait → sending | 第二个消息看到非可认领状态后退出。 |
| DB 提交后 Redis 发布失败 | execution 保持 pending，之后扫描重新投递 | Redis 短时故障不丢提醒。 |
| Worker 执行时崩溃 | sending 租约超时恢复为 retry_wait | SMTP 结果未知时可能重复。 |
| SMTP 连接超时/暂时不可用 | 有界指数退避 | 到上限转 failed 并在历史记录原因。 |
| SMTP 已接受，DB 更新失败 | 租约恢复后可能重试 | 不宣称恰好一次；潜在重复需透明记录。 |
| Redis 重启丢队列 | DB 中 pending 重新发布 | broker 消息不是唯一事实来源。 |
| 容器或服务停机错过周期时间 | 只安排最近遗漏的一次，跳过更早积压，指针推进至未来 | 规则已确认；首版需监控调度延迟。 |
| 用户取消时任务已在队列 | Worker 发送前再次检查 DB 状态 | 未开始任务取消；已进入 SMTP 的调用可能完成。 |
| 编辑与扫描并发 | API 和扫描都锁 Reminder，version 乐观并发校验 | 返回 409 或按事务串行化。 |
| SMTP 远端实际投递失败 | 当前 SMTP sender 无退信查询 | accepted 不等于 delivered；首版无端到端回执。 |

关键指标：扫描延迟、pending 最老年龄、过期 sending 数、retry_wait 数、failed 数、Celery 队列深度、SMTP 错误分类。日志需以提醒/执行 ID 关联，禁止记录正文、密码和敏感邮件内容。

## 14. 测试与验收方案

本节为未来实现验收用例设计；本次不新增或运行测试。时区和数据库锁测试必须补充 PostgreSQL 集成验证，SQLite 无法完整模拟 PostgreSQL SKIP LOCKED 语义。

| 测试场景 | 前置条件 | 执行步骤 | 预期结果 |
|---|---|---|---|
| 单次提醒正常发送 | 用户有有效账号邮箱；SMTP stub 接受 | 创建未来 once；将时钟推进到期；扫描并执行 Worker | 只生成一条 execution，SMTP 收件地址正确，状态 accepted，提醒 completed。 |
| 每日重复 | daily 规则和固定时区 | 依次扫描两次计划时间 | 每日产生一条记录，next_run_at 按本地时间推进。 |
| 每周重复 | 起始日为周三 | 执行扫描并推进到下一周 | 只在每周三执行，跨周按本地 09:30。 |
| 每月重复 | 规则日号 31，覆盖二月与三月 | 推进时钟并反复调度 | 二月跳过，三月 31 日执行，唯一键不冲突。 |
| 结束日期 | end_date 为计划日 | 扫描结束日及其后的计划 | 结束日计划可执行；再无未来计划后标记 completed。 |
| 用户编辑提醒 | active 提醒无 sending execution | 使用当前 expected_version 更新字段 | 规则更新、版本加一、旧 pending 取消、next_run 重算。 |
| 并发编辑冲突 | 两个请求都读取 version=4 | 顺序提交两个更新 | 第一个成功；第二个返回 409，不覆盖前一个。 |
| 编辑与 Worker 认领并发 | 执行接近到期 | 并发编辑和 Worker claim | 一方先锁成功；不出现旧规则重复发送，冲突请求收到 409。 |
| 暂停与恢复 | 周期提醒 active | pause、扫描、resume | 暂停期间不发送未来项；恢复后重新按规则安排。 |
| 暂停时有 pending execution | 已创建 pending、未 SMTP | 暂停并消费旧 Celery 消息 | execution 取消；旧消息 Worker 不发送。 |
| 取消提醒 | active 提醒含 pending | cancel 后执行队列消息 | 提醒 cancelled，pending 标记 cancelled，后续不发送。 |
| 终态操作 | 提醒 completed 或 cancelled | 尝试编辑、恢复、重复取消 | 返回文档定义的 409 或幂等当前状态，不发送新邮件。 |
| 创建过去时间 | once 日期时间小于当前本地时间 | POST 创建 | 422，数据库无提醒记录。 |
| 非法内容与重复规则 | 空标题、过长正文、未知 config 键 | 提交请求 | 422，字段错误可定位，不写数据库。 |
| SMTP 暂时失败后重试 | sender 返回网络超时/SMTP 4xx | Worker 失败并推进时钟至 next_retry_at | retry_count 增加，状态 retry_wait，按策略再次调用。 |
| SMTP 永久失败/次数耗尽 | sender 返回永久错误或每次均失败 | 执行 Worker 直到终态 | 状态 failed、finished_at 非空、不会无限重试。 |
| Worker 领取后异常退出 | execution 处于 sending 且 started_at 超过租约 | 运行恢复扫描，再运行 Worker | 恢复为 retry_wait 并可重新发送；存在 SMTP 结果未知重复窗口。 |
| Redis 暂时不可用 | Beat 扫描能访问 DB，broker 失败 | 创建 execution 后模拟投递异常，恢复 Redis | execution 留为 pending，后续扫描补投且只有一条数据库记录。 |
| Beat 重复扫描 | 使用相同或重叠 now 连续扫描 | 连续调用扫描任务两次 | 唯一约束确保每个 scheduled_at 只有一条 execution。 |
| 多 Worker 并发 | PostgreSQL，两个 Worker 同时处理同一 ID | 并行投递相同 task | 只有一个 Worker 认领并调用 SMTP。 |
| DB 提交成功、发布前进程崩溃 | execution 已 pending | 重启 Beat 并执行扫描 | pending 被重新投递并完成。 |
| SMTP 已接受、状态写入失败 | sender 接受后模拟 DB commit 失败 | 等租约过期并恢复 | 记录进入重试；测试明确验证潜在第二封，不伪称 exactly-once。 |
| 账号邮箱变化 | 创建 reminder 后修改 User.account（测试直接操作） | Worker 首次认领 | 使用认领时最新 account 并保存 recipient_email 快照。 |
| 权限隔离 | 两个用户各有提醒 | 用户 A 查询/编辑/历史访问用户 B 的 ID | 所有请求 404，不泄露对象存在与否。 |
| 夏令时跳时 | 时区存在本地缺失时刻 | 运行 recurrence 计算 | 按待确认策略顺延或拒绝；同一天最多一条计划。 |
| 夏令时重叠 | 时区存在重复本地时刻 | 运行 recurrence 计算 | 按待确认策略生成唯一 instant，不双发。 |
| 不同浏览器时区 | 客户端提交不同 IANA 时区 | 创建相同本地 wall time 的提醒 | next_run UTC 不同但本地显示与输入一致。 |
| 服务重启后遗漏 | 多个计划逾期，Reminder 仍 active | 推进 now 后重启 Beat 扫描 | 每条周期提醒最多补最近一次遗漏，旧遗漏被折叠并推进下次计划。 |
| 邮件内容安全 | 标题/正文含 HTML 特殊字符 | 用可选 HTML 模板发送 | 文本原样可读，HTML 安全转义，不执行注入。 |

## 15. 分阶段开发任务清单

### 阶段 0：确认业务规则

- 确认夏令时缺失/重复本地时刻处理。
- 确认技能是否必须先加入“我的技能”才可管理提醒。
- 确认 execution 历史是否向用户展示脱敏收件邮箱。
- 确认标题/正文长度、重试上限和可见失败文案。
- 复核账号邮箱变化规则；当前项目无邮箱变更流程。

### 阶段 1：数据库与技能元数据

- 新增 Reminder、ReminderExecution ORM 模型及数据库约束。
- 加入 Alembic 元数据导入并创建唯一两张提醒表。
- 在 skills 的幂等注册入口加入 reminder / 提醒助手 / tool。
- 验证迁移升级/回滚及 PostgreSQL 索引、CHECK 和外键。

### 阶段 2：业务 API

- 新增 schemas、repository、service、errors、dependencies、router。
- 实现创建、列表、详情、更新、取消、暂停/恢复、执行历史。
- 所有查询用当前用户 ID；加入 expected_version 和行级锁。
- 注册 API router，保持 detail 错误 envelope 和 Origin 校验。
- 为业务规则、权限和冲突状态增加单元/集成测试。

### 阶段 3：时间规则与 SMTP

- 实现 recurrence 计算、ZoneInfo 校验、DST 策略、月末跳过、end_date。
- 将 SMTP sender 抽出可复用通用邮件接口，验证码行为保持兼容。
- 实现提醒邮件模板、错误分类、超时与有界重试。
- 对 SMTP 使用替身测试，禁止真实测试邮件。

### 阶段 4：Celery 扫描和 Worker

- 添加 Celery Redis 依赖与配置。
- 实现数据库扫描、SKIP LOCKED 认领、execution 唯一键处理、待投递恢复。
- 实现 Worker 短事务认领、事务外邮件发送、执行结果持久化。
- 实现 stale sending 恢复、Beat 30 秒 schedule、指标与结构化日志。
- 完成重复扫描、多 Worker、Redis 故障和 SMTP-DB 不一致测试。

### 阶段 5：前端管理页

- 注册 /reminders 平台路由，技能启动入口直接跳转。
- 新增提醒列表、创建/编辑表单、执行历史视图与 API client。
- 复用现有样式 tokens、按钮、Toast、Dialog 与布局。
- 完成空/加载/错误/冲突/响应式/键盘访问体验验证。

### 阶段 6：部署与灰度

- Compose 增加 Worker、单实例 Beat，共享后端镜像及配置。
- 将迁移作为单次部署步骤；确认 Worker 与 API/Beat 同步发布。
- 配置告警、队列监控、SMTP 配置检查、备份与回滚方案。
- 先在非生产环境用 SMTP stub 验收，再由运维批准真实 SMTP 投递。

## 16. 需要新增或调整的代码点

本次不改代码，后续预期变更如下：

| 区域 | 预期新增/调整 |
|---|---|
| backend/app/modules/reminders | Reminder 独立业务模块及 API、模型、DTO、Service、Repository、调度与薄 Celery Task。 |
| backend/app/infrastructure/email/email_sender.py | 通用 SMTP 邮件方法与可分类异常；兼容现有验证码邮件。 |
| backend/app/core/config.py / backend/pyproject.toml | Celery/broker 与提醒调度配置、依赖声明。 |
| backend/app/core/celery_app.py（建议） | Celery app 和任务发现配置，不触发 API lifespan。 |
| backend/app/api/router.py | 注册 Reminder router。 |
| backend/app/core/application.py、skills.repository.py | 幂等注册 reminder 工具元数据；只新增新技能项，不改已有记录。 |
| backend/migrations/env.py、backend/migrations/versions | 导入模型并新增两表迁移。 |
| docker-compose.yml、部署文档、.env.example | 增加 worker/beat 服务和非秘密配置项；本次不修改。 |
| frontend/src/features/platform/platformData.ts、skillUsage.ts、app/App.tsx | 路由常量、Reminder 工具启动分派和页面渲染。 |
| frontend/src/features/reminders | 管理页、表单、历史、API client 与样式。 |

## 17. 待确认事项与默认建议

已由用户确认：
1. 每周提醒按起始日期的星期重复。
2. 月份不存在指定日号时跳过该月，不改为月末。
3. 服务停机错过多次周期提醒时，只补发最近一次遗漏，其余跳过并推进到未来计划。

建议开发前确认：

| 问题 | 建议默认 | 影响 |
|---|---|---|
| 夏令时跳时/重叠时刻 | 周期缺失时刻顺延到当日首个有效时间；重复时刻取较早 instant；单次歧义/无效时刻拒绝。 | 会影响同一墙上时间与 UTC instant 的映射及验收结果。 |
| 技能授权 | 延续市场模式：用户先添加 Reminder 后，才显示/允许该工具入口；API 仍以登录用户隔离数据。 | 确定“我的技能”中的入口和技能移除后已有提醒是否仍运行。建议移除技能不自动删除/取消已创建提醒。 |
| 执行邮箱展示 | API 历史默认不回传完整 recipient_email，只回脱敏邮箱或不回邮箱。 | 执行表需要完整收件快照供审计，展示应遵守最小化原则。 |
| 失败重试 | 首版最多 5 次尝试；临时错误退避，配置或永久错误立即终止。 | 决定失败等待时长和运维告警阈值。 |
| 周期提醒暂停时已有 retry_wait | 暂停会取消还未开始的当前 occurrence 和后续发送；已进入 SMTP 的调用无法撤回。 | 决定暂停语义是否仅冻结未来提醒，还是同时阻止当前失败重试。本文方案采用后者。 |
| 业务错误 machine code | 首版沿用 {"detail": "..."}，错误 key 留在模块异常和日志；如前端需按 code 分支，先统一项目错误 envelope。 | 避免本模块引入与现有 API 不一致的错误体。 |

## 18. 验收完成标准

- 技能市场可见 Reminder / 提醒助手，类型为 tool，不启动对话。
- 用户只能读取和操作自己的提醒；所有计划规则、执行历史均持久化在上述两张表中。
- 对单次、每日、每周、每月规则、时区、月末和停机补偿行为有稳定自动化验证。
- 重复扫描/多 Worker 不会创建重复执行记录或并行调用同一 execution。
- Redis 暂时不可用及容器重启后可从数据库恢复待执行任务。
- 邮件失败有界重试并保留原因；accepted 明确表示 SMTP 接受，不表示实际投递成功。
- API、前端、Celery、迁移和 Compose 配置通过各自静态检查、自动化测试和部署验收。
- 仅有 reminders、reminder_executions 两张新增提醒业务表。

