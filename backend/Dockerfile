# YouTube AI 學習助手 v3.0 — NAS 用容器
# 金鑰（.env）不會被包進映像檔：由 docker-compose 的 env_file 在啟動時讀入。
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# 更新程式碼時用 --build-arg CACHEBUST=$(date +%s)，避免 NAS 的舊版 Docker 誤用快取
ARG CACHEBUST=1
COPY accounts.py ai_router.py app.py ./
COPY web ./web
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
