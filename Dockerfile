FROM node:24.11.1-bookworm-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12.11-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir uv==0.10.10
COPY backend/pyproject.toml ./backend/pyproject.toml
COPY backend/uv.lock ./backend/uv.lock
RUN uv sync --project backend --no-dev --frozen
COPY backend ./backend
COPY --from=frontend-build /app/frontend/dist ./frontend/dist
EXPOSE 8000
CMD ["uv", "run", "--project", "backend", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
