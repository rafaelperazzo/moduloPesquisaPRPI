"""
Retenção dos dados dos estudantes (LGPD, arts. 15 e 16; política em /lgpd, seção 7).

6 anos depois do fim da bolsa, os documentos da indicação são apagados do S3 e os dados pessoais
do estudante são anonimizados no banco. Ficam o nome, o projeto e o período, para as declarações e
o histórico. Nas tabelas legadas (alunos e cadastro_geral) o CPF também fica, para a busca por CPF
das declarações antigas continuar funcionando (decisão de 2026-09-25).

O prazo vem do banco, e não de uma regra de lifecycle do S3: os objetos de docs_indicacoes/ têm a
data do reenvio e da migração para o KMS (2025-2026), e não a da indicação.

Usado pelo app (tarefa mensal) e por scripts/expurgar_dados_estudantes.py (primeira execução, manual).
Não importa o pesquisa.py: quem chama passa a conexão e o cliente do S3.
"""
from loguru import logger
from werkzeug.utils import secure_filename

RETENCAO_ANOS = 6
PREFIXO_DOCS_S3 = 'pesquisa/docs_indicacoes/'
LOTE = 200

# tabela: coluna com o fim da bolsa, colunas anonimizadas, colunas com nomes de arquivos no S3 e
# colunas mantidas (as demais aparecem no --simular como "não classificadas", para revisão)
TABELAS_RETENCAO = {
    'indicacoes': {
        'data': 'fim',
        'anonimizar': ('cpf', 'cpf_hash', 'rg', 'orgao_emissor', 'uf', 'nascimento', 'estado_civil', 'sexo',
                       'nome_banco', 'agencia', 'conta', 'telefone', 'celular', 'email', 'endereco',
                       'matricula', 'lattes', 'escola', 'ano_conclusao'),
        'arquivos': ('arquivo_cpf_rg', 'arquivo_extrato', 'arquivo_historico', 'arquivo_termo', 'arquivo_plano'),
        'manter': ('idProjeto', 'nome', 'modalidade', 'tipo_de_vaga', 'fomento', 'curso', 'ano_de_ingresso',
                   'inicio', 'fim', 'situacao', 'substituido', 'motivo', 'ch', 'iv'),
    },
    'alunos': {
        'data': 'fim',
        'anonimizar': ('email',),
        'arquivos': (),
        'manter': ('nome', 'cpf', 'cpf_hash', 'iv', 'modalidade', 'orientador', 'projeto', 'inicio', 'fim', 'ch'),
    },
    'cadastro_geral': {
        'data': 'estudante_fim',
        'anonimizar': ('rg', 'telefone', 'celular', 'estudante_banco', 'estudante_no_agencia',
                       'estudante_no_conta_corrente', 'e-mail'),
        'arquivos': (),
        'manter': ('cpf', 'cpf_hash', 'iv', 'estudante_nome_completo', 'estudante_modalidade',
                   'estudante_tipo_de_vaga', 'estudante_inicio', 'estudante_fim', 'token', 'siape',
                   'nome_do_coordenador', 'orientador_cpf', 'orientador_email', 'orientador_lotacao',
                   'titulo_do_projeto', 'inicio', 'termino', 'ch_semanal'),
    },
}

TIPOS_TEXTO = {'char', 'varchar', 'tinytext', 'text', 'mediumtext', 'longtext', 'enum', 'set'}
TIPOS_NUMERO = {'tinyint', 'smallint', 'mediumint', 'int', 'bigint', 'decimal', 'float', 'double'}
TIPOS_DATA = {'date', 'datetime', 'timestamp'}


def q(coluna):
    """Nome de coluna entre crases (cadastro_geral tem `e-mail`). Os nomes vêm só de TABELAS_RETENCAO."""
    return '`' + coluna.replace('`', '') + '`'


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
        if not nome:
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


def condicao_vencida(config, anos):
    """Linhas ainda não expurgadas com o fim da bolsa há mais de `anos` anos. CAST: em cadastro_geral a data é texto."""
    return (f"expurgo IS NULL AND CAST({q(config['data'])} AS DATE) IS NOT NULL "
            f"AND CAST({q(config['data'])} AS DATE) < CURDATE() - INTERVAL {int(anos)} YEAR")


