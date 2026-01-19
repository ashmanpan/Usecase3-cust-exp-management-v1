# Restoration Monitor Agent Dockerfile - Port 8005
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agent_template/ ./agent_template/
COPY agents/restoration_monitor/ ./agents/restoration_monitor/
ENV PYTHONPATH=/app
EXPOSE 8005
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8005/health')" || exit 1
CMD ["python", "-m", "agents.restoration_monitor.main"]
