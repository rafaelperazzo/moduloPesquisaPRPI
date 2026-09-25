"""Testes da retenção de 6 anos após o fim da bolsa (modules/retencao.py), com banco e S3 falsos.

Rodar a partir de app/: pytest test_retencao.py -v
"""
import re
from datetime import date

import pytest
from loguru import logger

from modules import retencao as R

HOJE = date.today()
DOCS = ('arquivo_cpf_rg', 'arquivo_extrato', 'arquivo_historico', 'arquivo_termo', 'arquivo_plano')
VENCIDA = date(HOJE.year - 7, 1, 31)
NO_PRAZO = date(HOJE.year - 5, 1, 31)


def colunas(nomes, tipo='varchar', anulavel=True):
    return {n: (tipo, anulavel) for n in nomes}


def banco_padrao():
    ind = colunas(['id', 'expurgo', 'fim', 'inicio'], 'date')
    ind.update(colunas(R.TABELAS_RETENCAO['indicacoes']['anonimizar'] + R.TABELAS_RETENCAO['indicacoes']['arquivos']))
    ind.update(colunas(['nome', 'idProjeto', 'modalidade']))
    ind['conta'] = ('text', False)          # NOT NULL: vira ''
    ind['ano_conclusao'] = ('int', False)   # NOT NULL numérica: vira 0

    def indicacao(id_, fim, **extra):
        linha = {c: f'{c}-{id_}' for c in ind}
        linha.update(id=id_, fim=fim, expurgo=None, nome=f'Estudante {id_}', idProjeto=10 + id_)
        for c in DOCS:
            linha[c] = f'{c.upper()}.{id_}.pdf'
        linha['arquivo_af'] = 'N/A'
        linha.update(extra)
        return linha

    cg = colunas(['id', 'expurgo', 'cpf', 'cpf_hash', 'estudante_nome_completo', 'orientador_cpf', 'orientador_email',
                  'estudante_fim', 'termino'] + list(R.TABELAS_RETENCAO['cadastro_geral']['anonimizar']), 'text')
    return {
        'indicacoes': {'colunas': ind, 'linhas': [
            indicacao(1, VENCIDA),
            indicacao(2, NO_PRAZO),
            indicacao(3, None),
            indicacao(4, VENCIDA, expurgo=date(2026, 1, 1)),
            indicacao(5, VENCIDA, arquivo_termo='../../etc/passwd', arquivo_plano=''),
        ]},
        'alunos': {'colunas': colunas(['id', 'expurgo', 'nome', 'cpf', 'cpf_hash', 'email', 'fim']), 'linhas': [
            {'id': 1, 'expurgo': None, 'nome': 'Aluno', 'cpf': 'cifrado', 'cpf_hash': 'h1', 'email': 'a@x.br', 'fim': 'Julho de 2018'},
            {'id': 2, 'expurgo': None, 'nome': 'Aluno 2', 'cpf': 'c2', 'cpf_hash': 'h2', 'email': 'b@x.br', 'fim': '31/07/2019'},
            {'id': 3, 'expurgo': None, 'nome': 'Aluno 3', 'cpf': 'c3', 'cpf_hash': 'h3', 'email': 'c@x.br', 'fim': f'Março de {HOJE.year}'},
        ]},
        'cadastro_geral': {'colunas': cg, 'linhas': [
            {**{c: f'{c}-1' for c in cg}, 'id': 1, 'expurgo': None, 'estudante_fim': VENCIDA.isoformat()},
            {**{c: f'{c}-2' for c in cg}, 'id': 2, 'expurgo': None, 'estudante_fim': 'data inválida', 'termino': None},
            {**{c: f'{c}-3' for c in cg}, 'id': 3, 'expurgo': None, 'estudante_fim': None, 'termino': '2018-07-01 00:00:00'},
        ]},
    }


