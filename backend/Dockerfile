FROM python:3.14-slim@sha256:caaf356f40667c496d405780745b9ac25771c189a51dfcc42430d531ea09f8a2 AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY requirements-build.lock ./
RUN pip install --require-hashes -r requirements-build.lock

COPY pyproject.toml README.md ./
COPY app ./app
RUN pip wheel --no-deps --no-build-isolation --wheel-dir /wheels .

FROM python:3.14-slim@sha256:caaf356f40667c496d405780745b9ac25771c189a51dfcc42430d531ea09f8a2 AS runtime

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

RUN groupadd --gid 10001 auroom \
    && useradd --uid 10001 --gid auroom --no-create-home auroom \
    && mkdir -p /data/media \
    && chown auroom:auroom /data/media
USER 10001:10001

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
