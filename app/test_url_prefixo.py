# -*- coding: utf-8 -*-
"""
O prefixo das rotas vem do URL_PREFIX (aplicado pelo waitress), então nenhum link,
action ou redirect pode ter o /pesquisa/ fixo. Os links usam url_for ou URL_PREFIX.
"""
import os
import re
from pesquisa import app

# Rota fixa: /pesquisa/ seguido de minúscula. Não pega os parâmetros do SSM
# (/pesquisa/DB_HOST) nem o site externo sites.ufca.edu.br/prpi/pesquisa/.
PREFIXO_FIXO = re.compile(r'(?<!prpi)/pesquisa/[a-z]')
URL_FOR = re.compile(r"""url_for\(\s*['"]([A-Za-z0-9_]+)['"]""")


def _arquivos():
    yield 'pesquisa.py'
    for arquivo in sorted(os.listdir('templates')):
        if arquivo.endswith('.html'):
            yield os.path.join('templates', arquivo)


def test_sem_prefixo_fixo():
    achados = []
    for caminho in _arquivos():
        with open(caminho, encoding='utf-8') as f:
            for n, linha in enumerate(f, 1):
                if PREFIXO_FIXO.search(linha):
                    achados.append(f'{caminho}:{n}')
    assert not achados, achados


def test_url_for_aponta_para_rotas_existentes():
    endpoints = set(app.view_functions)
    faltando = []
    for caminho in _arquivos():
        with open(caminho, encoding='utf-8') as f:
            for nome in URL_FOR.findall(f.read()):
                if nome not in endpoints:
                    faltando.append(f'{caminho}: {nome}')
    assert not faltando, faltando


def test_url_for_segue_o_prefixo():
    with app.test_request_context('/', base_url='http://localhost/outro'):
        from flask import url_for
        assert url_for('meusProjetos') == '/outro/meusProjetos'
        assert url_for('indicacao', id=7, b=1) == '/outro/indicacao?id=7&b=1'
        assert url_for('verArquivosProjeto', filename='x.pdf') == '/outro/verArquivosProjeto/x.pdf'


def test_url_for_na_raiz():
    # URL_PREFIX="/" vira "" (raiz): o waitress passa SCRIPT_NAME vazio
    with app.test_request_context('/', base_url='http://localhost'):
        from flask import url_for
        assert url_for('meusProjetos') == '/meusProjetos'
        assert url_for('home') == '/'


def test_url_prefix_normalizado():
    from pesquisa import normalizar_prefixo
    assert normalizar_prefixo('/') == ''
    assert normalizar_prefixo(' / ') == ''
    assert normalizar_prefixo('/pesquisa/') == '/pesquisa'
    assert normalizar_prefixo('/pesquisa') == '/pesquisa'
