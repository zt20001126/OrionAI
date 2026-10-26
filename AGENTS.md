# OrionAI 开发约束

## 项目概述

OrionAI 是企业级 AI 智能体应用平台的基础骨架，采用 Monorepo、前后端分离和模块化单体架构。前端使用 React、TypeScript、Vite；后端使用 Python、FastAPI、LangGraph；数据层使用 PostgreSQL、Redis、SQLAlchemy 和 Alembic。

## 目录职责

- frontend/：前端应用。
- frontend/src/features/：按业务组织前端功能模块。
- frontend/src/components/：跨业务通用 UI 与布局组件。
- backend/app/core/：核心配置与应用生命周期。
- backend/app/api/：API 路由定义和聚合。
- backend/app/modules/：后端业务模块。
- backend/app/agent/：Agent 执行引擎。
- backend/app/infrastructure/：数据库、Redis、LLM、对象存储等基础设施适配。
- backend/app/shared/：少量跨模块公共代码。
- docs/：架构、API、需求和开发文档。
- deploy/：容器和部署配置。

## 架构边界

- Router 负责接收请求、校验参数和组织响应。
- Service 负责业务逻辑；Repository 负责数据访问。
- Agent Runtime 负责智能体执行。
- Infrastructure 负责外部基础设施适配，不承载具体业务逻辑。
- 不把复杂业务逻辑直接写进 Router。
- modules/agents/ 管理智能体业务，agent/ 执行智能体。
- 不额外创建 bootstrap/；应用生命周期统一由 core/ 管理。
- 保持清晰、单向的依赖关系，避免循环依赖。

## 编码规范

- Python 遵循 PEP 8 并添加类型注解。
- TypeScript 启用严格类型检查。
- 代码使用规范英文命名；注释和项目文档优先使用中文。
- 避免重复代码和不必要的抽象。
- 不提前引入微服务、Kubernetes 等复杂架构。
- 不为追求目录齐全而创建无实际用途的文件。

## Codex 开发约束

- 修改代码前先阅读相关模块，优先复用现有实现。
- 遵循最小必要修改原则；新功能放入对应业务模块。
- 重要架构变更先说明方案。
- 不擅自增加新框架或大型依赖，不随意调整整体目录结构。
- 修改后执行相关测试和静态检查，并如实报告结果。
- 不虚构测试结果，不在代码或文档中泄露密钥。

## 前端 UI 规则

- 任何前端开发任务开始前，必须先阅读 [docs/design/UI_DESIGN.md](docs/design/UI_DESIGN.md)。
- 新页面必须与现有登录注册页、技能市场页保持一致的 OrionAI Light Design System 视觉语言。
- 优先复用现有公共组件、页面壳层、图标组件和全局主题变量。
- 不允许随意引入新的颜色体系、字体或组件风格。
- 不允许自行改变全局导航结构和页面布局规范。
- 页面可以根据业务需求采用不同布局，但必须保持统一视觉风格。
- 如果新需求需要突破现有规范，必须先说明原因并请求确认。
- 修改页面时应保留已有业务逻辑和交互功能。
