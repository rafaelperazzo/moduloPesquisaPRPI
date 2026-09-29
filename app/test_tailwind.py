# -*- coding: utf-8 -*-
"""
O Tailwind é compilado localmente (tailwind/build.sh -> static/css/tailwind.css),
sem o Play CDN: nenhum template carrega JavaScript do cdn.tailwindcss.com e o CSS
versionado precisa estar em dia com as classes usadas nos templates.
"""
import os
import re
import subprocess

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_TAILWIND = os.path.join(RAIZ, 'tailwind')
CSS = os.path.join(RAIZ, 'app', 'static', 'css', 'tailwind.css')
TEMPLATES = os.path.join(RAIZ, 'app', 'templates')


def _templates():
    for arquivo in sorted(os.listdir(TEMPLATES)):
        if arquivo.endswith('.html'):
            with open(os.path.join(TEMPLATES, arquivo), encoding='utf-8') as f:
                yield arquivo, f.read()


def test_sem_play_cdn():
    achados = [nome for nome, html in _templates()
               if 'cdn.tailwindcss.com' in html or 'tailwind-play' in html]
    assert not achados, achados


def test_css_compilado_existe():
    assert os.path.getsize(CSS) > 1000


def test_base_carrega_css_no_fim_do_head():
    # Igual ao Play CDN, que anexava o <style> ao fim do <head>: o Tailwind vem
    # depois dos estilos próprios de cada página.
    html = dict(_templates())['BASE_v3.html']
    head = html.split('</head>')[0]
    assert head.rstrip().endswith("filename='css/tailwind.css') }}\">")


def _cli():
    with open(os.path.join(DIR_TAILWIND, 'build.sh'), encoding='utf-8') as f:
        versao = re.search(r'^VERSAO="([^"]+)"', f.read(), re.M).group(1)
    cache = os.environ.get('XDG_CACHE_HOME', os.path.expanduser('~/.cache'))
    return os.path.join(cache, 'tailwindcss', f'tailwindcss-linux-x64-{versao}')


def test_css_em_dia_com_os_templates(tmp_path):
    cli = _cli()
    if not os.access(cli, os.X_OK):
        pytest.skip('executável do Tailwind ausente: rode tailwind/build.sh uma vez')
    saida = tmp_path / 'tailwind.css'
    subprocess.run([cli, '-c', 'tailwind.config.js', '-i', 'input.css', '-o', str(saida), '--minify'],
                   cwd=DIR_TAILWIND, check=True, capture_output=True)
    with open(CSS, encoding='utf-8') as f:
        atual = f.read()
    assert saida.read_text(encoding='utf-8') == atual, 'CSS desatualizado: rode tailwind/build.sh e commite app/static/css/tailwind.css'
