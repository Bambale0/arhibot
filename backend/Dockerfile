FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY requirements-build.lock ./
RUN pip install --require-hashes -r requirements-build.lock

COPY pyproject.toml README.md ./
COPY app ./app
RUN pip wheel --no-deps --no-build-isolation --wheel-dir /wheels .

FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock

COPY alembic.ini ./
COPY alembic ./alembic
COPY --from=builder /wheels/ai_architecture_backend-*.whl /tmp/
RUN pip install --no-deps /tmp/ai_architecture_backend-*.whl \
    && rm -f /tmp/ai_architecture_backend-*.whl

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
