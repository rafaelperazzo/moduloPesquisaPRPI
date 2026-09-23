#!/usr/bin/env python3
"""
Migração dos arquivos do S3 de GPG (senha única) para SSE-KMS com a chave
gerenciada pela AWS (aws/s3). Plano completo: migracao.s3.md (fase 1).

Para cada pesquisa/<prefixo>/<nome>.gpg:
  1. baixa o .gpg para a memória;
  2. descriptografa em memória com a GPG_KEY (nada sem criptografia vai para o disco);
  3. identifica o tipo real pelo conteúdo (PDF, JPEG, PNG; vazio ou desconhecido
     também são migrados, sem alteração, e ficam marcados no relatório). A
     integridade é garantida pelo próprio gpg (MDC): só migra se ele der ok;
  4. grava pesquisa/<prefixo>/<nome> com SSE-KMS (aws/s3), guardando na metadata
     o .gpg de origem e o ETag dele;
  5. relê o objeto novo (head_object) para conferir a criptografia e o tamanho.

Os .gpg NÃO são alterados nem apagados: continuam no lugar (período de segurança
de 90 dias, fase 4 do plano). Pode ser interrompido e executado de novo: pula quem
já foi migrado a partir do mesmo .gpg (compara o ETag) e refaz quem teve o .gpg
substituído depois da migração.

Nunca sobrescreve um arquivo enviado pelo app depois da fase 2 (objeto sem a
metadata migrado-de): esse é mais novo que o .gpg e fica como "substituido". A
gravação é condicional (IfNoneMatch/IfMatch): se o app gravar o arquivo entre a
conferência e o PUT, o S3 recusa (412) e o arquivo sai como falha, sem perda.

Execução na EC2 (roteiro completo em migracao.s3.md):
    sudo -u pesquisa -H tmux new -s migracao
    cd /opt/moduloPesquisaPRPI/app
    env/bin/python scripts/migrar_gpg_kms.py --prefixo submissoes --limite 10 --simular
    env/bin/python scripts/migrar_gpg_kms.py --prefixo submissoes --limite 10
    env/bin/python scripts/migrar_gpg_kms.py --prefixo submissoes
    env/bin/python scripts/migrar_gpg_kms.py --prefixo docs_indicacoes
    env/bin/python scripts/migrar_gpg_kms.py --verificar

Usa as credenciais do ambiente (na EC2, a role da instância). A GPG_KEY e o nome
do bucket vêm do SSM (/pesquisa/GPG_KEY e /pesquisa/AWS_S3_BUCKET). Nunca imprime
a senha, o conteúdo dos arquivos nem o nome do bucket fora do resumo inicial.
"""
import argparse
import csv
import os
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import boto3
import gnupg
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

REGIAO = "us-east-2"
RAIZ = "pesquisa/"
PREFIXOS = ("submissoes", "docs_indicacoes")
PASTA_RELATORIOS_S3 = "pesquisa/_migracao/"
META_ORIGEM = "migrado-de"
META_ETAG = "origem-etag"

CONFIG_AWS = Config(
    region_name=REGIAO,
    use_dualstack_endpoint=True,
    retries={"max_attempts": 8, "mode": "standard"},
    max_pool_connections=32,
)

parar = threading.Event()
_local = threading.local()


def gpg_da_thread():
    """Uma instância do python-gnupg por thread (cada chamada abre um processo gpg)."""
    if not hasattr(_local, "gpg"):
        _local.gpg = gnupg.GPG()
    return _local.gpg


def ler_parametro(ssm, nome):
    return ssm.get_parameter(Name=nome, WithDecryption=True)["Parameter"]["Value"]


def listar_prefixo(s3, bucket, prefixo):
    """Retorna {chave: {'etag', 'tamanho'}} de todos os objetos do prefixo."""
    objetos = {}
    paginador = s3.get_paginator("list_objects_v2")
    for pagina in paginador.paginate(Bucket=bucket, Prefix=f"{RAIZ}{prefixo}/"):
        for obj in pagina.get("Contents", []):
            objetos[obj["Key"]] = {"etag": obj["ETag"].strip('"'), "tamanho": obj["Size"]}
    return objetos


