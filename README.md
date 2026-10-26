# OrionAI

OrionAI 是一个面向企业级 AI 智能体应用的平台基础骨架。仓库采用 Monorepo 管理前后端，当前包含邮箱注册、邮箱密码登录、忘记密码和 Cookie 会话；对话、知识库、智能体和工作流业务尚未实现。

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
docker-compose.yml        后端、PostgreSQL、Redis
AGENTS.md                 Codex 项目开发约束
~~~

## 项目文档

- [API 接口文档](docs/api/api.md)
- [数据库表结构](docs/database/database.md)
- [架构概览](docs/architecture/overview.md)

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

认证只需配置随机的 `AUTH_CODE_PEPPER`，以及 SMTP 主机、账号、密码和发件人邮箱。SMTP 默认使用 SSL 端口 465，发件人名称默认为 `OrionAI`；会话 Cookie 默认有效 7 天，并在 production 环境启用 `Secure`。验证码和会话保存在 Redis；账号、scrypt 密码哈希、创建时间和最后登录时间保存在唯一的 `users` 表。邮件配置不完整时，请求验证码会返回 503。

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

在项目根目录运行：

~~~powershell
docker compose up --build
~~~

Compose 只启动后端、PostgreSQL 和 Redis。前端在另一个终端单独运行：

~~~powershell
Set-Location frontend
npm run dev
~~~

Compose 文件中的服务按 `backend`、`postgres`、`redis` 顺序排列。后端依赖数据库和 Redis 的健康检查，实际启动时会等它们就绪；后端容器启动时会先执行 Alembic 迁移。

打开 http://localhost:5173 查看前端，http://localhost:8000/api/health 检查后端，http://localhost:8000/docs 查看 FastAPI 自动生成的接口文档。停止 Compose 服务：

~~~powershell
docker compose down
~~~

如需删除本地数据库和 Redis 持久卷，可额外运行 docker compose down -v。

## 分别启动前后端

若要在宿主机分别运行前后端，可只用 Docker 启动 PostgreSQL 和 Redis：

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
conda run -n agent python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
~~~

此命令使用名为 agent 的 Python 3.12 Conda 环境创建项目虚拟环境；若环境名称不同，请替换 agent，或使用已安装的 py -3.12。前端 Vite 将 /api 请求代理到本机的 http://localhost:8000。

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
