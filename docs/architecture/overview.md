# 架构概览

本文描述当前仓库实现；带日期的需求和实施方案是历史设计记录。OrionAI 是 React/TypeScript/Vite 前端与 Python/FastAPI 后端组成的 Monorepo、模块化单体。前端通过 `/api` 访问后端；运行时使用 PostgreSQL、Redis、对象存储和外部模型服务。

## 边界与调用

- `backend/app/api/` 聚合路由，`core/` 管理应用和 Agent 的生命周期；业务模块负责各自 Router、Service、Repository 和模型。
- `modules/conversations/` 管理会话和消息，按技能代码从 `modules/agents/registry.py` 选择运行时。`agent/` 提供通用 Agent 能力；图片、简历、文旅和数字人有各自的编排。会话支持同步、SSE 和可监听、可中断的运行。
- 应用启动时注册通用对话、图片、简历、数字人、文旅洞察、提醒和记忆训练技能，并初始化模型与 LangGraph Checkpointer。Checkpointer 使用独立 `CHECKPOINT_DATABASE_URL`；业务数据使用 `DATABASE_URL`。
- 数字人复用对话运行时和历史，提供语音识别、合成，以及日期、天气、新闻、文献、行情、提醒和图片/视频生成工具。图片助手使用 TokenHub；数字人生图和视频使用百炼。媒体结果通过受控接口读取。
- 文旅洞察导入 Excel 评分规则和 CSV 评论，保存分析匹配与情感结果；简历模块保存结构化简历并支持照片及 PDF 导出。
- 会员服务以数据库期限为准，Redis 缓存准入结果；Stripe 测试支付通过签名 Webhook 处理订单。技能执行、部分训练和提醒写操作受会员准入限制。
- Celery Worker 处理提醒投递与记忆训练题目生成；Beat 定期扫描提醒。Redis 是消息 broker，提醒规则和执行状态保存在 PostgreSQL。

## 数据与隔离

注册用户和访客均有 `users.id`，业务数据按用户隔离；Cookie 对应会话与验证码存于 Redis。会话消息、技能、任务结果、提醒、会员和文旅数据存于 PostgreSQL；图片、视频等文件存于 OSS，任务记录保存元数据。LangGraph Checkpointer 的内部表由其自身管理。主要业务 ID 使用应用侧 Snowflake，API 中的相关 ID 以字符串传输；并发进程须配置不同的 `SNOWFLAKE_WORKER_ID`。

具体路由、表及配置分别见 [API](../api/api.md)、[数据库](../database/database.md) 和 [本地开发](../development/local-setup.md)。
