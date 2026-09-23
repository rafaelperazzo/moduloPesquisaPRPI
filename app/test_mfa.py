"""Testes do MFA (Cognito) com o cliente boto3 mockado: não acessam a AWS.

O MFA só existe em produção; aqui USAR_COGNITO é forçado para True via monkeypatch.
Rodar a partir de app/: pytest test_mfa.py -v
"""
import re
import time
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from flask.sessions import SecureCookieSessionInterface

import pesquisa as P

SENHA = 'Senha#Segura2026'
USUARIOS = {
    # id, username, permission, roles, password, migrado, nome, email
    '111': (1, '111', 1, 'user', None, 1, 'Fulano', 'fulano@ufca.edu.br'),
    '222': (2, '222', 1, 'user', None, 0, 'Legado', 'legado@ufca.edu.br'),
}


def erro(codigo):
    return ClientError({'Error': {'Code': codigo, 'Message': codigo}}, 'op')


def resultado_tokens():
    return {'AuthenticationResult': {'AccessToken': 'access', 'RefreshToken': 'refresh', 'ExpiresIn': 3600}}


@pytest.fixture
def cognito(monkeypatch):
    c = MagicMock()
    c.admin_get_user.return_value = {'UserStatus': 'CONFIRMED', 'UserAttributes': [
        {'Name': 'custom:roles', 'Value': 'user'}, {'Name': 'custom:permission', 'Value': '1'}]}
    c.admin_initiate_auth.return_value = resultado_tokens()
    c.get_user.return_value = {'UserAttributes': [{'Name': 'email', 'Value': 'fulano@ufca.edu.br'}],
                               'UserMFASettingList': []}
    c.associate_software_token.return_value = {'SecretCode': 'JBSWY3DPEHPK3PXP'}
    c.verify_software_token.return_value = {'Status': 'SUCCESS'}
    c.admin_create_user.return_value = {'User': {'Attributes': [{'Name': 'sub', 'Value': 'sub-1'}]}}

    monkeypatch.setattr(P.app, 'session_interface', SecureCookieSessionInterface())
    monkeypatch.setattr(P.app, 'secret_key', 'teste-mfa')
    monkeypatch.setitem(P.app.config, 'WTF_CSRF_ENABLED', False)
    monkeypatch.setattr(P.limiter, 'enabled', False)
    monkeypatch.setattr(P, 'USAR_COGNITO', True)
    monkeypatch.setattr(P, 'cognito', c)
    monkeypatch.setattr(P, 'buscar_usuario', lambda valor, campo='username': USUARIOS.get(str(valor)))
    monkeypatch.setattr(P, 'registrar_acesso', lambda *a: None)
    monkeypatch.setattr(P, 'marcar_migrado', lambda *a: True)
    monkeypatch.setattr(P, 'verificar_senha_legado', lambda linha, senha: senha == SENHA)
    return c


@pytest.fixture
def emails(monkeypatch):
    enviados = []
    monkeypatch.setattr(P, 'send_email_async', lambda dest, assunto, corpo: enviados.append((dest, assunto, corpo)) or True)
    return enviados


@pytest.fixture
def client(cognito):
    return P.app.test_client()


def logado(client, **extra):
    with client.session_transaction() as s:
        s.update({'username': '111', 'permissao': 1, 'roles': ['user'], 'edital': 0,
                  'cognito_tokens': {'access': 'access', 'refresh': 'refresh', 'expira': time.time() + 3000}})
        s.update(extra)


def sessao(client):
    with client.session_transaction() as s:
        return dict(s)


# --- autenticar_cognito ------------------------------------------------------

def test_desafio_mfa_interativo_aguarda_codigo(cognito):
    cognito.admin_initiate_auth.return_value = {'ChallengeName': 'SOFTWARE_TOKEN_MFA', 'Session': 'S1',
                                                'ChallengeParameters': {}}
    with P.app.test_request_context('/login', method='POST'):
        assert P.autenticar_cognito('111', SENHA) == 'mfa'
        assert P.session['cognito_mfa']['tipo'] == 'SOFTWARE_TOKEN_MFA'
        assert 'username' not in P.session


def test_desafio_mfa_basic_auth_valida_so_a_senha(cognito):
    cognito.admin_initiate_auth.return_value = {'ChallengeName': 'EMAIL_OTP', 'Session': 'S1'}
    with P.app.test_request_context('/get_bib/1', method='GET'):
        assert P.autenticar_cognito('111', SENHA, interativo=False) == 'ok'
        assert 'cognito_mfa' not in P.session
        assert P.session['username'] == '111'


def test_login_sem_mfa_fica_pendente(cognito):
    with P.app.test_request_context('/login', method='POST'):
        assert P.autenticar_cognito('111', SENHA) == 'ok'
        assert P.session['mfa_pendente'] is True
        assert P.session['cognito_tokens']['access'] == 'access'


