# -*- coding: utf-8 -*-
"""
CSS, JS, fontes e imagens saem do próprio app (static/), sem CDN nem shields.io:
cada requisição a terceiros entrega o IP do visitante a eles. Só o Turnstile da
Cloudflare fica de fora, porque precisa ser carregado de lá.

Rodar a partir de app/: pytest test_assets_locais.py -v
"""
import os
import re
import subprocess

from flask import render_template

import pesquisa as P

EXTERNO = re.compile(r'<(?:script|img|link)\b[^>]*\b(?:src|href)=["\'](https?:)?//[^"\']+', re.I)
PERMITIDOS = ('https://challenges.cloudflare.com/turnstile/',)


def test_templates_sem_assets_externos():
    achados = []
    for arquivo in sorted(os.listdir('templates')):
        if not arquivo.endswith('.html'):
            continue
        with open(os.path.join('templates', arquivo), encoding='utf-8') as f:
            for n, linha in enumerate(f, 1):
                for m in EXTERNO.finditer(linha):
                    if not any(p in m.group(0) for p in PERMITIDOS):
                        achados.append(f'{arquivo}:{n}')
    assert not achados, achados


def _git(repo, *args, data=None):
    env = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@t', GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@t')
    if data:
        env.update(GIT_AUTHOR_DATE=data, GIT_COMMITTER_DATE=data)
    subprocess.run(['git', *args], cwd=repo, env=env, check=True, capture_output=True)


def test_versao_e_a_tag_mais_recente_pela_data(tmp_path):
    # Na ordem alfabética v9.0.0 vem depois de v13.0.0; vale a data do commit.
    _git(tmp_path, 'init', '-q')
    _git(tmp_path, 'commit', '-q', '--allow-empty', '-m', 'a', data='2026-01-10T12:00:00')
    _git(tmp_path, 'tag', 'v9.0.0')
    _git(tmp_path, 'commit', '-q', '--allow-empty', '-m', 'b', data='2026-09-20T12:00:00')
    _git(tmp_path, 'tag', '-a', 'v13.0.0', '-m', 'anotada')
    _git(tmp_path, 'commit', '-q', '--allow-empty', '-m', 'c', data='2026-09-29T12:00:00')
    sub = tmp_path / 'app'
    sub.mkdir()
    assert P.versao_do_repositorio(str(sub)) == ('v13.0.0', '29/09/2026')


def test_rodape_mostra_versao_e_data(monkeypatch):
    monkeypatch.setattr(P, '__version__', 'v1.2.3')
    monkeypatch.setattr(P, 'DATA_ATUALIZACAO', '01/02/2026')
    with P.app.test_request_context('/'):
        html = render_template('BASE_v3.html')
    assert 'v1.2.3' in html and '01/02/2026' in html
    assert 'shields.io' not in html