class CursorFalso:
    def __init__(self, db, log):
        self.db, self.log, self.resultado = db, log, []

    def execute(self, sql, params=()):
        self.log.append((sql, params))
        tabela = (re.search(r'(?:FROM|UPDATE) `(\w+)`', sql) or [None, None])[1]
        if 'information_schema' in sql:
            t = self.db.get(params[0])
            self.resultado = [(n, tp, 'YES' if an else 'NO') for n, (tp, an) in (t['colunas'].items() if t else [])]
        elif sql.startswith('SELECT id'):
            nomes = re.findall(r'`([\w-]+)`', sql.split(' FROM ')[0])
            linhas = sorted((l for l in self.db[tabela]['linhas'] if l['expurgo'] is None), key=lambda l: l['id'])
            self.resultado = [(l['id'], *[l.get(n) for n in nomes]) for l in linhas]
        elif sql.startswith('UPDATE'):
            if self.db.get('falhar_update'):
                raise RuntimeError('banco fora')
            atribuicoes = re.findall(r"`([\w-]+)` = (NULL|''|0|'1900-01-01')", sql)
            for linha in self.db[tabela]['linhas']:
                if linha['id'] == params[0] and linha['expurgo'] is None:
                    for coluna, valor in atribuicoes:
                        linha[coluna] = {'NULL': None, "''": '', '0': 0}.get(valor, valor)
                    linha['expurgo'] = HOJE

    def fetchall(self):
        return self.resultado

    def fetchone(self):
        return self.resultado[0]

    def close(self):
        pass


class ConexaoFalsa:
    def __init__(self, db, log):
        self.db, self.log = db, log
        self.commits = self.rollbacks = 0

    def cursor(self):
        return CursorFalso(self.db, self.log)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


class S3Falso:
    def __init__(self, erro=False):
        self.apagadas, self.erro = [], erro

    def delete_objects(self, Bucket, Delete):
        if self.erro:
            return {'Errors': [{'Key': o['Key'], 'Code': 'AccessDenied'} for o in Delete['Objects']]}
        self.apagadas.extend(o['Key'] for o in Delete['Objects'])
        return {}


@pytest.fixture
def ambiente():
    db, sqls = banco_padrao(), []
    return db, sqls, (lambda: ConexaoFalsa(db, sqls))


def linha(db, tabela, id_):
    return next(l for l in db[tabela]['linhas'] if l['id'] == id_)


def test_indicacao_vencida_perde_arquivos_e_dados_pessoais(ambiente):
    db, _, conectar = ambiente
    s3 = S3Falso()
    resultado = R.expurgar_dados_estudantes(conectar, s3=s3, bucket='b', tabelas=['indicacoes'])

    esperadas = [R.PREFIXO_DOCS_S3 + f'{c.upper()}.1.pdf' for c in DOCS]
    assert sorted(s3.apagadas) == sorted(esperadas)
    l1 = linha(db, 'indicacoes', 1)
    for c in R.TABELAS_RETENCAO['indicacoes']['anonimizar'] + R.TABELAS_RETENCAO['indicacoes']['arquivos']:
        assert l1[c] in (None, '', 0), c
    assert l1['cpf'] is None and l1['cpf_hash'] is None
    assert l1['conta'] == '' and l1['ano_conclusao'] == 0   # NOT NULL: valor vazio do tipo
    assert l1['arquivo_af'] is None                          # "N/A" não é arquivo, mas a coluna é limpa
    assert l1['nome'] == 'Estudante 1' and l1['idProjeto'] == 11 and l1['fim'] == VENCIDA
    assert l1['expurgo'] == HOJE
    assert resultado['indicacoes']['linhas'] == 1 and resultado['indicacoes']['arquivos'] == 5


def test_no_prazo_sem_data_ou_ja_expurgada_nao_muda(ambiente):
    db, _, conectar = ambiente
    antes = {i: dict(linha(db, 'indicacoes', i)) for i in (2, 3, 4)}
    R.expurgar_dados_estudantes(conectar, s3=S3Falso(), bucket='b', tabelas=['indicacoes'])
    for i, original in antes.items():
        assert linha(db, 'indicacoes', i) == original


