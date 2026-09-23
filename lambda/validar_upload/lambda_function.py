"""
Lambda validar-upload (migracao.s3.md, fase 3).

Disparada por uma regra do EventBridge ("Object Created" no bucket, chave com prefixo
pesquisa/incoming/). O navegador envia os arquivos a pesquisa/incoming/<prefixo>/<nome> por
uma URL assinada gerada pelo app; esta função:
  1. confere a chave (prefixo conhecido, nome só com [A-Za-z0-9_.-] terminando em .pdf);
  2. confere o tamanho (1 byte a 16 MB) e o tipo real pelos primeiros bytes:
     submissoes: só PDF; docs_indicacoes: PDF, JPEG ou PNG (fotos de documentos);
  3. se válido, copia para pesquisa/<prefixo>/<nome> em SSE-KMS (aws/s3), com o ContentType
     real e a metadata enviado-por=navegador (CopySourceIfMatch: copia a versão conferida);
  4. apaga o objeto de incoming/ (válido ou não). A regra do bucket apaga sobras em 1 dia.

Os bytes do arquivo nunca passam pela função, só os 8 primeiros. Nada de conteúdo vai para o log.
"""
import json
import logging
import re

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")

ENTRADA = "pesquisa/incoming/"
LIMITE_BYTES = 16 * 1000 * 1000  # MAX_CONTENT_LENGTH do app
TIPOS_ACEITOS = {
    "submissoes": {"application/pdf"},
    "docs_indicacoes": {"application/pdf", "image/jpeg", "image/png"},
}
ASSINATURAS = (
    (b"%PDF-", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)
NOME_VALIDO = re.compile(r"[A-Za-z0-9_.-]{1,200}\.pdf")


def tipo_do_conteudo(inicio):
    for assinatura, content_type in ASSINATURAS:
        if inicio.startswith(assinatura):
            return content_type
    return None


def registrar(resultado, chave, **extra):
    logger.info(json.dumps({"resultado": resultado, "chave": chave, **extra}, ensure_ascii=False))
    return {"resultado": resultado, "chave": chave, **extra}


def apagar(bucket, chave):
    try:
        s3.delete_object(Bucket=bucket, Key=chave)
    except ClientError as e:
        logger.error(json.dumps({"erro": "delete_object", "chave": chave,
                                 "codigo": e.response.get("Error", {}).get("Code")}))


def recusar(bucket, chave, motivo, **extra):
    apagar(bucket, chave)
    return registrar("recusado", chave, motivo=motivo, **extra)


def lambda_handler(event, context):
    detalhe = event.get("detail", {})
    bucket = detalhe.get("bucket", {}).get("name", "")
    chave = detalhe.get("object", {}).get("key", "")
    if not bucket or not chave.startswith(ENTRADA):
        return registrar("ignorado", chave, motivo="fora de pesquisa/incoming/")

    partes = chave[len(ENTRADA):].split("/")
    if len(partes) != 2 or partes[0] not in TIPOS_ACEITOS or not NOME_VALIDO.fullmatch(partes[1]):
        return recusar(bucket, chave, "chave inválida")
    prefixo, nome = partes

    try:
        cabecalho = s3.head_object(Bucket=bucket, Key=chave)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return registrar("ignorado", chave, motivo="já processado")  # evento repetido
        raise

    tamanho = cabecalho["ContentLength"]
    if not 0 < tamanho <= LIMITE_BYTES:
        return recusar(bucket, chave, "tamanho", tamanho=tamanho)

    inicio = s3.get_object(Bucket=bucket, Key=chave, Range="bytes=0-7",
                           IfMatch=cabecalho["ETag"])["Body"].read()
    content_type = tipo_do_conteudo(inicio)
    if content_type not in TIPOS_ACEITOS[prefixo]:
        return recusar(bucket, chave, "tipo", tipo=content_type or "desconhecido", tamanho=tamanho)

    destino = f"pesquisa/{prefixo}/{nome}"
    s3.copy_object(
        Bucket=bucket,
        Key=destino,
        CopySource={"Bucket": bucket, "Key": chave},
        CopySourceIfMatch=cabecalho["ETag"],
        ServerSideEncryption="aws:kms",  # sem SSEKMSKeyId: chave gerenciada pela AWS (aws/s3)
        MetadataDirective="REPLACE",
        ContentType=content_type,
        Metadata={"enviado-por": "navegador"},
    )
    apagar(bucket, chave)
    return registrar("aceito", chave, destino=destino, tipo=content_type, tamanho=tamanho)
