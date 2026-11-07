# 本地开发

启动、测试和格式化命令见[项目 README](../../README.md)。环境变量以根目录 `.env.example` 为模板，应用配置及默认值以 `backend/app/core/config.py` 为准。不要提交 `.env` 或真实密钥。

## 配置与依赖

- `DATABASE_URL` 指向业务库，`CHECKPOINT_DATABASE_URL` 指向 LangGraph 状态库；模板使用宿主机 `localhost:5434`，容器内自动转换为 Compose PostgreSQL 地址。PostgreSQL 入口只初始化业务数据库，不会创建 Checkpointer 数据库；全新数据卷需按 README 手动创建。已有数据的迁移应先核对数据库状态。
- `REDIS_URL` 用于会话、验证码、会员准入缓存和 Celery broker；Compose 中各服务显式使用容器内 Redis 地址。
- Compose 要求非空的 DeepSeek、百炼和 TokenHub 配置（具体变量参见 README）；实际模型调用还需要有效凭据。SMTP 和 `AUTH_CODE_PEPPER` 支持认证、邮件提醒及反馈；OSS 支持头像、生成媒体和训练图片。相关凭据缺失会使对应功能不可用。
- 会员支付仅支持 Stripe Sandbox；设置 `STRIPE_SECRET_KEY`、`STRIPE_WEBHOOK_SECRET` 和前端返回地址后，还需让 Stripe Webhook 到达 `/api/payments/stripe/webhook`。GNews 功能使用 `GNEWS_API_KEY`；数字人文献查询使用 `OPENALEX_API_KEY`。OpenAlex 请求超时、重试和数量上限由数字人文献工具代码常量控制。语音及数字人生图、视频的模型和限额见配置代码。
- Compose 的 `environment` 明确列出了传入容器的变量；`.env.example` 中的其他变量不一定自动传入容器。需要覆盖时应检查或调整服务配置。

## 后台任务

Compose Worker 监听 `reminders,memory_training`，Beat 周期扫描提醒；Beat 保持单实例。API 启动前执行 Alembic 迁移，Worker 和 Beat 等待 API 健康。宿主机启动后端时，在 `backend/` 并激活虚拟环境后，分别运行：

```powershell
python -m celery -A app.core.celery_app:celery_app worker --loglevel=INFO --queues=reminders,memory_training --pool=solo
python -m celery -A app.core.celery_app:celery_app beat --loglevel=INFO
```

并发运行的 API、Worker 和 Beat 进程应配置不同的 `SNOWFLAKE_WORKER_ID`；Compose 分别使用默认 1、2、3。记忆训练素材同步命令见 README。PostgreSQL 与 Redis 数据持久化在 Compose 卷中，删除卷会删除本地数据。
