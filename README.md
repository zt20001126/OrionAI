# OrionAI

OrionAI 是一个面向企业级 AI 智能体应用的平台基础骨架。仓库采用 Monorepo 管理前后端，当前实现邮箱及访客认证、技能市场、智能体对话、数字人、图片助手、简历助手、文旅洞察、记忆训练、提醒、会员与测试支付等功能。知识库和通用工作流尚未作为完整业务提供。

## 技术栈

- 前端：React 19.3、TypeScript 6、Vite 8
- 后端：Python 3.12+、FastAPI、LangGraph
- 数据：PostgreSQL 17、Redis 7.4、SQLAlchemy 2、Alembic
- 本地部署：Docker Compose

## 目录概览

~~~text
frontend/                 React + TypeScript 前端
backend/app/              FastAPI 模块化单体应用
backend/migrations/       Alembic 迁移环境
backend/tests/            后端测试
deploy/docker/            前后端开发镜像
deploy/nginx/             Nginx 配置预留目录
docs/                     架构与开发文档
docker-compose.yml        前端、后端、Celery Worker/Beat、PostgreSQL、Redis
AGENTS.md                 Codex 项目开发约束
~~~

## 项目文档

- [API 接口文档](docs/api/api.md)
- [数据库表结构](docs/database/database.md)
- [架构概览](docs/architecture/overview.md)
- [本地开发](docs/development/local-setup.md)
- [前端设计规范](docs/design/UI_DESIGN.md)
- [历史需求](docs/requirements/)与[历史实施方案](docs/implementation-plans/)：记录编写时的设计，实际行为以代码和当前文档为准。

## 本地开发环境要求

- Windows 10/11
- Node.js 24 LTS 与 npm
- Python 3.12 或更高版本（Docker 后端镜像使用 Python 3.12）
- Docker Desktop（启用 Linux 容器）及 Docker Compose

## 环境变量

先在项目根目录复制示例文件：

~~~powershell
Copy-Item .env.example .env
~~~

.env.example 也包含认证和 SMTP 配置项。宿主机后端使用 localhost，Compose 后端使用容器内的 postgres 和 redis 地址。数据库默认密码为 orionai，仅用于本地开发；若自定义账号或密码，请同步修改 docker-compose.yml。不要提交 .env 或真实密钥。

认证和邮件功能需要随机的 `AUTH_CODE_PEPPER`，以及 SMTP 主机、账号、密码和发件人邮箱。Compose 启动还要求填写 `DATABASE_URL`、`CHECKPOINT_DATABASE_URL`、`DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL`、`ALIYUN_BAILIAN_API_KEY`、`ALIYUN_BAILIAN_BASE_URL` 和 `TENCENT_TOKENHUB_API_KEY`；按功能配置 OSS、Stripe 和 GNews。完整说明见[本地开发](docs/development/local-setup.md)。SMTP 默认使用 SSL 端口 465，发件人名称默认为 `OrionAI`；会话 Cookie 默认有效 7 天，并在 production 环境启用 `Secure`。验证码和会话保存在 Redis；注册账号及访客身份保存在 `users` 表，业务数据存储在其他业务表。邮件配置不完整时，请求验证码会返回 503。

### 认证接口

| 接口 | 用途 |
| --- | --- |
| `POST /api/auth/email-codes` | 请求注册或重置密码验证码（`email`、`purpose`） |
| `POST /api/auth/register` | 验证邮箱并创建账号（`email`、`code`、`password`、`password_confirmation`） |
| `POST /api/auth/login` | 邮箱密码登录（`email`、`password`） |
| `GET /api/auth/session` | 恢复当前 Cookie 会话 |
| `POST /api/auth/logout` | 撤销当前会话 |
| `POST /api/auth/password-reset` | 验证邮箱并重置密码 |

验证码有效 10 分钟、同一邮箱用途 60 秒内不能重发，最多输错 5 次；注册和密码重置用途独立。重置密码请求对未知邮箱返回通用成功响应且不发送邮件。成功登录/注册只返回账号信息，会话令牌仅出现在 HttpOnly Cookie 中。

