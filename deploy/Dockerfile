# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    REVIEWAGENT_HOME=/opt/review-agent \
    REVIEWAGENT_ENABLE_SCRAPING=0

WORKDIR /opt/review-agent

# tesseract 只在启用 OCR 时需要；镜像不默认装浏览器，采集按需另挂
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-chi-sim \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --upgrade pip && pip install ".[api,import]"

COPY config ./config
COPY .env.example ./.env.example
RUN mkdir -p data output

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz').read()" || exit 1

CMD ["reviewagent", "serve", "--host", "0.0.0.0", "--port", "8000"]
