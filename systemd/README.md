# Healthcheck systemd (produção)

Watchdog externo que consulta `GET {URL_PREFIX}/health` periodicamente e
reinicia o serviço da aplicação (`pesquisa.service`) se a resposta não for
HTTP 200. A rota `/health` só responde em produção (`PRODUCAO=1`); em
qualquer outro ambiente retorna 404.

## Instalação na VPS

```bash
sudo cp pesquisa-healthcheck.sh /usr/local/bin/pesquisa-healthcheck.sh
sudo chmod +x /usr/local/bin/pesquisa-healthcheck.sh

sudo cp pesquisa-healthcheck.service pesquisa-healthcheck.timer /etc/systemd/system/
```

Edite `/etc/systemd/system/pesquisa-healthcheck.service` e ajuste:
- `PESQUISA_HEALTH_URL` — porta (`SERVER_PORT`) e prefixo (`URL_PREFIX`) reais
- `PESQUISA_SERVICE_NAME` — nome da unit que roda `python3 pesquisa.py`, caso não seja `pesquisa.service`

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pesquisa-healthcheck.timer
```

## Verificação

```bash
systemctl list-timers pesquisa-healthcheck.timer
journalctl -t pesquisa-healthcheck -f
```
