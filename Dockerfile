FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV RUSSWORKS_RUNTIME_MODE=production
ENV RUSSWORKS_DATA_ROOT=/app/data/daily
ENV RUSSWORKS_OUTPUT_ROOT=/app/data/outputs
ENV RUSSWORKS_CONFIG_PATH=/app/config/russworks_config.yaml
ENV RUSSWORKS_REPORT_VOLUME=/app/data

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config
COPY templates ./templates

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

VOLUME ["/app/data", "/app/config"]

CMD ["python", "-m", "russworks.deployment.runtime"]
