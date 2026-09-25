"""
Retenção dos dados dos estudantes (LGPD, arts. 15 e 16; política em /lgpd, seção 7).

6 anos depois do fim da bolsa, os documentos da indicação são apagados do S3 e os dados pessoais
do estudante são anonimizados no banco. Ficam o nome, o projeto e o período, para as declarações e
o histórico. Nas tabelas legadas (alunos e cadastro_geral) o CPF também fica, para a busca por CPF
das declarações antigas continuar funcionando (decisão de 2026-09-25).

O prazo vem do banco, e não de uma regra de lifecycle do S3: os objetos de docs_indicacoes/ têm a
data do reenvio e da migração para o KMS (2025-2026), e não a da indicação.

As datas são interpretadas em Python, e não com CAST no SQL: nas tabelas legadas elas são texto
("Julho de 2018", "31/07/2019"). As tabelas têm poucos milhares de linhas, então cada execução lê
id e data de todas as linhas ainda não expurgadas.

Usado pelo app (tarefa mensal) e por scripts/expurgar_dados_estudantes.py (primeira execução, manual).
Não importa o pesquisa.py: quem chama passa a conexão e o cliente do S3.
"""
import calendar
import re
import unicodedata
from datetime import date, datetime

from loguru import logger
from werkzeug.utils import secure_filename

RETENCAO_ANOS = 6
PREFIXO_DOCS_S3 = 'pesquisa/docs_indicacoes/'
SEM_ARQUIVO = {'', 'n/a', 'na', '-'}   # valores de preenchimento nas colunas arquivo_* (arquivo_af é sempre "N/A")

# tabela: colunas com o fim da bolsa (a primeira com data válida vale), colunas anonimizadas, colunas com
# nomes de arquivos no S3 e colunas mantidas (as demais aparecem no --simular como "não classificadas")
TABELAS_RETENCAO = {
    'indicacoes': {
        'data': ('fim',),
        'anonimizar': ('cpf', 'cpf_hash', 'rg', 'orgao_emissor', 'uf', 'nascimento', 'estado_civil', 'sexo',
                       'nome_banco', 'agencia', 'conta', 'telefone', 'celular', 'email', 'endereco',
                       'matricula', 'lattes', 'escola', 'ano_conclusao'),
        'arquivos': ('arquivo_cpf_rg', 'arquivo_extrato', 'arquivo_historico', 'arquivo_termo', 'arquivo_plano',
                     'arquivo_af'),
        'manter': ('idProjeto', 'nome', 'modalidade', 'tipo_de_vaga', 'fomento', 'curso', 'ano_de_ingresso',
                   'inicio', 'fim', 'situacao', 'substituido', 'motivo', 'ch', 'iv', 'data'),
    },
    'alunos': {
        'data': ('fim',),
        'anonimizar': ('email',),
        'arquivos': (),
        'manter': ('nome', 'cpf', 'cpf_hash', 'iv', 'modalidade', 'orientador', 'projeto', 'inicio', 'fim', 'ch',
                   'curso', 'fomento', 'programa'),
    },
    'cadastro_geral': {
        'data': ('estudante_fim', 'termino'),
        'anonimizar': ('rg', 'telefone', 'celular', 'estudante_banco', 'estudante_no_agencia',
                       'estudante_no_conta_corrente', 'e-mail', 'matricula', 'id_lattes', 'estudante_obs'),
        'arquivos': (),
        # dados do orientador (orientador_*) não são do estudante e ficam fora deste expurgo
        'manter': ('cpf', 'cpf_hash', 'iv', 'estudante_nome_completo', 'estudante_modalidade',
                   'estudante_tipo_de_vaga', 'estudante_inicio', 'estudante_fim', 'estudante_situacao',
                   'estudante_agencia_de_fomento', 'token', 'siape', 'nome_do_coordenador', 'orientador_cpf',
                   'orientador_email', 'orientador_lotacao', 'orientador_id_lattes', 'orientador_sexo',
                   'orientador_situacao_funcional', 'orientador_titulacao', 'titulo_do_projeto', 'inicio', 'termino',
                   'ch_semanal', 'categoria', 'curso', 'edital', 'grande_area', 'sub_area', 'linha_de_pesquisa',
                   'resumo', 'situacao'),
    },
}

TIPOS_NUMERO = {'tinyint', 'smallint', 'mediumint', 'int', 'bigint', 'decimal', 'float', 'double'}
TIPOS_DATA = {'date', 'datetime', 'timestamp'}
MESES = {nome: i for i, nome in enumerate(('janeiro', 'fevereiro', 'marco', 'abril', 'maio', 'junho', 'julho',
                                           'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'), start=1)}