def simular_tabela(cur, tabela, config, colunas, anos):
    """Só contagens: nada é alterado."""
    arquivos = [c for c in config['arquivos'] if c in colunas]
    soma_arquivos = ' + '.join(f"(COALESCE({q(c)}, '') <> '')" for c in arquivos) or '0'
    cur.execute(f"SELECT COUNT(*), COALESCE(SUM({soma_arquivos}), 0), MIN(CAST({q(config['data'])} AS DATE)), "
                f"MAX(CAST({q(config['data'])} AS DATE)) FROM {q(tabela)} WHERE {condicao_vencida(config, anos)}")
    linhas, total_arquivos, mais_antigo, mais_recente = cur.fetchone()
    cur.execute(f"SELECT COUNT(*) FROM {q(tabela)} WHERE expurgo IS NULL AND CAST({q(config['data'])} AS DATE) IS NULL")
    sem_data = cur.fetchone()[0]
    return {'linhas': int(linhas or 0), 'arquivos': int(total_arquivos or 0), 'fim_mais_antigo': mais_antigo,
            'fim_mais_recente': mais_recente, 'sem_data': int(sem_data or 0)}


def expurgar_tabela(conn, tabela, config, colunas, anos, s3, bucket, limite):
    """Apaga os arquivos e anonimiza, linha a linha. Uma linha só é anonimizada depois que o S3 confirma
    a exclusão dos arquivos dela; se algo falhar, ela fica para a próxima execução."""
    cur = conn.cursor()
    anonimizar = [c for c in config['anonimizar'] if c in colunas]
    arquivos = [c for c in config['arquivos'] if c in colunas]
    atribuicoes = [f"{q(c)} = {valor_anonimo(*colunas[c])}" for c in anonimizar + arquivos]
    atualizacao = f"UPDATE {q(tabela)} SET {', '.join(atribuicoes + ['expurgo = NOW()'])} WHERE id = %s AND expurgo IS NULL"
    selecao = (f"SELECT id{''.join(', ' + q(c) for c in arquivos)} FROM {q(tabela)} "
               f"WHERE {condicao_vencida(config, anos)} AND id > %s ORDER BY id LIMIT {LOTE}")
    resumo = {'linhas': 0, 'arquivos': 0, 'arquivos_recusados': 0, 'arquivos_mantidos_dev': 0, 'falhas': 0}
    ultimo_id = 0
    while limite is None or resumo['linhas'] < limite:
        cur.execute(selecao, (ultimo_id,))
        lote = cur.fetchall()
        if not lote:
            break
        for linha in lote:
            if limite is not None and resumo['linhas'] >= limite:
                break
            ultimo_id = linha[0]
            chaves, recusados = chaves_dos_arquivos(linha[1:])
            resumo['arquivos_recusados'] += recusados
            try:
                if chaves and s3 is not None:
                    if not apagar_do_s3(s3, bucket, chaves):
                        resumo['falhas'] += 1
                        logger.error("[retencao] {} id={}: o S3 não apagou todos os arquivos; linha mantida", tabela, ultimo_id)
                        continue
                    resumo['arquivos'] += len(chaves)
                elif chaves:
                    resumo['arquivos_mantidos_dev'] += len(chaves)
                cur.execute(atualizacao, (ultimo_id,))
                conn.commit()
                resumo['linhas'] += 1
            except Exception as e:  # S3 ou banco: registra e segue para a próxima linha
                conn.rollback()
                resumo['falhas'] += 1
                logger.error("[retencao] {} id={}: erro no expurgo: {}", tabela, ultimo_id, type(e).__name__)
    cur.close()
    return resumo


def expurgar_dados_estudantes(conectar, s3=None, bucket=None, simular=False, limite=None, tabelas=None,
                              anos=RETENCAO_ANOS):
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
            if 'expurgo' not in colunas or config['data'] not in colunas:
                resultado[tabela] = {'erro': 'tabela sem a coluna expurgo ou sem a coluna de data (rodar o retencao.sql.sample)'}
                logger.error("[retencao] {}: {}", tabela, resultado[tabela]['erro'])
                continue
            conhecidas = set(config['anonimizar']) | set(config['arquivos']) | set(config['manter']) | {'id', 'expurgo'}
            extras = {
                'colunas_ausentes': sorted((set(config['anonimizar']) | set(config['arquivos'])) - set(colunas)),
                'colunas_nao_classificadas': sorted(set(colunas) - conhecidas),
            }
            if simular:
                resultado[tabela] = {**simular_tabela(cur, tabela, config, colunas, anos), **extras}
            else:
                resultado[tabela] = {**expurgar_tabela(conn, tabela, config, colunas, anos, s3, bucket, limite), **extras}
                r = resultado[tabela]
                logger.info("[retencao] {}: {} linhas anonimizadas, {} arquivos apagados do S3, {} falhas, "
                            "{} nomes de arquivo recusados", tabela, r['linhas'], r['arquivos'], r['falhas'],
                            r['arquivos_recusados'])
            cur.close()
        finally:
            conn.close()
    return resultado
