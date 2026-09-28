"""Declarações e certificados públicos do discente: só abrem pelo link assinado e temporário
gerado na busca pelo CPF completo. O id sequencial da indicação, sozinho, expunha nome e CPF.

Rodar a partir de app/: pytest test_documento_discente.py -v
"""
import pytest
from flask.sessions import SecureCookieSessionInterface

import pesquisa as P

ROTAS = ['/discente/minhaDeclaracao2019', '/discente/meuCertificado']


@pytest.fixture
def consultas(monkeypatch):
    """Captura os ids consultados; o banco responde vazio ('declaração inexistente!')."""
    feitas = []
    monkeypatch.setattr(P, 'executarSelect2', lambda consulta, tipo=0, valores=(): feitas.append(valores) or ([], 0))
    return feitas


@pytest.fixture
def client(monkeypatch, consultas):
    monkeypatch.setattr(P.app, 'session_interface', SecureCookieSessionInterface())
    monkeypatch.setattr(P.limiter, 'enabled', False)
    return P.app.test_client()


@pytest.mark.parametrize('rota', ROTAS)
def test_id_sequencial_nao_abre_mais_o_documento(client, consultas, rota):
    resposta = client.get(f'{rota}?id=5')
    assert resposta.status_code == 403
    assert 'Busque novamente pelo seu CPF' in resposta.get_data(as_text=True)
    assert consultas == []


@pytest.mark.parametrize('rota', ROTAS)
def test_token_adulterado_e_recusado(client, consultas, rota):
    token = P.serializador_documento_discente().dumps(5)
    assert client.get(f'{rota}?t={token[:-2]}xx').status_code == 403
    outro_salt = P.URLSafeTimedSerializer(P.app.config['SECRET_KEY'], salt='outro').dumps(5)
    assert client.get(f'{rota}?t={outro_salt}').status_code == 403
    assert consultas == []


@pytest.mark.parametrize('rota', ROTAS)
def test_token_expirado_e_recusado(client, consultas, monkeypatch, rota):
    with P.app.test_request_context():
        token = P.token_documento_discente(5)
    monkeypatch.setattr(P, 'DOCUMENTO_DISCENTE_VALIDADE', -1)
    assert client.get(f'{rota}?t={token}').status_code == 403
    assert consultas == []


@pytest.mark.parametrize('rota', ROTAS)
def test_token_valido_consulta_a_indicacao_do_token(client, consultas, rota):
    with P.app.test_request_context():
        token = P.token_documento_discente(5)
    resposta = client.get(f'{rota}?t={token}')
    assert resposta.get_data(as_text=True) == 'declaração inexistente!'
    assert consultas == [(P.AES_KEY, '5')]


def test_busca_por_cpf_gera_links_assinados():
    linha = ('Fulano', '***', 'PIBIC', 'Orientador', 'Projeto', None, None, 7975)
    with P.app.test_request_context():
        html = P.render_template('alunos.html', listaProjetos=[], lista2019=[linha])
    assert '?id=' not in html and html.count('?t=') == 2
    token = html.split('?t=')[1].split('"')[0]
    assert P.id_documento_discente(token) == 7975


@pytest.mark.parametrize('rota', ['/declaracao?idProjeto=1', '/autenticacao'])
def test_rotas_legadas_removidas(client, rota):
    assert client.get(rota).status_code == 404
    assert client.post(rota, data={'tipo': '1', 'codigo': '1'}).status_code == 404
