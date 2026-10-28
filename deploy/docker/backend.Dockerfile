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

# Playwright 的系统依赖单独成层，避免后续浏览器或字体下载失败时丢失该层缓存。
RUN --mount=type=cache,id=orionai-apt-archives,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=orionai-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && cp /etc/apt/apt.conf.d/docker-clean /tmp/orionai-docker-clean \
    && rm -f /etc/apt/apt.conf.d/docker-clean \
    && python -m playwright install-deps chromium \
    && mv /tmp/orionai-docker-clean /etc/apt/apt.conf.d/docker-clean

# PDF 渲染使用默认无头模式，只安装 Chromium headless shell。
RUN python -m playwright install --only-shell chromium

# 简历模板使用 Noto CJK；独立成层，取包失败时不会重装 Playwright 依赖和浏览器。
RUN --mount=type=cache,id=orionai-apt-archives,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=orionai-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    cp /etc/apt/apt.conf.d/docker-clean /tmp/orionai-docker-clean \
    && rm -f /etc/apt/apt.conf.d/docker-clean \
    && apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && mv /tmp/orionai-docker-clean /etc/apt/apt.conf.d/docker-clean

COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./alembic.ini

# 源码层变化时只更新本地 editable 安装，不触发第三方依赖解析。
RUN python -m pip install --no-build-isolation --no-deps -e .

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]
