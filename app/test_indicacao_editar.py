"""Testes do CPF na lista de indicações e da edição de indicações pelo admin, com o banco mockado.

Rodar a partir de app/: pytest test_indicacao_editar.py -v
"""
import pytest
from flask.sessions import SecureCookieSessionInterface
from loguru import logger

import pesquisa as P

CPF_ATUAL = '529.982.247-25'
CPF_NOVO = '111.444.777-35'


def indicacao(**extra):
    """Indicação como carregar_indicacao a devolve (colunas pessoais já decifradas)."""
    dados = {'id': 7, 'idProjeto': 70, 'edital': 3, 'orientador': 'Prof. X', 'iv': 'iv-da-linha-7', 'expurgo': None,
             'nome': 'Maria Discente', 'cpf': CPF_ATUAL, 'rg': '123', 'orgao_emissor': 'SSP', 'uf': 'CE - Ceará',
             'nascimento': '2004-05-06', 'estado_civil': 0, 'sexo': 2, 'curso': 'Medicina', 'matricula': 'M1',
             'ano_de_ingresso': 2023, 'lattes': 'http://lattes.cnpq.br/1', 'escola': 'Escola Y', 'ano_conclusao': 2022,
             'nome_banco': 'Banco Z', 'agencia': '0001-2', 'conta': '12345-6', 'telefone': '(88)3333-3333',
             'celular': '(88)99999-9999', 'email': 'maria@aluno.ufca.edu.br', 'endereco': 'Rua A, 1',
             'modalidade': 1, 'tipo_de_vaga': 1, 'fomento': 0, 'inicio': '2026-03-01', 'fim': '2027-02-28',
             'arquivo_cpf_rg': 'RG.70.x.pdf', 'arquivo_extrato': 'N/A', 'arquivo_historico': None,
             'arquivo_termo': 'TERMO.70.x.pdf', 'arquivo_plano': 'N/D'}
    dados.update(extra)
    return dados


def formulario(atual, **mudancas):
    """O formulário como o navegador envia: todos os campos, com os valores atuais, mais as mudanças."""
    dados = {c: '' if atual.get(c) is None else str(atual[c]) for c, _, _ in P.CAMPOS_EDICAO_INDICACAO}
    dados.update({k: str(v) for k, v in mudancas.items()})
    return dados


@pytest.fixture
def ambiente(monkeypatch):
    estado = {'indicacao': indicacao(), 'alteracoes': [], 'rowcount': 1}
    monkeypatch.setattr(P.app, 'session_interface', SecureCookieSessionInterface())
    monkeypatch.setattr(P.app, 'secret_key', 'teste-indicacao')
    monkeypatch.setitem(P.app.config, 'WTF_CSRF_ENABLED', False)
    monkeypatch.setattr(P.limiter, 'enabled', False)
    monkeypatch.setattr(P, 'carregar_mensagens', lambda: [])
    monkeypatch.setattr(P, 'carregar_indicacao', lambda id_: estado['indicacao'] if id_ == 7 else None)

    def executar_alteracao(consulta, valores=()):
        estado['alteracoes'].append((consulta, valores))
        return estado['rowcount']
    monkeypatch.setattr(P, 'executar_alteracao', executar_alteracao)
    client = P.app.test_client()
    return estado, client


def como_admin(client):
    with client.session_transaction() as s:
        s.update({'username': '1', 'permissao': 0, 'roles': ['admin', 'user'], 'edital': 0})


def como_usuario(client):
    with client.session_transaction() as s:
        s.update({'username': '2', 'permissao': 1, 'roles': ['user'], 'edital': 0})


# ----- helpers -----

@pytest.mark.parametrize('cpf,valido', [(CPF_ATUAL, True), ('52998224725', True), (CPF_NOVO, True),
                                        ('529.982.247-24', False), ('111.111.111-11', False), ('123', False),
                                        ('', False), (None, False)])
def test_cpf_valido(cpf, valido):
    assert P.cpf_valido(cpf) is valido


@pytest.mark.parametrize('cpf,esperado', [('52998224725', '529.982.247-25'), (CPF_ATUAL, CPF_ATUAL),
                                          ('1234', '1234'), (None, '')])
def test_formatar_cpf(cpf, esperado):
    assert P.formatar_cpf(cpf) == esperado


