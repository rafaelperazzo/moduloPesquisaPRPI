"""Testes do Sentry sem dados pessoais (LGPD): o evento que sairia para o Sentry é capturado localmente.

Rodar a partir de app/: pytest test_sentry.py -v
"""
import json

import pytest
import sentry_sdk
from flask.sessions import SecureCookieSessionInterface
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.scrubber import EventScrubber
from sentry_sdk.transport import Transport

import pesquisa as P


@pytest.mark.parametrize('entrada,esperado', [
    ('Login de fulano@ufca.edu.br', 'Login de [email]'),
    ('[200.129.10.5][/avaliacao] abriu', '[[ip]][/avaliacao] abriu'),
    ('acesso de 2001:db8:85a3:0:0:8a2e:370:7334', 'acesso de [ip]'),
    ('cpf 123.456.789-01 e 12345678901', 'cpf [cpf] e [cpf]'),
    ('horário 12:30:45 e versão 11.1.0', 'horário 12:30:45 e versão 11.1.0'),  # não confunde com IP
    (None, None),
])
def test_mascarar_texto_sentry(entrada, esperado):
    assert P.mascarar_texto_sentry(entrada) == esperado


def test_before_send_mascara_mensagem_logentry_e_excecoes():
    evento = {'message': 'erro de a@b.com', 'logentry': {'message': 'ip 10.0.0.1', 'formatted': 'cpf 12345678901'},
              'exception': {'values': [{'type': 'Error', 'value': 'Duplicate entry 123.456.789-01'}]}}
    saida = P.sentry_before_send(evento, {})
    assert saida['message'] == 'erro de [email]'
    assert saida['logentry'] == {'message': 'ip [ip]', 'formatted': 'cpf [cpf]'}
    assert saida['exception']['values'][0]['value'] == 'Duplicate entry [cpf]'


def test_before_breadcrumb_mascara_a_mensagem():
    assert P.sentry_before_breadcrumb({'message': 'login 10.1.2.3'}, {})['message'] == 'login [ip]'
    assert P.sentry_before_breadcrumb({'category': 'http'}, {}) == {'category': 'http', 'message': None}


class Captura(Transport):
    def __init__(self, options=None):
        super().__init__(options)
        self.eventos = []

    def capture_envelope(self, envelope):
        for item in envelope.items:
            if item.headers.get('type') == 'event':
                self.eventos.append(json.loads(item.payload.get_bytes()))


@pytest.fixture
def sentry_local(monkeypatch):
    """Mesma configuração do pesquisa.py (produção), com o transporte capturando em vez de enviar."""
    monkeypatch.setattr(P.app, 'session_interface', SecureCookieSessionInterface())
    monkeypatch.setattr(P.app, 'secret_key', 'teste-sentry')
    transporte = Captura()
    sentry_sdk.init(dsn='https://chave@exemplo.invalid/1', transport=transporte, integrations=[FlaskIntegration()],
                    send_default_pii=False, include_local_variables=False,
                    event_scrubber=EventScrubber(denylist=P.SENTRY_DENYLIST, pii_denylist=P.SENTRY_PII_DENYLIST, recursive=True),
                    before_send=P.sentry_before_send, before_breadcrumb=P.sentry_before_breadcrumb)
    yield transporte
    sentry_sdk.init(dsn=None)


def test_evento_real_sem_dados_pessoais(sentry_local):
    def falha(cpf, senha, nome_banco):
        conta = '98765-4'
        raise ValueError(f'falha ao gravar {cpf} de maria@x.com')

    with P.app.test_request_context('/cadastrarProjeto?x=1', method='POST',
                                    headers={'CF-Connecting-IP': '200.1.2.3', 'X-Forwarded-For': '200.1.2.3',
                                             'Cookie': 'session=abc', 'User-Agent': 'teste'},
                                    environ_base={'REMOTE_ADDR': '200.1.2.3'}):
        sentry_sdk.add_breadcrumb(message='[200.1.2.3] login de maria@x.com')
        with sentry_sdk.new_scope() as escopo:
            escopo.set_extra('cpf', '12345678901')
            escopo.set_extra('rota', '/cadastrarProjeto')
            try:
                falha('123.456.789-01', 'Senha#1', 'Banco X')
            except ValueError:
                sentry_sdk.capture_exception()
    sentry_sdk.flush()

    assert len(sentry_local.eventos) == 1
    evento = sentry_local.eventos[0]
    # O Sentry envia as linhas de código ao redor do erro; aqui elas são o próprio teste, que tem os dados
    # de exemplo escritos. Em produção são linhas do pesquisa.py, sem dados de usuários.
    for frame in evento['exception']['values'][0]['stacktrace']['frames']:
        for chave in ('pre_context', 'context_line', 'post_context'):
            frame.pop(chave, None)
    texto = json.dumps(evento, ensure_ascii=False)
    for dado in ('200.1.2.3', 'maria@x.com', '123.456.789-01', '12345678901', 'Senha#1', 'Banco X', '98765-4', 'session=abc'):
        assert dado not in texto, dado
    assert '[cpf]' in evento['exception']['values'][0]['value']            # a mensagem continua útil
    assert evento['exception']['values'][0]['stacktrace']['frames']          # o stack trace continua
    assert all('vars' not in f for f in evento['exception']['values'][0]['stacktrace']['frames'])
    assert evento['extra']['rota'] == '/cadastrarProjeto'
