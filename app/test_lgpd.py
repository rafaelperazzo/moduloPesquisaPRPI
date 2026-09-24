"""Testes da LGPD (/lgpd, ciência dos termos, "Meus dados" e solicitações), com o banco mockado.

Rodar a partir de app/: pytest test_lgpd.py -v
"""
import inspect
import json
from datetime import datetime, date

import pytest
from flask.sessions import SecureCookieSessionInterface

import pesquisa as P

USUARIO = (1, '111', 1, 'user', 'hash-secreto', 1, 'Fulano', 'fulano@ufca.edu.br')


@pytest.fixture
def banco(monkeypatch):
    """Registra as escritas (atualizar2) e controla a consulta do aceite."""
    estado = {'aceitou': False, 'escritas': [], 'situacao': 'aberta', 'consultas': []}

    def executarSelect2(consulta, tipo=0, valores=()):
        if 'FROM lgpd_aceites' in consulta:
            return ([(1,)], 1) if estado['aceitou'] else ([], 0)
        if 'FROM lgpd_solicitacoes WHERE id=' in consulta:
            if valores[0] != 5:
                return (None, 0)
            return (('ABCDEF123456', 'Maria Discente', 'maria@aluno.ufca.edu.br', 'acesso', estado['situacao']), 1)
        if 'FROM lgpd_solicitacoes WHERE protocolo=' in consulta:
            estado['consultas'].append(valores)
            if valores == ('ABCDEF123456', 'maria@aluno.ufca.edu.br'):
                return (('ABCDEF123456', 'acesso', datetime(2026, 9, 24, 10, 0), date(2026, 10, 9), estado['situacao'],
                         'Resposta enviada ao e-mail institucional.' if estado['situacao'] == 'respondida' else None,
                         datetime(2026, 9, 30, 15, 0) if estado['situacao'] == 'respondida' else None), 1)
            return (None, 0)
        return ([], 0)

    def atualizar2(consulta, valores=()):
        estado['escritas'].append((consulta, list(valores)))
        if 'INSERT IGNORE INTO lgpd_aceites' in consulta:
            estado['aceitou'] = True

    def consultar_dicts(consulta, valores=()):
        if 'FROM editalProjeto LEFT JOIN' in consulta:
            return [{'id': 7, 'edital': 'PIBIC 2026', 'titulo': 'Projeto X', 'ua': 'CCT', 'area_capes': 'Computação',
                     'data': datetime(2026, 3, 1, 10, 0), 'inicio': date(2026, 8, 1), 'fim': date(2027, 7, 31)}]
        if 'COUNT(*)' in consulta:
            return [{'total': 2}]
        if 'FROM acessos' in consulta:
            return [{'ip': '10.0.0.1', 'username': '111', 'data': datetime(2026, 9, 1)},
                    {'ip': '10.0.0.2', 'username': '111', 'data': datetime(2026, 9, 20)}]
        if 'FROM lgpd_aceites' in consulta:
            return [{'versao': P.LGPD_VERSAO, 'data': datetime(2026, 9, 24, 9, 0), 'ip': '10.0.0.2'}]
        return []

    monkeypatch.setattr(P.app, 'session_interface', SecureCookieSessionInterface())
    monkeypatch.setattr(P.app, 'secret_key', 'teste-lgpd')
    monkeypatch.setitem(P.app.config, 'WTF_CSRF_ENABLED', False)
    monkeypatch.setattr(P.limiter, 'enabled', False)
    monkeypatch.setattr(P, 'executarSelect2', executarSelect2)
    monkeypatch.setattr(P, 'atualizar2', atualizar2)
    monkeypatch.setattr(P, 'consultar_dicts', consultar_dicts)
    monkeypatch.setattr(P, 'buscar_usuario', lambda valor, campo='username': USUARIO)
    monkeypatch.setattr(P, 'carregar_mensagens', lambda: [])
    return estado


@pytest.fixture
def emails(monkeypatch):
    enviados = []
    monkeypatch.setattr(P, 'send_email_async', lambda dest, assunto, corpo: enviados.append((dest, assunto, corpo)) or True)
    return enviados


