FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg gosu \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY sidecar/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sidecar/app.py sidecar/docker_ops.py ./

COPY docker/sidecar/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --shell /bin/bash --create-home appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