def test_nome_de_arquivo_suspeito_e_recusado(ambiente):
    db, _, conectar = ambiente
    s3 = S3Falso()
    resultado = R.expurgar_dados_estudantes(conectar, s3=s3, bucket='b', tabelas=['indicacoes'])
    assert not any(k.endswith('.5.pdf') or 'passwd' in k for k in s3.apagadas)   # nada da linha 5 é apagado
    assert resultado['indicacoes']['arquivos_recusados'] == 1 and resultado['indicacoes']['falhas'] == 1
    l5 = linha(db, 'indicacoes', 5)
    assert l5['expurgo'] is None and l5['cpf'] == 'cpf-5' and l5['arquivo_cpf_rg'] == 'ARQUIVO_CPF_RG.5.pdf'


def test_falha_no_s3_mantem_a_linha(ambiente):
    db, _, conectar = ambiente
    resultado = R.expurgar_dados_estudantes(conectar, s3=S3Falso(erro=True), bucket='b', tabelas=['indicacoes'])
    assert linha(db, 'indicacoes', 1)['expurgo'] is None
    assert linha(db, 'indicacoes', 1)['cpf'] == 'cpf-1'
    assert resultado['indicacoes']['falhas'] == 2 and resultado['indicacoes']['linhas'] == 0


def test_falha_no_banco_registra_e_segue(ambiente):
    db, _, conectar = ambiente
    db['falhar_update'] = True
    resultado = R.expurgar_dados_estudantes(conectar, s3=S3Falso(), bucket='b', tabelas=['indicacoes'])
    assert resultado['indicacoes']['falhas'] == 2 and resultado['indicacoes']['linhas'] == 0


def test_simular_nao_altera_nada(ambiente):
    db, sqls, conectar = ambiente
    s3 = S3Falso()
    resultado = R.expurgar_dados_estudantes(conectar, s3=s3, bucket='b', simular=True)
    assert s3.apagadas == []
    assert not any(sql.startswith('UPDATE') for sql, _ in sqls)
    assert resultado['indicacoes']['linhas'] == 2 and resultado['indicacoes']['arquivos'] == 8
    assert resultado['indicacoes']['sem_data'] == 1
    assert resultado['indicacoes']['linhas_com_nome_recusado'] == 1 and resultado['indicacoes']['ids_com_nome_recusado'] == [5]
    assert resultado['indicacoes']['preenchimentos_ignorados'] == 2   # arquivo_af "N/A" nas linhas 1 e 5
    assert resultado['alunos']['linhas'] == 2 and resultado['alunos']['fim_mais_recente'] == date(2019, 7, 31)
    assert resultado['cadastro_geral']['linhas'] == 2 and resultado['cadastro_geral']['sem_data'] == 1


def test_limite_por_tabela(ambiente):
    db, _, conectar = ambiente
    resultado = R.expurgar_dados_estudantes(conectar, s3=S3Falso(), bucket='b', tabelas=['indicacoes'], limite=1)
    assert resultado['indicacoes']['linhas'] == 1
    assert linha(db, 'indicacoes', 1)['expurgo'] == HOJE and linha(db, 'indicacoes', 5)['expurgo'] is None


def test_dev_sem_s3_so_anonimiza(ambiente):
    db, _, conectar = ambiente
    resultado = R.expurgar_dados_estudantes(conectar, s3=None, tabelas=['indicacoes'])
    assert resultado['indicacoes']['linhas'] == 1 and resultado['indicacoes']['arquivos'] == 0
    assert resultado['indicacoes']['arquivos_mantidos_dev'] == 5


