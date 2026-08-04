#!/usr/bin/env bash
# Consulta o endpoint /health do Yoko Pesquisa e reinicia o serviço via
# systemd se a resposta não for HTTP 200. Pensado para ser disparado
# periodicamente pela unit pesquisa-healthcheck.timer.
set -euo pipefail

URL="${PESQUISA_HEALTH_URL:-http://127.0.0.1:80/pesquisa/health}"
SERVICE="${PESQUISA_SERVICE_NAME:-pesquisa.service}"

if curl --fail --silent --show-error --max-time 10 "$URL" > /dev/null; then
    logger -t pesquisa-healthcheck "OK - ${URL}"
else
    logger -t pesquisa-healthcheck "FALHA - ${URL} não respondeu 200. Reiniciando ${SERVICE}..."
    systemctl restart "$SERVICE"
fi