@pytest.fixture
def client(banco):
    return P.app.test_client()


def logado(client, **extra):
    with client.session_transaction() as s:
        s.update({'username': '111', 'permissao': 1, 'roles': ['user'], 'edital': 0})
        s.update(extra)


def sessao(client):
    with client.session_transaction() as s:
        return dict(s)


# ----- página pública -----

def test_politica_abre_sem_login(client):
    resposta = client.get('/lgpd')
    assert resposta.status_code == 200
    html = resposta.get_data(as_text=True)
    assert 'Transferência internacional' in html and 'us-east-2' in html
    assert 'Atendimento aos requisitos da LGPD' in html and 'Em andamento' in html
    assert f'Versão {P.LGPD_VERSAO}' in html


def test_google_analytics_removido():
    for arquivo in ('avaliacao.html', 'cadastrarProjeto.html', 'editalProjeto.html'):
        with open(f'templates/{arquivo}', encoding='utf-8') as f:
            assert 'googletagmanager' not in f.read(), arquivo


def test_retencao_dos_logs_por_tempo():
    assert P.LOG_RETENCAO == "90 days"


# ----- ciência dos termos após o login -----

def test_iniciar_sessao_marca_aceite_pendente(client, banco):
    with P.app.test_request_context():
        P.iniciar_sessao('111', 1, 'user')
        assert P.session.get('aceite_pendente') is True
    banco['aceitou'] = True
    with P.app.test_request_context():
        P.session['aceite_pendente'] = True
        P.iniciar_sessao('111', 1, 'user')
        assert 'aceite_pendente' not in P.session


def test_erro_de_banco_nao_trava_o_login(monkeypatch, banco):
    def falha(*a, **k):
        raise RuntimeError("tabela inexistente")
    monkeypatch.setattr(P, 'executarSelect2', falha)
    assert P.aceite_pendente('111') is False
    monkeypatch.setattr(P, 'executarSelect2', lambda *a, **k: None)  # executarSelect2 devolve None em erro
    assert P.aceite_pendente('111') is False


def test_pendente_redireciona_para_o_aceite(client):
    logado(client, aceite_pendente=True)
    resposta = client.get('/meusProjetos')
    assert resposta.status_code == 302 and resposta.location.endswith('/lgpd/aceite')
    assert client.get('/').location.endswith('/lgpd/aceite')


def test_pendente_ainda_acessa_politica_logout_e_mfa(client):
    logado(client, aceite_pendente=True)
    assert client.get('/lgpd').status_code == 200
    assert client.get('/lgpd/aceite').status_code == 200
    assert client.get('/lgpd/solicitacao').status_code == 200
    assert '/lgpd/aceite' not in (client.get('/mfa/configurar').location or '')
    assert client.get('/logout').location.endswith('/')


def test_mfa_pendente_tem_prioridade(client):
    logado(client, aceite_pendente=True, mfa_pendente=True)
    P.USAR_COGNITO, anterior = True, P.USAR_COGNITO
    try:
        assert client.get('/meusProjetos').location.endswith('/mfa/configurar')
    finally:
        P.USAR_COGNITO = anterior


def test_aceite_sem_marcar_nao_grava(client, banco):
    logado(client, aceite_pendente=True)
    resposta = client.post('/lgpd/aceite', data={})
    assert resposta.status_code == 200
    assert banco['escritas'] == []
    assert sessao(client).get('aceite_pendente') is True


def test_aceite_grava_e_libera(client, banco):
    logado(client, aceite_pendente=True)
    resposta = client.post('/lgpd/aceite', data={'ciente': '1'}, environ_base={'REMOTE_ADDR': '10.1.2.3'})
    assert resposta.status_code == 302 and resposta.location.endswith('/')
    consulta, valores = banco['escritas'][0]
    assert 'INSERT IGNORE INTO lgpd_aceites' in consulta
    assert valores == ['111', P.LGPD_VERSAO, '10.1.2.3']
    assert 'aceite_pendente' not in sessao(client)
    assert client.get('/lgpd').status_code == 200


