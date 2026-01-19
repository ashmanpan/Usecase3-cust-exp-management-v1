# Event Correlator Agent Dockerfile
# From DESIGN.md: Alert correlation, flap detection, deduplication
# Port: 8001

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
COPY agents/event_correlator/ ./agents/event_correlator/

# Set Python path
ENV PYTHONPATH=/app

# Expose A2A port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" || exit 1

# Run agent
CMD ["python", "-m", "agents.event_correlator.main"]
