"""Testes do registro de acessos: o que é gravado, as recusas e o mascaramento de dados pessoais e tokens.

Rodar a partir de app/: pytest test_log_acessos.py -v
"""
import ast
import hashlib
import json

import pytest
from flask.sessions import SecureCookieSessionInterface
from loguru import logger

import pesquisa as P

TOKEN = 'token-falso-de-teste-do-avaliador-0001'  # valor inventado; não imita JWT (evita alerta do GitGuardian)
CPF = '529.982.247-25'


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(P.app, 'session_interface', SecureCookieSessionInterface())
    monkeypatch.setattr(P.app, 'secret_key', 'teste-log')
    monkeypatch.setitem(P.app.config, 'WTF_CSRF_ENABLED', False)
    monkeypatch.setattr(P.limiter, 'enabled', False)
    monkeypatch.setattr(P, 'carregar_mensagens', lambda: [])
    monkeypatch.setattr(P, 'getDados', lambda ip: {'city': 'Juazeiro do Norte', 'state': 'Ceará', 'country': 'Brazil'})
    return P.app.test_client()


@pytest.fixture
def registros():
    """Os registros do loguru como o app.json os grava (serialize=True): mensagem + extra."""
    capturados = []
    sink = logger.add(lambda m: capturados.append(json.loads(m)['record']), serialize=True, level='INFO')
    yield capturados
    logger.remove(sink)


def de_acesso(registros):
    return [r for r in registros if r['extra'].get('rota') is not None and 'cidade' in r['extra']]


def como(client, roles, username='111'):
    with client.session_transaction() as s:
        s.update({'username': username, 'permissao': 0, 'roles': roles, 'edital': 0})


# ----- o que é gravado -----

def test_acesso_grava_ip_da_cloudflare_usuario_rota_metodo_e_localizacao(client, registros):
    como(client, ['admin', 'user'])
    client.get('/lgpd', headers={'CF-Connecting-IP': '200.1.2.3'}, environ_base={'REMOTE_ADDR': '172.70.0.1'})
    r = de_acesso(registros)[0]
    assert r['message'] == 'Acesso a recurso (AUTENTICADO)'
    assert r['extra'] == {'ip': '200.1.2.3', 'username': '111', 'rota': '/lgpd', 'metodo': 'GET',
                          'cidade': 'Juazeiro do Norte', 'estado': 'Ceará', 'pais': 'Brazil'}


def test_sem_cabecalho_da_cloudflare_usa_o_remote_addr(client, registros):
    client.get('/lgpd', environ_base={'REMOTE_ADDR': '10.0.0.9'})
    r = de_acesso(registros)[0]
    assert r['extra']['ip'] == '10.0.0.9' and r['extra']['username'] == 'N/A'
    assert r['message'] == 'Acesso a recurso (NÃO AUTENTICADO)'


# ----- mascaramento do caminho -----

def test_token_do_avaliador_nao_vai_para_o_log(client, registros):
    client.get('/arquivo/' + TOKEN)
    rota = de_acesso(registros)[0]['extra']['rota']
    assert TOKEN not in rota and 'falso-de-teste' not in rota
    assert rota == '/arquivo/tok:' + hashlib.sha256(TOKEN.encode()).hexdigest()[:12]
    assert all(TOKEN not in json.dumps(r) and 'falso-de-teste' not in json.dumps(r) for r in registros)


def test_cpf_no_caminho_nao_vai_para_o_log(client, registros, monkeypatch):
    monkeypatch.setattr(P, 'executarSelect2', lambda *a, **k: ([], 0))
    client.get('/indicacao/' + CPF)
    client.get('/indicacao/52998224725')
    rotas = [r['extra']['rota'] for r in de_acesso(registros)]
    assert rotas == ['/indicacao/[cpf]', '/indicacao/[cpf]']
    assert all('52998224725' not in json.dumps(r) and CPF not in json.dumps(r) for r in registros)


def test_email_no_caminho_nao_vai_para_o_log(client, registros, monkeypatch):
    monkeypatch.setattr(P, 'atualizar2', lambda *a, **k: None)
    monkeypatch.setattr(P, 'executarSelect2', lambda *a, **k: ([], 0))
    como(client, ['admin', 'user'])
    client.get('/admin/listaNegra/fulano@ufca.edu.br')
    assert [r['extra']['rota'] for r in de_acesso(registros)] == ['/admin/listaNegra/[email]']


@pytest.mark.parametrize('token', ['abc', TOKEN])
def test_resumo_token(token):
    resumo = P.resumo_token(token)
    assert resumo.startswith('tok:') and len(resumo) == 16 and token not in resumo


# ----- recusas -----

def test_acesso_negado_sem_login_fica_registrado(client, registros):
    client.get('/admin/indicacoes?edital=1', headers={'CF-Connecting-IP': '200.9.9.9'})
    r = de_acesso(registros)
    assert [x['message'] for x in r] == ['Acesso negado (NÃO AUTENTICADO)']
    assert r[0]['level']['name'] == 'WARNING' and r[0]['extra']['ip'] == '200.9.9.9'


def test_acesso_negado_sem_permissao_fica_registrado(client, registros):
    como(client, ['user'], username='222')
    client.get('/admin/indicacoes?edital=1')
    r = de_acesso(registros)
    assert [x['message'] for x in r] == ['Acesso negado (SEM PERMISSÃO: exige admin)']
    assert r[0]['extra']['username'] == '222'


