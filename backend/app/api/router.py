from fastapi import APIRouter

from app.api.health import router as health_router
from app.modules.agents.image_agent.router import router as image_agent_router
from app.modules.auth.router import router as auth_router
from app.modules.conversations.router import router as conversations_router
from app.modules.skills.router import router as skills_router
from app.modules.users.router import router as users_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(conversations_router)
api_router.include_router(skills_router)
api_router.include_router(users_router)
api_router.include_router(image_agent_router)
