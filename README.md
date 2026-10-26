# OrionAI

OrionAI 是一个面向企业级 AI 智能体应用的平台基础骨架。仓库采用 Monorepo 管理前后端，当前仅包含可启动的前端基础页、FastAPI 健康检查、数据库与 Redis 连接配置及开发环境；登录、对话、知识库、智能体和工作流业务尚未实现。

## 技术栈

- 前端：React 19.3、TypeScript 6、Vite 8
- 后端：Python 3.12+、FastAPI、LangGraph
- 数据：PostgreSQL 17、Redis 7.4、SQLAlchemy 2、Alembic
- 本地部署：Docker Compose

## 目录概览

~~~text
frontend/                 React + TypeScript 前端
backend/app/              FastAPI 模块化单体应用
backend/migrations/       Alembic 迁移环境（无业务迁移）
backend/tests/            后端测试
deploy/docker/            前后端开发镜像
deploy/nginx/             Nginx 配置预留目录
docs/                     架构与开发文档
docker-compose.yml        前端、后端、PostgreSQL、Redis
AGENTS.md                 Codex 项目开发约束
~~~

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

.env.example 中的数据库密码仅为本地开发占位值。需要共享或部署时，请替换为本地专用值，不要提交 .env 或真实密钥。Compose 会通过服务名连接容器内的 PostgreSQL 和 Redis；直接在宿主机运行后端时，默认连接 localhost。

## Docker Compose 启动

在项目根目录运行：

~~~powershell
docker compose up --build
~~~

打开 http://localhost:5173 查看前端，http://localhost:8000/api/health 检查后端，http://localhost:8000/docs 查看 FastAPI 自动生成的接口文档。停止服务：

~~~powershell
docker compose down
~~~

如需删除本地数据库和 Redis 持久卷，可额外运行 docker compose down -v。

## 分别启动前后端

先启动 PostgreSQL 和 Redis：

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
python -m uvicorn app.main:app --reload
~~~

此命令使用名为 agent 的 Python 3.12 Conda 环境创建项目虚拟环境；若环境名称不同，请替换 agent，或使用已安装的 py -3.12。前端 Vite 将 /api 请求代理到本机的 http://localhost:8000。数据库迁移环境已经初始化，当前没有业务表或迁移版本。

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