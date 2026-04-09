FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends xvfb xauth \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "xvfb-run -a --server-args='-screen 0 1366x900x24 -ac +extension RANDR' uvicorn proxy_RT:app --host 0.0.0.0 --port ${PORT:-8000}"]
