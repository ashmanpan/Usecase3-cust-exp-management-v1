# Tunnel Provisioning Agent Dockerfile - Port 8004
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agent_template/ ./agent_template/
COPY agents/tunnel_provisioning/ ./agents/tunnel_provisioning/
ENV PYTHONPATH=/app
EXPOSE 8004
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8004/health')" || exit 1
CMD ["python", "-m", "agents.tunnel_provisioning.main"]