def situacao(s3, bucket, chave_gpg, etag_gpg, objetos):
    """'pendente', 'migrado', 'desatualizado' (o .gpg mudou depois da migração) ou
    'substituido' (o app enviou uma versão nova, sem .gpg: nunca é sobrescrita)."""
    destino = chave_gpg[:-4]
    if destino not in objetos:
        return "pendente"
    cabecalho = s3.head_object(Bucket=bucket, Key=destino)
    if META_ORIGEM not in cabecalho.get("Metadata", {}):
        return "substituido"
    if cabecalho.get("Metadata", {}).get(META_ETAG) != etag_gpg:
        return "desatualizado"
    if cabecalho.get("ServerSideEncryption") != "aws:kms":
        return "desatualizado"
    return "migrado"


ASSINATURAS = (
    (b"%PDF", "application/pdf", "pdf"),
    (b"\xff\xd8\xff", "image/jpeg", "jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
)


def tipo_do_conteudo(conteudo):
    """(content_type, rótulo) pelo início do arquivo. Os nomes terminam sempre em .pdf,
    mas o formulário de indicação aceita qualquer tipo (ex.: foto do extrato em JPEG)."""
    if not conteudo:
        return "application/octet-stream", "vazio"
    for assinatura, content_type, rotulo in ASSINATURAS:
        if conteudo.startswith(assinatura):
            return content_type, rotulo
    return "application/octet-stream", "desconhecido"


def migrar_um(s3, bucket, senha, chave_gpg, etag_gpg, simular, etag_destino=None):
    """Migra um .gpg. Retorna (status, tamanho, tipo, erro).
    etag_destino: ETag do objeto sem .gpg já existente (desatualizado) ou None (pendente)."""
    destino = chave_gpg[:-4]
    if simular:
        return "simulado", 0, "", ""
    cifrado = s3.get_object(Bucket=bucket, Key=chave_gpg, IfMatch=etag_gpg)["Body"].read()
    resultado = gpg_da_thread().decrypt(cifrado, passphrase=senha)
    del cifrado
    if not resultado.ok:
        return "falha", 0, "", f"gpg: {resultado.status}"
    conteudo = resultado.data
    content_type, rotulo = tipo_do_conteudo(conteudo)
    condicao = {"IfMatch": etag_destino} if etag_destino else {"IfNoneMatch": "*"}
    s3.put_object(
        Bucket=bucket,
        Key=destino,
        **condicao,
        Body=conteudo,
        ContentType=content_type,
        ServerSideEncryption="aws:kms",  # sem SSEKMSKeyId: chave gerenciada pela AWS (aws/s3)
        Metadata={META_ORIGEM: chave_gpg.rsplit("/", 1)[-1], META_ETAG: etag_gpg},
    )
    conferencia = s3.head_object(Bucket=bucket, Key=destino)
    if conferencia.get("ServerSideEncryption") != "aws:kms":
        return "falha", len(conteudo), rotulo, "objeto gravado sem SSE-KMS"
    if conferencia.get("ContentLength") != len(conteudo):
        return "falha", len(conteudo), rotulo, "tamanho gravado diferente do original"
    return "migrado", len(conteudo), rotulo, ""


def processar(s3, bucket, senha, prefixo, limite, simular, workers, pasta_saida):
    objetos = listar_prefixo(s3, bucket, prefixo)
    gpgs = sorted((k, v) for k, v in objetos.items() if k.endswith(".gpg"))
    print(f"[{prefixo}] {len(gpgs)} arquivos .gpg encontrados; conferindo quais já foram migrados...", flush=True)

    # Descobre o que falta (head_object só para quem já tem versão sem .gpg)
    a_migrar = []
    ja_migrados = 0
    with ThreadPoolExecutor(max_workers=max(workers, 8)) as executor:
        futuros = {executor.submit(situacao, s3, bucket, k, v["etag"], objetos): (k, v) for k, v in gpgs}
        for futuro in as_completed(futuros):
            k, v = futuros[futuro]
            estado = futuro.result()
            if estado in ("migrado", "substituido"):
                ja_migrados += 1
            else:
                a_migrar.append((k, v, estado))
    a_migrar.sort()
    if limite:
        a_migrar = a_migrar[:limite]
    desatualizados = sum(1 for _, _, e in a_migrar if e == "desatualizado")
    print(f"[{prefixo}] já migrados ou substituídos pelo app: {ja_migrados} | a processar agora: {len(a_migrar)}"
          f" (dos quais {desatualizados} com .gpg alterado depois da migração)"
          f"{' | SIMULAÇÃO: nada será gravado' if simular else ''}", flush=True)
    if not a_migrar:
        return 0

    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho_csv = os.path.join(pasta_saida, f"migracao_{prefixo}_{carimbo}{'_simulacao' if simular else ''}.csv")
    contagem = {"migrado": 0, "falha": 0, "simulado": 0}
    nao_pdf = {}
    inicio = time.time()
    with open(caminho_csv, "w", newline="", encoding="utf-8") as arquivo_csv, \
            ThreadPoolExecutor(max_workers=workers) as executor:
        escritor = csv.writer(arquivo_csv)
        escritor.writerow(["chave_gpg", "status", "tamanho_bytes", "tipo", "erro"])
        futuros = {executor.submit(migrar_um, s3, bucket, senha, k, v["etag"], simular,
                                   objetos.get(k[:-4], {}).get("etag") if e == "desatualizado" else None): k
                   for k, v, e in a_migrar}
        cancelados = False
        for n, futuro in enumerate(as_completed(futuros), start=1):
            if parar.is_set() and not cancelados:
                for f in futuros:
                    f.cancel()  # os que já estão em andamento terminam normalmente
                cancelados = True
            if futuro.cancelled():
                continue
            k = futuros[futuro]
            try:
                status, tamanho, tipo, erro = futuro.result()
            except (ClientError, BotoCoreError) as e:
                status, tamanho, tipo, erro = "falha", 0, "", f"{type(e).__name__}: {getattr(e, 'response', {}).get('Error', {}).get('Code', str(e))}"
            except Exception as e:  # noqa: BLE001 - registra e segue para o próximo arquivo
                status, tamanho, tipo, erro = "falha", 0, "", f"{type(e).__name__}: {e}"
            contagem[status] += 1
            if status == "migrado" and tipo != "pdf":
                nao_pdf[tipo] = nao_pdf.get(tipo, 0) + 1
            escritor.writerow([k, status, tamanho, tipo, erro])
            if status == "falha":
                print(f"  FALHA {k}: {erro}", flush=True)
            if n % 100 == 0 or n == len(futuros):
                decorrido = time.time() - inicio
                print(f"[{prefixo}] {n}/{len(futuros)} | migrados {contagem['migrado']} | falhas {contagem['falha']}"
                      f" | {n / decorrido:.1f} arq/s", flush=True)
    if nao_pdf:
        resumo = ", ".join(f"{qtd} {tipo}" for tipo, qtd in sorted(nao_pdf.items()))
        print(f"[{prefixo}] migrados que não são PDF (conteúdo preservado, ver coluna 'tipo' do CSV): {resumo}", flush=True)
    if parar.is_set():
        print(f"[{prefixo}] interrompido: rode o mesmo comando de novo para continuar de onde parou.", flush=True)
    print(f"[{prefixo}] relatório: {caminho_csv}", flush=True)
    if not simular:
        try:
            s3.upload_file(caminho_csv, bucket, PASTA_RELATORIOS_S3 + os.path.basename(caminho_csv),
                           ExtraArgs={"ServerSideEncryption": "aws:kms"})
            print(f"[{prefixo}] relatório enviado para s3://.../{PASTA_RELATORIOS_S3}", flush=True)
        except (ClientError, BotoCoreError) as e:
            print(f"[{prefixo}] aviso: relatório não enviado ao S3 ({type(e).__name__}); a cópia local foi mantida", flush=True)
    return contagem["falha"]


def verificar(s3, bucket, workers):
    """Resumo por prefixo: total de .gpg, migrados e pendentes. Não grava nada."""
    pendencias = 0
    for prefixo in PREFIXOS:
        objetos = listar_prefixo(s3, bucket, prefixo)
        gpgs = [(k, v) for k, v in objetos.items() if k.endswith(".gpg")]
        estados = {"migrado": 0, "pendente": 0, "desatualizado": 0, "substituido": 0}
        faltando = []
        with ThreadPoolExecutor(max_workers=max(workers, 8)) as executor:
            futuros = {executor.submit(situacao, s3, bucket, k, v["etag"], objetos): k for k, v in gpgs}
            for futuro in as_completed(futuros):
                estado = futuro.result()
                estados[estado] += 1
                if estado in ("pendente", "desatualizado"):
                    faltando.append(futuros[futuro])
        pendencias += estados["pendente"] + estados["desatualizado"]
        print(f"[{prefixo}] .gpg: {len(gpgs)} | migrados: {estados['migrado']} | pendentes: {estados['pendente']}"
              f" | .gpg alterado depois da migração: {estados['desatualizado']}"
              f" | substituídos pelo app: {estados['substituido']}")
        for k in sorted(faltando)[:20]:
            print(f"    falta: {k}")
        if len(faltando) > 20:
            print(f"    ... e mais {len(faltando) - 20}")
    print("OK: tudo migrado." if pendencias == 0 else f"ATENÇÃO: {pendencias} arquivo(s) ainda por migrar.")
    return pendencias


def main():
    parser = argparse.ArgumentParser(description="Migra os arquivos .gpg do S3 para SSE-KMS (aws/s3).")
    parser.add_argument("--prefixo", choices=PREFIXOS, help="pasta a migrar (submissoes ou docs_indicacoes)")
    parser.add_argument("--limite", type=int, default=0, help="migra só os N primeiros pendentes (lote de teste)")
    parser.add_argument("--simular", action="store_true", help="só lista o que faria, sem gravar nada")
    parser.add_argument("--workers", type=int, default=4, help="threads de migração (padrão 4; use 2 se a memória for pouca)")
    parser.add_argument("--verificar", action="store_true", help="só confere a situação dos dois prefixos")
    parser.add_argument("--saida", default=os.path.expanduser("~/migracao_s3"), help="pasta dos relatórios CSV")
    args = parser.parse_args()
    if not args.verificar and not args.prefixo:
        parser.error("informe --prefixo ou --verificar")

    sessao = boto3.session.Session(region_name=REGIAO)
    s3 = sessao.client("s3", config=CONFIG_AWS)
    ssm = sessao.client("ssm", config=Config(region_name=REGIAO, retries={"max_attempts": 5, "mode": "standard"}))
    try:
        bucket = ler_parametro(ssm, "/pesquisa/AWS_S3_BUCKET")
        identidade = sessao.client("sts").get_caller_identity()["Arn"]
    except (ClientError, BotoCoreError) as e:
        sys.exit(f"Erro ao acessar a AWS (credenciais ou SSM): {type(e).__name__}: {e}")
    print(f"Identidade AWS: {identidade}\nBucket: {bucket}", flush=True)

    if args.verificar:
        sys.exit(1 if verificar(s3, bucket, args.workers) else 0)

    try:
        senha = ler_parametro(ssm, "/pesquisa/GPG_KEY")
    except (ClientError, BotoCoreError) as e:
        sys.exit(f"Erro ao ler a GPG_KEY no SSM: {type(e).__name__}")
    os.makedirs(args.saida, exist_ok=True)

    def interromper(_sinal, _quadro):
        if parar.is_set():
            sys.exit("Interrompido.")
        print("\nInterrompendo: termino os arquivos em andamento e salvo o relatório "
              "(Ctrl+C de novo para sair na hora)...", flush=True)
        parar.set()
    signal.signal(signal.SIGINT, interromper)

    falhas = processar(s3, bucket, senha, args.prefixo, args.limite, args.simular, args.workers, args.saida)
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