def test_aceite_sem_login_vai_para_o_login(client):
    assert client.get('/lgpd/aceite').location.endswith('/login')


# ----- Meus dados -----

def test_meus_dados_exige_login(client):
    resposta = client.get('/meusDados')  # login_required devolve a tela de login
    assert resposta.status_code == 200 and b'Projeto X' not in resposta.data and b'Fulano' not in resposta.data


def test_meus_dados_mostra_os_dados(client):
    logado(client)
    html = client.get('/meusDados').get_data(as_text=True)
    assert 'Fulano' in html and 'fulano@ufca.edu.br' in html and 'Projeto X' in html
    assert 'hash-secreto' not in html
    assert '<strong>2</strong> discente(s)' in html


def test_meus_dados_json_sem_senha_e_ordenado(client):
    logado(client)
    resposta = client.get('/meusDados.json')
    assert resposta.status_code == 200
    assert 'attachment' in resposta.headers['Content-Disposition']
    dados = json.loads(resposta.data)
    assert 'hash-secreto' not in resposta.get_data(as_text=True)
    assert dados['cadastro'] == {'usuario': '111', 'nome': 'Fulano', 'email': 'fulano@ufca.edu.br', 'papeis': 'user'}
    assert dados['projetos'][0]['inicio'] == '2026-08-01'
    assert dados['acessos'][0]['ip'] == '10.0.0.2'  # mais recente primeiro
    assert dados['total_indicacoes_de_discentes'] == 2
    assert dados['ciencia_dos_termos'][0]['versao'] == P.LGPD_VERSAO


# ----- solicitações dos titulares -----

FORMULARIO = {'nome': 'Maria Discente', 'email': 'maria@aluno.ufca.edu.br', 'vinculo': 'discente',
              'tipo': 'acesso', 'descricao': 'Quero saber quais dados meus estão na plataforma.'}


def test_solicitacao_grava_e_envia_dois_emails(client, banco, emails):
    resposta = client.post('/lgpd/solicitacao', data=FORMULARIO)
    html = resposta.get_data(as_text=True)
    assert resposta.status_code == 200 and 'Solicitação registrada' in html
    consulta, valores = banco['escritas'][0]
    assert 'INSERT INTO lgpd_solicitacoes' in consulta
    protocolo = valores[0]
    assert len(protocolo) == 12 and protocolo in html
    assert (valores[6] - date.today()).days == P.LGPD_PRAZO_RESPOSTA
    assert [e[0] for e in emails] == [P.DEFAULT_INSTITUCIONAL, 'maria@aluno.ufca.edu.br']
    assert 'Quero saber' in emails[0][2]          # a PRPI recebe a descrição
    assert 'Quero saber' not in emails[1][2]      # o titular recebe só o protocolo e o prazo
    assert protocolo in emails[1][2]


@pytest.mark.parametrize('campo,valor', [('email', 'invalido'), ('tipo', 'hackear'), ('vinculo', 'x'), ('nome', '')])
def test_solicitacao_invalida_nao_grava(client, banco, emails, campo, valor):
    dados = dict(FORMULARIO, **{campo: valor})
    resposta = client.post('/lgpd/solicitacao', data=dados)
    assert resposta.status_code == 200
    assert banco['escritas'] == [] and emails == []


def test_solicitacao_tem_limite():
    # O limitador usa o Redis, ausente nos testes: confere o decorator no código da rota
    fonte = inspect.getsource(inspect.unwrap(P.lgpd_solicitacao))
    assert '@limiter.limit("3/day;2/hour;1/minute", methods=["POST"])' in fonte