def test_bloqueio_por_aceite_pendente_fica_registrado(client, registros):
    como(client, ['user'])
    with client.session_transaction() as s:
        s['aceite_pendente'] = True
    client.get('/meusDados')
    assert 'Acesso bloqueado (ciência da política de privacidade pendente)' in [x['message'] for x in de_acesso(registros)]


def test_bloqueio_por_senha_vazada_fica_registrado(client, registros):
    como(client, ['user'])
    with client.session_transaction() as s:
        s['senha_vazada'] = True
    client.get('/meusDados')
    assert 'Acesso bloqueado (SENHA VAZADA: troca de senha pendente)' in [x['message'] for x in de_acesso(registros)]


def test_404_fica_registrado_e_continua_404(client, registros):
    r = client.get('/wp-login.php', headers={'CF-Connecting-IP': '203.0.113.5'})
    assert r.status_code == 404
    assert [(x['message'], x['extra']['ip']) for x in de_acesso(registros)] == [('Recurso inexistente (404)', '203.0.113.5')]


def test_429_fica_registrado(client, registros):
    with P.app.test_request_context('/login', headers={'CF-Connecting-IP': '203.0.113.7'}):
        class Excedido:
            description = '10 per 1 minute'
        corpo, status = P.ratelimit_handler(Excedido())
    assert status == 429
    r = de_acesso(registros)[0]
    assert r['message'] == 'Acesso bloqueado (LIMITE DE TENTATIVAS: 10 per 1 minute)' and r['level']['name'] == 'WARNING'


# ----- cobertura -----

def test_rotas_sem_registro_sao_so_as_esperadas():
    arvore = ast.parse(open('pesquisa.py', encoding='utf-8').read())
    sem_log = set()
    for no in arvore.body:
        if isinstance(no, ast.FunctionDef):
            decoradores = [ast.unparse(d) for d in no.decorator_list]
            if any(d.startswith('app.route') for d in decoradores) and 'log_required' not in decoradores:
                sem_log.add(no.name)
    # health/version: chamadas pelo healthcheck; home/seguranca: páginas informativas públicas
    assert sem_log == {'home', 'seguranca', 'health', 'version'}


# ----- mensagens do log: sem CPF, e-mail, nomes, valores de SQL nem a AES_KEY -----

def test_patcher_mascara_cpf_e_email_mas_mantem_o_ip(registros):
    logger.warning("Duplicate entry '{}' para {} vindo de {}", CPF, 'fulano@ufca.edu.br', '200.1.2.3')
    with logger.contextualize(erro="Duplicate entry '52998224725' for key 'cpf'"):
        logger.error("falhou")
    textos = json.dumps(registros[-2:])
    assert CPF not in textos and '52998224725' not in textos and 'fulano@ufca.edu.br' not in textos
    assert '[cpf]' in textos and '[email]' in textos and '200.1.2.3' in textos


def test_erro_no_insert_nao_grava_os_valores_nem_a_chave(registros, monkeypatch):
    class Cursor:
        def execute(self, *a):
            raise P.MySQLdb.Error("Duplicate entry '529.982.247-25' for key 'cpf'")
        def close(self): pass

    class Conexao:
        def select_db(self, *a): pass
        def cursor(self): return Cursor()
        def close(self): pass

    monkeypatch.setattr(P.MySQLdb, 'connect', lambda *a, **k: Conexao())
    consulta, valores = P.montar_insert_indicacao([('nome', 'Maria'), ('cpf', CPF), ('conta', '12345-6')], 'iv1', CPF)
    P.inserir(consulta, valores)
    textos = json.dumps(registros)
    assert 'Erro ao inserir registro' in textos
    for proibido in (P.AES_KEY, CPF, '12345-6', 'Maria'):
        assert proibido not in textos


def test_resumo_email():
    assert P.resumo_email('Fulano@UFCA.edu.br ') == P.resumo_email('fulano@ufca.edu.br')
    assert P.resumo_email('fulano@ufca.edu.br').startswith('email:') and '@' not in P.resumo_email('x@y.z')


def test_nenhuma_chamada_de_log_recebe_dado_pessoal_ou_valores_de_sql():
    """Trava contra regressões: nomes de variáveis que carregam dados pessoais, credenciais ou os valores
    de uma consulta (que levam a AES_KEY) não podem ir direto para o logger."""
    proibidos = {'valores', 'parametros', 'cpf', 'email', 'email_avaliador', 'nome_avaliador', 'orientador',
                 'senha', 'password', 'token', 'tokenAvaliacao', 'AES_KEY', 'destinatario'}
    arvore = ast.parse(open('pesquisa.py', encoding='utf-8').read())
    achados = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) and getattr(no.func.value, 'id', None) == 'logger':
            valores = list(no.args) + [k.value for k in no.keywords]
            for valor in valores:
                for nome in ast.walk(valor):
                    if isinstance(nome, ast.Name) and nome.id in proibidos:
                        # permitido só dentro de resumo_token/resumo_email/calcula_hash
                        pais = [n for n in ast.walk(valor) if isinstance(n, ast.Call)
                                and getattr(n.func, 'id', '') in ('resumo_token', 'resumo_email', 'calcula_hash', 'len')
                                and nome in list(ast.walk(n))]
                        if not pais:
                            achados.append(f"linha {no.lineno}: {nome.id}")
    assert achados == []
