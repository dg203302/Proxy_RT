FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app

RUN apt-get update && apt-get install -y xvfb

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "xvfb-run --auto-servernum --server-args='-screen 0 1280x1024x24' uvicorn proxy_RT:app --host 0.0.0.0 --port ${PORT:-8000}"]