RE_MES_ANO = re.compile(r'^([a-z]+)\s+(?:de\s+)?(\d{4})$')
RE_DIA_MES_ANO = re.compile(r'^(\d{1,2})/(\d{1,2})/(\d{4})$')


def q(coluna):
    """Nome de coluna entre crases (cadastro_geral tem `e-mail`). Os nomes vêm só de TABELAS_RETENCAO."""
    return '`' + coluna.replace('`', '') + '`'


def interpretar_data(valor):
    """date, datetime, 'AAAA-MM-DD[ ...]', 'DD/MM/AAAA' ou 'Julho de 2018' (último dia do mês); senão None."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if valor is None:
        return None
    texto = unicodedata.normalize('NFKD', str(valor)).encode('ascii', 'ignore').decode().strip().lower()
    try:
        if re.match(r'^\d{4}-\d{2}-\d{2}', texto):
            return date.fromisoformat(texto[:10])
        m = RE_DIA_MES_ANO.match(texto)
        if m:
            return date(int(m[3]), int(m[2]), int(m[1]))
        m = RE_MES_ANO.match(texto)
        if m and m[1] in MESES:
            ano, mes = int(m[2]), MESES[m[1]]
            return date(ano, mes, calendar.monthrange(ano, mes)[1])
    except ValueError:  # 0000-00-00, 31/02/2019...
        return None
    return None


def data_limite(anos, hoje=None):
    """Fins de bolsa anteriores a esta data já passaram do prazo de guarda."""
    hoje = hoje or date.today()
    try:
        return hoje.replace(year=hoje.year - anos)
    except ValueError:  # 29 de fevereiro
        return hoje.replace(year=hoje.year - anos, day=28)


def valor_anonimo(tipo, anulavel):
    """NULL quando a coluna aceita; senão, um valor vazio do tipo (em modo estrito, NULL daria erro)."""
    if anulavel:
        return 'NULL'
    if tipo in TIPOS_NUMERO:
        return '0'
    if tipo in TIPOS_DATA:
        return "'1900-01-01'"
    return "''"


def colunas_da_tabela(cur, tabela):
    """{coluna: (tipo, aceita NULL)} da tabela no banco atual; vazio se a tabela não existe."""
    cur.execute("SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s", (tabela,))
    return {nome: (tipo.lower(), anulavel == 'YES') for nome, tipo, anulavel in cur.fetchall()}


def chaves_dos_arquivos(nomes):
    """Chaves no S3 dos arquivos da linha. Nomes que não passam no secure_filename são recusados (e contados)."""
    chaves, recusados = [], 0
    for nome in nomes:
        if nome is None or str(nome).strip().lower() in SEM_ARQUIVO:
            continue
        nome = str(nome)
        if secure_filename(nome) != nome:
            recusados += 1
            continue
        chaves.append(PREFIXO_DOCS_S3 + nome)
    return chaves, recusados


def apagar_do_s3(s3, bucket, chaves):
    """Apaga as chaves (no bucket versionado, vira marca de exclusão; a versão some em 1 dia pela lifecycle).
    Devolve True só se o S3 não informou nenhum erro."""
    for i in range(0, len(chaves), 1000):
        resposta = s3.delete_objects(Bucket=bucket, Delete={'Objects': [{'Key': c} for c in chaves[i:i + 1000]],
                                                            'Quiet': True})
        if resposta.get('Errors'):
            return False
    return True


def linhas_vencidas(cur, tabela, config, colunas, anos, hoje=None):
    """(vencidas, sem_data): vencidas = [(id, fim, (arquivos...))], em ordem de id, das linhas ainda não
    expurgadas cujo fim da bolsa passou do prazo; sem_data = quantas não têm nenhuma data válida."""
    datas = [c for c in config['data'] if c in colunas]
    arquivos = [c for c in config['arquivos'] if c in colunas]
    cur.execute(f"SELECT id{''.join(', ' + q(c) for c in datas + arquivos)} FROM {q(tabela)} "
                f"WHERE expurgo IS NULL ORDER BY id")
    limite = data_limite(anos, hoje)
    vencidas, sem_data = [], 0
    for linha in cur.fetchall():
        fim = next((d for d in map(interpretar_data, linha[1:1 + len(datas)]) if d), None)
        if fim is None:
            sem_data += 1
        elif fim < limite:
            vencidas.append((linha[0], fim, tuple(linha[1 + len(datas):])))
    return vencidas, sem_data


def expurgar_tabela(conn, tabela, config, colunas, vencidas, s3, bucket, limite):
    """Apaga os arquivos e anonimiza, linha a linha. Uma linha só é anonimizada depois que o S3 confirma
    a exclusão dos arquivos dela; se algo falhar, ela fica para a próxima execução."""
    cur = conn.cursor()
    anonimizar = [c for c in config['anonimizar'] if c in colunas]
    arquivos = [c for c in config['arquivos'] if c in colunas]
    atribuicoes = [f"{q(c)} = {valor_anonimo(*colunas[c])}" for c in anonimizar + arquivos]
    atualizacao = f"UPDATE {q(tabela)} SET {', '.join(atribuicoes + ['expurgo = NOW()'])} WHERE id = %s AND expurgo IS NULL"
    resumo = {'linhas': 0, 'arquivos': 0, 'arquivos_recusados': 0, 'arquivos_mantidos_dev': 0, 'falhas': 0}
    for id_, _, nomes in vencidas:
        if limite is not None and resumo['linhas'] >= limite:
            break
        chaves, recusados = chaves_dos_arquivos(nomes)
        resumo['arquivos_recusados'] += recusados
        try:
            if chaves and s3 is not None:
                if not apagar_do_s3(s3, bucket, chaves):
                    resumo['falhas'] += 1
                    logger.error("[retencao] {} id={}: o S3 não apagou todos os arquivos; linha mantida", tabela, id_)
                    continue
                resumo['arquivos'] += len(chaves)
            elif chaves:
                resumo['arquivos_mantidos_dev'] += len(chaves)
            cur.execute(atualizacao, (id_,))
            conn.commit()
            resumo['linhas'] += 1
        except Exception as e:  # S3 ou banco: registra e segue para a próxima linha
            conn.rollback()
            resumo['falhas'] += 1
            logger.error("[retencao] {} id={}: erro no expurgo: {}", tabela, id_, type(e).__name__)
    cur.close()
    return resumo


def expurgar_dados_estudantes(conectar, s3=None, bucket=None, simular=False, limite=None, tabelas=None,
                              anos=RETENCAO_ANOS, hoje=None):
    """
    Expurga as tabelas de TABELAS_RETENCAO (ou só `tabelas`). `conectar()` devolve uma conexão DB-API nova.
    `s3=None` (dev) não apaga nada no S3. `limite`: no máximo N linhas por tabela.
    Devolve {tabela: resumo}. O log leva só contagens e ids, nunca nome, CPF ou nome de arquivo.
    """
    resultado = {}
    for tabela in tabelas or TABELAS_RETENCAO:
        config = TABELAS_RETENCAO[tabela]
        conn = conectar()
        try:
            cur = conn.cursor()
            colunas = colunas_da_tabela(cur, tabela)
            if 'expurgo' not in colunas or not any(c in colunas for c in config['data']):
                resultado[tabela] = {'erro': 'tabela sem a coluna expurgo ou sem a coluna de data (rodar o retencao.sql.sample)'}
                logger.error("[retencao] {}: {}", tabela, resultado[tabela]['erro'])
                continue
            conhecidas = set(config['anonimizar']) | set(config['arquivos']) | set(config['manter']) | {'id', 'expurgo'}
            extras = {
                'colunas_ausentes': sorted((set(config['anonimizar']) | set(config['arquivos'])) - set(colunas)),
                'colunas_nao_classificadas': sorted(set(colunas) - conhecidas),
            }
            vencidas, sem_data = linhas_vencidas(cur, tabela, config, colunas, anos, hoje)
            cur.close()
            if simular:
                fins = [fim for _, fim, _ in vencidas]
                resultado[tabela] = {'linhas': len(vencidas), 'sem_data': sem_data,
                                     'arquivos': sum(len(chaves_dos_arquivos(n)[0]) for _, _, n in vencidas),
                                     'fim_mais_antigo': min(fins, default=None),
                                     'fim_mais_recente': max(fins, default=None), **extras}
            else:
                resultado[tabela] = {**expurgar_tabela(conn, tabela, config, colunas, vencidas, s3, bucket, limite),
                                     'sem_data': sem_data, **extras}
                r = resultado[tabela]
                logger.info("[retencao] {}: {} linhas anonimizadas, {} arquivos apagados do S3, {} falhas, "
                            "{} nomes de arquivo recusados, {} linhas sem data válida", tabela, r['linhas'],
                            r['arquivos'], r['falhas'], r['arquivos_recusados'], sem_data)
        finally:
            conn.close()
    return resultado
