"""Testes do Cloudflare Turnstile (substitui o reCAPTCHA), com a chamada à Cloudflare mockada.

Rodar a partir de app/: pytest test_turnstile.py -v
"""
import re
from unittest.mock import MagicMock

import pytest
import requests
from flask.sessions import SecureCookieSessionInterface

import pesquisa as P


@pytest.fixture
def app_teste(monkeypatch):
    monkeypatch.setattr(P.app, 'session_interface', SecureCookieSessionInterface())
    monkeypatch.setattr(P.app, 'secret_key', 'teste-turnstile')
    monkeypatch.setitem(P.app.config, 'WTF_CSRF_ENABLED', False)
    monkeypatch.setattr(P.limiter, 'enabled', False)
    monkeypatch.setattr(P, 'carregar_mensagens', lambda: [])
    return P.app


@pytest.fixture
def client(app_teste):
    return app_teste.test_client()


@pytest.fixture
def producao(monkeypatch):
    monkeypatch.setattr(P, 'PRODUCAO', 1)


def cloudflare(monkeypatch, sucesso=True, erro=None):
    """Mocka o siteverify e devolve o mock, para conferir os parâmetros enviados."""
    chamada = MagicMock()
    if erro is not None:
        chamada.side_effect = erro
    else:
        chamada.return_value.json.return_value = {'success': sucesso, 'error-codes': [] if sucesso else ['invalid-input-response']}
    monkeypatch.setattr(P.requests, 'post', chamada)
    return chamada


def validar(app_teste, dados, **headers):
    with app_teste.test_request_context('/login', method='POST', data=dados, headers=headers):
        return P.turnstile_valido()


# ----- validação -----

def test_em_dev_nao_valida(app_teste, monkeypatch):
    chamada = cloudflare(monkeypatch)
    assert validar(app_teste, {}) is True
    chamada.assert_not_called()


def test_producao_sem_token_recusa_sem_chamar_a_cloudflare(app_teste, producao, monkeypatch):
    chamada = cloudflare(monkeypatch)
    assert validar(app_teste, {}) is False
    chamada.assert_not_called()


def test_producao_token_valido(app_teste, producao, monkeypatch):
    chamada = cloudflare(monkeypatch, sucesso=True)
    assert validar(app_teste, {'cf-turnstile-response': 'tok'}, **{'CF-Connecting-IP': '200.1.2.3'}) is True
    args, kwargs = chamada.call_args
    assert args[0] == P.TURNSTILE_URL
    assert kwargs['data'] == {'secret': P.TURNSTILE_SECRET_KEY, 'response': 'tok', 'remoteip': '200.1.2.3'}
    assert kwargs['timeout'] == 5


def test_producao_token_recusado(app_teste, producao, monkeypatch):
    cloudflare(monkeypatch, sucesso=False)
    assert validar(app_teste, {'cf-turnstile-response': 'tok'}) is False


@pytest.mark.parametrize('erro', [requests.Timeout('lento'), requests.ConnectionError('fora do ar')])
def test_cloudflare_indisponivel_aceita(app_teste, producao, monkeypatch, erro):
    cloudflare(monkeypatch, erro=erro)
    assert validar(app_teste, {'cf-turnstile-response': 'tok'}) is True


def test_chave_secreta_sai_do_ambiente():
    import os
    assert 'TURNSTILE_SECRET_KEY' not in os.environ


# ----- rotas -----

def test_login_sem_token_em_producao_volta_ao_login(client, producao, monkeypatch):
    cloudflare(monkeypatch)
    autenticar = MagicMock()
    monkeypatch.setattr(P, 'autenticar_usuario', autenticar)
    resposta = client.post('/login', data={'siape': '111', 'senha': 'x'})
    assert resposta.status_code == 302 and resposta.location.endswith('/login')
    autenticar.assert_not_called()


def test_login_com_token_valido_segue(client, producao, monkeypatch):
    cloudflare(monkeypatch, sucesso=True)
    monkeypatch.setattr(P, 'autenticar_usuario', lambda *a, **k: 'invalido')
    resposta = client.post('/login', data={'siape': '111', 'senha': 'x', 'cf-turnstile-response': 'tok'})
    assert resposta.status_code == 302 and resposta.location.endswith('/login')
    with client.session_transaction() as s:
        assert any('Usuário ou senha inválidos' in m for _, m in s.get('_flashes', []))


@pytest.mark.parametrize('rota,volta', [
    ('/enviarMinhaSenha', '/esqueciMinhaSenha'),
    ('/projetosAluno', '/projetos_discente'),
    ('/projetos_discente', '/projetos_discente'),
    ('/score2', '/scorelattes'),
    ('/lgpd/consulta', '/lgpd/consulta'),
])
def test_rotas_publicas_exigem_token_em_producao(client, producao, monkeypatch, rota, volta):
    cloudflare(monkeypatch)
    resposta = client.post(rota, data={'email': 'a@b.c', 'txtNome': '12345678901', 'area_capes': '1'})
    assert resposta.status_code == 302 and resposta.location.endswith(volta)


def test_solicitacao_lgpd_sem_token_devolve_o_formulario_preenchido(client, producao, monkeypatch):
    cloudflare(monkeypatch)
    escritas = []
    monkeypatch.setattr(P, 'atualizar2', lambda *a, **k: escritas.append(a))
    dados = {'nome': 'Maria', 'email': 'maria@x.com', 'vinculo': 'discente', 'tipo': 'acesso', 'descricao': 'Meus dados'}
    html = client.post('/lgpd/solicitacao', data=dados).get_data(as_text=True)
    assert escritas == []
    assert 'Meus dados' in html and 'verificação de segurança' in html


# ----- templates -----

@pytest.mark.parametrize('rota', ['/login', '/esqueciMinhaSenha', '/projetos_discente', '/scorelattes',
                                  '/lgpd/solicitacao', '/lgpd/consulta'])
def test_widget_dentro_do_formulario(client, rota):
    html = client.get(rota).get_data(as_text=True)
    assert 'recaptcha' not in html.lower()
    assert 'challenges.cloudflare.com/turnstile/v0/api.js' in html
    formulario = re.search(r'<form\b.*?</form>', html, re.S | re.I).group(0)
    assert f'data-sitekey="{P.TURNSTILE_SITE_KEY}"' in formulario


def test_paginas_sem_formulario_publico_nao_carregam_turnstile(client):
    html = client.get('/lgpd').get_data(as_text=True)
    assert 'challenges.cloudflare.com' not in html and 'google.com/recaptcha' not in html


def test_templates_ativos_sem_recaptcha():
    import os
    ignorados = {'base.html', 'consulta.html'}  # não são renderizados por nenhuma rota
    for arquivo in os.listdir('templates'):
        if arquivo.endswith('.html') and arquivo not in ignorados:
            with open(os.path.join('templates', arquivo), encoding='utf-8') as f:
                assert 'recaptcha' not in f.read().lower(), arquivo
