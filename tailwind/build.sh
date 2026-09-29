#!/usr/bin/env bash
# Gera app/static/css/tailwind.css a partir das classes usadas nos templates.
# Rode sempre que um template ganhar classes novas e commite o CSS gerado.
#
#   tailwind/build.sh
#
# Usa o executável standalone do Tailwind (não precisa de Node), baixado uma
# única vez para ~/.cache/tailwindcss e conferido pelo sha256 da release.
set -euo pipefail

VERSAO="3.4.17"
BINARIO="tailwindcss-linux-x64"
SHA256="7d24f7fa191d2193b78cd5f5a42a6093e14409521908529f42d80b11fde1f1d4"

DIR="$(cd "$(dirname "$0")" && pwd)"
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/tailwindcss"
CLI="$CACHE/${BINARIO}-${VERSAO}"

if [ ! -x "$CLI" ]; then
    mkdir -p "$CACHE"
    echo "Baixando Tailwind v${VERSAO}..."
    curl -sSfL -o "$CLI.tmp" "https://github.com/tailwindlabs/tailwindcss/releases/download/v${VERSAO}/${BINARIO}"
    echo "${SHA256}  $CLI.tmp" | sha256sum -c --quiet -
    chmod +x "$CLI.tmp"
    mv "$CLI.tmp" "$CLI"
fi

cd "$DIR"
"$CLI" -c tailwind.config.js -i input.css -o ../app/static/css/tailwind.css --minify
