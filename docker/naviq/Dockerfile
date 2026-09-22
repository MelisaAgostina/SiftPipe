FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --shell /bin/bash --create-home appuser

# NaViQ's dependencies are installed at container start (its requirements.txt only exists via the
# bind mount), as appuser. A venv it owns gives every file a wheel installs (including data files
# like man pages) somewhere writable; the system Python prefix is root-owned.
RUN python -m venv /opt/venv && chown -R appuser:appuser /opt/venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY docker/naviq/siftpipe_settings.py /opt/siftpipe/siftpipe_settings.py
ENV PYTHONPATH=/opt/siftpipe
ENV DJANGO_SETTINGS_MODULE=siftpipe_settings

WORKDIR /app

COPY docker/naviq/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && chown appuser:appuser /entrypoint.sh

USER appuser

EXPOSE 8001

HEALTHCHECK --interval=15s --timeout=5s --start-period=300s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8001/', timeout=3).status == 200 else 1)"

ENTRYPOINT ["/entrypoint.sh"]
