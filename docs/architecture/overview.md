# 架构概览

OrionAI 当前为 Monorepo 和前后端分离的模块化单体，包含邮箱认证与基础对话智能体。React/Vite 前端通过 /api 代理访问 FastAPI；FastAPI 路由按模块聚合，基础设施目录集中封装数据库、Redis、SMTP 和 DeepSeek OpenAI-compatible 模型客户端。用户、会话和消息保存在 PostgreSQL；验证码及登录状态保存在 Redis。

对话 API 的 Router 调用 `modules/conversations` Service；Service 通过 Repository 读写 `conversations/messages`，并调用 `agent/` 中的 BaseAgent 门面。新会话首条消息会触发标题生成器并与 Agent 并行；结果仅在标题为空时写入现有会话字段，模型失败时回退为首条消息摘要。Agent 图由 input、model、tool、output 节点组成；LangGraph Checkpointer 在应用 lifespan 内建立，按认证用户和会话生成稳定线程 ID，使题卡等待可跨请求恢复。模型配置由 `core/config.py` 管理，Provider 位于 `infrastructure/llm/`。Agent 只接收显式注入的模型、工具和 Checkpointer，不直接访问 FastAPI 或 ORM。

`users`、`conversations`、`messages`、`skills` 和 `user_skills` 的 BIGINT 主键由 `infrastructure/database/snowflake.py` 在应用侧生成，业务外键使用对应的 BIGINT ID。`SNOWFLAKE_WORKER_ID` 必须在同时运行的 backend 实例间保持唯一；API 将 Snowflake ID 作为十进制字符串返回，避免 JavaScript 精度损失。