def test_admin_lista_e_responde_enviando_email(client, banco, emails):
    logado(client, roles=['admin', 'user'], permissao=0)
    assert client.get('/admin/lgpd/solicitacoes').status_code == 200
    assert client.get('/admin/lgpd/solicitacoes?situacao=todas').status_code == 200
    resposta = client.post('/admin/lgpd/solicitacoes/5/responder', data={'resposta': 'Dados corrigidos em 30/09.'})
    assert resposta.location.endswith('/admin/lgpd/solicitacoes')
    consulta, valores = banco['escritas'][0]
    assert "situacao='respondida'" in consulta and "AND situacao='aberta'" in consulta
    assert valores == ['Dados corrigidos em 30/09.', '111', 5]
    assert len(emails) == 1
    destino, assunto, corpo = emails[0]
    assert destino == 'maria@aluno.ufca.edu.br' and 'ABCDEF123456' in assunto
    assert 'Dados corrigidos em 30/09.' in corpo and P.LGPD_LINK_CONSULTA in corpo


def test_admin_nao_responde_duas_vezes(client, banco, emails):
    logado(client, roles=['admin', 'user'], permissao=0)
    banco['situacao'] = 'respondida'
    client.post('/admin/lgpd/solicitacoes/5/responder', data={'resposta': 'De novo'})
    assert banco['escritas'] == [] and emails == []


def test_admin_solicitacao_inexistente(client, banco, emails):
    logado(client, roles=['admin', 'user'], permissao=0)
    client.post('/admin/lgpd/solicitacoes/99/responder', data={'resposta': 'X'})
    assert banco['escritas'] == [] and emails == []


def test_admin_falha_no_email_avisa(client, banco, monkeypatch):
    logado(client, roles=['admin', 'user'], permissao=0)
    monkeypatch.setattr(P, 'send_email_async', lambda *a: False)
    client.post('/admin/lgpd/solicitacoes/5/responder', data={'resposta': 'Ok'})
    with client.session_transaction() as s:
        mensagens = [m for _, m in s.get('_flashes', [])]
    assert any('falhou' in m for m in mensagens)


# ----- consulta pelo protocolo -----

def test_consulta_abre_sem_login(client):
    resposta = client.get('/lgpd/consulta?protocolo=ABCDEF123456')
    assert resposta.status_code == 200 and 'ABCDEF123456' in resposta.get_data(as_text=True)


def test_consulta_aberta(client):
    html = client.post('/lgpd/consulta', data={'protocolo': 'abcdef123456', 'email': 'maria@aluno.ufca.edu.br'}).get_data(as_text=True)
    assert 'Em análise' in html and '09/10/2026' in html


def test_consulta_respondida_mostra_resposta(client, banco):
    banco['situacao'] = 'respondida'
    html = client.post('/lgpd/consulta', data={'protocolo': 'ABCDEF123456', 'email': 'maria@aluno.ufca.edu.br'}).get_data(as_text=True)
    assert 'Respondida' in html and 'Resposta enviada ao e-mail institucional.' in html


@pytest.mark.parametrize('protocolo,email', [('ABCDEF123456', 'outra@pessoa.com'), ('ZZZZZZZZZZZZ', 'maria@aluno.ufca.edu.br')])
def test_consulta_exige_protocolo_e_email_certos(client, banco, protocolo, email):
    html = client.post('/lgpd/consulta', data={'protocolo': protocolo, 'email': email}).get_data(as_text=True)
    assert 'Nenhuma solicitação encontrada' in html and 'Em análise' not in html


def test_consulta_protocolo_mal_formado_nem_vai_ao_banco(client, banco):
    client.post('/lgpd/consulta', data={'protocolo': "x' OR 1=1 --", 'email': 'a@b.c'})
    assert banco['consultas'] == []


def test_consulta_tem_limite():
    fonte = inspect.getsource(inspect.unwrap(P.lgpd_consulta))
    assert '@limiter.limit("20/day;10/hour;3/minute", methods=["POST"])' in fonte


def test_confirmacao_ao_titular_traz_link_da_consulta(client, emails):
    client.post('/lgpd/solicitacao', data=FORMULARIO)
    assert P.LGPD_LINK_CONSULTA in emails[1][2]


def test_usuario_comum_nao_ve_solicitacoes(client):
    logado(client)
    resposta = client.get('/admin/lgpd/solicitacoes')
    assert resposta.status_code == 302
