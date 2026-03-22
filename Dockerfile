FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml ./
COPY src/ ./src/

# Install dependencies (no dev deps)
RUN uv sync --no-dev

# Non-root user for security
RUN useradd -m -u 1000 webgate
USER webgate

# MCP servers communicate over stdio — no port needed
CMD ["uv", "run", "mcp-webgate"]
