"""Testes do cadastro e da alteração de usuários com o Cognito (boto3 e banco mockados: não acessam a AWS).

Em produção o cadastro novo vai só para o Cognito (sem linha em users), com custom:roles e
custom:permission derivado de roles; buscar_usuario encontra esses usuários no Cognito.
Rodar a partir de app/: pytest test_cadastro_cognito.py -v
"""
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from flask.sessions import SecureCookieSessionInterface

import pesquisa as P

FORM = {'siape': '1234567', 'nome': '  Maria   da Silva ', 'email': 'Maria@UFCA.edu.br', 'roles': 'user'}


def erro(codigo):
    return ClientError({'Error': {'Code': codigo, 'Message': codigo}}, 'op')


def usuario_cognito(username, roles='user', permission='1', email='so@ufca.edu.br', nome='Só Cognito'):
    return {'Username': username, 'UserStatus': 'CONFIRMED', 'UserAttributes': [
        {'Name': 'name', 'Value': nome}, {'Name': 'email', 'Value': email},
        {'Name': 'custom:roles', 'Value': roles}, {'Name': 'custom:permission', 'Value': permission}]}


def atributos(chamada):
    return {a['Name']: a['Value'] for a in chamada.kwargs['UserAttributes']}


@pytest.fixture
def ambiente(monkeypatch):
    """Tabela users em memória (lista de linhas no formato de buscar_usuario) e Cognito mockado."""
    estado = {'users': [], 'escritas': [], 'erro_db': False}
    c = MagicMock()
    c.admin_get_user.side_effect = erro('UserNotFoundException')
    c.list_users.return_value = {'Users': []}
    c.admin_create_user.return_value = {'User': {'Attributes': [{'Name': 'sub', 'Value': 'sub-novo'}]}}

    def executar_select(consulta, tipo=0, valores=()):
        if estado['erro_db']:
            return None
        if 'FROM users' not in consulta:
            return [], 0
        u = estado['users']
        if 'ORDER BY nome' in consulta:
            achou = [(l[0], l[1], l[6], l[7], l[3], l[5]) for l in u]
        elif 'username != %s' in consulta:
            achou = [l for l in u if l[7].lower() == valores[0].lower() and l[1] != valores[1]]
        elif 'WHERE email=%s' in consulta:
            achou = [l for l in u if l[7].lower() == str(valores[0]).lower()]
        elif 'WHERE username=%s' in consulta:
            achou = [l for l in u if l[1] == str(valores[0])]
        elif 'WHERE id=%s' in consulta:
            achou = [l for l in u if l[0] == int(valores[0])]
            if consulta.startswith('SELECT id, username, nome, email, roles FROM'):
                achou = [(l[0], l[1], l[6], l[7], l[3]) for l in achou]
        else:
            raise AssertionError(consulta)
        return achou, len(achou)

    def atualizar(consulta, valores=()):
        estado['escritas'].append((consulta, list(valores)))
        if consulta.startswith('UPDATE users SET nome'):
            nome, email, roles, permissao, id_ = valores
            estado['users'] = [(l[0], l[1], permissao, roles, l[4], l[5], nome, email) if l[0] == id_ else l
                               for l in estado['users']]

    monkeypatch.setattr(P.app, 'session_interface', SecureCookieSessionInterface())
    monkeypatch.setattr(P.app, 'secret_key', 'teste-cadastro-cognito')
    monkeypatch.setitem(P.app.config, 'WTF_CSRF_ENABLED', False)
    monkeypatch.setattr(P.limiter, 'enabled', False)
    monkeypatch.setattr(P, 'USAR_COGNITO', True)
    monkeypatch.setattr(P, 'cognito', c)
    monkeypatch.setattr(P, 'executarSelect2', executar_select)
    monkeypatch.setattr(P, 'atualizar2', atualizar)
    monkeypatch.setattr(P, 'registrar_acesso', lambda *a: None)
    monkeypatch.setattr(P, 'aceite_pendente', lambda username: False)
    monkeypatch.setattr(P, 'carregar_mensagens', lambda: [])
    client = P.app.test_client()
    with client.session_transaction() as s:
        s.update({'username': '999', 'permissao': 0, 'roles': ['user', 'admin'], 'edital': 0})
    return estado, c, client


