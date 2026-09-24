"""Testes da criptografia do CPF e dos dados bancários (migracao.cripto_cpf.md), com o banco mockado.

A execução real (MariaDB 11 + script de migração + consultas do app) foi conferida num container
descartável; aqui ficam as regras que não dependem do banco.
Rodar a partir de app/: pytest test_cripto_cpf.py -v
"""
import hashlib
import hmac
import os
import sys

import pytest
from flask.sessions import SecureCookieSessionInterface

import pesquisa as P

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))
import cifrar_cpf_banco as M  # noqa: E402


# ----- helpers do app -----

@pytest.mark.parametrize('entrada,esperado', [('123.456.789-01', '12345678901'), ('12345678901', '12345678901'),
                                              (' 123 456 789 01 ', '12345678901'), (None, ''), ('', '')])
def test_normalizar_cpf(entrada, esperado):
    assert P.normalizar_cpf(entrada) == esperado


def test_hash_cpf_e_hmac_dos_digitos_e_igual_com_ou_sem_pontuacao():
    esperado = hmac.new(P.CPF_HMAC_KEY.encode(), b'12345678901', hashlib.sha256).hexdigest()
    assert P.hash_cpf('123.456.789-01') == P.hash_cpf('12345678901') == esperado
    assert len(esperado) == 64
    assert P.hash_cpf('12345678901') != hashlib.sha256(b'12345678901').hexdigest()  # não é SHA-256 simples


def test_hash_do_app_e_do_script_sao_iguais():
    assert M.hash_cpf(P.CPF_HMAC_KEY, '123.456.789-01') == P.hash_cpf('12345678901')
    assert M.hash_cpf(P.CPF_HMAC_KEY, '') == P.hash_cpf(None)


@pytest.mark.parametrize('entrada,esperado', [('123.456.789-01', '***.456.789-**'), ('12345678901', '***.456.789-**'),
                                              ('123', ''), (None, '')])
def test_mascarar_cpf(entrada, esperado):
    assert P.mascarar_cpf(entrada) == esperado


def test_sql_decifra_usa_modo_explicito_e_transicao():
    sql = P.sql_decifra('cpf', 'i')
    assert sql.count('%s') == 1
    assert "'aes-256-cbc'" in sql and 'i.iv' in sql
    assert sql.startswith("IF(i.cpf_hash IS NULL OR i.cpf IS NULL OR i.cpf = '', i.cpf,")


def test_sql_busca_cpf_tem_dois_parametros_na_ordem_certa():
    assert P.sql_busca_cpf('indicacoes').count('%s') == 2
    assert P.valores_busca_cpf('123.456.789-01') == (P.hash_cpf('12345678901'), '123.456.789-01')


# ----- INSERT da indicação -----

def campos_exemplo():
    return [('idProjeto', 10), ('nome', 'Nova'), ('nascimento', '2005-05-05'), ('rg', '500'), ('cpf', '555.666.777-88'),
            ('nome_banco', 'Caixa'), ('agencia', '0001'), ('conta', '1-2'), ('telefone', 't'), ('celular', 'c'),
            ('email', 'e@x'), ('endereco', 'Rua'), ('iv', 'ivNOVONOVONOVONOVONOVO')]


def test_insert_cifra_as_nove_colunas_e_grava_o_hash():
    consulta, valores = P.montar_insert_indicacao(campos_exemplo(), 'ivNOVONOVONOVONOVONOVO', '555.666.777-88')
    assert consulta.count(P.SQL_CIFRA) == 9 == len(P.COLUNAS_CIFRADAS_INDICACAO)
    assert consulta.count('%s') == len(valores)
    assert consulta.split('(')[1].split(')')[0].endswith(',cpf_hash')
    assert valores[-1] == P.hash_cpf('55566677788')
    assert "'aes-256-cbc'" in consulta
    # valores das colunas cifradas vêm acompanhados da chave e do iv
    i = valores.index('555.666.777-88')
    assert valores[i + 1] == P.AES_KEY and valores[i + 2] == 'ivNOVONOVONOVONOVONOVO'
    # colunas não cifradas vão em claro
    assert valores[valores.index('Nova') + 1] != P.AES_KEY


def test_rota_nao_tem_mais_o_update_que_cifrava_depois():
    import inspect
    fonte = inspect.getsource(P)
    assert 'consulta_criptografar' not in fonte
    assert 'montar_insert_indicacao(campos, iv, cpf)' in fonte


# ----- rotas (banco mockado) -----

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(P.app, 'session_interface', SecureCookieSessionInterface())
    monkeypatch.setattr(P.app, 'secret_key', 'teste-cripto')
    monkeypatch.setitem(P.app.config, 'WTF_CSRF_ENABLED', False)
    monkeypatch.setattr(P.limiter, 'enabled', False)
    monkeypatch.setattr(P, 'carregar_mensagens', lambda: [])
    return P.app.test_client()


def test_busca_por_cpf_invalido_nao_consulta_o_banco(monkeypatch):
    monkeypatch.setattr(P.MySQLdb, 'connect', lambda *a, **k: pytest.fail('não deveria consultar o banco'))
    assert P.gerarProjetosPorAluno('123') == ([], [])
    assert P.gerarProjetosPorAluno('') == ([], [])


