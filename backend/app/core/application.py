"""创建 FastAPI 应用并管理 Agent 依赖的生命周期。"""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy.exc import SQLAlchemyError

from app.agent import create_basic_conversation_agent
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.infrastructure.database.session import SessionLocal
from app.infrastructure.llm import ModelProviderError, OpenAICompatibleChatModelProvider
from app.modules.agents.image_agent.runtime.image_agent import ImageAgent
from app.modules.agents.registry import AgentRegistry
from app.modules.auth.errors import AuthError
from app.modules.conversations.errors import ConversationError
from app.modules.conversations.title import ModelConversationTitleGenerator
from app.modules.image_generation.providers.result_downloader import ImageResultDownloader
from app.modules.image_generation.providers.tokenhub_client import TokenHubImageClient
from app.modules.image_generation.service import TaskResultStore
from app.modules.skills.errors import SkillsError
from app.modules.skills.repository import ensure_general_chat_skill, ensure_image_agent_skill
from app.modules.users.errors import UsersError

logger = logging.getLogger(__name__)


def create_agent_lifespan(
    settings: Settings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """构建生产 Agent；Checkpointer 自有 schema 由其 setup 管理。"""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        try:
            model_provider = OpenAICompatibleChatModelProvider(settings)
            chat_model = model_provider.create_chat_model()
            title_model = model_provider.create_chat_model()
        except ModelProviderError:
            logger.exception("conversation_agent_provider_configuration_failed")
            raise
        database_url = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        async with AsyncPostgresSaver.from_conn_string(database_url) as checkpointer:
            await checkpointer.setup()
            with SessionLocal() as session:
                try:
                    ensure_general_chat_skill(session)
                    ensure_image_agent_skill(session)
                except SQLAlchemyError:
                    session.rollback()
                    logger.exception("general_chat_skill_initialization_failed")
                    raise
            conversation_agent = create_basic_conversation_agent(
                chat_model=chat_model,
                checkpointer=checkpointer,
            )
            image_agent = ImageAgent(
                settings=settings,
                chat_model=chat_model,
                checkpointer=checkpointer,
                task_store=TaskResultStore(),
                tokenhub_client=TokenHubImageClient(settings),
                result_downloader=ImageResultDownloader(
                    timeout_seconds=settings.tokenhub_timeout_seconds,
                    max_bytes=settings.image_result_max_bytes,
                ),
            )
            application.state.conversation_agent = conversation_agent
            application.state.agent_registry = AgentRegistry(
                {"general_chat": conversation_agent, "image_agent": image_agent}
            )
            application.state.conversation_title_generator = ModelConversationTitleGenerator(
                model=title_model,
                timeout_seconds=settings.conversation_title_timeout_seconds,
            )
            yield
            del application.state.conversation_agent
            del application.state.agent_registry
            del application.state.conversation_title_generator

    return lifespan


def create_app(
    *,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None,
) -> FastAPI:
    """创建应用；可注入测试 lifespan，生产默认启用 PostgreSQL Checkpointer。"""

    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        lifespan=lifespan or create_agent_lifespan(settings),
    )

    @application.exception_handler(AuthError)
    async def handle_auth_error(_request: Request, error: AuthError) -> JSONResponse:
        return JSONResponse(status_code=error.status_code, content={"detail": error.detail})

    @application.exception_handler(ConversationError)
    async def handle_conversation_error(
        _request: Request, error: ConversationError
    ) -> JSONResponse:
        return JSONResponse(status_code=error.status_code, content={"detail": error.detail})

    @application.exception_handler(SkillsError)
    async def handle_skills_error(_request: Request, error: SkillsError) -> JSONResponse:
        return JSONResponse(status_code=error.status_code, content={"detail": error.detail})

    @application.exception_handler(UsersError)
    async def handle_users_error(_request: Request, error: UsersError) -> JSONResponse:
        return JSONResponse(status_code=error.status_code, content={"detail": error.detail})

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_router, prefix=settings.api_prefix)
    return application
