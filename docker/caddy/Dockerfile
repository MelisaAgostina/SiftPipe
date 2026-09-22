FROM caddy:2-alpine

RUN apk add --no-cache libcap \
    && setcap cap_net_bind_service=+ep /usr/bin/caddy

RUN addgroup -g 10001 appuser \
    && adduser -D -u 10001 -G appuser appuser \
    && mkdir -p /data /config \
    && chown -R appuser:appuser /data /config

COPY docker/caddy/Caddyfile /etc/caddy/Caddyfile

USER appuser

EXPOSE 80 443

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
