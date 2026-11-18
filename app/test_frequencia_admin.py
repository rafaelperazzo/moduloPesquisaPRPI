"""Testes das frequências das indicações pelo admin (listar, editar, excluir), com o banco mockado.

Rodar a partir de app/: pytest test_frequencia_admin.py -v
"""
import datetime

import pytest
from flask.sessions import SecureCookieSessionInterface
from loguru import logger

import pesquisa as P

TEXTO_SECRETO = 'Revisão bibliográfica sobre o tema X'


def frequencia(**extra):
    dados = {'id': 5, 'idIndicacao': 7, 'mes': 3, 'ano': 2026, 's1': TEXTO_SECRETO, 's2': 'Coleta',
             's3': 'Análise', 's4': 'Relatório', 'obs': '', 'data': '02/04/2026 10:15'}
    dados.update(extra)
    return dados


def formulario(atual, **mudancas):
    dados = {c: '' if atual.get(c) is None else str(atual[c]) for c in ('mes', 'ano', 's1', 's2', 's3', 's4', 'obs')}
    dados.update({k: str(v) for k, v in mudancas.items()})
    return dados


@pytest.fixture
def ambiente(monkeypatch):
    estado = {'frequencia': frequencia(), 'alteracoes': [], 'rowcount': 1, 'colisao': 0,
              'lista': [frequencia(), frequencia(id=6, mes=4, s1='Semana de abril', data=None)]}
    monkeypatch.setattr(P.app, 'session_interface', SecureCookieSessionInterface())
    monkeypatch.setattr(P.app, 'secret_key', 'teste-frequencia')
    monkeypatch.setitem(P.app.config, 'WTF_CSRF_ENABLED', False)
    monkeypatch.setattr(P.limiter, 'enabled', False)
    monkeypatch.setattr(P, 'carregar_mensagens', lambda: [])
    monkeypatch.setattr(P, 'carregar_indicacao',
                        lambda id_: {'id': 7, 'idProjeto': 70, 'nome': 'Maria Discente', 'tipo_de_vaga': 0,
                                     'edital': 3, 'orientador': 'Prof. X'} if id_ == 7 else None)
    monkeypatch.setattr(P, 'carregar_frequencia', lambda id_: estado['frequencia'] if id_ == 5 else None)
    monkeypatch.setattr(P, 'consultar_dicts', lambda c, v=(): estado['lista'])
    monkeypatch.setattr(P, 'executarSelect2', lambda c, tipo=0, valores=(): ([], estado['colisao']))

    def executar_alteracao(consulta, valores=()):
        estado['alteracoes'].append((consulta, valores))
        return estado['rowcount']
    monkeypatch.setattr(P, 'executar_alteracao', executar_alteracao)
    return estado, P.app.test_client()


def como_admin(client):
    with client.session_transaction() as s:
        s.update({'username': '1', 'permissao': 0, 'roles': ['admin', 'user'], 'edital': 0})


def como_usuario(client):
    with client.session_transaction() as s:
        s.update({'username': '2', 'permissao': 1, 'roles': ['user'], 'edital': 0})


# ----- permissão -----

def test_rotas_exigem_admin(ambiente):
    estado, client = ambiente
    como_usuario(client)
    assert client.get('/admin/indicacao/7/frequencias').status_code in (302, 401, 403)
    assert client.get('/admin/frequencia/5/editar').status_code in (302, 401, 403)
    assert client.post('/admin/frequencia/5/editar',
                       data=formulario(estado['frequencia'], s2='x')).status_code in (302, 401, 403)
    assert client.post('/admin/frequencia/5/excluir').status_code in (302, 401, 403)
    assert estado['alteracoes'] == []


# ----- lista -----

def test_link_na_lista_de_indicacoes(ambiente, monkeypatch):
    _, client = ambiente
    linha = [7, 70, 'Maria', 'PIBIC', 'VOLUNTÁRIO(A)'] + [None] * 9 + ['Prof. X', '', 3, 'UFCA'] + [None] * 5 \
        + ['52998224725', None]
    monkeypatch.setattr(P, 'executarSelect2', lambda c, tipo=0, valores=(): ([linha], 1))
    monkeypatch.setattr(P, 'obterColunaUnica', lambda *a: 'Edital 3')
    como_admin(client)
    html = client.get('/admin/indicacoes?edital=3').get_data(as_text=True)
    assert '/admin/indicacao/7/frequencias' in html


def test_lista_mostra_as_frequencias(ambiente):
    _, client = ambiente
    como_admin(client)
    r = client.get('/admin/indicacao/7/frequencias')
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'março/2026' in html and 'abril/2026' in html and '02/04/2026 10:15' in html
    assert TEXTO_SECRETO in html and 'VOLUNTÁRIO(A)' in html
    assert '/admin/frequencia/5/editar' in html and '/admin/frequencia/6/excluir' in html
    assert 'Total de frequências: 2' in html