def test_update_usa_o_iv_da_linha_e_recalcula_o_hash():
    consulta, valores = P.montar_update_indicacao([('telefone', '(88)1111-1111'), ('email', 'x@y.br')],
                                                  'iv-da-linha', CPF_NOVO, 7)
    assert consulta.count('%s') == len(valores)
    assert "telefone = TO_BASE64(AES_ENCRYPT(%s, %s, %s, 'aes-256-cbc'))" in consulta
    assert 'email = %s' in consulta
    assert consulta.endswith('WHERE id = %s AND expurgo IS NULL')
    assert valores[:3] == ('(88)1111-1111', P.AES_KEY, 'iv-da-linha')
    assert valores[-2:] == (P.hash_cpf(CPF_NOVO), 7)


# ----- lista -----

@pytest.mark.parametrize('tipo', [None, '1'])
def test_lista_com_e_sem_tipo_tem_as_mesmas_colunas_e_o_cpf(tipo):
    consulta, valores = P.consulta_lista_indicacoes('3', tipo)
    assert consulta.count('%s') == len(valores)
    colunas = consulta.split(' FROM ')[0]
    assert "AES_DECRYPT(FROM_BASE64(indicacoes.cpf)" in colunas
    assert colunas.rstrip().endswith("DATE_FORMAT(indicacoes.expurgo,'%d/%m/%Y')")
    assert ('indicacoes.tipo_de_vaga=%s' in consulta) is (tipo is not None)


def test_lista_mostra_cpf_formatado_e_link_de_edicao(ambiente, monkeypatch):
    _, client = ambiente
    linha = [7, 70, 'Maria', 'PIBIC', 'BOLSISTA', 'B', 'A', 'C', None, None, None, None, '01/03/2026', '28/02/2027',
             'Prof. X', '', 3, 'UFCA', 'Rua', 'cel', 'tel', '06/05/2004', 'rg', '52998224725', None]
    expurgada = [8, 71, 'João', 'PIBIC', 'BOLSISTA'] + [None] * 18 + [None, '25/09/2026']
    expurgada[14], expurgada[15] = 'Prof. Y', ''
    monkeypatch.setattr(P, 'executarSelect2', lambda c, tipo=0, valores=(): ([linha, expurgada], 2))
    monkeypatch.setattr(P, 'obterColunaUnica', lambda *a: 'Edital 3')
    como_admin(client)
    html = client.get('/admin/indicacoes?edital=3&tipo=1').get_data(as_text=True)
    assert '529.982.247-25' in html
    assert '/admin/indicacao/7/editar' in html
    assert '/admin/indicacao/8/editar' not in html and 'Anonimizada em 25/09/2026' in html


# ----- edição -----

def test_edicao_exige_admin(ambiente):
    estado, client = ambiente
    como_usuario(client)
    assert client.get('/admin/indicacao/7/editar').status_code in (302, 401, 403)
    assert client.post('/admin/indicacao/7/editar', data=formulario(estado['indicacao'])).status_code in (302, 401, 403)
    assert estado['alteracoes'] == []


def test_formulario_mostra_os_dados_decifrados(ambiente):
    _, client = ambiente
    como_admin(client)
    html = client.get('/admin/indicacao/7/editar').get_data(as_text=True)
    assert 'value="529.982.247-25"' in html and 'value="12345-6"' in html and 'value="2004-05-06"' in html
    assert 'RG.70.x.pdf' in html


def test_salvar_grava_so_o_que_mudou(ambiente):
    estado, client = ambiente
    como_admin(client)
    r = client.post('/admin/indicacao/7/editar',
                    data=formulario(estado['indicacao'], telefone='(88)1111-1111', conta='999-0', fim='2027-03-31'))
    assert r.status_code == 302 and 'edital=3' in r.location
    consulta, valores = estado['alteracoes'][0]
    colunas = consulta.split(' WHERE ')[0]
    assert 'telefone = TO_BASE64' in colunas and 'conta = TO_BASE64' in colunas and 'fim = %s' in colunas
    for inalterada in ('nome =', 'cpf =', 'rg =', 'email =', 'nascimento ='):
        assert inalterada not in colunas
    assert 'iv-da-linha-7' in valores and '2027-03-31 23:59:59' in valores
    assert valores[-2:] == (P.hash_cpf(CPF_ATUAL), 7)


def test_troca_de_cpf_recalcula_o_hash(ambiente):
    estado, client = ambiente
    como_admin(client)
    client.post('/admin/indicacao/7/editar', data=formulario(estado['indicacao'], cpf='11144477735'))
    consulta, valores = estado['alteracoes'][0]
    assert 'cpf = TO_BASE64' in consulta
    assert CPF_NOVO in valores and valores[-2] == P.hash_cpf(CPF_NOVO)


