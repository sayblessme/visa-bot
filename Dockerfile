FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for Playwright and psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    libxshmfence1 && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --upgrade pip && \
    pip install . && \
    pip install httpx

# Install Playwright browsers
RUN playwright install chromium && playwright install-deps chromium

COPY . .

CMD ["python", "-m", "app.main"]
