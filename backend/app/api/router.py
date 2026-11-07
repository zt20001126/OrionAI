from fastapi import APIRouter

from app.api.health import router as health_router
from app.modules.auth.routers.gitee import router as gitee_oauth_router
from app.modules.auth.routers.router import router as auth_router
from app.modules.conversations.router.router import router as conversations_router
from app.modules.digital_human.router.router import router as digital_human_router
from app.modules.feedback.router import router as feedback_router
from app.modules.image_generation.router import router as image_result_router
from app.modules.membership.router import router as membership_router
from app.modules.membership.router import users_router as membership_users_router
from app.modules.memory_training.router import router as memory_training_router
from app.modules.payment.router import router as payment_router
from app.modules.payment.router import webhook_router as payment_webhook_router
from app.modules.reminders.router import router as reminders_router
from app.modules.resume.router import router as resume_router
from app.modules.skills.router import router as skills_router
from app.modules.tourism_insight.router.router import router as tourism_insight_router
from app.modules.users.router import router as users_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(gitee_oauth_router, prefix="/v1/auth")
api_router.include_router(conversations_router)
api_router.include_router(digital_human_router)
api_router.include_router(feedback_router)
api_router.include_router(skills_router)
api_router.include_router(users_router)
api_router.include_router(image_result_router)
api_router.include_router(memory_training_router)
api_router.include_router(resume_router)
api_router.include_router(reminders_router)
api_router.include_router(membership_router)
api_router.include_router(membership_users_router)
api_router.include_router(payment_router)
api_router.include_router(payment_webhook_router)
api_router.include_router(tourism_insight_router)
