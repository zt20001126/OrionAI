from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.modules.auth.errors import AuthError


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name)

    @application.exception_handler(AuthError)
    async def handle_auth_error(_request: Request, error: AuthError) -> JSONResponse:
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