def flashes(client):
    with client.session_transaction() as s:
        return ' '.join(m for _, m in s.get('_flashes', []))


# ----- regras -----

@pytest.mark.parametrize('roles,esperado', [('user', 1), ('admin', 0), ('user,admin', 0), ('', 1)])
def test_permissao_derivada_de_roles(roles, esperado):
    assert P.permissao_de_roles(roles) == esperado


@pytest.mark.parametrize('email,ok', [('a.b@ufca.edu.br', True), ('a"b@ufca.edu.br', False),
                                      ('a@b', False), ('x@y.com" or "1', False)])
def test_email_valido(email, ok):
    assert P.email_valido(email) is ok


# ----- cadastro -----

def test_cadastro_vai_so_para_o_cognito_com_roles_e_permission(ambiente):
    estado, c, client = ambiente
    resp = client.post('/admin/cadastrar_usuario', data=dict(FORM, roles='user,admin'))
    assert resp.status_code == 302
    chamada = c.admin_create_user.call_args
    assert chamada.kwargs['Username'] == '1234567'
    assert chamada.kwargs['DesiredDeliveryMediums'] == ['EMAIL'] and 'MessageAction' not in chamada.kwargs
    assert atributos(chamada) == {'name': 'Maria da Silva', 'email': 'maria@ufca.edu.br', 'email_verified': 'true',
                                  'custom:roles': 'user,admin', 'custom:permission': '0', 'custom:legacy_id': '0'}
    assert estado['escritas'] == []  # nada na tabela users (nem INSERT nem marcar_migrado)
    assert 'convite foi enviado' in flashes(client)


def test_cadastro_user_tem_permission_1(ambiente):
    _, c, client = ambiente
    client.post('/admin/cadastrar_usuario', data=FORM)
    assert atributos(c.admin_create_user.call_args)['custom:permission'] == '1'


@pytest.mark.parametrize('campo,valor', [('roles', 'superadmin'), ('email', 'nao-e-email'), ('siape', '12 34'),
                                         ('nome', '   ')])
def test_cadastro_com_dados_invalidos_nao_cria(ambiente, campo, valor):
    _, c, client = ambiente
    client.post('/admin/cadastrar_usuario', data=dict(FORM, **{campo: valor}))
    assert not c.admin_create_user.called
    assert 'Dados inválidos' in flashes(client)


def test_cadastro_com_siape_ja_no_cognito_nao_cria(ambiente):
    _, c, client = ambiente
    c.admin_get_user.side_effect = None
    c.admin_get_user.return_value = usuario_cognito('1234567')
    client.post('/admin/cadastrar_usuario', data=FORM)
    assert not c.admin_create_user.called
    assert 'Usuário já cadastrado' in flashes(client)


def test_cadastro_com_email_ja_no_cognito_nao_cria(ambiente):
    _, c, client = ambiente
    c.list_users.return_value = {'Users': [usuario_cognito('777', email='maria@ufca.edu.br')]}
    client.post('/admin/cadastrar_usuario', data=FORM)
    assert c.list_users.call_args.kwargs['Filter'] == 'email = "maria@ufca.edu.br"'
    assert not c.admin_create_user.called
    assert 'E-mail já cadastrado' in flashes(client)


def test_cadastro_com_siape_na_tabela_users_nao_cria(ambiente):
    estado, c, client = ambiente
    estado['users'] = [(5, '1234567', 1, 'user', None, 0, 'Legado', 'legado@ufca.edu.br')]
    client.post('/admin/cadastrar_usuario', data=FORM)
    assert not c.admin_create_user.called
    assert 'Usuário já cadastrado' in flashes(client)


