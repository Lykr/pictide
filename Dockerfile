# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./web/
RUN npm install --global --no-audit --no-fund "$(node -p 'require("./web/package.json").packageManager')" \
    && pnpm --dir web install --frozen-lockfile
COPY web/ ./web/
COPY LICENSE NOTICE ./
RUN pnpm --dir web run typecheck && pnpm --dir web run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PICTIDE_DATA_DIR=/data \
    HOME=/data
WORKDIR /app
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates libgomp1 libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 pictide \
    && useradd --uid 10001 --gid pictide --no-create-home --home-dir /data --shell /usr/sbin/nologin pictide \
    && mkdir /data && chown pictide:pictide /data
COPY backend/requirements.txt ./backend/requirements.txt
RUN python -m pip install --no-cache-dir --no-compile --requirement backend/requirements.txt
COPY backend/ ./backend/
COPY --from=frontend /build/web/dist/ ./web/dist/
COPY docs/assets/workflows/ ./docs/assets/workflows/
COPY LICENSE NOTICE ./
LABEL org.opencontainers.image.title="Pictide" \
      org.opencontainers.image.source="https://github.com/Lykr/pictide" \
      org.opencontainers.image.licenses="Apache-2.0"
USER 10001:10001
VOLUME ["/data"]
EXPOSE 8189
HEALTHCHECK --interval=10s --timeout=5s --start-period=15m --retries=3 \
    CMD ["python", "-c", "from urllib.request import ProxyHandler, build_opener; response = build_opener(ProxyHandler({})).open('http://127.0.0.1:8189/api/bootstrap', timeout=3); assert response.status == 200"]
ENTRYPOINT ["python", "-m", "backend.host", "--cli", "--no-browser", "--lan", "--data-dir", "/data"]
CMD ["--vocabulary", "filtered"]
