FROM node:22-alpine AS frontend-build

WORKDIR /frontend
COPY frontend/medivector-chat-app/package.json frontend/medivector-chat-app/pnpm-lock.yaml ./
RUN corepack enable && corepack prepare pnpm@10.18.3 --activate && pnpm install --frozen-lockfile

COPY frontend/medivector-chat-app/ ./
RUN pnpm run build

FROM python:3.11-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py test.py ./
COPY --from=frontend-build /frontend/dist ./frontend/medivector-chat-app/dist

EXPOSE 8000
CMD ["python", "app.py"]