def test_migracao_silenciosa_obtem_tokens_e_cai_no_cadastro(cognito):
    with P.app.test_request_context('/login', method='POST'):
        assert P.autenticar_usuario('222', SENHA) == 'ok'
        cognito.admin_set_user_password.assert_called_once()
        cognito.admin_initiate_auth.assert_called_once()
        assert P.session['mfa_pendente'] is True


def test_refresh_do_access_token_expirado(cognito):
    cognito.admin_initiate_auth.return_value = {'AuthenticationResult': {'AccessToken': 'novo', 'ExpiresIn': 3600}}
    with P.app.test_request_context('/'):
        P.session['cognito_tokens'] = {'access': 'velho', 'refresh': 'refresh', 'expira': time.time() - 1}
        assert P.obter_access_token() == 'novo'
        assert P.session['cognito_tokens']['refresh'] == 'refresh'
        assert cognito.admin_initiate_auth.call_args.kwargs['AuthFlow'] == 'REFRESH_TOKEN_AUTH'


# --- gates --------------------------------------------------------------------

def test_gate_mfa_pendente_redireciona_para_cadastro(client):
    logado(client, mfa_pendente=True)
    resposta = client.get('/')
    assert resposta.status_code == 302 and resposta.location.endswith('/mfa/configurar')
    assert client.get('/mfa/configurar').status_code == 200


def test_sessao_basic_auth_nao_navega_no_site(client):
    logado(client, somente_basic_auth=True)
    resposta = client.get('/')
    assert resposta.status_code == 302 and resposta.location.endswith('/login')
    assert 'username' not in sessao(client)


def test_dev_nao_tem_mfa(client, monkeypatch):
    monkeypatch.setattr(P, 'USAR_COGNITO', False)
    logado(client, mfa_pendente=True)
    assert client.get('/mfa/configurar').location.endswith('/')
    assert client.get('/seguranca').status_code == 200  # gate inativo em dev


# --- cadastro ----------------------------------------------------------------

def test_cadastro_totp(client, cognito):
    logado(client, mfa_pendente=True)
    resposta = client.get('/mfa/totp')
    assert resposta.status_code == 200
    assert b'<svg' in resposta.data and b'JBSWY3DPEHPK3PXP' in resposta.data
    resposta = client.post('/mfa/totp', data={'codigo': '123456'})
    assert resposta.location.endswith('/')
    cognito.set_user_mfa_preference.assert_called_once_with(
        AccessToken='access', SoftwareTokenMfaSettings={'Enabled': True, 'PreferredMfa': True})
    s = sessao(client)
    assert 'mfa_pendente' not in s and 'mfa_totp_secret' not in s


def test_cadastro_totp_codigo_errado_mantem_o_mesmo_qr(client, cognito):
    logado(client, mfa_pendente=True)
    client.get('/mfa/totp')
    cognito.verify_software_token.side_effect = erro('CodeMismatchException')
    resposta = client.post('/mfa/totp', data={'codigo': '000000'})
    assert resposta.status_code == 200 and b'JBSWY3DPEHPK3PXP' in resposta.data
    assert cognito.associate_software_token.call_count == 1
    assert sessao(client)['mfa_pendente'] is True


def test_troca_de_totp_para_email_desativa_o_app(client, cognito):
    cognito.get_user.return_value['UserMFASettingList'] = ['SOFTWARE_TOKEN_MFA']
    logado(client)
    client.post('/mfa/email')
    cognito.set_user_mfa_preference.assert_called_once_with(
        AccessToken='access', EmailMfaSettings={'Enabled': True, 'PreferredMfa': True},
        SoftwareTokenMfaSettings={'Enabled': False, 'PreferredMfa': False})


def test_otpauth_uri():
    uri, svg = P.qrcode_totp_svg('111', 'ABC')
    assert uri == 'otpauth://totp/Yoko%20Pesquisa:111?secret=ABC&issuer=Yoko%20Pesquisa'
    assert svg.lstrip().startswith('<svg') and 'viewBox' in svg


# --- desafio no login -----------------------------------------------------------

def desafio(client, tipo='SOFTWARE_TOKEN_MFA'):
    with client.session_transaction() as s:
        s['cognito_mfa'] = {'username': '111', 'session': 'S1', 'tipo': tipo, 'destino': 'f***@ufca.edu.br',
                            'senha_vazada': False}


def test_verificar_codigo_correto_conclui_login(client, cognito):
    desafio(client)
    cognito.admin_respond_to_auth_challenge.return_value = resultado_tokens()
    resposta = client.post('/mfa/verificar', data={'codigo': '123 456'})
    assert resposta.location.endswith('/')
    respostas = cognito.admin_respond_to_auth_challenge.call_args.kwargs['ChallengeResponses']
    assert respostas == {'USERNAME': '111', 'SOFTWARE_TOKEN_MFA_CODE': '123456'}
    s = sessao(client)
    assert s['username'] == '111' and 'mfa_pendente' not in s and 'cognito_mfa' not in s


