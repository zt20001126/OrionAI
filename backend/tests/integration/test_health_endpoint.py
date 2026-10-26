from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.application import create_app


@asynccontextmanager
async def _test_lifespan(_application: FastAPI):
    """健康检查不需要启动对话 Agent 和 PostgreSQL Checkpointer。"""

    yield


def test_health_endpoint_returns_service_status() -> None:
    with TestClient(create_app(lifespan=_test_lifespan)) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "OrionAI"}
