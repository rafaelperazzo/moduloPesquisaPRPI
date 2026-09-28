"""Declaração de orientador (/minhaDeclaracaoOrientador): por id do projeto ou da indicação,
só o coordenador do projeto ou um admin. O token de 2018 (longo e aleatório) segue como está.

Rodar a partir de app/: pytest test_declaracao_orientador.py -v
"""
import pytest
from flask.sessions import SecureCookieSessionInterface

import pesquisa as P

DONO = '1111111'
PROJETO = '10'   # projeto de DONO
INDICACAO = '77'  # indicação do PROJETO


@pytest.fixture
def consultas(monkeypatch):
    feitas = []
    monkeypatch.setattr(P, 'executarSelect2', lambda consulta, tipo=0, valores=(): feitas.append(valores) or ([], 0))
    colunas = {('editalProjeto', 'siape', PROJETO): DONO, ('indicacoes', 'idProjeto', INDICACAO): PROJETO}
    monkeypatch.setattr(P, 'obterColunaUnica', lambda tabela, coluna, colunaId, valorId: colunas.get((tabela, coluna, str(valorId)), '0'))
    return feitas


@pytest.fixture
def client(monkeypatch, consultas):
    monkeypatch.setattr(P.app, 'session_interface', SecureCookieSessionInterface())
    monkeypatch.setattr(P.limiter, 'enabled', False)
    return P.app.test_client()


def logado(client, username, roles=('user',)):
    with client.session_transaction() as s:
        s.update({'username': username, 'permissao': 1, 'roles': list(roles), 'edital': 0})


@pytest.mark.parametrize('query', [f'id={PROJETO}', f'idAluno={INDICACAO}'])
def test_outro_usuario_nao_emite(client, consultas, query):
    logado(client, '2222222')
    resposta = client.get(f'/minhaDeclaracaoOrientador?{query}')
    assert resposta.status_code == 403
    assert consultas == []


@pytest.mark.parametrize('query', [f'id={PROJETO}', f'idAluno={INDICACAO}'])
def test_coordenador_emite(client, consultas, query):
    logado(client, DONO)
    resposta = client.get(f'/minhaDeclaracaoOrientador?{query}')
    assert resposta.get_data(as_text=True) == 'declaracao inexistente...'  # passou da checagem e consultou
    assert len(consultas) == 1


@pytest.mark.parametrize('query', [f'id={PROJETO}', f'idAluno={INDICACAO}'])
def test_admin_emite(client, consultas, query):
    logado(client, '3333333', roles=('user', 'admin'))
    client.get(f'/minhaDeclaracaoOrientador?{query}')
    assert len(consultas) == 1


@pytest.mark.parametrize('query', ['id=abc', 'idAluno=abc', 'id=999', 'idAluno=999'])
def test_id_invalido_ou_inexistente_e_negado(client, consultas, query):
    logado(client, DONO)
    assert client.get(f'/minhaDeclaracaoOrientador?{query}').status_code == 403
    assert consultas == []


def test_token_2018_continua_sem_checagem_de_dono(client, consultas):
    logado(client, '2222222')
    resposta = client.get('/minhaDeclaracaoOrientador?token=abc')
    assert resposta.get_data(as_text=True) == 'declaração inexistente!'
    assert consultas == [('abc',)]


def test_sem_login_vai_para_o_login(client, consultas):
    assert b'login' in client.get(f'/minhaDeclaracaoOrientador?id={PROJETO}').data.lower()
    assert consultas == []