def test_api_indicacao_busca_pelo_hash(client, monkeypatch):
    chamadas = []
    monkeypatch.setattr(P, 'executarSelect2', lambda c, tipo=0, valores=(): chamadas.append((c, valores)) or ([], 0))
    assert client.get('/indicacao/12345678901').status_code == 200
    consulta, valores = chamadas[0]
    assert 'cpf_hash = %s' in consulta
    assert valores == (P.hash_cpf('12345678901'), '123.456.789-01')


def test_api_indicacao_cpf_invalido_nao_consulta(client, monkeypatch):
    monkeypatch.setattr(P, 'executarSelect2', lambda *a, **k: pytest.fail('não deveria consultar o banco'))
    assert client.get('/indicacao/123').get_json() == []


def test_verificacao_publica_mostra_cpf_mascarado(client, monkeypatch):
    def select(consulta, tipo=0, valores=()):
        if 'indicacoes.id=%s' in consulta:  # consulta do discente (a do projeto também cita indicacoes)
            return ([('Maria', '123.456.789-01', 'PROJETO X', '01/01/2026', '31/12/2026', 'PROF A', 7)], 1)
        return ([], 0)
    monkeypatch.setattr(P, 'executarSelect2', select)
    monkeypatch.setattr(P, 'verificar_codigo_auth', lambda *a: True)
    html = client.post('/verificarDeclaracao', data={'id_projeto': '7', 'codigo': 'a' * 64}).get_data(as_text=True)
    assert '***.456.789-**' in html and '123.456.789-01' not in html


def test_listagens_passam_a_chave_para_cada_coluna_decifrada(client, monkeypatch):
    chamadas = []
    monkeypatch.setattr(P, 'executarSelect2', lambda c, tipo=0, valores=(): chamadas.append((c, valores)) or ([], 0))
    monkeypatch.setattr(P, 'obterColunaUnica', lambda *a: 'Edital')
    with client.session_transaction() as s:
        s.update({'username': '1', 'permissao': 0, 'roles': ['admin', 'user'], 'edital': 0})
    client.get('/admin/indicacoes?edital=1&tipo=1')
    client.get('/admin/indicacoes?edital=1')
    client.get('/admin/substituicoes?id=1')
    for consulta, valores in chamadas:
        assert consulta.count('%s') == len(valores), consulta[:80]
        if 'nome_banco' in consulta:
            assert 'nome_banco,agencia,conta' not in consulta.replace(' ', '')  # nada em claro


# ----- script de migração -----

@pytest.mark.parametrize('tabela', list(M.TABELAS))
def test_update_do_script_tem_os_parametros_certos(tabela):
    colunas, iv_novo = M.TABELAS[tabela]
    consulta = M.montar_update(tabela, colunas, iv_novo)
    params = M.parametros_update(colunas, iv_novo, 'ivXXXXXXXXXXXXXXXXXXXX', 'k', 'h', 1)
    assert consulta.count('%s') == len(params)
    assert consulta.endswith('WHERE id = %s AND cpf_hash IS NULL')  # idempotente
    assert consulta.count(M.MODO) == len(colunas)
    assert params[-2:] == ['h', 1]


def test_script_cifra_os_dados_bancarios_de_indicacoes():
    assert M.TABELAS['indicacoes'][0] == ('cpf', 'nome_banco', 'agencia', 'conta')
    assert M.TABELAS['alunos'] == (('cpf',), True)          # alunos ganha iv novo
    assert M.TABELAS['cadastro_geral'] == (('cpf',), False)  # o resto já estava cifrado


@pytest.mark.parametrize('iv,ok', [('ivAAAAAAAAAAAAAAAAAAAA', True), ('', False), (None, False), ('curto', False)])
def test_iv_valido(iv, ok):
    assert M.iv_valido(iv) is ok


# valores medidos num MariaDB 11 (TO_BASE64 quebra a linha a cada 76 caracteres)
@pytest.mark.parametrize('tamanho,cifrado', [(11, 24), (14, 24), (15, 24), (16, 44), (100, 153), (367, 498), (368, 518)])
def test_tamanho_cifrado(tamanho, cifrado):
    assert M.tamanho_cifrado(tamanho) == cifrado


class CursorFalso:
    """Responde CHARACTER_MAXIMUM_LENGTH e MAX(LENGTH(...)) a partir de dicionários."""
    def __init__(self, limites, maiores):
        self.limites, self.maiores, self.ultimo = limites, maiores, None
    def execute(self, sql, params=()):
        if 'CHARACTER_MAXIMUM_LENGTH' in sql:
            self.ultimo = (self.limites.get(params, 500),)
        else:
            tabela, coluna = sql.split('FROM `')[1].split('`')[0], sql.split('LENGTH(`')[1].split('`')[0]
            self.ultimo = (self.maiores.get((tabela, coluna), 0),)
    def fetchone(self):
        return self.ultimo


def test_conferir_tamanhos_barra_coluna_pequena():
    # alunos.cpf ainda com varchar(16) (SQL de estrutura não aplicado) e um CPF de 16 caracteres
    cur = CursorFalso({('alunos', 'cpf'): 16}, {('alunos', 'cpf'): 16, ('indicacoes', 'nome_banco'): 100})
    problemas = M.conferir_tamanhos(cur)
    assert len(problemas) == 1 and problemas[0].startswith('alunos.cpf')


def test_conferir_tamanhos_ok_depois_do_sql_de_estrutura():
    cur = CursorFalso({('alunos', 'cpf'): 64}, {('alunos', 'cpf'): 16, ('indicacoes', 'nome_banco'): 100,
                                               ('indicacoes', 'cpf'): 14})
    assert M.conferir_tamanhos(cur) == []
