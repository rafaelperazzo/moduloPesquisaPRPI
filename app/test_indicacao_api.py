"""/indicacao/<cpf>: só o back-end do cppgi (chave X-Chave-Interna); de fora, 404.
Resposta sem e-mail, sem modalidade e sem CORS.

Rodar a partir de app/: pytest test_indicacao_api.py -v
"""
import pytest
from flask.sessions import SecureCookieSessionInterface

import pesquisa as P

CHAVE = 'chave-de-teste'
CPF = '52998224725'
LINHA = ('FULANO DE TAL', 1, 'CNPq', 42, '(2026) PROJETO (ORIENTADOR)')


@pytest.fixture
def consultas(monkeypatch):
    feitas = []
    monkeypatch.setattr(P, 'executarSelect2', lambda consulta, tipo=0, valores=(): feitas.append(consulta) or ([LINHA], 1))
    return feitas


@pytest.fixture
def client(monkeypatch, consultas):
    monkeypatch.setattr(P.app, 'session_interface', SecureCookieSessionInterface())
    monkeypatch.setattr(P.limiter, 'enabled', False)
    monkeypatch.setattr(P, 'INDICACAO_API_KEY', CHAVE)
    return P.app.test_client()


@pytest.mark.parametrize('cabecalhos', [{}, {'X-Chave-Interna': ''}, {'X-Chave-Interna': 'errada'},
                                        {'X-Chave-Interna': CHAVE + 'x'}])
def test_sem_chave_valida_responde_404_sem_consultar(client, consultas, cabecalhos):
    assert client.get(f'/indicacao/{CPF}', headers=cabecalhos).status_code == 404
    assert consultas == []


def test_sem_chave_configurada_nada_passa(client, consultas, monkeypatch):
    monkeypatch.setattr(P, 'INDICACAO_API_KEY', '')
    assert client.get(f'/indicacao/{CPF}', headers={'X-Chave-Interna': ''}).status_code == 404
    assert consultas == []


def test_com_chave_devolve_so_os_campos_usados_pelo_cppgi(client, consultas):
    resposta = client.get(f'/indicacao/{CPF}', headers={'X-Chave-Interna': CHAVE})
    assert resposta.status_code == 200
    assert resposta.get_json() == [{'nome': 'FULANO DE TAL', 'tipo_vinculo': 1, 'fomento': 'CNPq',
                                    'idProjeto': 42, 'dados': '(2026) PROJETO (ORIENTADOR)'}]
    assert 'Access-Control-Allow-Origin' not in resposta.headers
    assert 'email' not in consultas[0] and 'modalidade' not in consultas[0]
