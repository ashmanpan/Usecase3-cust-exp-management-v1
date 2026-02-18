# Traffic Analytics Agent Dockerfile - Port 8006
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agent_template/ ./agent_template/
COPY agents/traffic_analytics/ ./agents/traffic_analytics/
RUN groupadd -r agent && useradd -r -g agent -d /app -s /sbin/nologin agent && \
    chown -R agent:agent /app
ENV PYTHONPATH=/app
USER agent
EXPOSE 8006
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8006/health')" || exit 1
CMD ["python", "-m", "agents.traffic_analytics.main"]
