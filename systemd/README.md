# Healthcheck systemd (produção)

Watchdog externo que consulta `GET {URL_PREFIX}/health` periodicamente e
reinicia o serviço da aplicação (`pesquisa.service`) se a resposta não for
HTTP 200. A rota `/health` só responde em produção (`PRODUCAO=1`); em
qualquer outro ambiente retorna 404.

## Instalação na VPS

A partir do checkout do repositório na VPS:

```bash
sudo systemd/instalar-healthcheck.sh
```

O script copia `pesquisa-healthcheck.sh` para `/usr/local/bin`, as units para
`/etc/systemd/system`, recarrega o systemd e habilita o timer.

Antes de rodar (ou depois, editando `/etc/systemd/system/pesquisa-healthcheck.service`
e rodando `systemctl daemon-reload`), confira se os valores batem com o ambiente real:
- `PESQUISA_HEALTH_URL` — porta (`SERVER_PORT`) e prefixo (`URL_PREFIX`) reais
- `PESQUISA_SERVICE_NAME` — nome da unit que roda `python3 pesquisa.py`, caso não seja `pesquisa.service`

## Verificação

```bash
systemctl list-timers pesquisa-healthcheck.timer
journalctl -t pesquisa-healthcheck -f
```