def test_lista_vazia(ambiente):
    estado, client = ambiente
    estado['lista'] = []
    como_admin(client)
    assert 'Nenhuma frequência enviada' in client.get('/admin/indicacao/7/frequencias').get_data(as_text=True)


def test_lista_escapa_o_texto(ambiente):
    estado, client = ambiente
    estado['lista'] = [frequencia(s1='<script>alert(1)</script>')]
    como_admin(client)
    html = client.get('/admin/indicacao/7/frequencias').get_data(as_text=True)
    assert '<script>alert(1)</script>' not in html and '&lt;script&gt;' in html


def test_indicacao_inexistente(ambiente):
    _, client = ambiente
    como_admin(client)
    assert client.get('/admin/indicacao/999/frequencias').status_code == 302


# ----- edição -----

def test_formulario_vem_preenchido(ambiente):
    _, client = ambiente
    como_admin(client)
    html = client.get('/admin/frequencia/5/editar').get_data(as_text=True)
    assert TEXTO_SECRETO in html and 'value="3" selected' in html and 'value="2026"' in html


def test_salvar_grava_mes_ano_e_textos(ambiente):
    estado, client = ambiente
    como_admin(client)
    r = client.post('/admin/frequencia/5/editar', data=formulario(estado['frequencia'], mes=5, s2=' Nova coleta '))
    assert r.status_code == 302 and r.location.endswith('/admin/indicacao/7/frequencias')
    consulta, valores = estado['alteracoes'][0]
    assert consulta.startswith('UPDATE frequencias') and 'data' not in consulta.split('WHERE')[0]
    assert valores == (5, 2026, TEXTO_SECRETO, 'Nova coleta', 'Análise', 'Relatório', '', 5)


def test_nada_mudou_nao_grava(ambiente):
    estado, client = ambiente
    como_admin(client)
    r = client.post('/admin/frequencia/5/editar', data=formulario(estado['frequencia']))
    assert r.status_code == 302 and estado['alteracoes'] == []


@pytest.mark.parametrize('mudanca', [{'mes': 13}, {'mes': 'x'}, {'ano': 2017}, {'ano': 'abc'},
                                     {'ano': datetime.date.today().year + 2}, {'s3': '  '},
                                     {'s1': 'a' * 301}, {'obs': 'b' * 301}])
def test_valores_invalidos_nao_gravam(ambiente, mudanca):
    estado, client = ambiente
    como_admin(client)
    r = client.post('/admin/frequencia/5/editar', data=formulario(estado['frequencia'], **mudanca))
    assert r.status_code == 400 and estado['alteracoes'] == []


def test_colisao_de_mes_ano_nao_grava(ambiente):
    estado, client = ambiente
    estado['colisao'] = 1
    como_admin(client)
    r = client.post('/admin/frequencia/5/editar', data=formulario(estado['frequencia'], mes=4))
    assert r.status_code == 400 and 'Já existe outra frequência' in r.get_data(as_text=True)
    assert estado['alteracoes'] == []


def test_rowcount_zero_mostra_erro(ambiente):
    estado, client = ambiente
    estado['rowcount'] = 0
    como_admin(client)
    r = client.post('/admin/frequencia/5/editar', data=formulario(estado['frequencia'], s2='outra'))
    assert r.status_code == 302 and r.location.endswith('/admin/frequencia/5/editar')


def test_frequencia_inexistente(ambiente):
    _, client = ambiente
    como_admin(client)
    assert client.get('/admin/frequencia/999/editar').status_code == 302
    assert client.post('/admin/frequencia/999/excluir').status_code == 302


def test_log_nao_tem_o_conteudo(ambiente):
    estado, client = ambiente
    mensagens = []
    sink = logger.add(lambda m: mensagens.append(str(m)), level="INFO")
    try:
        como_admin(client)
        client.post('/admin/frequencia/5/editar', data=formulario(estado['frequencia'], s2='Texto novo'))
    finally:
        logger.remove(sink)
    linha = next(m for m in mensagens if '[frequencia] id=5' in m)
    assert TEXTO_SECRETO not in linha and 'Texto novo' not in linha


# ----- exclusão -----

def test_excluir_so_por_post(ambiente):
    estado, client = ambiente
    como_admin(client)
    assert client.get('/admin/frequencia/5/excluir').status_code == 405
    assert estado['alteracoes'] == []


def test_excluir(ambiente):
    estado, client = ambiente
    como_admin(client)
    r = client.post('/admin/frequencia/5/excluir')
    assert r.status_code == 302 and r.location.endswith('/admin/indicacao/7/frequencias')
    assert estado['alteracoes'] == [('DELETE FROM frequencias WHERE id=%s', (5,))]