def test_cpf_antigo_sem_pontuacao_nao_conta_como_alterado(ambiente):
    estado, client = ambiente
    estado['indicacao'] = indicacao(cpf='52998224725')
    como_admin(client)
    client.post('/admin/indicacao/7/editar', data=formulario(estado['indicacao'], telefone='1'))
    assert 'cpf =' not in estado['alteracoes'][0][0]


def test_nada_mudou_nao_grava(ambiente):
    estado, client = ambiente
    como_admin(client)
    r = client.post('/admin/indicacao/7/editar', data=formulario(estado['indicacao']))
    assert r.status_code == 302 and estado['alteracoes'] == []


@pytest.mark.parametrize('mudanca', [{'cpf': '529.982.247-24'}, {'email': 'sem-arroba'}, {'fim': '2025-01-01'},
                                     {'nascimento': '2999-01-01'}, {'inicio': '31/12/2026'}, {'sexo': '9'},
                                     {'modalidade': '4'}, {'tipo_de_vaga': '2'}, {'fomento': 'x'},
                                     {'ano_de_ingresso': '99'}, {'nome': ''}])
def test_valores_invalidos_nao_gravam(ambiente, mudanca):
    estado, client = ambiente
    como_admin(client)
    r = client.post('/admin/indicacao/7/editar', data=formulario(estado['indicacao'], **mudanca))
    assert r.status_code == 400 and 'Nada foi gravado' in r.get_data(as_text=True)
    assert estado['alteracoes'] == []


def test_campos_nao_textuais_em_branco_mantem_o_valor(ambiente):
    estado, client = ambiente
    estado['indicacao'] = indicacao(email=None, estado_civil=None, ano_conclusao=None, nascimento='06/05/2004')
    como_admin(client)
    dados = formulario(estado['indicacao'], telefone='2')
    dados.update(email='', estado_civil='', ano_conclusao='', nascimento='')
    r = client.post('/admin/indicacao/7/editar', data=dados)
    assert r.status_code == 302
    colunas = estado['alteracoes'][0][0].split(' WHERE ')[0]
    assert colunas.startswith('UPDATE indicacoes SET telefone =') and 'nascimento' not in colunas


def test_voluntario_grava_na_nos_dados_bancarios(ambiente):
    estado, client = ambiente
    como_admin(client)
    dados = formulario(estado['indicacao'], tipo_de_vaga='0')
    for campo in ('nome_banco', 'agencia', 'conta'):
        dados.pop(campo)   # desativados no navegador: não são enviados
    client.post('/admin/indicacao/7/editar', data=dados)
    consulta, valores = estado['alteracoes'][0]
    assert 'tipo_de_vaga = %s' in consulta and valores.count('N/A') == 3


def test_indicacao_expurgada_nao_edita(ambiente):
    estado, client = ambiente
    estado['indicacao'] = indicacao(expurgo='25/09/2026', cpf=None)
    como_admin(client)
    html = client.get('/admin/indicacao/7/editar').get_data(as_text=True)
    assert 'anonimizada em 25/09/2026' in html and 'form-indicacao' not in html
    client.post('/admin/indicacao/7/editar', data=formulario(indicacao(), telefone='1'))
    assert estado['alteracoes'] == []


def test_sem_iv_nao_grava_dado_cifrado(ambiente):
    estado, client = ambiente
    estado['indicacao'] = indicacao(iv='')
    como_admin(client)
    client.post('/admin/indicacao/7/editar', data=formulario(estado['indicacao'], telefone='1'))
    assert estado['alteracoes'] == []


def test_rowcount_zero_mostra_erro(ambiente):
    estado, client = ambiente
    estado['rowcount'] = 0
    como_admin(client)
    r = client.post('/admin/indicacao/7/editar', data=formulario(estado['indicacao'], telefone='1'))
    assert r.status_code == 302 and r.location.endswith('/admin/indicacao/7/editar')


def test_indicacao_inexistente(ambiente):
    _, client = ambiente
    como_admin(client)
    assert client.get('/admin/indicacao/999/editar').status_code == 302


def test_log_tem_os_campos_e_nenhum_valor(ambiente):
    estado, client = ambiente
    mensagens = []
    sink = logger.add(lambda m: mensagens.append(str(m)), level="INFO")
    try:
        como_admin(client)
        client.post('/admin/indicacao/7/editar',
                    data=formulario(estado['indicacao'], telefone='(88)1111-1111', cpf='11144477735'))
    finally:
        logger.remove(sink)
    linha = next(m for m in mensagens if '[indicacao] id=7 alterada' in m)
    assert "'cpf'" in linha and "'telefone'" in linha
    for valor in ('1111-1111', '111.444.777-35', '11144477735', 'Maria'):
        assert valor not in linha