def test_legadas_mantem_cpf_e_dados_do_orientador(ambiente):
    db, _, conectar = ambiente
    R.expurgar_dados_estudantes(conectar, s3=S3Falso(), bucket='b', tabelas=['alunos', 'cadastro_geral'])
    aluno = linha(db, 'alunos', 1)
    assert aluno['email'] is None and aluno['cpf'] == 'cifrado' and aluno['cpf_hash'] == 'h1' and aluno['expurgo']
    assert linha(db, 'alunos', 2)['email'] is None                          # 31/07/2019
    assert linha(db, 'alunos', 3)['email'] == 'c@x.br'                      # este ano: no prazo
    cg = linha(db, 'cadastro_geral', 1)
    for c in R.TABELAS_RETENCAO['cadastro_geral']['anonimizar']:
        assert cg[c] is None, c
    assert cg['cpf'] == 'cpf-1' and cg['cpf_hash'] == 'cpf_hash-1'
    assert cg['orientador_cpf'] == 'orientador_cpf-1' and cg['orientador_email'] == 'orientador_email-1'
    assert cg['estudante_nome_completo'] == 'estudante_nome_completo-1'
    assert linha(db, 'cadastro_geral', 2)['expurgo'] is None   # sem data válida: fica para revisão
    assert linha(db, 'cadastro_geral', 3)['rg'] is None        # estudante_fim vazio: vale o termino


def test_e_mail_com_hifen_vai_entre_crases(ambiente):
    _, sqls, conectar = ambiente
    R.expurgar_dados_estudantes(conectar, s3=S3Falso(), bucket='b', tabelas=['cadastro_geral'])
    update = next(sql for sql, _ in sqls if sql.startswith('UPDATE'))
    assert '`e-mail` = NULL' in update


def test_sem_coluna_expurgo_nao_faz_nada(ambiente):
    db, sqls, conectar = ambiente
    del db['alunos']['colunas']['expurgo']
    resultado = R.expurgar_dados_estudantes(conectar, s3=S3Falso(), bucket='b', tabelas=['alunos'])
    assert 'erro' in resultado['alunos']
    assert not any(sql.startswith('UPDATE') for sql, _ in sqls)


def test_colunas_nao_classificadas_aparecem(ambiente):
    db, _, conectar = ambiente
    db['alunos']['colunas']['telefone_novo'] = ('varchar', True)
    resultado = R.expurgar_dados_estudantes(conectar, simular=True, tabelas=['alunos'])
    assert resultado['alunos']['colunas_nao_classificadas'] == ['telefone_novo']


def test_log_sem_dados_pessoais(ambiente):
    _, _, conectar = ambiente
    mensagens = []
    sink = logger.add(lambda m: mensagens.append(str(m)), level="INFO")
    try:
        R.expurgar_dados_estudantes(conectar, s3=S3Falso(erro=True), bucket='b')
        R.expurgar_dados_estudantes(conectar, s3=S3Falso(), bucket='b')
    finally:
        logger.remove(sink)
    texto = '\n'.join(mensagens)
    assert '[retencao]' in texto
    for proibido in ('Estudante', 'cpf-1', '.pdf', 'a@x.br', 'passwd'):
        assert proibido not in texto


@pytest.mark.parametrize('valor, esperado', [
    ('Julho de 2018', date(2018, 7, 31)),
    ('Fevereiro de 2016', date(2016, 2, 29)),
    ('Março de 2015', date(2015, 3, 31)),
    ('marco 2015', date(2015, 3, 31)),
    ('31/07/2019', date(2019, 7, 31)),
    ('2018-07-01 00:00:00', date(2018, 7, 1)),
    (date(2020, 9, 15), date(2020, 9, 15)),
    ('0000-00-00', None), ('31/02/2019', None), ('', None), (None, None), ('Julhoo de 2018', None),
])
def test_interpretar_data(valor, esperado):
    assert R.interpretar_data(valor) == esperado


def test_data_limite_em_29_de_fevereiro():
    assert R.data_limite(6, date(2028, 2, 29)) == date(2022, 2, 28)


def test_politica_declara_6_anos():
    with open('templates/lgpd.html', encoding='utf-8') as f:
        html = f.read()
    assert '6 anos após o término da bolsa' in html
    assert "('Arts. 15 e 16', 'Término do tratamento e eliminação', 'implementado'" in html
