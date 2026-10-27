# syntax=docker/dockerfile:1.7

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/pyproject.toml ./pyproject.toml

# pyproject.toml 完整描述构建依赖、项目依赖和 dev 可选依赖。
# 单独安装这些依赖，使业务代码变化不会使该层失效。
RUN --mount=type=cache,id=orionai-pip,target=/root/.cache/pip,sharing=locked \
    python - <<'PY'
import subprocess
import sys
import tomllib
from pathlib import Path

project_data = tomllib.loads(Path("pyproject.toml").read_text())
project = project_data["project"]
requirements = (
    project_data["build-system"]["requires"]
    + project["dependencies"]
    + project.get("optional-dependencies", {}).get("dev", [])
)
subprocess.check_call([sys.executable, "-m", "pip", "install", *requirements])
PY

COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./alembic.ini

# 源码层变化时只更新本地 editable 安装，不触发第三方依赖解析。
RUN python -m pip install --no-build-isolation --no-deps -e .

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]
