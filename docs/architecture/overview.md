# 架构概览

OrionAI 当前为 Monorepo 和前后端分离的模块化单体基础骨架，包含邮箱认证基础功能。React/Vite 前端通过 /api 代理访问 FastAPI；FastAPI 路由按模块聚合，基础设施目录集中封装数据库、Redis 和 SMTP 连接。用户账号保存在 PostgreSQL 的 users 表，验证码和会话保存在 Redis；Agent 执行流程尚未实现。

新增业务时，应由 API Router 调用对应模块的 Service；数据访问由 Repository 或模块内数据访问组件负责；Agent 业务管理放在 modules/agents/，执行引擎放在 agent/。模块间保持单向依赖。