## Docker Compose 启动

首次使用全新 PostgreSQL 数据卷时，先启动数据库并创建 Checkpointer 数据库（以下使用 `.env.example` 的默认用户名和数据库名；自定义时请相应调整）：

~~~powershell
docker compose up -d postgres redis
docker compose exec postgres createdb -U orionai -O orionai checkpoint
~~~

确认 `.env` 中 Compose 必填变量均已配置后，在项目根目录启动全部服务：

~~~powershell
docker compose up -d --build
~~~

Compose 启用 Uvicorn 热重载并监视 `.py` 和 `.md` 文件。后端代码通过目录挂载同步到容器，日常修改 Python、Agent 或 Prompt 文件不需要重新构建；依赖或 `pyproject.toml` 变化时再执行 `--build`。

Compose 启动前端 Vite 开发服务器、后端、PostgreSQL、Redis、提醒 Celery Worker 和 Beat。前端源代码目录挂载到容器中，修改页面代码会触发热更新；修改 `package.json` 或 `package-lock.json` 后需要重新构建前端镜像：

~~~powershell
docker compose up -d --build frontend
~~~

Worker 消费 `reminders` 和 `memory_training` 队列。前端容器通过 Compose 内部网络将 `/api` 请求代理到 `backend:8000`。如果只在宿主机启动前后端，可按下方“分别启动前后端”操作。

Compose 文件中的 API、Worker 和 Beat 均等待 PostgreSQL 与 Redis 健康检查；仅 API 容器在启动 Uvicorn 前执行 Alembic 迁移。提醒扫描由 Celery Beat 每 30 秒触发，Beat 必须保持单实例。提醒规则和执行状态以 PostgreSQL 为准，Redis 仅作为 Celery broker。

记忆训练图片不会在 Docker 启动时同步到 OSS。新增或维护 `frontend/public/memory-training-assets/` 中的素材后，先启动 Compose，再显式运行以下命令，将缺失或内容变化的图片写入 OSS，并幂等登记图片 URL：

~~~powershell
docker compose exec backend python -m app.scripts.upload_memory_images /app/memory-training-assets
~~~

Compose 默认给 API、提醒 Worker 和 Beat 分配不同的 Snowflake worker ID。若增加 Worker 容器，需在该服务配置中为每个同时运行的进程设置唯一 `SNOWFLAKE_WORKER_ID`；不要横向扩展 Beat。

打开 http://localhost:5173 查看前端，http://localhost:8000/api/health 检查后端，http://localhost:8000/docs 查看 FastAPI 自动生成的接口文档。停止 Compose 服务：

~~~powershell
docker compose down
~~~

如需删除本地数据库和 Redis 持久卷，可额外运行 docker compose down -v。

## 分别启动前后端

若要在宿主机分别运行前后端，可只用 Docker 启动 PostgreSQL 和 Redis。首次使用新数据卷时也需要按上文创建 `checkpoint` 数据库：

~~~powershell
docker compose up -d postgres redis
~~~

安装并启动前端：

~~~powershell
Set-Location frontend
npm ci
npm run dev
~~~

另开 PowerShell 窗口安装并启动后端：

~~~powershell
Set-Location backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
~~~

该命令使用 Windows Python 启动器创建虚拟环境；也可使用已有的 Python 3.12+。宿主机运行时还需另行启动 Celery Worker 和 Beat 才能使用异步记忆训练及提醒，命令见[本地开发](docs/development/local-setup.md)。前端 Vite 将 /api 请求代理到本机的 http://localhost:8000。

## 测试、格式化与静态检查

前端（在 frontend/）：

~~~powershell
npm run typecheck
npm run lint
npm run test
npm run build
npm run format:check
~~~

后端（在 backend/ 且已安装开发依赖）：

~~~powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
~~~

格式化前端文件可运行 npm run format；格式化 Python 文件可运行 python -m ruff format .。
