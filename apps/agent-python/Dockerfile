FROM python:3.11-slim

WORKDIR /app

# Install system deps for chromadb
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python deps
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]" || pip install --no-cache-dir \
    fastapi uvicorn pydantic pydantic-settings httpx anthropic \
    chromadb sentence-transformers structlog python-dotenv

# Copy app code
COPY apps/agent-python/app/ app/
COPY packages/ packages/

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