def test_cadastro_com_erro_no_cognito_nao_cria(ambiente):
    _, c, client = ambiente
    c.admin_get_user.side_effect = erro('InternalErrorException')
    client.post('/admin/cadastrar_usuario', data=FORM)
    assert not c.admin_create_user.called
    assert 'Nada foi gravado' in flashes(client)


def test_cadastro_em_dev_grava_em_users_com_permission(ambiente, monkeypatch):
    estado, c, client = ambiente
    monkeypatch.setattr(P, 'USAR_COGNITO', False)
    client.post('/admin/cadastrar_usuario', data=dict(FORM, roles='admin'))
    assert not c.admin_create_user.called and not c.admin_get_user.called
    consulta, valores = estado['escritas'][0]
    assert consulta.startswith('INSERT INTO users')
    assert valores[0:3] == ['1234567', 'Maria da Silva', 'maria@ufca.edu.br'] and valores[4:] == ['admin', 0]


# ----- buscar_usuario com fallback para o Cognito -----

def test_buscar_usuario_encontra_quem_esta_so_no_cognito(ambiente):
    _, c, _ = ambiente
    c.admin_get_user.side_effect = None
    c.admin_get_user.return_value = usuario_cognito('1234567', roles='user,admin', permission='0')
    assert P.buscar_usuario('1234567') == (None, '1234567', 0, 'user,admin', None, 1, 'Só Cognito', 'so@ufca.edu.br')


def test_buscar_usuario_por_email_no_cognito(ambiente):
    _, c, _ = ambiente
    item = usuario_cognito('1234567')
    item['Attributes'] = item.pop('UserAttributes')  # list_users devolve 'Attributes'
    c.list_users.return_value = {'Users': [item]}
    linha = P.buscar_usuario('SO@ufca.edu.br', 'email')
    assert linha[0] is None and linha[1] == '1234567' and linha[5] == 1
    assert c.list_users.call_args.kwargs['Filter'] == 'email = "so@ufca.edu.br"'


def test_buscar_usuario_prefere_a_tabela_users(ambiente):
    estado, c, _ = ambiente
    estado['users'] = [(5, '1234567', 1, 'user', None, 1, 'Local', 'local@ufca.edu.br')]
    assert P.buscar_usuario('1234567')[0] == 5
    assert not c.admin_get_user.called


def test_buscar_usuario_com_erro_no_banco_nao_consulta_o_cognito(ambiente):
    estado, c, _ = ambiente
    estado['erro_db'] = True
    assert P.buscar_usuario('1234567') is None
    assert not c.admin_get_user.called


def test_buscar_usuario_com_erro_no_cognito_retorna_none(ambiente):
    _, c, _ = ambiente
    c.admin_get_user.side_effect = erro('InternalErrorException')
    assert P.buscar_usuario('1234567') is None


def test_login_de_quem_esta_so_no_cognito_autentica_no_cognito(ambiente):
    _, c, _ = ambiente
    c.admin_get_user.side_effect = None
    c.admin_get_user.return_value = usuario_cognito('1234567')
    c.admin_initiate_auth.side_effect = erro('NotAuthorizedException')
    with P.app.test_request_context('/login', method='POST'):
        assert P.autenticar_usuario('1234567', 'errada') == 'invalido'
    assert c.admin_initiate_auth.call_args.kwargs['AuthParameters']['USERNAME'] == '1234567'


# ----- listar e alterar -----

def test_listar_junta_tabela_e_cognito(ambiente):
    estado, c, client = ambiente
    estado['users'] = [(5, '111', 1, 'user', None, 1, 'Zélia', 'z@ufca.edu.br')]
    so = usuario_cognito('222', nome='Ágata')
    so['Attributes'] = so.pop('UserAttributes')
    local = usuario_cognito('111', nome='Zélia')
    local['Attributes'] = local.pop('UserAttributes')
    c.list_users.side_effect = [{'Users': [local], 'PaginationToken': 't'}, {'Users': [so]}]
    html = client.get('/admin/listarUsuarios').get_data(as_text=True)
    assert html.index('Ágata') < html.index('Zélia')  # ordem por nome, sem acento
    assert '/admin/alterarUsuarioCognito/222' in html and '/admin/alterarUsuario/5' in html
    assert html.count('Só no Cognito') == 1
    assert c.list_users.call_args.kwargs['PaginationToken'] == 't'


