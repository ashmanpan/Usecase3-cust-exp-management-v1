# Path Computation Agent Dockerfile
# From DESIGN.md: Query KG Dijkstra for alternate paths
# Port: 8003

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent template (shared code)
COPY agent_template/ ./agent_template/

# Copy this agent
COPY agents/path_computation/ ./agents/path_computation/

# Set Python path
ENV PYTHONPATH=/app

# Expose A2A port
EXPOSE 8003

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8003/health')" || exit 1

# Run agent
CMD ["python", "-m", "agents.path_computation.main"]
