#!/usr/bin/env bash
# Instala o watchdog de healthcheck do Yoko Pesquisa nesta VPS.
# Execute como root, a partir do checkout do repositório:
#   sudo systemd/instalar-healthcheck.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Execute como root (sudo $0)." >&2
    exit 1
fi

DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"

for f in pesquisa-healthcheck.sh pesquisa-healthcheck.service pesquisa-healthcheck.timer; do
    [[ -f "$DIR/$f" ]] || { echo "Arquivo não encontrado: $DIR/$f" >&2; exit 1; }
done

echo "Instalando script em /usr/local/bin/pesquisa-healthcheck.sh..."
install -m 755 "$DIR/pesquisa-healthcheck.sh" /usr/local/bin/pesquisa-healthcheck.sh

echo "Instalando units em /etc/systemd/system/..."
install -m 644 "$DIR/pesquisa-healthcheck.service" /etc/systemd/system/pesquisa-healthcheck.service
install -m 644 "$DIR/pesquisa-healthcheck.timer" /etc/systemd/system/pesquisa-healthcheck.timer

if ! systemctl list-unit-files pesquisa.service &>/dev/null; then
    echo "Aviso: unit 'pesquisa.service' não encontrada. Confira PESQUISA_SERVICE_NAME em pesquisa-healthcheck.service." >&2
fi

echo "Recarregando systemd..."
systemctl daemon-reload

echo "Habilitando e iniciando o timer..."
systemctl enable --now pesquisa-healthcheck.timer

echo "Disparando uma execução manual para validar..."
systemctl start pesquisa-healthcheck.service
sleep 1

echo
systemctl list-timers pesquisa-healthcheck.timer --no-pager
echo
journalctl -t pesquisa-healthcheck -n 5 --no-pager