def test_verificar_email_otp(client, cognito):
    desafio(client, 'EMAIL_OTP')
    assert b'f***@ufca.edu.br' in client.get('/mfa/verificar').data
    cognito.admin_respond_to_auth_challenge.return_value = resultado_tokens()
    client.post('/mfa/verificar', data={'codigo': '12345678'})
    respostas = cognito.admin_respond_to_auth_challenge.call_args.kwargs['ChallengeResponses']
    assert respostas['EMAIL_OTP_CODE'] == '12345678'


def test_verificar_codigo_errado_permite_nova_tentativa(client, cognito):
    desafio(client)
    cognito.admin_respond_to_auth_challenge.side_effect = erro('CodeMismatchException')
    resposta = client.post('/mfa/verificar', data={'codigo': '000000'})
    assert resposta.location.endswith('/mfa/verificar')
    assert 'cognito_mfa' in sessao(client) and 'username' not in sessao(client)


def test_verificar_sessao_expirada_volta_ao_login(client, cognito):
    desafio(client)
    cognito.admin_respond_to_auth_challenge.side_effect = erro('NotAuthorizedException')
    resposta = client.post('/mfa/verificar', data={'codigo': '000000'})
    assert resposta.location.endswith('/login')
    assert 'cognito_mfa' not in sessao(client)


# --- recuperação -------------------------------------------------------------

def codigo_enviado(emails):
    return re.search(r'>(\d{8})<', emails[-1][2]).group(1)


def test_recuperacao_desvincula_o_app(client, cognito, emails):
    desafio(client)
    resposta = client.post('/mfa/recuperar')
    assert resposta.location.endswith('/mfa/recuperar/confirmar')
    assert emails[0][0] == 'fulano@ufca.edu.br'
    resposta = client.post('/mfa/recuperar/confirmar', data={'codigo': codigo_enviado(emails)})
    assert resposta.location.endswith('/login')
    cognito.admin_set_user_mfa_preference.assert_called_once_with(
        UserPoolId=P.COGNITO_USER_POOL_ID, Username='111',
        SoftwareTokenMfaSettings={'Enabled': False, 'PreferredMfa': False})
    assert len(emails) == 2  # aviso de MFA redefinido
    s = sessao(client)
    assert 'mfa_recuperacao' not in s and 'cognito_mfa' not in s and 'username' not in s


def test_recuperacao_bloqueia_apos_5_tentativas(client, cognito, emails):
    desafio(client)
    client.post('/mfa/recuperar')
    certo = codigo_enviado(emails)
    for _ in range(P.MFA_RECUPERACAO_TENTATIVAS):
        client.post('/mfa/recuperar/confirmar', data={'codigo': '00000000' if certo != '00000000' else '11111111'})
    resposta = client.post('/mfa/recuperar/confirmar', data={'codigo': certo})
    assert resposta.location.endswith('/login')
    cognito.admin_set_user_mfa_preference.assert_not_called()


def test_recuperacao_expirada(client, cognito, emails):
    desafio(client)
    client.post('/mfa/recuperar')
    with client.session_transaction() as s:
        s['mfa_recuperacao'] = {**s['mfa_recuperacao'], 'expira': time.time() - 1}
    resposta = client.post('/mfa/recuperar/confirmar', data={'codigo': codigo_enviado(emails)})
    assert resposta.location.endswith('/login')
    cognito.admin_set_user_mfa_preference.assert_not_called()


def test_recuperacao_so_para_app_autenticador(client, emails):
    desafio(client, 'EMAIL_OTP')
    assert client.post('/mfa/recuperar').location.endswith('/login')
    assert emails == []


# --- troca de senha com MFA ativo -------------------------------------------------

def test_nova_senha_usa_o_access_token_sem_reautenticar(client, cognito):
    logado(client)
    nova = 'Outra#Senha2026x'
    resposta = client.post('/novaSenha', data={'senha_atual': SENHA, 'nova_senha': nova, 'confirmar_senha': nova})
    assert resposta.location.endswith('/')
    cognito.change_password.assert_called_once_with(PreviousPassword=SENHA, ProposedPassword=nova, AccessToken='access')
    cognito.admin_initiate_auth.assert_not_called()


def test_nova_senha_atual_incorreta(client, cognito):
    logado(client)
    cognito.change_password.side_effect = erro('NotAuthorizedException')
    nova = 'Outra#Senha2026x'
    client.post('/novaSenha', data={'senha_atual': 'errada', 'nova_senha': nova, 'confirmar_senha': nova})
    assert 'Senha atual incorreta.' in str(sessao(client).get('_flashes'))