def test_listar_com_erro_no_cognito_mostra_so_a_tabela(ambiente):
    estado, c, client = ambiente
    estado['users'] = [(5, '111', 1, 'user', None, 1, 'Zélia', 'z@ufca.edu.br')]
    c.list_users.side_effect = erro('AccessDeniedException')
    html = client.get('/admin/listarUsuarios').get_data(as_text=True)
    assert 'Zélia' in html and 'Não foi possível consultar o Cognito' in html


def test_alterar_usuario_local_deriva_permission_e_sincroniza(ambiente):
    estado, c, client = ambiente
    estado['users'] = [(5, '111', 1, 'user', None, 1, 'Fulano', 'f@ufca.edu.br')]
    client.post('/admin/alterarUsuario/5', data={'nome': 'Fulano', 'email': 'f@ufca.edu.br', 'roles': 'user,admin'})
    consulta, valores = estado['escritas'][0]
    assert 'permission=%s' in consulta and valores == ['Fulano', 'f@ufca.edu.br', 'user,admin', 0, 5]
    enviados = atributos(c.admin_update_user_attributes.call_args)
    assert enviados['custom:roles'] == 'user,admin' and enviados['custom:permission'] == '0'
    assert enviados['custom:legacy_id'] == '5'


def test_alterar_usuario_local_recusa_roles_invalidas(ambiente):
    estado, c, client = ambiente
    estado['users'] = [(5, '111', 1, 'user', None, 1, 'Fulano', 'f@ufca.edu.br')]
    client.post('/admin/alterarUsuario/5', data={'nome': 'Fulano', 'email': 'f@ufca.edu.br', 'roles': 'root'})
    assert estado['escritas'] == [] and not c.admin_update_user_attributes.called


def test_alterar_usuario_so_no_cognito(ambiente):
    estado, c, client = ambiente
    c.admin_get_user.side_effect = None
    c.admin_get_user.return_value = usuario_cognito('222', roles='user,admin', permission='0')
    html = client.get('/admin/alterarUsuarioCognito/222').get_data(as_text=True)
    assert 'action="/admin/alterarUsuarioCognito/222"' in html and 'Só Cognito' in html
    client.post('/admin/alterarUsuarioCognito/222', data={'nome': 'Novo Nome', 'email': 'novo@ufca.edu.br',
                                                         'roles': 'user'})
    chamada = c.admin_update_user_attributes.call_args
    assert chamada.kwargs['Username'] == '222'
    assert atributos(chamada) == {'name': 'Novo Nome', 'email': 'novo@ufca.edu.br', 'email_verified': 'true',
                                  'custom:roles': 'user', 'custom:permission': '1', 'custom:legacy_id': '0'}
    assert estado['escritas'] == []


def test_alterar_usuario_so_no_cognito_recusa_email_de_outro(ambiente):
    _, c, client = ambiente
    c.admin_get_user.side_effect = None
    c.admin_get_user.return_value = usuario_cognito('222')
    c.list_users.return_value = {'Users': [usuario_cognito('333', email='outro@ufca.edu.br')]}
    client.post('/admin/alterarUsuarioCognito/222', data={'nome': 'Nome', 'email': 'outro@ufca.edu.br',
                                                         'roles': 'user'})
    assert not c.admin_update_user_attributes.called
    assert 'E-mail já cadastrado' in flashes(client)


def test_alterar_usuario_cognito_com_linha_local_redireciona(ambiente):
    estado, _, client = ambiente
    estado['users'] = [(5, '111', 1, 'user', None, 1, 'Fulano', 'f@ufca.edu.br')]
    resp = client.get('/admin/alterarUsuarioCognito/111')
    assert resp.status_code == 302 and resp.headers['Location'].endswith('/admin/alterarUsuario/5')
