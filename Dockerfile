# syntax=docker/dockerfile:1
#
# Targets:
#   app      (default) the API plus the built React app. This is what gets deployed.
#   test     the backend with dev tools; runs the test suite.
#   backend  the backend only; used for one-off scripts such as data loading.

# ---- Backend: Python dependencies and code ----
FROM python:3.13-slim AS backend
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/ ./
RUN pip install .

# ---- Test: same image plus pytest, ruff and mypy ----
FROM backend AS test
RUN pip install ".[dev]"
CMD ["pytest"]

# ---- Frontend: build the React app ----
FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- App: the API serving the built React app ----
FROM backend AS app
COPY --from=frontend /frontend/dist ./static
ENV FRONTEND_DIST_DIR=/app/static
RUN useradd --create-home appuser
USER appuser
EXPOSE 8000
# Heroku and similar hosts provide the port in $PORT.
CMD ["sh", "-c", "uvicorn app.main:create_production_app --factory --host 0.0.0.0 --port ${PORT:-8000}"]
