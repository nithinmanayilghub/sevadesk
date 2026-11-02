# Builds the backend image: installs locked dependencies, runs migrations, then starts the API.
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /usr/local/bin/uv

WORKDIR /app
# Install only locked, non-dev dependencies (this layer is cached until the lock changes).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# The app is not installed as a package, so make "app" importable and use the uv venv.
ENV PYTHONPATH=/app
ENV PATH="/app/.venv/bin:$PATH"

COPY . .

# The version shown by /api/v1/hello. Override with --build-arg APP_VERSION=...
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
