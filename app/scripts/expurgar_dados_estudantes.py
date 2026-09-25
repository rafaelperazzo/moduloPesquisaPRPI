#!/usr/bin/env python3
"""
Retenção de 6 anos após o fim da bolsa (modules/retencao.py; roteiro em migracao.lgpd.md, "Retenção"):

  * indicacoes:     apaga os documentos em pesquisa/docs_indicacoes/ e anonimiza os dados pessoais,
                    inclusive o CPF; ficam nome, projeto e período;
  * alunos:         anonimiza o e-mail; o CPF fica (busca das declarações antigas);
  * cadastro_geral: anonimiza RG, contato e dados bancários do estudante; o CPF e os dados do
                    orientador ficam.

É a mesma função da tarefa mensal do app (dia 1º, 21:00), sem o limite de 500 linhas: serve para a
primeira execução, que pega o acervo antigo. IRREVERSÍVEL: fazer um backup do banco antes.
Idempotente (só processa expurgo IS NULL) e pode ser interrompido e executado de novo.
Nunca imprime nome, CPF nem nome de arquivo: só contagens.

Pré-requisitos: o retencao.sql.sample aplicado e a role da EC2 (s3:DeleteObject em pesquisa/*).

Execução na EC2:
    cd /opt/moduloPesquisaPRPI/app
    env/bin/python scripts/expurgar_dados_estudantes.py --simular
    env/bin/python scripts/expurgar_dados_estudantes.py --limite 5
    env/bin/python scripts/expurgar_dados_estudantes.py
"""
import argparse
import os
import sys

import mariadb

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.retencao import TABELAS_RETENCAO, expurgar_dados_estudantes  # noqa: E402

REGIAO = "us-east-2"


def carregar_ssm():
    """Mesmo carregamento do app: tudo sob /pesquisa vai para o os.environ."""
    import boto3
    ssm = boto3.client("ssm", region_name=REGIAO)
    for pagina in ssm.get_paginator("get_parameters_by_path").paginate(Path="/pesquisa", Recursive=True, WithDecryption=True):
        for p in pagina.get("Parameters", []):
            os.environ[p["Name"].rstrip("/").split("/")[-1]] = p["Value"]


def conectar(local):
    args = dict(host=os.environ.get("MYSQL_HOST", "localhost"), user=os.environ.get("MYSQL_USER", "pesquisa"),
                passwd=os.environ["MYSQL_PASSWORD"], db=os.environ.get("MYSQL_DATABASE", "pesquisa"))
    if not local:
        args["ssl"] = "required"
    conn = mariadb.connect(**args)
    conn.autocommit = False
    return conn


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tabela", choices=list(TABELAS_RETENCAO), help="só esta tabela (padrão: as três)")
    parser.add_argument("--limite", type=int, default=None, help="no máximo N linhas por tabela")
    parser.add_argument("--simular", action="store_true", help="só mostra as contagens, sem alterar nada")
    parser.add_argument("--local", action="store_true",
                        help="testes: banco local sem SSL e sem SSM, e sem apagar nada no S3 (MYSQL_* do ambiente)")
    args = parser.parse_args()

    s3, bucket = None, None
    if not args.local:
        carregar_ssm()
        import boto3
        from botocore.config import Config
        s3 = boto3.client("s3", region_name=REGIAO, config=Config(signature_version="s3v4"))
        bucket = os.environ.get("AWS_S3_BUCKET")
        if not bucket:
            sys.exit("AWS_S3_BUCKET é obrigatório (SSM /pesquisa/AWS_S3_BUCKET).")

    resultado = expurgar_dados_estudantes(lambda: conectar(args.local), s3=s3, bucket=bucket, simular=args.simular,
                                          limite=args.limite, tabelas=[args.tabela] if args.tabela else None)
    falhou = False
    for tabela, r in resultado.items():
        if 'erro' in r:
            falhou = True
            print(f"[{tabela}] ERRO: {r['erro']}", flush=True)
            continue
        if args.simular:
            print(f"[{tabela}] SIMULAÇÃO | linhas vencidas: {r['linhas']} | arquivos: {r['arquivos']} | "
                  f"fim mais antigo: {r['fim_mais_antigo']} | mais recente: {r['fim_mais_recente']} | "
                  f"sem data válida (não serão tratadas): {r['sem_data']}", flush=True)
            if r['arquivos'] or r['preenchimentos_ignorados'] or r['linhas_com_nome_recusado']:
                print(f"[{tabela}]   valores de preenchimento ignorados (N/A, -): {r['preenchimentos_ignorados']} | "
                      f"linhas com nome de arquivo recusado (ficam para revisão): {r['linhas_com_nome_recusado']}"
                      f"{' (ids: ' + ', '.join(map(str, r['ids_com_nome_recusado'])) + ')' if r['ids_com_nome_recusado'] else ''}",
                      flush=True)
        else:
            falhou = falhou or r['falhas'] > 0
            print(f"[{tabela}] anonimizadas: {r['linhas']} | arquivos apagados do S3: {r['arquivos']} | "
                  f"arquivos não apagados (--local): {r['arquivos_mantidos_dev']} | nomes recusados: "
                  f"{r['arquivos_recusados']} | falhas: {r['falhas']}", flush=True)
        if r['colunas_ausentes']:
            print(f"[{tabela}]   colunas da lista que não existem no banco: {', '.join(r['colunas_ausentes'])}", flush=True)
        if r['colunas_nao_classificadas']:
            print(f"[{tabela}]   colunas NÃO classificadas (revisar se são dados pessoais): "
                  f"{', '.join(r['colunas_nao_classificadas'])}", flush=True)
    sys.exit(1 if falhou else 0)


if __name__ == "__main__":
    main()
