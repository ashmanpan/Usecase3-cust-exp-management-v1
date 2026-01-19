# Orchestrator Agent Dockerfile

FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy agent template (shared library)
COPY agent_template /app/agent_template

# Copy orchestrator agent
COPY agents/orchestrator /app/agents/orchestrator

# Install dependencies
COPY agent_template/pyproject.toml /app/
RUN pip install --no-cache-dir -e .

# Create non-root user
RUN useradd --create-home --shell /bin/bash agent && \
    chown -R agent:agent /app
USER agent

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    LOG_FORMAT=json \
    LOG_LEVEL=INFO

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Working directory
WORKDIR /app/agents/orchestrator

# Entry point
CMD ["python", "main.py"]
