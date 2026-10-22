# Dev-образ backend и worker. Production-образ — задача 4.4.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1

WORKDIR /app

COPY requirements/ requirements/
RUN uv pip install --no-cache -r requirements/dev.txt

COPY . .

EXPOSE 8000
