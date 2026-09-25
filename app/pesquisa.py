# -*- coding: utf-8 -*-
from flask import Flask
from flask import render_template, send_file
from flask import request,url_for,send_from_directory,redirect,session,flash,has_request_context
from flask_httpauth import HTTPBasicAuth
from waitress import serve
import mariadb as MySQLdb
from werkzeug.utils import secure_filename
import hashlib
import hmac
import ipaddress
import os
import string
import sys
import re
from flask_uploads import UploadSet, configure_uploads, ALL, DOCUMENTS
import threading
import zeep
import zipfile
import gzip
import glob
import tempfile
import shutil
import xml.etree.ElementTree as ET
import time
from flask import Response
import json
from flask_wtf.csrf import CSRFProtect
from brseclabcripto.cripto3 import SecCripto
from git import Repo
import secrets
import io
import base64
import mimetypes
from functools import wraps
from functools import lru_cache
from urllib.parse import quote
import pyqrcode
from datetime import datetime, timedelta
from datetime import date
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.loguru import LoguruIntegration
from sentry_sdk.integrations.loguru import LoggingLevels
from sentry_sdk.integrations.logging import ignore_logger
from sentry_sdk.scrubber import EventScrubber, DEFAULT_DENYLIST, DEFAULT_PII_DENYLIST
#from logtail import LogtailHandler
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_session import Session
from redis import Redis
from flask_apscheduler import APScheduler
from loguru import logger
from flask import jsonify
import logging
import inspect
import requests
import geoip2.database
import boto3
from botocore.exceptions import ClientError, BotoCoreError
from botocore.config import Config
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from dotenv import load_dotenv
from requests_auth_aws_sigv4 import AWSSigV4
from relatorio_edital_pdf import gerar_pdf_resultado_edital
from modules.retencao import expurgar_dados_estudantes, expurgar_acessos

def load_ssm_parameters(prefix="/pesquisa", region_name="us-east-2"):
    """
    Busca todos os parâmetros sob o prefixo especificado no AWS SSM
    e os injeta no os.environ, registrando as ações via logger.
    """
    try:
        ssm = boto3.client(
            "ssm",
            region_name=region_name,
            config=Config(use_dualstack_endpoint=True)
        )
        paginator = ssm.get_paginator("get_parameters_by_path")
        
        # Pagina sobre os resultados caso haja mais de 10 parâmetros
        pages = paginator.paginate(
            Path=prefix,
            Recursive=True,
            WithDecryption=True
        )

        loaded_count = 0
        for page in pages:
            for param in page.get("Parameters", []):
                # Extrai apenas o nome final da chave (ex: '/pesquisa/DB_HOST' -> 'DB_HOST')
                key = param["Name"].rstrip("/").split("/")[-1]
                value = param["Value"]
                
                # Injeta na variável de ambiente do processo
                os.environ[key] = value
                loaded_count += 1

        logger.info(f"[SSM] {loaded_count} parâmetros carregados com sucesso do prefixo '{prefix}'.")

    except (BotoCoreError, ClientError) as e:
        logger.error(f"[SSM ERRO] Falha ao carregar parâmetros do SSM: {e}")
        # Opcional: descomente se desejar interromper a inicialização em caso de falha crítica
        raise e

def aws_auth():
    """Gera o assinador SigV4 com credenciais atualizadas da EC2."""
    session = boto3.Session(region_name="us-east-2")
    creds = session.get_credentials().get_frozen_credentials()
    return AWSSigV4(
        "lambda",
        region="us-east-2",
        aws_access_key_id=creds.access_key,
        aws_secret_access_key=creds.secret_key,
        aws_session_token=creds.token
    )

try:
    PRODUCAO = int(os.getenv("PRODUCAO", "0"))
except ValueError:
    PRODUCAO = 0

if PRODUCAO==0:
    load_dotenv()
else:
    load_ssm_parameters()

logger.remove()

class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        # Get corresponding Loguru level if it exists.
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message.
        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

WORKING_DIR=''
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_URL = os.getenv("SERVER_URL", "http://localhost")
SERVER_PORT = os.getenv("SERVER_PORT", "80")

UPLOAD_FOLDER = 'static/files'
ALLOWED_EXTENSIONS = set(['pdf','xml'])
URL_PREFIX = os.getenv('URL_PREFIX','/pesquisa')
PLOTS_DIR = 'static/plots/'
CURRICULOS_DIR='static/files/'
XML_DIR = 'xml/'
SITE = SERVER_URL + "static/files/"
IMAGENS_URL = SERVER_URL + "static/"
DECLARACOES_DIR = os.path.join(BASE_DIR, 'pdfs') + '/'
ROOT_SITE = SERVER_URL
USUARIO_SITE = ROOT_SITE + URL_PREFIX + "/usuario"
ATTACHMENTS_DIR = 'docs_indicacoes/'
SUBMISSOES_DIR = 'submissoes/'
MYSQL_DB = os.getenv("MYSQL_HOST", "localhost")
if PRODUCAO==1:
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "pesquisa")
else:
    MYSQL_DATABASE = os.getenv("MYSQL_TEST_DATABASE", "pesquisa_test")
DEFAULT_EMAIL = os.getenv("DEFAULT_EMAIL","teste@test.com")
DEFAULT_SUPPORT = os.getenv("DEFAULT_SUPPORT","teste@test.com")
DEFAULT_INSTITUCIONAL = os.getenv("DEFAULT_INSTITUCIONAL","pesquisa.prpi@ufca.edu.br")
LINK_AVALIACAO = ROOT_SITE + URL_PREFIX + "/avaliacao"
DSN_SENTRY = os.environ.pop("DSN_SENTRY", "")
#BS_SOURCE_TOKEN = os.environ.pop("BS_SOURCE_TOKEN", "")
#BS_HOST = os.getenv("BS_HOST", "")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
URL_LAMBDA = os.getenv("URL_LAMBDA","")

class RequestArquivosEmMemoria(Flask.request_class):
    """Uploads ficam em memória (o Werkzeug grava em /tmp os maiores que 500 KB): os PDFs vão
    direto ao S3 sem passar pelo disco. O MAX_CONTENT_LENGTH (16 MB) limita a memória por requisição."""
    def _get_file_stream(self, total_content_length, content_type, filename=None, content_length=None):
        return io.BytesIO()

app = Flask(__name__)
app.request_class = RequestArquivosEmMemoria
auth = HTTPBasicAuth()
csrf = CSRFProtect(app)
app.config['producao'] = PRODUCAO
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_REDIS'] = Redis.from_url(f'redis://{REDIS_HOST}:6379')
app.config['SESSION_PERMANENT'] = False
Session(app)

app.config['SCHEDULER_API_ENABLED'] = False
scheduler = APScheduler()
scheduler.api_enabled = True
scheduler.init_app(app)

SELF = "'self'"
csp = {
    'default-src': [SELF,],
    'img-src': '*',
    'script-src': [SELF,],
    'style-src': [SELF,],
    'font-src': [SELF,'https://cdn.jsdelivr.net',],
}
nonce_list = ['script-src', 'style-src','font-src']
if PRODUCAO==0:
    Talisman(app,content_security_policy=[],force_https=False,content_security_policy_nonce_in=nonce_list)
else:
    Talisman(app,content_security_policy=[],force_https=True)

limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri=f"redis://{REDIS_HOST}:6379",
    default_limits=["1000 per day", "500 per hour"],
    storage_options={"socket_connect_timeout": 30},
    strategy="fixed-window",
)

if PRODUCAO==1:
    app.config['WTF_CSRF_CHECK_DEFAULT'] = True
else:
    app.config['WTF_CSRF_CHECK_DEFAULT'] = False

try:
    __version__ = Repo('/git').tags[-1].name
    app.config['versao'] = __version__
except Exception as e:
    __version__ = "0.0.0"
    app.config['versao'] = __version__

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['CURRICULOS_FOLDER'] = CURRICULOS_DIR
app.config['DECLARACOES_FOLDER'] = DECLARACOES_DIR
app.config['TEMP_FOLDER'] = DECLARACOES_DIR

AES_KEY = os.environ.pop("AES_KEY", "000000")
GPG_KEY = os.environ.pop("GPG_KEY", "000000")
OPENVPN_KEY = os.environ.pop("OPENVPN_KEY", "000000")
cripto = SecCripto(AES_KEY)

# ---------------------------------------------------------------------------
# Criptografia do CPF e dos dados bancários (migracao.cripto_cpf.md): AES-256-CBC do MariaDB,
# com a AES_KEY e o iv de cada linha, como as demais colunas cifradas (rg, telefone...).
# A busca por CPF usa cpf_hash = HMAC-SHA256(CPF só com dígitos), com a chave /pesquisa/CPF_HMAC_KEY.
# cpf_hash IS NULL marca a linha ainda não cifrada: a leitura devolve o valor como está
# (transição da migração e banco de dev anonimizado).
# ---------------------------------------------------------------------------
CPF_HMAC_KEY = os.environ.pop("CPF_HMAC_KEY", "")
if not CPF_HMAC_KEY:
    if PRODUCAO == 1:
        logger.error("[cripto_cpf] CPF_HMAC_KEY ausente: as buscas por CPF não vão encontrar as linhas cifradas")
    CPF_HMAC_KEY = "chave-hmac-cpf-somente-dev"
SQL_CIFRA = "TO_BASE64(AES_ENCRYPT(%s, %s, %s, 'aes-256-cbc'))"  # parâmetros: valor, AES_KEY, iv

def normalizar_cpf(cpf):
    """Só os dígitos do CPF (com ou sem pontuação)."""
    return re.sub(r'\D', '', str(cpf or ''))

def hash_cpf(cpf):
    """Índice cego do CPF: HMAC-SHA256 dos dígitos. CPF vazio também gera hash (marca a linha como cifrada)."""
    return hmac.new(CPF_HMAC_KEY.encode(), normalizar_cpf(cpf).encode(), hashlib.sha256).hexdigest()

def mascarar_cpf(cpf):
    """CPF para exibição pública: ***.456.789-**."""
    digitos = normalizar_cpf(cpf)
    return f"***.{digitos[3:6]}.{digitos[6:9]}-**" if len(digitos) == 11 else ''

def sql_decifra(coluna, tabela=None):
    """Trecho SQL com a coluna decifrada. Consome 1 parâmetro (AES_KEY), na ordem em que aparece na consulta."""
    p = f"{tabela}." if tabela else ""
    return (f"IF({p}cpf_hash IS NULL OR {p}{coluna} IS NULL OR {p}{coluna} = '', {p}{coluna}, "
            f"CONVERT(AES_DECRYPT(FROM_BASE64({p}{coluna}), %s, {p}iv, 'aes-256-cbc'), CHAR))")

def sql_busca_cpf(tabela=None):
    """Condição de busca por CPF. Consome 2 parâmetros: valores_busca_cpf(cpf)."""
    p = f"{tabela}." if tabela else ""
    return f"({p}cpf_hash = %s OR ({p}cpf_hash IS NULL AND {p}cpf = %s))"

def valores_busca_cpf(cpf):
    return (hash_cpf(cpf), str(cpf))

# Colunas de indicacoes cifradas já no INSERT, sem janela em claro
COLUNAS_CIFRADAS_INDICACAO = {'nascimento', 'rg', 'cpf', 'nome_banco', 'agencia', 'conta', 'telefone', 'celular', 'endereco'}

def montar_insert_indicacao(campos, iv, cpf):
    """INSERT de indicacoes com as colunas pessoais cifradas e o cpf_hash. campos: [(coluna, valor), ...]."""
    colunas = [c for c, _ in campos] + ['cpf_hash']
    marcadores = [SQL_CIFRA if c in COLUNAS_CIFRADAS_INDICACAO else '%s' for c, _ in campos] + ['%s']
    valores = []
    for coluna, valor in campos:
        valores.extend((valor, AES_KEY, iv) if coluna in COLUNAS_CIFRADAS_INDICACAO else (valor,))
    valores.append(hash_cpf(cpf))
    consulta = f"INSERT INTO indicacoes ({','.join(colunas)}) VALUES ({','.join(marcadores)})"
    return consulta, tuple(valores)

def gerar_codigo_auth(identificador, titulo, prefixo='declaracao_orientador'):
    msg = f"{prefixo}:{identificador}:{titulo}".encode()
    return hmac.new(AES_KEY.encode(), msg, hashlib.sha256).hexdigest()

def verificar_codigo_auth(identificador, titulo, codigo, prefixo='declaracao_orientador'):
    return hmac.compare_digest(gerar_codigo_auth(identificador, titulo, prefixo), codigo)

ignore_logger("waitress")
logger.disable("waitress")
logger.disable("sentry_sdk")
logger.enable("apscheduler")
logger.enable("flask-limiter")

# LGPD: os logs (IP, rota, localização) são guardados por 2 anos, como declarado em /lgpd.
# Em produção, o app.json é trocado só no dia 1º de cada mês, sem limite de tamanho, e o arquivo fechado
# é compactado e enviado ao S3 (LOG_PREFIXO_S3). A regra de lifecycle "pesquisa-logs-2-anos" do bucket
# apaga os objetos depois de 730 dias. A cópia local fica só LOG_RETENCAO, conferida a cada rotação.
LOG_RETENCAO = "90 days"
LOG_PREFIXO_S3 = 'pesquisa/logs/'

class RotacaoMensalDoLog:
    """rotation do loguru: troca o arquivo só quando muda o mês (dia 1º)."""
    def __init__(self):
        self.mes = None

    def __call__(self, message, file):
        if self.mes is None:
            # Primeira mensagem depois de iniciar o app: o mês do arquivo é o da última escrita nele.
            info = os.stat(file.name)
            inicio = datetime.fromtimestamp(info.st_mtime) if info.st_size else datetime.now()
            self.mes = (inicio.year, inicio.month)
        agora = message.record["time"]
        if (agora.year, agora.month) != self.mes:
            self.mes = (agora.year, agora.month)
            return True
        return False

def enviar_log_s3(caminho_gz):
    """Envia um log compactado ao S3, em SSE-KMS (aws/s3), como os demais arquivos do pesquisa."""
    chave = LOG_PREFIXO_S3 + os.path.basename(caminho_gz)
    try:
        with open(caminho_gz, 'rb') as arquivo:
            s3.put_object(Bucket=AWS_S3_BUCKET, Key=chave, Body=arquivo, ContentType='application/gzip',
                          ServerSideEncryption='aws:kms', Metadata={'enviado-por': 'app'})
        logger.info("[log] Arquivo {} enviado ao S3", chave)
        return True
    except (ClientError, BotoCoreError, OSError) as e:
        logger.error("[log] Erro ao enviar o arquivo {} ao S3: {}", chave, e)
        return False

def compactar_e_enviar_log(caminho):
    """
    compression do loguru: compacta o arquivo que acabou de ser fechado e o envia ao S3 numa thread.
    O loguru chama esta função segurando a trava do log, então ela não pode usar o logger (daria
    deadlock); quem escreve no log é a thread do envio, depois que a rotação termina.
    """
    caminho_gz = caminho + '.gz'
    with open(caminho, 'rb') as origem, gzip.open(caminho_gz, 'wb') as destino:
        shutil.copyfileobj(origem, destino)
    os.remove(caminho)
    threading.Thread(target=enviar_log_s3, args=(caminho_gz,), daemon=True).start()

if PRODUCAO==1:
    #handler = LogtailHandler(
    #    source_token=BS_SOURCE_TOKEN,
    #    host=BS_HOST,
    #)
    logger.add("app.json", rotation=RotacaoMensalDoLog(), retention=LOG_RETENCAO, backtrace=False,
               diagnose=False, level="INFO", serialize=True,mode='a',
               format="{time} | {name} | {level} | {message} | {extra}",
               compression=compactar_e_enviar_log)
    #logger.add(handler, format="{time} | {name} | {level} | {message} | {extra}", level="INFO",
    #           serialize=True,backtrace=False, diagnose=False)
else:
    logger.add("app.log", rotation="20 MB", retention=LOG_RETENCAO, backtrace=False,
               diagnose=False, level="INFO", serialize=True,mode='w',
               format="{time} | {name} | {level} | {message} | {extra}",
               compression='gz')

# Sentry sem dados pessoais (LGPD, migracao.lgpd.md): sem IP, usuário e cookies (send_default_pii=False),
# sem as variáveis locais dos stack traces (guardam CPF, senha e dados bancários), com os nomes em
# português na lista de campos removidos e com IP, e-mail e CPF mascarados nas mensagens e breadcrumbs.
SENTRY_DENYLIST = DEFAULT_DENYLIST + ['senha', 'cpf', 'rg', 'conta', 'agencia', 'nome_banco', 'nascimento', 'telefone',
                                      'celular', 'endereco', 'email', 'chave', 'codigo', 'username', 'siape', 'ip']
SENTRY_PII_DENYLIST = DEFAULT_PII_DENYLIST + ['cf-connecting-ip', 'true-client-ip', 'x-forwarded-for', 'x-real-ip']
RE_SENTRY_MASCARAS = [
    (re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'), '[email]'),
    (re.compile(r'\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b'), '[cpf]'),
    (re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'), '[ip]'),
    (re.compile(r'\b(?:[0-9a-fA-F]{1,4}:){3,7}[0-9a-fA-F]{1,4}\b'), '[ip]'),
]

def mascarar_texto_sentry(texto):
    if not isinstance(texto, str):
        return texto
    for padrao, substituto in RE_SENTRY_MASCARAS:
        texto = padrao.sub(substituto, texto)
    return texto

def sentry_before_send(event, hint):
    """Mascara IP, e-mail e CPF no texto do evento (mensagem, logentry e exceções)."""
    if 'message' in event:
        event['message'] = mascarar_texto_sentry(event['message'])
    for chave in ('message', 'formatted'):
        if chave in event.get('logentry', {}):
            event['logentry'][chave] = mascarar_texto_sentry(event['logentry'][chave])
    for excecao in event.get('exception', {}).get('values', []):
        excecao['value'] = mascarar_texto_sentry(excecao.get('value'))
    return event

def sentry_before_breadcrumb(crumb, hint):
    """Os breadcrumbs repetem as mensagens do log, que citam IP e e-mail."""
    crumb['message'] = mascarar_texto_sentry(crumb.get('message'))
    return crumb

if PRODUCAO==1:
    # CONFIGURANDO SENTRY
    sentry_sdk.init(
        dsn=DSN_SENTRY,
        _experiments={
            "enable_logs": False
        },
        integrations = [
            FlaskIntegration(
                transaction_style="url",
            ),
            LoguruIntegration(
                level=LoggingLevels.INFO.value,
                event_level=LoggingLevels.ERROR.value,
                sentry_logs_level=LoggingLevels.INFO.value,
            ),
        ],
        send_default_pii=False,
        include_local_variables=False,
        event_scrubber=EventScrubber(denylist=SENTRY_DENYLIST, pii_denylist=SENTRY_PII_DENYLIST, recursive=True),
        before_send=sentry_before_send,
        before_breadcrumb=sentry_before_breadcrumb,
    )

#AWS

AWS_S3_KEY_ID = os.environ.pop("AWS_S3_KEY_ID", "default_key_id")
AWS_S3_SECRET_KEY = os.environ.pop("AWS_S3_SECRET_KEY", "default_secret_key")
AWS_REGION = os.getenv("AWS_REGION", "us-east-2")
AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET", "default_bucket")
# signature_version='s3v4': obrigatória para URLs assinadas de objetos SSE-KMS
if PRODUCAO==1:
    s3 = boto3.client('s3', region_name=AWS_REGION,
                      config=Config(use_dualstack_endpoint=True, signature_version='s3v4'))
else:
    s3 = boto3.client('s3', region_name=AWS_REGION,
                      aws_access_key_id=AWS_S3_KEY_ID,
                      aws_secret_access_key=AWS_S3_SECRET_KEY,
                      config=Config(use_dualstack_endpoint=True, signature_version='s3v4'))

def enviar_logs_pendentes():
    """Reenvia os logs compactados que ainda não estão no S3 (envio que falhou ou app parado no meio)."""
    for caminho_gz in sorted(glob.glob("app.*.json.gz")):
        try:
            s3.head_object(Bucket=AWS_S3_BUCKET, Key=LOG_PREFIXO_S3 + os.path.basename(caminho_gz))
        except ClientError as e:
            if e.response.get('Error', {}).get('Code') in ('404', 'NoSuchKey', 'NotFound'):
                enviar_log_s3(caminho_gz)
            else:
                logger.error("[log] Erro ao conferir o arquivo {} no S3: {}", caminho_gz, e)
        except BotoCoreError as e:
            logger.error("[log] Erro ao conferir o arquivo {} no S3: {}", caminho_gz, e)

if PRODUCAO==1:
    threading.Thread(target=enviar_logs_pendentes, daemon=True).start()

#Arquivos no S3: URLs assinadas de download e links dos avaliadores (migracao.s3.md, fase 1)
URL_DOWNLOAD_VALIDADE = 60  # segundos
ARQUIVOS_LINK_VALIDADE = 30 * 24 * 3600  # links dos PDFs na página /avaliacao: 30 dias
ARQUIVOS_LINK_KEY = os.environ.pop("ARQUIVOS_LINK_KEY", "")
if not ARQUIVOS_LINK_KEY:
    # Sem a chave fixa, os links dos avaliadores deixam de valer a cada reinício do serviço
    logger.warning("ARQUIVOS_LINK_KEY não definida: usando chave temporária")
    ARQUIVOS_LINK_KEY = secrets.token_hex(32)
assinador_arquivos = URLSafeTimedSerializer(ARQUIVOS_LINK_KEY, salt='arquivo-avaliador')

lambda_client = boto3.client('lambda', region_name='us-east-2')

#COGNITO (somente em produção; em dev a autenticação continua no MariaDB)
COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID", "")
COGNITO_APP_CLIENT_ID = os.getenv("COGNITO_APP_CLIENT_ID", "")
USAR_COGNITO = PRODUCAO == 1
cognito = boto3.client('cognito-idp', region_name=AWS_REGION) if USAR_COGNITO else None

SQS_QUEUE_URL = os.getenv(
    "AWS_SQS_EMAIL_QUEUE_URL",
    ""
)
sqs_client = boto3.client(
    "sqs",
    region_name="us-east-2",
    config=Config(
        connect_timeout=2,
        read_timeout=3,
        retries={"max_attempts": 1},
        use_dualstack_endpoint=True  # Habilita IPv4/IPv6
    )
)

def send_email_async(recipients: list[str] | str, subject: str, html_body: str) -> bool:
    """
    Publica a mensagem na fila SQS para envio assíncrono via Lambda/SES.
    Só enfileira quando PRODUCAO==1; nos demais ambientes apenas registra em log
    e retorna True (para que os fluxos que dependem do envio sigam normalmente).
    """
    if isinstance(recipients, str):
        recipients = [recipients]

    if PRODUCAO != 1:
        logger.info("PRODUCAO!=1: e-mail NÃO enfileirado (assunto: {})", subject)
        return True

    payload = {
        "recipients": recipients,
        "subject": subject,
        "html": html_body
    }

    try:
        response = sqs_client.send_message(
            QueueUrl=SQS_QUEUE_URL,
            MessageBody=json.dumps(payload, ensure_ascii=False)
        )
        logger.info(f"E-mail enfileirado: MessageId={response.get('MessageId')}")
        return True
    except Exception as exc:
        logger.error(f"Erro ao enfileirar e-mail no SQS: {exc}")
        return False

#Obtendo senhas
PASSWORD = os.environ.pop("MYSQL_PASSWORD", "World")
app.config['SECRET_KEY'] = secrets.token_hex()
app.config['WTF_CSRF_TIME_LIMIT'] = None
app.config['MAX_CONTENT_LENGTH'] = 16 * 1000 * 1000

#Flask-flask_uploads
app.config['UPLOADED_DOCUMENTS_DEST'] = os.path.join(BASE_DIR, 'docs_indicacoes') + '/'
app.config['UPLOADS_DEFAULT_DEST'] = ATTACHMENTS_DIR
anexos = UploadSet('documents',ALL)
app.config['UPLOADED_SUBMISSOES_DEST'] = os.path.join(BASE_DIR, 'submissoes') + '/'
submissoes = UploadSet("submissoes", DOCUMENTS, default_dest=SUBMISSOES_DIR)

configure_uploads(app, anexos)
configure_uploads(app, submissoes)

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1)

@app.context_processor
def utility_processor():
    def gen_nonce():
        """Generate a nonce for Content Security Policy."""
        return secrets.token_hex(16)
    return dict(gen_nonce=gen_nonce)

@app.context_processor
def inject_messages():
    def get_messages():
        return carregar_mensagens()
    return dict(get_messages=get_messages)

@app.context_processor
def inject_default_support():
    return dict(default_support=DEFAULT_SUPPORT, default_institutional=DEFAULT_INSTITUCIONAL)

# ---------------------------------------------------------------------------
# Cloudflare Turnstile (substitui o reCAPTCHA): o widget fica em templates/_turnstile.html e o
# token (cf-turnstile-response) é validado no servidor, só em produção, como o MFA.
# Sem as chaves no SSM, valem as chaves de teste da Cloudflare, que sempre aprovam.
# ---------------------------------------------------------------------------
TURNSTILE_SITE_KEY = os.getenv("TURNSTILE_SITE_KEY", "1x00000000000000000000AA")
TURNSTILE_SECRET_KEY = os.environ.pop("TURNSTILE_SECRET_KEY", "1x0000000000000000000000000000000AA")
TURNSTILE_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
MENSAGEM_TURNSTILE = "Não foi possível confirmar a verificação de segurança. Aguarde a caixa de verificação e tente novamente."

@app.context_processor
def inject_turnstile():
    return dict(turnstile_site_key=TURNSTILE_SITE_KEY)

def turnstile_valido():
    """Valida o token do Turnstile com a Cloudflare. Sem token ou recusado: False.
    Se a própria Cloudflare não responder, aceita e registra aviso, para não travar o login."""
    if PRODUCAO != 1:
        return True
    token = str(request.form.get('cf-turnstile-response', ''))
    if not token:
        logger.info("[turnstile] Envio sem token: rota={}", request.path)
        return False
    ip = request.headers.get('CF-Connecting-IP') or request.remote_addr
    try:
        resposta = requests.post(TURNSTILE_URL, timeout=5,
                                 data={'secret': TURNSTILE_SECRET_KEY, 'response': token[:2048], 'remoteip': ip})
        resposta.raise_for_status()
        resultado = resposta.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("[turnstile] Cloudflare indisponível; envio aceito sem validação: rota={} erro={}", request.path, str(e))
        return True
    if not resultado.get('success'):
        logger.info("[turnstile] Token recusado: rota={} erros={}", request.path, resultado.get('error-codes'))
        return False
    return True

def exigir_turnstile(voltar):
    """Decorator para as rotas de formulário: no POST sem Turnstile válido, volta ao formulário (endpoint `voltar`)."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if request.method == 'POST' and not turnstile_valido():
                flash(MENSAGEM_TURNSTILE, 'error')
                return redirect(url_for(voltar))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@lru_cache(maxsize=None)
def imagem_base64(filename):
    """Lê um arquivo de app/static e retorna como data URI base64, para embutir em PDFs sem depender de requisição HTTP."""
    caminho = os.path.join(app.static_folder, filename)
    mime, _ = mimetypes.guess_type(caminho)
    with open(caminho, 'rb') as f:
        codificado = base64.b64encode(f.read()).decode('ascii')
    return f"data:{mime or 'application/octet-stream'};base64,{codificado}"

@app.context_processor
def inject_imagem_base64():
    return dict(imagem_base64=imagem_base64)

@lru_cache(maxsize=None)
def asset_inline(filename):
    """Lê um arquivo de texto (CSS/JS) de app/static e retorna seu conteúdo bruto, para embutir em <style>/<script> sem depender de requisição HTTP (ex.: CDNs que a Lambda de geração de PDF não alcança)."""
    caminho = os.path.join(app.static_folder, filename)
    with open(caminho, 'r', encoding='utf-8') as f:
        return f.read()

@app.context_processor
def inject_asset_inline():
    return dict(asset_inline=asset_inline)

def login_required(role='admin'):
    def decorator_login_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not 'username' in session:
                return render_template('login.html')
            if role not in session['roles']:
                flash('Você não tem permissão para acessar este recurso.','error')
                return redirect(url_for('home'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator_login_required

ROTAS_PERMITIDAS_SENHA_VAZADA = {'nova_senha', 'encerrarSessao', 'static'}

@app.before_request
def bloquear_acesso_com_senha_vazada():
    """
    Quando o login detecta (via Cloudflare Leaked Credential Check) que a
    senha do usuário está vazada, a sessão é marcada com 'senha_vazada'.
    Enquanto essa marca existir, o usuário só pode acessar a tela de troca
    de senha, o logout e arquivos estáticos - todas as demais rotas são
    redirecionadas até que uma nova senha seja definida.
    """
    if session.get('senha_vazada') and request.endpoint not in ROTAS_PERMITIDAS_SENHA_VAZADA:
        flash("Você precisa definir uma nova senha antes de continuar.", "error")
        return redirect(url_for('nova_senha'))

ROTAS_PERMITIDAS_MFA_PENDENTE = {'mfa_configurar', 'mfa_totp', 'mfa_email', 'nova_senha',
                                 'encerrarSessao', 'seguranca', 'static'}
ROTAS_BASIC_AUTH = {'secret_page', 'get_bib', 'static'}

@app.before_request
def exigir_cadastro_mfa():
    """
    Em produção o MFA é obrigatório para quem está no Cognito. Login concluído sem
    desafio de MFA marca a sessão com 'mfa_pendente': até cadastrar o MFA, o usuário
    só acessa as telas de cadastro, a troca de senha e o logout.
    Sessões abertas pelo HTTP Basic Auth (sem MFA) ficam restritas às suas rotas.
    """
    if not USAR_COGNITO:
        return None
    if session.get('somente_basic_auth') and request.endpoint not in ROTAS_BASIC_AUTH:
        session.clear()
        return redirect(url_for('login'))
    if session.get('mfa_pendente') and request.endpoint not in ROTAS_PERMITIDAS_MFA_PENDENTE:
        flash("Para continuar, configure a verificação em duas etapas (MFA).", "error")
        return redirect(url_for('mfa_configurar'))

ROTAS_PERMITIDAS_ACEITE = ({'lgpd', 'lgpd_aceite', 'lgpd_solicitacao', 'lgpd_consulta', 'health', 'version'}
                           | ROTAS_PERMITIDAS_MFA_PENDENTE | ROTAS_PERMITIDAS_SENHA_VAZADA | ROTAS_BASIC_AUTH)

@app.before_request
def exigir_aceite_lgpd():
    """
    LGPD (migracao.lgpd.md): o login marca a sessão com 'aceite_pendente' quando o usuário
    ainda não registrou ciência da versão atual dos Termos de Uso e da Política de Privacidade.
    Até registrar, só acessa a política, o próprio aceite, o logout e as telas de MFA/senha.
    Roda depois dos bloqueios de senha vazada e de MFA, que têm prioridade.
    """
    if session.get('aceite_pendente') and request.endpoint not in ROTAS_PERMITIDAS_ACEITE:
        return redirect(url_for('lgpd_aceite'))

def log_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        geolocalizacao = getDados(request.remote_addr)
        if session.get('username') is None:
            with logger.contextualize(ip=request.remote_addr,username="N/A",rota=request.path,metodo=request.method,cidade=geolocalizacao['city'],estado=geolocalizacao['state'],pais=geolocalizacao['country']):
                logger.info("Acesso a recurso (NÃO AUTENTICADO)")
        else:
            with logger.contextualize(ip=request.remote_addr,username=session['username'],rota=request.path,metodo=request.method,cidade=geolocalizacao['city'],estado=geolocalizacao['state'],pais=geolocalizacao['country']):
                logger.info("Acesso a recurso (AUTENTICADO)")
        return f(*args, **kwargs)
    return decorated_function

def getDados(ip):
    """Obtém dados de geolocalização a partir de um IP."""
    try:
        with geoip2.database.Reader('geolite2-city.mmdb') as reader:
            try:
                response = reader.city(ip)
                return {
                    'country': response.country.name,
                    'city': response.city.name,
                    'state': response.subdivisions.most_specific.name,
                }
            except geoip2.errors.AddressNotFoundError:
                if "10." in ip or "192.168." in ip or "172.16." in ip:
                    # IPs privados não são geolocalizáveis
                    return {
                        'country': "INTERNO",
                        'city': "INTERNO",
                        'state': "INTERNO",
                    }
                else:
                    return {
                        'country': "NAO-ENCONTRADO",
                        'city': "NAO-ENCONTRADO",
                        'state': "NAO-ENCONTRADO",
                    }
            except Exception as e:
                with logger.contextualize(ip=ip,erro=str(e),classe_erro=type(e).__name__):
                    logger.warning("Erro ao obter dados de geolocalização: {}", str(e))
                return {
                    'country': "NAO-ENCONTRADO",
                    'city': "NAO-ENCONTRADO",
                    'state': "NAO-ENCONTRADO",
                }
    except Exception as e:
        with logger.contextualize(ip=ip,erro=str(e),classe_erro=type(e).__name__):
            logger.warning("Erro ao abrir o banco de dados de geolocalização: {}", str(e))
        return {
            'country': "NAO-ENCONTRADO",
            'city': "NAO-ENCONTRADO",
            'state': "NAO-ENCONTRADO",
        }

def calcula_hash(mensagem):
    """
    Calcula o hash SHA-256 de uma mensagem.
    """
    hash_cripto = hashlib.sha224()
    hash_cripto.update(mensagem.encode('utf-8'))
    return hash_cripto.hexdigest()

def generate_secure_password(length=16, include_uppercase=True,
                             include_numbers=True, include_special_chars=True):
    # Define character sets - Senhas seguras
    lowercase_letters = string.ascii_lowercase
    uppercase_letters = string.ascii_uppercase if include_uppercase else ""
    digits = string.digits if include_numbers else ""
    special_chars = string.punctuation if include_special_chars else ""

    # Combine character sets and create a password
    all_characters = lowercase_letters + uppercase_letters + digits + special_chars
    if len(all_characters) == 0:
        raise ValueError("At least one character set must be included")

    # Gera novamente até atender à política (12+ caracteres e 4 classes), exigida também pelo Cognito
    while True:
        password = ''.join(secrets.choice(all_characters) for _ in range(length))
        if length < 12 or not (include_uppercase and include_numbers and include_special_chars) or senha_segura_valida(password):
            return password

def removerAspas(texto):
    resultado = texto.replace('"',' ')
    resultado = resultado.replace("'"," ")
    return resultado

def removerTravessao(texto):
    resultado = texto.replace("-","")
    return resultado

def getID(cpf):
    wsdl = './cnpq'
    client = zeep.Client(wsdl=wsdl)
    idlattes = client.service.getIdentificadorCNPq(cpf,"","")
    if idlattes is None:
        idlattes = "0000000000000000"
    return str(idlattes)

def salvarCV(idlattes):
    wsdl = './cnpq'
    client = zeep.Client(wsdl=wsdl)
    resultado = client.service.getCurriculoCompactado(idlattes)
    if resultado is not None:
        arquivo = open(idlattes + '.zip','wb')
        arquivo.write(resultado)
        arquivo.close()
        with zipfile.ZipFile(idlattes + '.zip','r') as zip_ref:
            zip_ref.extractall(XML_DIR)
        if os.path.exists(idlattes + '.zip'):
            os.remove(idlattes + '.zip')

#Search: logger\.(info|warning|error)(\(".*)(%s)(.*)
#Replace: logger.$1$2{}$4

def extrair_modalidade(texto):
    opcoes = [
    r"PIBIC-Ensino Médio", 
    r"PIBIC-Ensino Medio", 
    r"PIBIC-Acoes Afirmativas", 
    r"PIBITI", 
    r"PIBIC"
    ]
    padrao = "|".join(opcoes)
    try:
        resultado = re.search(padrao, texto,re.IGNORECASE).group()
    except AttributeError:
        resultado = "-"
    return resultado.upper()


def atualizarPontuacaoLattes(cpf, area, idProjeto):
    periodo = "5"
    url_score = URL_LAMBDA + str(cpf).strip() + "/" + str(area).strip() + "/" + periodo + "/" + "0"
    url_sumario = URL_LAMBDA + str(cpf).strip() + "/" + str(area).strip() + "/" + periodo + "/" + "1"
    sumario = ""
    pontuacao = "0.0"
    try:
        sumario = requests.get(url_sumario, auth=aws_auth(), timeout=120).text
        pontuacao = requests.get(url_score, auth=aws_auth(), timeout=120).text
        pontuacao = json.loads(pontuacao)
        pontuacao = pontuacao['score']
    except Exception as e:
        logger.warning("Erro ao processar a pontuação Lattes: {}", str(e))
        sumario = "Erro ao processar a pontuacao lattes. Comunicação com o CNPq falhou."
        pontuacao = "0.0"
    try:
        consulta = """UPDATE editalProjeto
        SET scorelattes= %s WHERE id= %s"""
        atualizar2(consulta, valores=[pontuacao, idProjeto])
    except Exception as e:
        logger.warning("Erro ao atualizar o scorelattes: {} com o cpf: {}", str(e), str(cpf))
    return pontuacao, sumario

def processarPontuacaoLattes(cpf,area,idProjeto,dados):
    periodo = "5"
    url_score = URL_LAMBDA + str(cpf).strip() + "/" + str(area).strip() + "/" + periodo + "/" + "0"
    url_sumario = URL_LAMBDA + str(cpf).strip() + "/" + str(area).strip() + "/" + periodo + "/" + "1"
    sumario = ""
    pontuacao = "0.0"
    try:
        sumario = requests.get(url_sumario, auth=aws_auth(), timeout=120).text
        pontuacao = requests.get(url_score, auth=aws_auth(), timeout=120).text
        pontuacao = json.loads(pontuacao)
        pontuacao = pontuacao['score']
    except Exception as e:
        logger.warning("Erro ao processar a pontuação Lattes: {}", str(e))
        sumario = "Erro ao processar a pontuacao lattes. Comunicação com o CNPq falhou."
        pontuacao = "0.0"
    try:
        consulta = """UPDATE editalProjeto 
        SET scorelattes= %s WHERE id= %s"""
        atualizar2(consulta,valores=[pontuacao,idProjeto])
    except Exception as e:
        with app.app_context():
            logger.warning("Erro ao atualizar o scorelattes: {} com o cpf: {}", str(e),str(cpf))
    with app.app_context():
        try:
            #ENVIAR E-MAIL DE CONFIRMAÇÃO
            codigo_do_edital = str(obterColunaUnica("editalProjeto","tipo","id",str(idProjeto)))
            descricao_do_edital = str(obterColunaUnica("editais","nome","id",codigo_do_edital))
            modalidade = extrair_modalidade(descricao_do_edital)
            texto_email = render_template('confirmacao_submissao.html',email_proponente=dados[0],id_projeto=idProjeto,proponente=dados[1],titulo_projeto=dados[2],resumo_projeto=dados[3],score=pontuacao,sumario=sumario,modalidade=modalidade)
            if send_email_async(dados[0], "Plataforma Yoko - CONFIRMAÇÃO DE SUBMISSAO DE PROJETO DE PESQUISA", texto_email):
                logger.info("Email enfileirado com sucesso. processarPontuacaoLattes - IdProjeto: {}", idProjeto)
            else:
                logger.error("Erro ao enfileirar e-mail. processarPontuacaoLattes")
        except Exception as e:
            logger.error(str(e))
            logger.error("Procedimento para o ID: " + str(idProjeto) + " finalizado. Erros ocorreram ao enviar e-mail.")

def processarPontuacaoLattes2(xml_content, area, idProjeto, dados):
    """
    Equivalente a processarPontuacaoLattes, mas calcula a pontuação a partir
    do conteúdo XML do currículo Lattes enviado como arquivo (usado quando o
    serviço de consulta por CPF junto ao CNPq está offline).
    """
    ano_fim = date.today().year
    ano_inicio = ano_fim - 5
    sumario = ""
    pontuacao = "0.0"
    try:
        resultado = obter_score_lattes(
            xml_content=xml_content,
            ano_inicio=ano_inicio,
            ano_fim=ano_fim,
            area_capes=area,
            tipo="detalhada"
        )
        pontuacao = resultado['score_total']
        sumario = resultado['html']
    except Exception as e:
        logger.warning("Erro ao processar a pontuação Lattes a partir do arquivo: {}", str(e))
        sumario = "Erro ao processar a pontuacao lattes a partir do arquivo enviado."
        pontuacao = "0.0"
    try:
        consulta = """UPDATE editalProjeto
        SET scorelattes= %s WHERE id= %s"""
        atualizar2(consulta,valores=[pontuacao,idProjeto])
    except Exception as e:
        with app.app_context():
            logger.warning("Erro ao atualizar o scorelattes: {} - idProjeto: {}", str(e), str(idProjeto))
    with app.app_context():
        try:
            #ENVIAR E-MAIL DE CONFIRMAÇÃO
            codigo_do_edital = str(obterColunaUnica("editalProjeto","tipo","id",str(idProjeto)))
            descricao_do_edital = str(obterColunaUnica("editais","nome","id",codigo_do_edital))
            modalidade = extrair_modalidade(descricao_do_edital)
            texto_email = render_template('confirmacao_submissao.html',email_proponente=dados[0],id_projeto=idProjeto,proponente=dados[1],titulo_projeto=dados[2],resumo_projeto=dados[3],score=pontuacao,sumario=sumario,modalidade=modalidade)
            if send_email_async(dados[0], "Plataforma Yoko - CONFIRMAÇÃO DE SUBMISSAO DE PROJETO DE PESQUISA", texto_email):
                logger.info("Email enfileirado com sucesso. processarPontuacaoLattes2 - IdProjeto: {}", idProjeto)
            else:
                logger.error("Erro ao enfileirar e-mail. processarPontuacaoLattes2")
        except Exception as e:
            logger.error(str(e))
            logger.error("Procedimento para o ID: " + str(idProjeto) + " finalizado. Erros ocorreram ao enviar e-mail.")        

def calcularScoreLattes(tipo,area,since,until,arquivo):
    #Tipo = 0: Apenas pontuacao; Tipo = 1: Sumário
    pasta = WORKING_DIR + "modules/"
    if tipo==1:
        command = "python " + pasta + "scorerun.py -v -p 2017 -s " +  since + " -u " + until + " \"" + area + "\" " +  arquivo
    else:
        command = "python " + pasta + "scorerun.py -p 2017 -s " +  since + " -u " + until + " \"" + area + "\" " +  arquivo
    s = os.popen(command).read()
    return (s)

def atualizar(consulta):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required") 
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    try:
        cursor.execute(consulta)
        conn.commit()
    except MySQLdb.Error as e:
        logger.warning(e)
        logger.warning(consulta)
    finally:
        cursor.close()
        conn.close()

def atualizar2(consulta,valores=()):
    """Função para UPDATE, INSERT e DELETE no banco de dados.

    Args:
        consulta (str): consulta SQL
        valores (list, optional): Valores para consulta. Defaults to ().
    """
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required") 
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    try:
        if valores==():
            cursor.execute(consulta)
            conn.commit()
        else:
            cursor.execute(consulta,tuple(valores))
            conn.commit()
    except MySQLdb.Error as e:
        logger.warning(e)
        logger.warning(consulta)
    finally:
        cursor.close()
        conn.close()

def inserir(consulta,valores):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    try:
        cursor.execute(consulta,valores)
        conn.commit()
    except MySQLdb.Error as e:
        logger.warning(e)
        logger.warning("Erro ao inserir registro")
        logger.warning(valores)
    finally:
        cursor.close()
        conn.close()

def numero_valido(numero):
    """Verifica se um número é válido.

    Args:
        numero (string): Identificador

    Returns:
        boolean: Verdadeiro ou falso
    """
    try:
        int(numero)
        return True
    except ValueError:
        return False

def username_valido(username):
    """Verifica se um nome de usuário é válido.

    Args:
        username (string): Nome de usuário

    Returns:
        boolean: Verdadeiro ou falso
    """
    if not username.isalnum():
        return False
    return True

def token_valido(token):
    """Verifica se um token é válido.

    Args:
        token (string): Token

    Returns:
        boolean: Verdadeiro ou falso
    """
    if not token.isalnum():
        return False
    else:
        return True

def senha_vazada_detectada():
    """Verifica se o Cloudflare identificou, via Leaked Credential Checks,
    que as credenciais enviadas no login fazem parte de um vazamento de
    dados conhecido.

    O Cloudflare envia o header 'Exposed-Credential-Check' com um valor de
    1 a 4 (o significado varia conforme o plano/tipo de detecção; no plano
    Free apenas a senha é checada). O header só chega à origem se o Managed
    Transform "Add Leaked Credentials Checks Header" estiver habilitado no
    painel (Rules > Managed Transforms).
    Referência: https://developers.cloudflare.com/waf/detections/leaked-credentials/

    Returns:
        boolean: Verdadeiro se a senha foi identificada como vazada
    """
    valor = request.headers.get('Exposed-Credential-Check', '0')
    return valor != '0' and valor != ''

def nome_valido(nome):
    """Verifica se um nome é válido.

    Args:
        nome (string): Nome

    Returns:
        boolean: Verdadeiro ou falso
    """
    padrao = "^[a-zA-Z\u00C0-\u00FF ]+$"
    if re.fullmatch(padrao, nome):
        return True
    else:
        return False

def id_generator(size=20, chars=string.ascii_uppercase + string.digits + string.ascii_lowercase):
    """Sufixo dos nomes de arquivo e tokens de avaliação: gerador criptográfico (secrets)."""
    return ''.join(secrets.choice(chars) for _ in range(size))

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def getData():
    import datetime
    Meses=('janeiro','fevereiro','março','abril','maio','junho',
       'julho','agosto','setembro','outubro','novembro','dezembro')
    agora1 = datetime.date.today()
    dia = agora1.day
    mes=agora1.month-1
    mesExtenso = Meses[mes]
    ano = agora1.year
    resultado = str(dia) + " de " + mesExtenso + " de " + str(ano) + "."
    return resultado

@app.errorhandler(429)
def ratelimit_handler(e):
    return (render_template('429.html', erro=e.description), 429)

def gerarDeclaracao(identificador):
    #CONEXÃO COM BD
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    consulta = f"SELECT nome,{sql_decifra('cpf')},modalidade,orientador,projeto,inicio,fim,id,ch FROM alunos WHERE id=%s"
    cursor.execute(consulta, (AES_KEY, identificador))
    linha = cursor.fetchone()

    #RECUPERANDO DADOS
    nome = linha[0]
    cpf = linha[1]
    modalidade = linha[2]
    orientador = linha[3]
    projeto = linha[4]
    ch = linha[8]
    vigencia_inicio = linha[5]
    vigencia_fim = linha[6]
    id_projeto = linha[7]
    carga_horaria = linha[8]

    consulta = "INSERT INTO autenticacao (idAluno,codigo,data) VALUES (%s,FLOOR(RAND()*(100000000-10000+1))+10000,NOW())"
    cursor.execute(consulta, (identificador,))
    conn.commit()
    conn.commit()
    conn.close()
    return (linha)

def gerarDeclaracaoOrientador(identificador):
    #CONEXÃO COM BD
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    consulta = "SELECT id,coordenador,siape,titulo,inicio,fim FROM projetos WHERE id=%s"
    cursor.execute(consulta, (identificador,))
    linha = cursor.fetchone()
    consultaBolsistas = "SELECT a.nome FROM alunos a, projetos p WHERE a.projeto=p.titulo AND p.id=%s"
    cursor.execute(consultaBolsistas, (identificador,))
    bolsistas = cursor.fetchall()
    #Montando lista de bolsistas:
    total_bolsistas = len(bolsistas)
    i = 0
    frase_bolsistas = ""
    for bolsista in bolsistas:
        if i==total_bolsistas: #Se for o ultimo bolsista
            frase_bolsistas = frase_bolsistas + str(bolsista[0])
        else: #Se nao for o ultimo bolsista
            frase_bolsistas = frase_bolsistas + str(bolsista[0]) + ", "
        i = i + 1
    conn.close()
    return (linha,frase_bolsistas)

def gerarProjetosPorAluno(cpf):
    if len(normalizar_cpf(cpf)) != 11:
        return ([], [])
    try:
        conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
        conn.select_db(MYSQL_DATABASE)
        cursor  = conn.cursor()
        consulta = f"""SELECT estudante_nome_completo,{sql_decifra('cpf')},estudante_modalidade,nome_do_coordenador,titulo_do_projeto,estudante_inicio,estudante_fim,token FROM cadastro_geral WHERE {sql_busca_cpf()} """
        cursor.execute(consulta, (AES_KEY,) + valores_busca_cpf(cpf))
        linhas = cursor.fetchall()
        consulta = f"""SELECT indicacoes.nome,{sql_decifra('cpf', 'indicacoes')},IF(indicacoes.modalidade=1,'PIBIC',IF(indicacoes.modalidade=2,'PIBITI','PIBIC-EM')),editalProjeto.nome,editalProjeto.titulo,indicacoes.inicio,indicacoes.fim,indicacoes.id
                    FROM indicacoes,editalProjeto
                    WHERE indicacoes.idProjeto=editalProjeto.id AND {sql_busca_cpf('indicacoes')} """
        cursor.execute(consulta, (AES_KEY,) + valores_busca_cpf(cpf))
        linhas2019 = cursor.fetchall()
        return (linhas,linhas2019)
    except Exception as e:
        logger.warning(e)
        logger.warning("ERRO Na função gerarProjetosPorAluno. Ver consulta abaixo.")
        logger.warning(consulta)
    finally:
        cursor.close()
        conn.close()

def gerarProjetosPorOrientador(identificador):
    #CONEXÃO COM BD
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    consulta = "SELECT id,coordenador,titulo,inicio,fim FROM projetos WHERE SIAPE=%s"
    cursor.execute(consulta, (identificador,))
    linhas = cursor.fetchall()
    conn.close()
    return (linhas)

def gerarAutenticacao(identificador):
    #CONEXÃO COM BD
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    consulta = f"SELECT a.nome,{sql_decifra('cpf', 'a')},a.modalidade,a.orientador,a.projeto,a.inicio,a.fim,b.codigo FROM alunos a, autenticacao b WHERE a.id=b.idAluno and b.codigo=%s ORDER BY b.data DESC LIMIT 1"
    cursor.execute(consulta, (AES_KEY, identificador))
    linha = cursor.fetchone()
    conn.close()
    return (linha)

def getEditaisAbertos():
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    consulta = """SELECT id,nome,DATE_FORMAT(deadline,'%d/%m/%Y - %H:%i') FROM editais WHERE now()<deadline ORDER BY id DESC"""
    cursor.execute(consulta)
    linhas = cursor.fetchall()
    cursor.close()
    conn.close()
    return linhas

# ---------------------------------------------------------------------------
# Autenticação (legado no MariaDB em dev; Cognito em produção)
# ---------------------------------------------------------------------------

COLUNAS_USUARIO = "id, username, permission, roles, password, migrado, nome, email"
CONSULTAS_USUARIO = {
    'username': f"SELECT {COLUNAS_USUARIO} FROM users WHERE username=%s LIMIT 1",
    'email': f"SELECT {COLUNAS_USUARIO} FROM users WHERE email=%s LIMIT 1",
    'id': f"SELECT {COLUNAS_USUARIO} FROM users WHERE id=%s LIMIT 1",
}

def buscar_usuario(valor, campo='username'):
    """Retorna a linha (id, username, permission, roles, password, migrado, nome, email)
    do usuário ou None se não existir."""
    resultado = executarSelect2(CONSULTAS_USUARIO[campo], valores=[valor])
    if resultado is None:  # executarSelect2 retorna None em caso de erro
        return None
    linhas, total = resultado
    return linhas[0] if total > 0 else None

def iniciar_sessao(username, permissao, roles):
    """Preenche a sessão usada pelo login_required (igual para os dois backends)."""
    session['username'] = str(username)
    session['permissao'] = int(permissao)
    session['roles'] = str(roles).split(',')
    session['edital'] = 0
    if aceite_pendente(username):
        session['aceite_pendente'] = True
    else:
        session.pop('aceite_pendente', None)

def codigo_erro(e):
    """Código do erro retornado pela AWS (ex.: NotAuthorizedException)."""
    if isinstance(e, ClientError):
        return e.response.get('Error', {}).get('Code', 'ClientError')
    return type(e).__name__

def log_migracao(evento, username, nivel='info', origem=None, etapa=None, erro=None, classe_erro=None, **extra):
    """Registra as operações de migração e de senha no Cognito.
    NUNCA passar senha, código de verificação, tokens ou o Session do desafio."""
    if has_request_context():
        ip, rota, metodo = request.remote_addr, request.path, request.method
        operador = session.get('username', 'N/A')
    else:
        ip = rota = metodo = operador = "N/A"
    with logger.contextualize(ip=ip, username=str(username), rota=rota, metodo=metodo, operador=operador,
                              evento=evento, origem=origem or "", etapa=etapa or "",
                              erro=erro or "", classe_erro=classe_erro or "", **extra):
        logger.log(nivel.upper(), "Cognito: {}", evento)

def verificar_senha_legado(linha, password):
    """Confere a senha no hash Argon2id da tabela users."""
    username = str(linha[1])
    try:
        valida = cripto.hash_argon2id_verify(str(linha[4]), password)
    except Exception as e:
        with logger.contextualize(ip=request.remote_addr,username=username,rota=request.path,metodo=request.method,erro=str(e),classe_erro=type(e).__name__):
            logger.warning("Senha inválida. Erro no Argon2")
        return False
    with logger.contextualize(ip=request.remote_addr,username=username,rota=request.path,metodo=request.method,erro=""):
        if valida:
            logger.info("Usuário autenticado com sucesso")
        else:
            logger.warning("Usuário/Senha inválida")
    return bool(valida)

def atributos_cognito(linha):
    """Atributos do usuário no Cognito a partir da linha da tabela users.
    email_verified=true é necessário para o Cognito entregar os códigos de recuperação."""
    return [
        {'Name': 'name', 'Value': str(linha[6] or '')},
        {'Name': 'email', 'Value': str(linha[7] or '')},
        {'Name': 'email_verified', 'Value': 'true'},
        {'Name': 'custom:roles', 'Value': str(linha[3])},
        {'Name': 'custom:permission', 'Value': str(int(linha[2]))},
        {'Name': 'custom:legacy_id', 'Value': str(int(linha[0]))},
    ]

def atributos_para_dict(atributos):
    return {a['Name']: a['Value'] for a in atributos}

def marcar_migrado(linha, sub, origem):
    """Grava migrado=1 e o sub do Cognito na tabela users."""
    username = str(linha[1])
    atualizar2("UPDATE users SET migrado=1, cognito_sub=%s WHERE id=%s", valores=[sub, linha[0]])
    confirmado = buscar_usuario(linha[0], 'id')
    if confirmado is None or int(confirmado[5]) != 1:
        # O usuário já está no Cognito; a próxima migração recupera pela idempotência
        log_migracao('migracao_falha_db', username, nivel='error', origem=origem, etapa='db_update', cognito_sub=sub)
        return False
    return True

def cognito_migrar_usuario(linha, senha=None, origem='login'):
    """Migra o usuário legado para o Cognito SEM enviar e-mail (único uso do SUPPRESS).

    Com senha=None (antes do esqueci minha senha ou do reset pelo admin) define uma senha
    aleatória que nunca é mostrada nem enviada. Levanta ClientError/BotoCoreError em caso
    de falha (InvalidPasswordException quando a senha não atende à política do pool).
    """
    username = str(linha[1])
    log_migracao('migracao_iniciada' if senha is not None else 'migracao_silenciosa_pre_recuperacao',
                 username, origem=origem)
    etapa = 'admin_create_user'
    try:
        try:
            resposta = cognito.admin_create_user(
                UserPoolId=COGNITO_USER_POOL_ID,
                Username=username,
                UserAttributes=atributos_cognito(linha),
                MessageAction='SUPPRESS',
            )
            sub = atributos_para_dict(resposta['User']['Attributes']).get('sub')
        except ClientError as e:
            if codigo_erro(e) != 'UsernameExistsException':
                raise
            # Migração anterior interrompida: reaproveita a conta existente
            log_migracao('migracao_usuario_ja_existia', username, nivel='warning', origem=origem, etapa=etapa)
            etapa = 'admin_update_user_attributes'
            cognito.admin_update_user_attributes(UserPoolId=COGNITO_USER_POOL_ID, Username=username,
                                                 UserAttributes=atributos_cognito(linha))
            usuario = cognito.admin_get_user(UserPoolId=COGNITO_USER_POOL_ID, Username=username)
            sub = atributos_para_dict(usuario['UserAttributes']).get('sub')
        etapa = 'admin_set_user_password'
        cognito.admin_set_user_password(
            UserPoolId=COGNITO_USER_POOL_ID,
            Username=username,
            Password=senha if senha is not None else generate_secure_password(),
            Permanent=True,
        )
    except (ClientError, BotoCoreError) as e:
        if codigo_erro(e) == 'InvalidPasswordException':
            log_migracao('migracao_adiada_politica_senha', username, nivel='warning', origem=origem, etapa=etapa)
        else:
            log_migracao('migracao_falha_cognito', username, nivel='error', origem=origem, etapa=etapa,
                         erro=str(e), classe_erro=codigo_erro(e))
        raise
    if marcar_migrado(linha, sub, origem):
        log_migracao('migracao_concluida_nova_senha' if origem == 'nova_senha' else 'migracao_concluida',
                     username, origem=origem, cognito_sub=sub)
    return sub

def cognito_convidar_usuario(linha):
    """Cadastra um usuário novo no Cognito; o Cognito envia o convite (senha provisória) por e-mail."""
    username = str(linha[1])
    try:
        resposta = cognito.admin_create_user(
            UserPoolId=COGNITO_USER_POOL_ID,
            Username=username,
            UserAttributes=atributos_cognito(linha),
            DesiredDeliveryMediums=['EMAIL'],
        )
    except (ClientError, BotoCoreError) as e:
        log_migracao('convite_falha_cognito', username, nivel='error', origem='cadastro',
                     erro=str(e), classe_erro=codigo_erro(e))
        raise
    sub = atributos_para_dict(resposta['User']['Attributes']).get('sub')
    marcar_migrado(linha, sub, 'cadastro')
    log_migracao('convite_enviado', username, origem='cadastro', cognito_sub=sub)
    return sub

def cognito_sincronizar_atributos(linha):
    """Replica no Cognito os dados alterados pelo admin (nome, e-mail, roles, permission)."""
    username = str(linha[1])
    try:
        cognito.admin_update_user_attributes(UserPoolId=COGNITO_USER_POOL_ID, Username=username,
                                             UserAttributes=atributos_cognito(linha))
    except (ClientError, BotoCoreError) as e:
        log_migracao('sincronizacao_falha_cognito', username, nivel='error', origem='alterar_usuario',
                     erro=str(e), classe_erro=codigo_erro(e))
        raise
    log_migracao('atributos_sincronizados', username, origem='alterar_usuario')

def cognito_iniciar_recuperacao(linha, origem):
    """Faz o Cognito enviar o e-mail de recuperação de senha.

    Usuário não migrado é migrado antes, em silêncio. Se o convite ainda não foi usado,
    o Cognito reenvia o convite; senão envia um código (forgot_password no esqueci minha
    senha, admin_reset_user_password no reset pelo admin). Retorna 'convite' ou 'codigo'.
    """
    username = str(linha[1])
    migrado = int(linha[5]) == 1
    if not migrado:
        cognito_migrar_usuario(linha, None, origem=origem)  # sem e-mail; conta fica CONFIRMED
    try:
        status = 'CONFIRMED'
        if migrado:
            status = cognito.admin_get_user(UserPoolId=COGNITO_USER_POOL_ID, Username=username)['UserStatus']
        if status == 'FORCE_CHANGE_PASSWORD':
            cognito.admin_create_user(UserPoolId=COGNITO_USER_POOL_ID, Username=username, MessageAction='RESEND')
            log_migracao('convite_reenviado', username, origem=origem)
            return 'convite'
        if origem == 'esqueci_senha':
            cognito.forgot_password(ClientId=COGNITO_APP_CLIENT_ID, Username=username)
        else:
            cognito.admin_reset_user_password(UserPoolId=COGNITO_USER_POOL_ID, Username=username)
        log_migracao('codigo_recuperacao_enviado', username, origem=origem)
        return 'codigo'
    except (ClientError, BotoCoreError) as e:
        log_migracao('recuperacao_falha_cognito', username, nivel='error', origem=origem,
                     erro=str(e), classe_erro=codigo_erro(e))
        raise

def cognito_autenticar(username, senha):
    """admin_initiate_auth; retorna a resposta (AuthenticationResult ou ChallengeName)."""
    return cognito.admin_initiate_auth(
        UserPoolId=COGNITO_USER_POOL_ID,
        ClientId=COGNITO_APP_CLIENT_ID,
        AuthFlow='ADMIN_USER_PASSWORD_AUTH',
        AuthParameters={'USERNAME': username, 'PASSWORD': senha},
    )

def iniciar_sessao_cognito(username):
    """Inicia a sessão com os papéis guardados no Cognito (custom:roles / custom:permission)."""
    usuario = cognito.admin_get_user(UserPoolId=COGNITO_USER_POOL_ID, Username=username)
    atributos = atributos_para_dict(usuario['UserAttributes'])
    if 'custom:roles' not in atributos or 'custom:permission' not in atributos:
        log_migracao('atributos_ausentes_cognito', username, nivel='warning')
    iniciar_sessao(username, atributos.get('custom:permission', '1'), atributos.get('custom:roles', 'user'))

# Desafios de MFA do Cognito -> nome do campo com o código na resposta ao desafio
MFA_TIPOS = {'SOFTWARE_TOKEN_MFA': 'SOFTWARE_TOKEN_MFA_CODE', 'EMAIL_OTP': 'EMAIL_OTP_CODE'}
EMISSOR_TOTP = "Yoko Pesquisa"

def guardar_tokens(resultado, refresh_anterior=None):
    """Guarda os tokens do Cognito na sessão (Redis, lado servidor). O access token é
    exigido pelas APIs de MFA e pelo change_password."""
    session['cognito_tokens'] = {
        'access': resultado['AccessToken'],
        'refresh': resultado.get('RefreshToken') or refresh_anterior,
        'expira': time.time() + int(resultado.get('ExpiresIn', 3600)) - 60,
    }

def obter_access_token():
    """Access token válido da sessão, renovado pelo refresh token quando expirado.
    Retorna None se a sessão não tiver tokens (ex.: login anterior ao MFA)."""
    tokens = session.get('cognito_tokens')
    if not tokens:
        return None
    if time.time() < tokens['expira']:
        return tokens['access']
    if not tokens.get('refresh'):
        return None
    try:
        resposta = cognito.admin_initiate_auth(
            UserPoolId=COGNITO_USER_POOL_ID,
            ClientId=COGNITO_APP_CLIENT_ID,
            AuthFlow='REFRESH_TOKEN_AUTH',
            AuthParameters={'REFRESH_TOKEN': tokens['refresh']},
        )
    except (ClientError, BotoCoreError) as e:
        log_migracao('mfa_falha', session.get('username', 'N/A'), nivel='warning', etapa='refresh_token',
                     classe_erro=codigo_erro(e))
        return None
    guardar_tokens(resposta['AuthenticationResult'], refresh_anterior=tokens['refresh'])
    return session['cognito_tokens']['access']

def concluir_login_cognito(username, resultado, via_mfa):
    """Ponto único de conclusão do login no Cognito: inicia a sessão e guarda os tokens.
    Sem desafio de MFA o usuário ainda não tem MFA: fica preso ao cadastro (mfa_pendente)."""
    iniciar_sessao_cognito(username)
    guardar_tokens(resultado)
    session.pop('somente_basic_auth', None)
    if via_mfa:
        session.pop('mfa_pendente', None)
    else:
        session['mfa_pendente'] = True

def autenticar_cognito(username, senha, interativo=True):
    """interativo=False (HTTP Basic Auth): valida só a senha, sem desafio de MFA nem tokens."""
    try:
        resposta = cognito_autenticar(username, senha)
    except (ClientError, BotoCoreError) as e:
        codigo = codigo_erro(e)
        if codigo == 'PasswordResetRequiredException':
            return 'reset'
        if codigo == 'UserNotFoundException':
            log_migracao('login_inconsistente_migrado_sem_cognito', username, nivel='error')
        elif codigo == 'NotAuthorizedException':
            with logger.contextualize(ip=request.remote_addr,username=username,rota=request.path,metodo=request.method,erro=""):
                logger.warning("Usuário/Senha inválida")
        else:
            log_migracao('login_falha_cognito', username, nivel='error', erro=str(e), classe_erro=codigo)
        return 'invalido'
    desafio = resposta.get('ChallengeName')
    if desafio == 'NEW_PASSWORD_REQUIRED':
        if interativo:
            session['cognito_desafio'] = {'username': username, 'session': resposta['Session']}
        return 'desafio'
    if desafio in MFA_TIPOS and interativo:
        session['cognito_mfa'] = {
            'username': username,
            'session': resposta['Session'],
            'tipo': desafio,
            'destino': resposta.get('ChallengeParameters', {}).get('CODE_DELIVERY_DESTINATION', ''),
            'senha_vazada': senha_vazada_detectada(),  # o header do Cloudflare só vem no POST do /login
        }
        log_migracao('mfa_desafio', username, origem='login', etapa=desafio)
        return 'mfa'
    # No Basic Auth o desafio de MFA só chega depois de a senha estar correta
    if 'AuthenticationResult' not in resposta and not (desafio in MFA_TIPOS and not interativo):
        log_migracao('login_desafio_nao_suportado', username, nivel='error', classe_erro=desafio)
        return 'invalido'
    try:
        if interativo:
            concluir_login_cognito(username, resposta['AuthenticationResult'], via_mfa=False)
        else:
            iniciar_sessao_cognito(username)
    except (ClientError, BotoCoreError) as e:
        log_migracao('login_falha_cognito', username, nivel='error', erro=str(e), classe_erro=codigo_erro(e))
        return 'invalido'
    with logger.contextualize(ip=request.remote_addr,username=username,rota=request.path,metodo=request.method,erro=""):
        logger.info("Usuário autenticado com sucesso (Cognito)")
    return 'ok'

def autenticar_usuario(username, senha, interativo=True):
    """Autentica o usuário e inicia a sessão.

    Em produção: usuário migrado autentica no Cognito; não migrado confere a senha
    legada e, se correta, é migrado em silêncio (mesma senha, permanente).
    Retorna 'ok', 'politica' (logado, mas precisa trocar a senha), 'desafio'
    (primeiro acesso de convidado), 'mfa' (aguardando o código do MFA),
    'reset' (senha resetada pelo admin) ou 'invalido'.
    interativo=False é o HTTP Basic Auth (sem MFA).
    """
    if not username_valido(username):
        return 'invalido'
    linha = buscar_usuario(username)
    if linha is None:
        return 'invalido'
    if USAR_COGNITO and int(linha[5]) == 1:
        return autenticar_cognito(username, senha, interativo)
    if not verificar_senha_legado(linha, senha):
        return 'invalido'
    resultado = 'ok'
    if USAR_COGNITO:
        try:
            cognito_migrar_usuario(linha, senha, origem='login')
        except (ClientError, BotoCoreError) as e:
            # Já registrado no log; o login segue pelo legado e a migração é tentada de novo depois
            if codigo_erro(e) == 'InvalidPasswordException':
                resultado = 'politica'
        else:
            if interativo:
                # Recém-migrado: autentica no Cognito para obter os tokens e cair no cadastro do MFA
                resultado_cognito = autenticar_cognito(username, senha)
                if resultado_cognito != 'invalido':
                    return resultado_cognito
                log_migracao('mfa_falha', username, nivel='warning', origem='login', etapa='login_pos_migracao')
    iniciar_sessao(linha[1], linha[2], linha[3])
    if resultado == 'politica':
        # Reaproveita o bloqueio de senha vazada: só libera após a troca em /novaSenha
        session['senha_vazada'] = True
    return resultado

@auth.verify_password
def verify_password(username, password):
    """Callback do HTTPBasicAuth: retorna o username se as credenciais forem válidas."""
    try:
        if autenticar_usuario(username, password, interativo=False) in ('ok', 'politica'):
            if USAR_COGNITO:
                # Sessão sem MFA: fica restrita às rotas de Basic Auth (ver exigir_cadastro_mfa)
                session['somente_basic_auth'] = True
            return username
        return False
    except Exception as e:
        with logger.contextualize(ip=request.remote_addr,username=username,rota=request.path,metodo=request.method,erro=str(e),classe_erro=type(e).__name__):
            logger.warning("ERRO Na função verify_password")
        return False

@auth.get_user_roles
def get_user_roles(user):
    consulta = "SELECT roles FROM users WHERE username=%s"
    linhas,total = executarSelect2(consulta,valores=(auth.username(),))
    if total>0:
        for linha in linhas:
            roles = str(linha[0])
            roles = roles.split(',')
            session['roles'] = roles
            return (roles)
    else:
        return (['user'])

def autenticado():
    if ('username') in session:
        return (True)
    else:
        return (False)

def logout():
    session.clear()

@app.route('/segredo')
@auth.login_required
@log_required
def secret_page():
    return session['username']

@app.route("/")
def home():
    session['PRODUCAO'] = PRODUCAO
    return render_template('root.html',mensagens=mensagens)

@app.route("/seguranca")
def seguranca():
    """Página informativa sobre os recursos de segurança da infraestrutura
    (Cloudflare) e da aplicação, para dar transparência aos usuários."""
    return render_template('seguranca.html')

# ---------------------------------------------------------------------------
# LGPD (migracao.lgpd.md): política de privacidade, ciência dos termos após o login,
# "Meus dados" (acesso e portabilidade) e solicitações dos titulares
# ---------------------------------------------------------------------------

LGPD_VERSAO = "1.0"          # mudar a versão faz todos os usuários registrarem a ciência de novo
LGPD_VIGENCIA = "24/09/2026"
LGPD_PRAZO_RESPOSTA = 15     # dias (art. 19, II)
LGPD_VINCULOS = {
    'discente': 'Discente (bolsista ou voluntário)',
    'orientador': 'Orientador(a) / servidor(a)',
    'avaliador': 'Avaliador(a) de projetos',
    'outro': 'Outro',
}
LGPD_TIPOS = {
    'confirmacao': 'Confirmação da existência de tratamento',
    'acesso': 'Acesso aos dados',
    'correcao': 'Correção de dados incompletos, inexatos ou desatualizados',
    'eliminacao': 'Anonimização, bloqueio ou eliminação',
    'portabilidade': 'Portabilidade dos dados',
    'compartilhamento': 'Informação sobre compartilhamento',
    'outro': 'Outro',
}
LGPD_SITUACOES = {'aberta': 'Aberta', 'respondida': 'Respondida'}
LGPD_LINK_CONSULTA = ROOT_SITE + URL_PREFIX + "/lgpd/consulta"

def aceite_pendente(username):
    """True se o usuário ainda não registrou ciência da versão atual dos termos.
    Erro de banco (ex.: tabela ainda não criada) conta como sem pendência, para nunca travar o login."""
    try:
        resultado = executarSelect2("SELECT 1 FROM lgpd_aceites WHERE username=%s AND versao=%s LIMIT 1",
                                    valores=(str(username), LGPD_VERSAO))
    except Exception as e:
        resultado = None
        logger.warning("[lgpd] Erro ao consultar o aceite: {}", str(e))
    if resultado is None:
        logger.warning("[lgpd] Consulta de aceite falhou; o login segue sem exigir a ciência")
        return False
    return resultado[1] == 0

def consultar_dicts(consulta, valores=()):
    """SELECT que devolve uma lista de dicionários (coluna -> valor), para "Meus dados"."""
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
    conn.select_db(MYSQL_DATABASE)
    cursor = conn.cursor()
    try:
        cursor.execute(consulta, tuple(valores))
        colunas = [c[0] for c in cursor.description]
        return [dict(zip(colunas, linha)) for linha in cursor.fetchall()]
    except Exception as e:
        logger.warning("[lgpd] Erro em consultar_dicts: {}", str(e))
        return []
    finally:
        cursor.close()
        conn.close()

def valor_exportavel(valor):
    """Converte datas, decimais e bytes para tipos que o JSON aceita."""
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, bytes):
        return valor.decode('utf-8', errors='replace')
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    return str(valor)

def dados_do_titular(username):
    """Dados pessoais do usuário logado (art. 18, I, II e V). Não inclui dados de outros
    titulares (discentes indicados): deles, só a quantidade."""
    linha = buscar_usuario(username)
    cadastro = {}
    if linha is not None:
        cadastro = {'usuario': linha[1], 'nome': linha[6], 'email': linha[7], 'papeis': linha[3]}
    projetos = consultar_dicts("""SELECT editalProjeto.id, editais.nome AS edital, editalProjeto.titulo,
        editalProjeto.categoria, editalProjeto.nome, editalProjeto.email, editalProjeto.ua,
        editalProjeto.area_capes, editalProjeto.grande_area, editalProjeto.grupo,
        editalProjeto.data, editalProjeto.inicio, editalProjeto.fim
        FROM editalProjeto LEFT JOIN editais ON editais.id=editalProjeto.tipo
        WHERE editalProjeto.siape=%s ORDER BY editalProjeto.data DESC""", (str(username),))
    indicacoes = consultar_dicts("""SELECT COUNT(*) AS total FROM indicacoes, editalProjeto
        WHERE editalProjeto.id=indicacoes.idProjeto AND editalProjeto.siape=%s""", (str(username),))
    # A tabela acessos não tem esquema no repositório: lê todas as colunas e ordena pela 1ª data
    acessos = consultar_dicts("SELECT * FROM acessos WHERE username=%s", (str(username),))
    if acessos:
        coluna_data = next((c for c, v in acessos[0].items() if isinstance(v, (datetime, date))), None)
        if coluna_data:
            acessos.sort(key=lambda a: a[coluna_data] or datetime.min, reverse=True)
    aceites = consultar_dicts("SELECT versao, data, ip FROM lgpd_aceites WHERE username=%s ORDER BY data DESC",
                              (str(username),))
    return {
        'gerado_em': datetime.now().isoformat(timespec='seconds'),
        'controlador': 'Universidade Federal do Cariri (UFCA) - PRPI',
        'cadastro': cadastro,
        'projetos': projetos,
        'total_indicacoes_de_discentes': indicacoes[0]['total'] if indicacoes else 0,
        'acessos': acessos[:50],
        'total_acessos': len(acessos),
        'ciencia_dos_termos': aceites,
    }

@app.route("/lgpd")
@log_required
def lgpd():
    """Política de privacidade e quadro de atendimento aos requisitos da LGPD (público)."""
    return render_template('lgpd.html', versao=LGPD_VERSAO, vigencia=LGPD_VIGENCIA,
                           prazo=LGPD_PRAZO_RESPOSTA, url_validade=URL_DOWNLOAD_VALIDADE,
                           link_dias=ARQUIVOS_LINK_VALIDADE // 86400)

@app.route("/lgpd/aceite", methods=['GET', 'POST'])
@log_required
def lgpd_aceite():
    """Registro de ciência dos Termos de Uso e da Política de Privacidade, pedido após o login.
    Não é consentimento (art. 7, I): a base legal do tratamento é outra (ver /lgpd)."""
    if 'username' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        if request.form.get('ciente') != '1':
            flash("Marque a caixa de ciência para continuar.", 'error')
            return render_template('lgpd_aceite.html', versao=LGPD_VERSAO, vigencia=LGPD_VIGENCIA)
        atualizar2("INSERT IGNORE INTO lgpd_aceites (username, versao, ip) VALUES (%s, %s, %s)",
                   valores=[session['username'], LGPD_VERSAO, request.remote_addr])
        session.pop('aceite_pendente', None)
        logger.info("[lgpd] Ciência dos termos registrada: usuario={} versao={}", session['username'], LGPD_VERSAO)
        flash("Ciência registrada. Obrigado!")
        return redirect(url_for('home'))
    return render_template('lgpd_aceite.html', versao=LGPD_VERSAO, vigencia=LGPD_VIGENCIA)

@app.route("/meusDados", methods=['GET'])
@login_required(role='user')
@log_required
def meus_dados():
    """Acesso aos próprios dados (art. 18, I e II)."""
    return render_template('meus_dados.html', dados=dados_do_titular(session['username']))

@app.route("/meusDados.json", methods=['GET'])
@login_required(role='user')
@log_required
def meus_dados_json():
    """Portabilidade (art. 18, V): os mesmos dados de /meusDados em JSON."""
    dados = dados_do_titular(session['username'])
    for chave in ('projetos', 'acessos', 'ciencia_dos_termos'):
        dados[chave] = [{c: valor_exportavel(v) for c, v in item.items()} for item in dados[chave]]
    corpo = json.dumps(dados, ensure_ascii=False, indent=2)
    logger.info("[lgpd] Exportação de dados pessoais: usuario={}", session['username'])
    return Response(corpo, mimetype='application/json',
                    headers={'Content-Disposition': f'attachment; filename="meus_dados_{secure_filename(session["username"])}.json"'})

def ler_formulario_solicitacao():
    """Lê e valida o formulário de solicitação. Retorna (campos, erro)."""
    campos = {c: str(request.form.get(c, '')).strip() for c in ('nome', 'email', 'vinculo', 'tipo', 'descricao')}
    if not all(campos.values()):
        return campos, "Preencha todos os campos."
    if len(campos['nome']) > 255 or len(campos['email']) > 255 or len(campos['descricao']) > 5000:
        return campos, "Algum campo passou do tamanho máximo (descrição: até 5000 caracteres)."
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", campos['email']):
        return campos, "Informe um e-mail válido."
    if campos['vinculo'] not in LGPD_VINCULOS or campos['tipo'] not in LGPD_TIPOS:
        return campos, "Selecione o vínculo e o tipo de solicitação."
    return campos, None

@app.route("/lgpd/solicitacao", methods=['GET', 'POST'])
@log_required
@limiter.limit("3/day;2/hour;1/minute", methods=["POST"])
def lgpd_solicitacao():
    """Canal do titular (art. 18): registra o pedido, avisa a PRPI e confirma o protocolo ao titular.
    Nunca devolve dados pessoais por aqui: a PRPI confere a identidade antes de responder."""
    if request.method == 'POST':
        campos, erro = ler_formulario_solicitacao()
        if not erro and not turnstile_valido():
            erro = MENSAGEM_TURNSTILE
        if erro:
            flash(erro, 'error')
            return render_template('lgpd_solicitacao.html', campos=campos, vinculos=LGPD_VINCULOS,
                                   tipos=LGPD_TIPOS, prazo=LGPD_PRAZO_RESPOSTA)
        protocolo = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(12))
        prazo = date.today() + timedelta(days=LGPD_PRAZO_RESPOSTA)
        atualizar2("""INSERT INTO lgpd_solicitacoes (protocolo, nome, email, vinculo, tipo, descricao, prazo)
            VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                   valores=[protocolo, campos['nome'], campos['email'], campos['vinculo'], campos['tipo'],
                            campos['descricao'], prazo])
        contexto = dict(protocolo=protocolo, prazo=prazo.strftime('%d/%m/%Y'), campos=campos,
                        vinculo=LGPD_VINCULOS[campos['vinculo']], tipo=LGPD_TIPOS[campos['tipo']],
                        link_consulta=LGPD_LINK_CONSULTA)
        send_email_async(DEFAULT_INSTITUCIONAL, f"Plataforma Yoko - Solicitação LGPD {protocolo}",
                         render_template('email_lgpd_solicitacao.html', para_prpi=True, **contexto))
        send_email_async(campos['email'], f"Plataforma Yoko - Solicitação LGPD recebida ({protocolo})",
                         render_template('email_lgpd_solicitacao.html', para_prpi=False, **contexto))
        logger.info("[lgpd] Solicitação registrada: protocolo={} tipo={} vinculo={}",
                    protocolo, campos['tipo'], campos['vinculo'])
        return render_template('lgpd_solicitacao.html', protocolo=protocolo, prazo=contexto['prazo'],
                               email=campos['email'])
    return render_template('lgpd_solicitacao.html', campos={}, vinculos=LGPD_VINCULOS, tipos=LGPD_TIPOS,
                           prazo=LGPD_PRAZO_RESPOSTA)

@app.route("/lgpd/consulta", methods=['GET', 'POST'])
@log_required
@limiter.limit("20/day;10/hour;3/minute", methods=["POST"])
@exigir_turnstile('lgpd_consulta')
def lgpd_consulta():
    """Consulta da solicitação pelo protocolo e pelo e-mail usado no pedido: situação, prazo e resposta.
    A resposta registrada pela PRPI não contém dados pessoais (regra do painel)."""
    if request.method == 'POST':
        protocolo = str(request.form.get('protocolo', '')).strip().upper()
        email = str(request.form.get('email', '')).strip()
        linha = None
        if re.fullmatch(r"[A-Z0-9]{12}", protocolo) and email:
            resultado = executarSelect2("""SELECT protocolo, tipo, data, prazo, situacao, resposta, respondido_em
                FROM lgpd_solicitacoes WHERE protocolo=%s AND LOWER(email)=LOWER(%s)""",
                                        tipo=1, valores=(protocolo, email))
            if resultado is not None and resultado[1] > 0:
                linha = resultado[0]
        if linha is None:
            logger.info("[lgpd] Consulta de solicitação sem resultado")
            flash("Nenhuma solicitação encontrada com esse protocolo e e-mail.", 'error')
            return render_template('lgpd_consulta.html', protocolo=protocolo, email=email)
        logger.info("[lgpd] Consulta de solicitação: protocolo={}", protocolo)
        return render_template('lgpd_consulta.html', solicitacao=linha, tipos=LGPD_TIPOS, situacoes=LGPD_SITUACOES)
    return render_template('lgpd_consulta.html', protocolo=str(request.args.get('protocolo', ''))[:12], email='')

@app.route("/admin/lgpd/solicitacoes", methods=['GET'])
@login_required(role='admin')
@log_required
def lgpd_solicitacoes():
    """Solicitações dos titulares, com o prazo de resposta em destaque."""
    situacao = request.args.get('situacao', 'aberta')
    consulta = """SELECT id, protocolo, nome, email, vinculo, tipo, descricao, data, prazo, situacao,
        resposta, respondido_em, respondido_por, DATEDIFF(prazo, CURDATE()) AS dias_restantes
        FROM lgpd_solicitacoes"""
    if situacao in LGPD_SITUACOES:
        resultado = executarSelect2(consulta + " WHERE situacao=%s ORDER BY prazo, data", valores=(situacao,))
    else:
        situacao = 'todas'
        resultado = executarSelect2(consulta + " ORDER BY data DESC")
    linhas, total = resultado if resultado is not None else ([], 0)
    return render_template('lgpd_solicitacoes.html', linhas=linhas, total=total, situacao=situacao,
                           vinculos=LGPD_VINCULOS, tipos=LGPD_TIPOS, situacoes=LGPD_SITUACOES)

@app.route("/admin/lgpd/solicitacoes/<int:id_solicitacao>/responder", methods=['POST'])
@login_required(role='admin')
@log_required
def lgpd_solicitacao_responder(id_solicitacao):
    """Registra a resposta e a envia por e-mail ao titular; ela também aparece em /lgpd/consulta.
    Por isso a resposta não pode conter dados pessoais: esses só seguem após a confirmação da identidade."""
    resposta = str(request.form.get('resposta', '')).strip()
    if not resposta:
        flash("Descreva a resposta dada ao titular.", 'error')
        return redirect(url_for('lgpd_solicitacoes'))
    resultado = executarSelect2("SELECT protocolo, nome, email, tipo, situacao FROM lgpd_solicitacoes WHERE id=%s",
                                tipo=1, valores=(id_solicitacao,))
    if resultado is None or resultado[1] == 0 or resultado[0] is None:
        flash("Solicitação não encontrada.", 'error')
        return redirect(url_for('lgpd_solicitacoes'))
    protocolo, nome, email, tipo, situacao = resultado[0]
    if situacao == 'respondida':
        flash("Esta solicitação já foi respondida.", 'error')
        return redirect(url_for('lgpd_solicitacoes'))
    atualizar2("""UPDATE lgpd_solicitacoes SET situacao='respondida', resposta=%s, respondido_em=NOW(),
        respondido_por=%s WHERE id=%s AND situacao='aberta'""", valores=[resposta, session['username'], id_solicitacao])
    enviado = send_email_async(email, f"Plataforma Yoko - Resposta à solicitação LGPD {protocolo}",
                               render_template('email_lgpd_resposta.html', nome=nome, protocolo=protocolo,
                                               tipo=LGPD_TIPOS.get(tipo, tipo), resposta=resposta,
                                               link_consulta=LGPD_LINK_CONSULTA))
    logger.info("[lgpd] Solicitação {} respondida por {} (e-mail ao titular: {})",
                protocolo, session['username'], 'enfileirado' if enviado else 'FALHOU')
    if enviado:
        flash(f"Solicitação {protocolo} respondida. A resposta foi enviada para {email}.")
    else:
        flash(f"Solicitação {protocolo} marcada como respondida, mas o e-mail para {email} falhou. "
              "Envie a resposta manualmente; ela já aparece na consulta pelo protocolo.", 'error')
    return redirect(url_for('lgpd_solicitacoes'))

@app.route("/version")
def version():
    return jsonify({"version": __version__})

@app.route("/health")
@limiter.exempt
def health():
    if PRODUCAO != 1:
        return jsonify({"status": "disabled"}), 404

    status = {"database": "ok", "redis": "ok"}
    saudavel = True

    try:
        conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
        conn.close()
    except Exception as e:
        logger.warning("Healthcheck: falha na conexão com o banco de dados: {}", str(e))
        status["database"] = "error"
        saudavel = False

    try:
        app.config['SESSION_REDIS'].ping()
    except Exception as e:
        logger.warning("Healthcheck: falha na conexão com o Redis: {}", str(e))
        status["redis"] = "error"
        saudavel = False

    return jsonify(status), 200 if saudavel else 503

@app.route("/admin")
@login_required(role='admin')
@log_required
def admin():
    if (autenticado() and int(session['permissao'])==0):
        consulta = """SELECT id,nome FROM editais ORDER BY id"""
        editais,total = executarSelect(consulta)
        return render_template('index.html',editais=editais,versao=__version__)
    else:
        return render_template('login.html',mensagem="É necessário autenticação para acessar a página solicitada")

@app.route("/declaracao", methods=['GET', 'POST'])
@log_required
def declaracao():
    if request.method == "GET":
        if 'idProjeto' in request.args:
            if not numero_valido(str(request.args['idProjeto'])):
                return "ID do projeto inválido!"
            texto_declaracao = gerarDeclaracao(str(request.args['idProjeto']))
            data_agora = getData()
            try:
                options = {
                    'page-size': 'A4',
                    'margin-top': '20mm',
                    'margin-right': '20mm',
                    'margin-bottom': '20mm',
                    'margin-left': '20mm',
}
                return render_template('a4.html',texto=texto_declaracao,
                                       data=data_agora,identificador=texto_declaracao[7],raiz=ROOT_SITE)
            except Exception as e:
                logger.warning(e)
                logger.warning("Nao foi possivel gerar o PDF da declaração.")
                return "Erro ao gerar o PDF da declaração. Verifique os logs para mais detalhes."
        else:
            return "OK"

@app.route("/projetosAluno", methods=['POST'])
@log_required
@limiter.limit("30/day;10/hour;3/minute",methods=["POST"])
@exigir_turnstile('get_projetos_discente')
def projetos():
    try:
        projetosAluno,projetosAluno2019 = gerarProjetosPorAluno(str(request.form['txtNome']))
        return render_template('alunos.html',listaProjetos=projetosAluno,
                               lista2019=projetosAluno2019)
    except Exception as e:
        logger.warning(e)
        logger.warning("Nao foi possivel gerar os projetos do aluno.")
        return "Erro! Não utilize acentos ou caracteres especiais na busca."

@app.route("/autenticacao", methods=['POST'])
@log_required
def autenticar():
    if not numero_valido(str(request.form['tipo'])):
        return "Tipo de autenticação inválido!"
    if not token_valido(str(request.form['codigo'])):
        return "Código de autenticação inválido!"
    tipo = int(request.form['tipo'])
    codigo = str(request.form['codigo'])
    if tipo==0:
        return redirect("/pesquisa/orientadorDeclaracao?idProjeto=" + codigo)
    else:
        return redirect("/pesquisa/declaracao?idProjeto=" + codigo)

@app.route("/verificarDeclaracao", methods=['GET', 'POST'])
@log_required
def verificarDeclaracao():
    if request.method == 'GET':
        return render_template('verificar_declaracao.html', resultado=None, tipo=None, dados=None, erro=None)
    id_doc = str(request.form.get('id_projeto', '')).strip()
    codigo = str(request.form.get('codigo', '')).strip().lower()
    if not numero_valido(id_doc):
        return render_template('verificar_declaracao.html', resultado='invalido', tipo=None, dados=None, erro="ID do documento inválido.")
    if not re.match(r'^[0-9a-f]{64}$', codigo):
        return render_template('verificar_declaracao.html', resultado='invalido', tipo=None, dados=None, erro="Código de autenticação inválido.")
    # Busca como projeto (orientador / avaliador)
    consulta_proj = """SELECT DISTINCT
        UPPER(editalProjeto.nome),
        editalProjeto.siape,
        editalProjeto.titulo,
        DATE_FORMAT(editalProjeto.inicio,'%d/%m/%Y') as inicio,
        DATE_FORMAT(editalProjeto.fim,'%d/%m/%Y') as fim,
        COALESCE((SELECT GROUP_CONCAT(indicacoes.nome ORDER BY indicacoes.nome SEPARATOR ', ')
                  FROM indicacoes WHERE indicacoes.idProjeto=editalProjeto.id
                  GROUP BY indicacoes.idProjeto), 'N/A') as indicados,
        editalProjeto.id
        FROM editalProjeto WHERE editalProjeto.id=%s"""
    resultado_proj, _ = executarSelect2(consulta_proj, tipo=0, valores=(id_doc,))
    if resultado_proj:
        linha = resultado_proj[0]
        for prefixo in ('declaracao_orientador', 'declaracao_avaliador'):
            if verificar_codigo_auth(id_doc, linha[2], codigo, prefixo):
                return render_template('verificar_declaracao.html', resultado='valido', tipo='projeto', dados=linha, erro=None)
    # Busca como indicação (discente)
    consulta_disc = f"""SELECT
        indicacoes.nome,
        {sql_decifra('cpf', 'indicacoes')},
        UPPER(editalProjeto.titulo),
        DATE_FORMAT(indicacoes.inicio,'%d/%m/%Y'),
        DATE_FORMAT(indicacoes.fim,'%d/%m/%Y'),
        UPPER(editalProjeto.nome),
        indicacoes.id
        FROM indicacoes, editalProjeto
        WHERE indicacoes.idProjeto = editalProjeto.id AND indicacoes.id=%s"""
    resultado_disc, _ = executarSelect2(consulta_disc, tipo=0, valores=(AES_KEY, id_doc))
    if resultado_disc:
        # Página pública: o CPF aparece mascarado (LGPD, necessidade)
        linha_disc = (resultado_disc[0][0], mascarar_cpf(resultado_disc[0][1])) + tuple(resultado_disc[0][2:])
        if verificar_codigo_auth(id_doc, linha_disc[2], codigo, 'declaracao_discente'):
            return render_template('verificar_declaracao.html', resultado='valido', tipo='discente', dados=linha_disc, erro=None)
    return render_template('verificar_declaracao.html', resultado='invalido', tipo=None, dados=None, erro="Código inválido. Este documento pode não ter sido emitido pelo sistema.")

@app.route("/projetosPorOrientador", methods=['POST'])
@log_required
def projetosOrientador():
    if not username_valido(str(request.form['txtSiape'])):
        return "SIAPE do orientador inválido!"
    projetos_por_orientador = gerarProjetosPorOrientador(str(request.form['txtSiape']))
    return render_template('projetos_orientador.html',listaProjetos=projetos_por_orientador)

@app.route("/orientadorDeclaracao", methods=['GET'])
@log_required
def declaracaoOrientador():
    if not numero_valido(str(request.args['idProjeto'])):
        return "ID do projeto inválido!"
    resultados = gerarDeclaracaoOrientador(str(request.args['idProjeto']))
    texto_declaracao = resultados[0]
    bolsistas = resultados[1]
    data_agora = getData()
    return render_template('orientador.html',texto=texto_declaracao,
                           data=data_agora,identificador=texto_declaracao[0],bolsistas=bolsistas)

def extrair_conteudo_xml_lattes(arquivo):
    """
    Extrai e valida o conteúdo XML de um arquivo de Currículo Lattes
    enviado em formato .xml ou .zip. Levanta ValueError em caso de
    arquivo inválido.
    """
    tmp_dir = tempfile.mkdtemp()
    try:
        extensao = os.path.splitext(arquivo.filename)[1].lower()
        caminho_xml = os.path.join(tmp_dir, 'curriculo.xml')

        if extensao == '.zip':
            caminho_zip = os.path.join(tmp_dir, 'curriculo.zip')
            arquivo.save(caminho_zip)
            if not zipfile.is_zipfile(caminho_zip):
                raise ValueError("Erro: o arquivo enviado não é um arquivo ZIP válido.")
            with zipfile.ZipFile(caminho_zip, 'r') as zip_ref:
                nomes_xml = [n for n in zip_ref.namelist() if n.lower().endswith('.xml')]
                if not nomes_xml:
                    raise ValueError("Erro: o arquivo ZIP não contém um arquivo XML.")
                zip_ref.extract(nomes_xml[0], tmp_dir)
            os.replace(os.path.join(tmp_dir, nomes_xml[0]), caminho_xml)
        elif extensao == '.xml':
            arquivo.save(caminho_xml)
        else:
            raise ValueError("Erro: o arquivo enviado deve ser um .xml ou .zip.")

        try:
            ET.parse(caminho_xml)
        except ET.ParseError:
            raise ValueError("Erro: o arquivo XML enviado não é válido.")

        with open(caminho_xml, "r", encoding="latin-1") as f:
            return f.read()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

@app.route("/cadastrarProjeto", methods=['GET', 'POST'])
@login_required(role='user')
@log_required
def cadastrarProjeto():
    if request.method == "POST":
        #CADASTRAR DADOS DO PROPONENTE
        tipo = int(request.form['tipo'])
        nome = obterColunaUnica('users','nome','username',session['username'])
        #nome = str(request.form['nome'])
        categoria_projeto = int(request.form['categoria_projeto'])
        siape = session['username']
        email = obterColunaUnica('users','email','username',session['username'])
        #email = str(request.form['email'])
        ua = str(request.form['ua'])
        area_capes = str(request.form['area_capes'])
        grande_area = str(request.form['grande_area'])
        grupo = str(request.form['grupo'])
        grupo = removerAspas(grupo)
        ods_projeto = str(request.form['ods_projeto'])
        inovacao = int(request.form['inovacao'])
        justificativa = ""
        if 'justificativa' in request.form:
            justificativa = str(request.form['justificativa'])
        else:
            justificativa = ""
        justificativa = removerAspas(justificativa)
        cpf = str(request.form.get('cpf',''))

        #ARQUIVOS ENVIADOS DIRETO AO S3 PELO NAVEGADOR: conferidos antes de gravar o projeto
        arquivos_diretos, erro_upload = uploads_diretos('submissoes', siape)
        if erro_upload:
            return erro_upload

        #DADOS PESSOAIS E BÁSICOS DO PROJETO
        consulta = """INSERT INTO editalProjeto 
        (categoria,tipo,nome,siape,email,ua,area_capes,grande_area,grupo,data,ods,inovacao,justificativa) 
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP(),%s,%s,%s)"""
        atualizar2(consulta, valores=[categoria_projeto,tipo,nome,siape,email,ua,area_capes,grande_area,grupo,ods_projeto,inovacao,justificativa])
        #RECUPERANDO O ID DO ÚLTIMO PROJETO CADASTRADO
        consulta_ultimo_id = """SELECT max(id) 
        FROM editalProjeto 
        WHERE siape = %s"""
        resultado, total = executarSelect2(consulta_ultimo_id, valores=[siape])
        if total > 0:
            ultimo_id = int(resultado[0][0])
        else:
            logger.warning("Não foi possível obter o ID do último projeto cadastrado.")
            return "ERRO INTERNO!"
        ultimo_id_str = "%03d" % (ultimo_id)

        #CADASTRAR DADOS DO PROJETO

        titulo = str(request.form['titulo'])
        titulo = removerAspas(titulo)
        validade = int(request.form['validade'])
        palavras_chave = str(request.form['palavras_chave'])
        palavras_chave = removerAspas(palavras_chave)
        descricao_resumida = str(request.form['descricao_resumida'])
        descricao_resumida = removerAspas(descricao_resumida)
        if 'numero_bolsas' in request.form:
            bolsas = int(request.form['numero_bolsas'])
        else:
            bolsas = 0
        transporte = str(request.form['transporte'])
        pesquisadores_vinculados = "N/A"
        if 'pesquisadores_vinculados' in request.form:
            pesquisadores_vinculados = str(request.form['pesquisadores_vinculados'])
        else:
            pesquisadores_vinculados = "N/A"
        autorizacoes = "N/A"
        autorizacoes_str = "N/A"
        if 'autorizacoes' in request.form:
            autorizacoes = request.form.getlist('autorizacoes')
            autorizacoes_str = ', '.join(autorizacoes)
        else:
            autorizacoes_str = "N/A"
        autorizacoes = autorizacoes_str
        consulta = """UPDATE editalProjeto 
        SET titulo= %s, validade= %s , palavras= %s , resumo= %s , bolsas= %s, pesquisadores_vinculados= %s, autorizacoes= %s WHERE id= %s """
        atualizar2(consulta, valores=[titulo,validade,palavras_chave,descricao_resumida,bolsas,pesquisadores_vinculados,autorizacoes,ultimo_id])
        consulta = "UPDATE editalProjeto SET transporte= %s WHERE id= %s"
        atualizar2(consulta, valores=[transporte,ultimo_id])
        inicio = str(request.form['inicio'])
        fim = str(request.form['fim'])
        consulta = "UPDATE editalProjeto SET inicio= %s WHERE id= %s "
        atualizar2(consulta, valores=[inicio,ultimo_id])
        consulta = "UPDATE editalProjeto SET fim= %s WHERE id= %s "
        atualizar2(consulta, valores=[fim,ultimo_id])
        codigo = id_generator()
        falhas_envio = []  # arquivos que não chegaram ao S3: a coluna não é gravada

        if ('arquivo_projeto' in request.files):
            arquivo_projeto = request.files['arquivo_projeto']
            if arquivo_projeto and allowed_file(arquivo_projeto.filename) :
                arquivo_projeto.filename = "projeto_" + ultimo_id_str + "_" + str(siape) + "_" + codigo + ".pdf"
                filename = secure_filename(arquivo_projeto.filename)
                if enviar_arquivo_s3(arquivo_projeto, 'submissoes', filename):
                    consulta = "UPDATE editalProjeto SET arquivo_projeto= %s WHERE id= %s "
                    atualizar2(consulta, valores=[filename,ultimo_id])
                else:
                    falhas_envio.append("arquivo_projeto")
            elif not allowed_file(arquivo_projeto.filename):
                return ("Arquivo de projeto não permitido")

        if ('arquivo_plano1' in request.files):

            arquivo_plano1 = request.files['arquivo_plano1']
            if arquivo_plano1 and allowed_file(arquivo_plano1.filename):
                arquivo_plano1.filename = "plano1_" + ultimo_id_str + "_" + str(siape) + "_" + codigo + ".pdf"
                filename = secure_filename(arquivo_plano1.filename)
                if enviar_arquivo_s3(arquivo_plano1, 'submissoes', filename):
                    consulta = "UPDATE editalProjeto SET arquivo_plano1= %s WHERE id= %s "
                    atualizar2(consulta, valores=[filename,ultimo_id])
                else:
                    falhas_envio.append("arquivo_plano1")
            elif not allowed_file(arquivo_plano1.filename):
                return ("Arquivo de plano 1 de trabalho não permitido")

        if ('arquivo_plano2' in request.files):
            arquivo_plano2 = request.files['arquivo_plano2']
            if arquivo_plano2 and allowed_file(arquivo_plano2.filename):
                arquivo_plano2.filename = "plano2_" + ultimo_id_str + "_" + str(siape) + "_" + codigo + ".pdf"
                filename = secure_filename(arquivo_plano2.filename)
                if enviar_arquivo_s3(arquivo_plano2, 'submissoes', filename):
                    consulta = "UPDATE editalProjeto SET arquivo_plano2= %s WHERE id= %s "
                    atualizar2(consulta, valores=[filename,ultimo_id])
                else:
                    falhas_envio.append("arquivo_plano2")
            elif not allowed_file(arquivo_plano2.filename):
                return ("Arquivo de plano 2 de trabalho não permitido")

        if ('arquivo_plano3' in request.files):
            arquivo_plano3 = request.files['arquivo_plano3']
            if arquivo_plano3.filename != '':
                if arquivo_plano3 and allowed_file(arquivo_plano3.filename):
                    arquivo_plano3.filename = "plano3_" + ultimo_id_str + "_" + str(siape) + "_" + codigo + ".pdf"
                    filename = secure_filename(arquivo_plano3.filename)
                    if enviar_arquivo_s3(arquivo_plano3, 'submissoes', filename):
                        consulta = "UPDATE editalProjeto SET arquivo_plano3= %s WHERE id= %s "
                        atualizar2(consulta, valores=[filename,ultimo_id])
                    else:
                        falhas_envio.append("arquivo_plano3")
                elif not allowed_file(arquivo_plano3.filename):
                        return ("Arquivo de plano 3 de trabalho não permitido")

        #ARQUIVO DE COMPROVANTES
        if ('arquivo_comprovantes' in request.files):
            arquivo_comprovantes = request.files['arquivo_comprovantes']
            if allowed_file(arquivo_comprovantes.filename):
                arquivo_comprovantes.filename = "Comprovantes_" + ultimo_id_str + "_" + str(siape) + "_" + codigo + ".pdf"
                filename = secure_filename(arquivo_comprovantes.filename)
                if enviar_arquivo_s3(arquivo_comprovantes, 'submissoes', filename):
                    consulta = "UPDATE editalProjeto SET arquivo_comprovantes= %s WHERE id= %s "
                    atualizar2(consulta, valores=[filename,ultimo_id])
                else:
                    falhas_envio.append("arquivo_comprovantes")

        #ARQUIVOS ENVIADOS DIRETO PELO NAVEGADOR (já conferidos; o campo vem de CAMPOS_UPLOAD_DIRETO)
        for campo, nome_arquivo in arquivos_diretos.items():
            atualizar2("UPDATE editalProjeto SET " + campo + "= %s WHERE id= %s", valores=[nome_arquivo, ultimo_id])

        #CADASTRAR AVALIADORES SUGERIDOS
        if 'avaliador1_email' in request.form:
            avaliador1_email = str(request.form['avaliador1_email'])
            if avaliador1_email!='':
                token = id_generator(40)
                consulta = "INSERT INTO avaliacoes (avaliador,token,idProjeto) VALUES (%s,%s,%s)"
                atualizar2(consulta, valores=[avaliador1_email,token,ultimo_id])

        if 'avaliador2_email' in request.form:
            avaliador2_email = str(request.form['avaliador2_email'])
            if avaliador2_email!='':
                token = id_generator(40)
                consulta = "INSERT INTO avaliacoes (avaliador,token,idProjeto) VALUES (%s,%s,%s)"
                atualizar2(consulta, valores=[avaliador2_email,token,ultimo_id])

        if 'avaliador3_email' in request.form:
            avaliador3_email = str(request.form['avaliador3_email'])
            if avaliador3_email!='':
                token = id_generator(40)
                consulta = "INSERT INTO avaliacoes (avaliador,token,idProjeto) VALUES (%s,%s,%s)"
                atualizar2(consulta, valores=[avaliador3_email,token,ultimo_id])
        #Incluir avaliador teste em caso de não inclusão
        if ('avaliador1_email' not in request.form and 'avaliador2_email' not in request.form and 'avaliador3_email' not in request.form):
            token = id_generator(40)
            consulta = """INSERT INTO avaliacoes (avaliador,token,idProjeto) VALUES ("TESTE@IGNORAR.COM", %s, %s)"""
            atualizar2(consulta, valores=[token, ultimo_id])
        elif avaliador1_email=="" and avaliador2_email=="" and avaliador3_email=="":
            token = id_generator(40)
            consulta = """INSERT INTO avaliacoes (avaliador,token,idProjeto) VALUES ("TESTE@IGNORAR.COM", %s, %s)"""
            atualizar2(consulta, valores=[token, ultimo_id])
        #CALCULANDO scorelattes
        dados = [email,nome,titulo,descricao_resumida]
        arquivo_lattes = request.files.get('arquivo_lattes')
        if cpf != '':
            t = threading.Thread(target=processarPontuacaoLattes,args=(cpf,area_capes,ultimo_id,dados,))
            t.start()
        elif arquivo_lattes is not None and arquivo_lattes.filename != '':
            try:
                conteudo_xml = extrair_conteudo_xml_lattes(arquivo_lattes)
            except ValueError as e:
                return str(e)
            t = threading.Thread(target=processarPontuacaoLattes2,args=(conteudo_xml,area_capes,ultimo_id,dados,))
            t.start()
        else:
            return "Erro: informe o CPF ou anexe o arquivo do Currículo Lattes (XML ou ZIP)."
        if falhas_envio:
            logger.error("[cadastrarProjeto] Projeto id={} sem os arquivos {}", ultimo_id, falhas_envio)
            return("Submissão registrada (projeto " + ultimo_id_str + "), MAS houve erro ao enviar os arquivos: "
                   + ", ".join(falhas_envio) + ". Entre em contato com a Coordenadoria de Pesquisa ("
                   + DEFAULT_SUPPORT + ") para enviá-los. NÃO faça uma nova submissão.")
        return("Submissão realizada com sucesso. ESTA PÁGINA JÁ PODE SER FECHADA COM SEGURANÇA.")
    else:
        editaisAbertos = getEditaisAbertos()
        session['PRODUCAO'] = PRODUCAO
        return render_template('cadastrarProjeto.html',abertos=editaisAbertos)

@app.route("/scorelattes", methods=['GET'])
@log_required
def calcularScorelattesFromID():
    return (render_template('scorelattes.html'))

def verificarLattesOnline():
    """
    Invoca a Lambda sci01-online, que testa a disponibilidade do serviço
    de score Lattes, e retorna True/False conforme o resultado.
    """
    try:
        resposta = lambda_client.invoke(
            FunctionName='sci01-online',
            InvocationType='RequestResponse',
            Payload=json.dumps({})
        )
        resposta_bytes = resposta['Payload'].read().decode('utf-8')
        return bool(json.loads(resposta_bytes))
    except Exception as e:
        logger.warning("Erro ao verificar status do serviço de score Lattes: {}", str(e))
        return False

@app.route("/statusLattes", methods=['GET'])
@limiter.limit("50/day;25/hour;5/minute",methods=["POST"])
@log_required
def statusLattes():
    return jsonify({"online": verificarLattesOnline()})

@app.route("/score", methods=['POST'])
@log_required
@limiter.limit("30/day;15/hour;5/minute",methods=["POST"])
def getScoreLattesFromFile():
    area_capes = str(request.form['area_capes'])
    cpf = str(request.form['cpf'])
    periodo = str(request.form['periodo'])
    url_sumario = URL_LAMBDA + cpf + "/" + area_capes + "/" + periodo + "/" + "1"
    sumario = "{}"
    try:
        sumario = requests.get(url_sumario, auth=aws_auth(), timeout=120).text
    except Exception as e:
        logger.warning(e)
        logger.warning("Erro ao obter sumário do Lattes. Verifique se o CPF, a área CAPES e o período estão corretos.")
        return "Erro ao obter sumário do Lattes. Falha na comunicação com o CNPq."
    return (sumario)

def obter_score_lattes(xml_content: str, ano_inicio: int, ano_fim: int, area_capes: str, tipo: str = "resumida"):
    """
    Invoca a Lambda calcular-score-lattes de forma síncrona.
    :param xml_content: Conteúdo do arquivo XML em string
    :param ano_inicio: Ano inicial do cálculo
    :param ano_fim: Ano final do cálculo
    :param area_capes: Área CAPES (ex: 'COMPUTACAO')
    :param tipo: 'resumida', 'detalhada' ou 'html'
    :return: dict com o resultado retornado pela função
    """
    # Monta a estrutura que o lambda_handler espera
    payload_interno = {
        "xml_content": xml_content,
        "ano_inicio": ano_inicio,
        "ano_fim": ano_fim,
        "area_capes": area_capes,
        "tipo": tipo
    }
    
    payload = {
        "body": json.dumps(payload_interno)
    }

    # Invoca a função via AWS API (síncrono: RequestResponse)
    resposta = lambda_client.invoke(
        FunctionName='calcular-score-lattes',
        InvocationType='RequestResponse',
        Payload=json.dumps(payload)
    )

    # Lê a resposta bruta da Lambda
    resposta_bytes = resposta['Payload'].read().decode('utf-8')
    dados_resposta = json.loads(resposta_bytes)

    status_code = dados_resposta.get('statusCode')
    corpo = dados_resposta.get('body')

    # Se for JSON, decodifica para dicionário Python
    if dados_resposta.get('headers', {}).get('Content-Type', '').startswith('application/json'):
        corpo = json.loads(corpo)

    if status_code != 200:
        raise Exception(f"Erro na Lambda ({status_code}): {corpo}")

    return corpo

@app.route("/score2", methods=['POST'])
@log_required
@limiter.limit("30/day;15/hour;5/minute",methods=["POST"])
@exigir_turnstile('calcularScorelattesFromID')
def getScoreLattesFromFile2():
    area_capes = str(request.form['area_capes'])
    cpf = str(request.form['cpf'])
    periodo = str(request.form['periodo'])

    tmp_dir = tempfile.gettempdir()
    caminho_xml = os.path.join(tmp_dir, 'curriculo.xml')

    arquivo = request.files.get('arquivo_lattes')
    if arquivo is not None and arquivo.filename != '':
        extensao = os.path.splitext(arquivo.filename)[1].lower()

        if extensao == '.zip':
            caminho_zip = os.path.join(tmp_dir, 'curriculo.zip')
            arquivo.save(caminho_zip)
            if not zipfile.is_zipfile(caminho_zip):
                os.remove(caminho_zip)
                return "Erro: o arquivo enviado não é um arquivo ZIP válido."
            try:
                with zipfile.ZipFile(caminho_zip, 'r') as zip_ref:
                    nomes_xml = [n for n in zip_ref.namelist() if n.lower().endswith('.xml')]
                    if not nomes_xml:
                        return "Erro: o arquivo ZIP não contém um arquivo XML."
                    zip_ref.extract(nomes_xml[0], tmp_dir)
            except zipfile.BadZipFile:
                return "Erro: o arquivo enviado não é um arquivo ZIP válido."
            finally:
                if os.path.exists(caminho_zip):
                    os.remove(caminho_zip)
            caminho_extraido = os.path.join(tmp_dir, nomes_xml[0])
            os.replace(caminho_extraido, caminho_xml)
        elif extensao == '.xml':
            arquivo.save(caminho_xml)
        else:
            return "Erro: o arquivo enviado deve ser um .xml ou .zip."

        try:
            ET.parse(caminho_xml)
        except ET.ParseError:
            os.remove(caminho_xml)
            return "Erro: o arquivo XML enviado não é válido."

        ano_fim = date.today().year
        ano_inicio = ano_fim - int(periodo)
        try:
            with open(caminho_xml, "r", encoding="latin-1") as f:
                conteudo_xml = f.read()
            resultado = obter_score_lattes(
                xml_content=conteudo_xml,
                ano_inicio=ano_inicio,
                ano_fim=ano_fim,
                area_capes=area_capes,
                tipo="html"
            )
        except Exception as e:
            logger.warning("Erro ao calcular o score Lattes a partir do arquivo enviado: {}", str(e))
            return "Erro ao calcular a pontuação a partir do arquivo enviado."
        finally:
            if os.path.exists(caminho_xml):
                os.remove(caminho_xml)
        if isinstance(resultado, str):
            return resultado
        return jsonify(resultado)

    url_sumario = URL_LAMBDA + cpf + "/" + area_capes + "/" + periodo + "/" + "1"
    sumario = "{}"
    try:
        sumario = requests.get(url_sumario, auth=aws_auth(), timeout=120).text
    except Exception as e:
        logger.warning(e)
        logger.warning("Erro ao obter sumário do Lattes. Verifique se o CPF, a área CAPES e o período estão corretos.")
        return "Erro ao obter sumário do Lattes. Falha na comunicação com o CNPq."
    return (sumario)

#Devolve os nomes dos arquivos do projeto e dos planos, caso existam
def getFiles(idProjeto):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    consulta = "SELECT arquivo_projeto,arquivo_plano1,arquivo_plano2 FROM editalProjeto WHERE id=%s"
    cursor.execute(consulta, (idProjeto,))
    linha = cursor.fetchone()
    conn.close()
    return(linha)

def naoEstaFinalizado(token):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    consulta = "SELECT finalizado FROM avaliacoes WHERE token=%s"
    cursor.execute(consulta, (token,))
    linha = cursor.fetchone()
    try:
        finalizado = int(linha[0])
    except Exception as e:
        return False
    conn.close()
    if finalizado==0:
        return True
    else:
        return False

def podeAvaliar(idProjeto):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    #consulta = "SELECT deadline_avaliacao,CURRENT_TIMESTAMP() FROM editais WHERE CURRENT_TIMESTAMP()<deadline_avaliacao AND id=" + codigoEdital
    consulta = "SELECT e.id as codigoEdital,e.deadline_avaliacao,p.id FROM editais e, editalProjeto p WHERE p.tipo=e.id and deadline_avaliacao>CURRENT_TIMESTAMP() AND p.id=%s"
    cursor.execute(consulta, (idProjeto,))
    total = cursor.rowcount
    conn.close()
    if (total==0): #Edital com avaliacoes encerradas
        return(False)
    else: #Edital com avaliacoes em andamento
        return(True)

@app.route("/avaliacao", methods=['GET', 'POST'])
@log_required
def getPaginaAvaliacao():
    """
    Página de avaliação de projetos.

    Esta página é acessada pelos avaliadores para avaliar os projetos.
    Ela recebe o ID do projeto e o token de avaliação via GET.
    Se o ID do projeto for válido e o token de avaliação for válido,
    a página exibe os links para os arquivos do projeto e permite que o avaliador
    envie sua avaliação.
    """
    if request.method == "GET":
        try:
            idProjeto = str(request.args.get('id'))
        except Exception as e:
            logger.warning("[/avaliacao] Erro ao obter ID do projeto: {}",str(e))
            return "ID do projeto não informado!"
        if not numero_valido(idProjeto):
            logger.warning("[/avaliacao] ID do projeto inválido!")
            return "ID do projeto inválido!"
        if podeAvaliar(idProjeto): #Se ainda está no prazo para receber avaliações
            try:
                tokenAvaliacao = request.args.get('token')
                if tokenAvaliacao is None or tokenAvaliacao == "":
                    raise ValueError("Token de avaliação não informado!")
                else:
                    tokenAvaliacao = str(tokenAvaliacao)
            except Exception as e:
                logger.warning("[/avaliacao] Erro ao obter token de avaliação: {}", str(e))
                return "Token de avaliação não informado!"
            if not token_valido(tokenAvaliacao):
                return "Token de avaliação inválido!"
            arquivos = getFiles(idProjeto)
            if str(arquivos[0])!="0":
                link_projeto = link_arquivo_avaliador(str(arquivos[0]))
            if str(arquivos[1])!="0":
                link_plano1 = link_arquivo_avaliador(str(arquivos[1]))
            if str(arquivos[2])!="0":
                link_plano2 = link_arquivo_avaliador(str(arquivos[2]))
            links = ""
            if 'link_projeto' in locals():
                links = links + "<a href=\"" + link_projeto + "\" target=\"_blank\">PROJETO</a><BR>"
            if 'link_plano1' in locals():
                links = links + "<a href=\"" + link_plano1 + "\" target=\"_blank\">PLANO DE TRABALHO 1</a><BR>"
            if 'link_plano2' in locals():
                links = links + "<a href=\"" + link_plano2 + "\" target=\"_blank\">PLANO DE TRABALHO 2</a><BR>"
            links = links + "<input type=\"hidden\" id=\"token\" name=\"token\" value=\"" + tokenAvaliacao + "\">"
            if naoEstaFinalizado(tokenAvaliacao):
                consulta = "UPDATE avaliacoes SET aceitou=1 WHERE token=%s"
                atualizar2(consulta, valores=(tokenAvaliacao,))
                idProjeto = obterColunaUnica_str("avaliacoes","idProjeto","token",tokenAvaliacao)
                edital = obterColunaUnica("editalProjeto","tipo","id",idProjeto)
                modalidade = int(obterColunaUnica("editais","modalidade","id",edital))
                logger.info("[{}][/avaliacao] Avaliador abriu formulário de avaliação do projeto {}.", request.remote_addr,str(idProjeto))
                return render_template('avaliacao.html',arquivos=links,modalidade=modalidade)
            else:
                return("Projeto já foi avaliado! Não é possível modificar a avaliação!")
        else:
            return "ID Inválido ou prazo de avaliação expirado!"
    else:
        logger.warning("[/avaliacao] Método não permitido: {} !",request.method)
        return "Método não permitido! Use GET para acessar esta página."

@app.route("/avaliar", methods=['GET', 'POST'])
@log_required
def enviarAvaliacao():
    """
    Grava a avaliação do avaliador no banco de dados.
    """
    if request.method == "POST":
        comentarios = str(request.form['txtComentarios'])
        recomendacao = str(request.form['txtRecomendacao'])
        nome_avaliador = str(request.form['txtNome'])
        token = str(request.form['token'])
        idProjeto = obterColunaUnica_str("avaliacoes","idProjeto","token",token)
        edital = obterColunaUnica("editalProjeto","tipo","id",idProjeto)
        modalidade = int(obterColunaUnica("editais","modalidade","id",edital))
        c1 = str(request.form['c1'])
        c2 = str(request.form['c2'])
        c3 = str(request.form['c3'])
        c4 = str(request.form['c4'])
        c5 = str(request.form['c5'])
        c6 = str(request.form['c6'])
        c7 = str(request.form['c7'])
        comite = str(request.form['comite'])
        try:
            consulta = "UPDATE avaliacoes SET recomendacao= %s WHERE token= %s "
            atualizar2(consulta, valores=[recomendacao,token])
            consulta = "UPDATE avaliacoes SET finalizado=1 WHERE token= %s "
            atualizar2(consulta, valores=[token])
            consulta = "UPDATE avaliacoes SET data_avaliacao=CURRENT_TIMESTAMP() WHERE token= %s "
            atualizar2(consulta, valores=[token])
            consulta = "UPDATE avaliacoes SET nome_avaliador= %s WHERE token= %s"
            atualizar2(consulta, valores=[nome_avaliador,token])
            comentarios = comentarios.replace('"',' ')
            comentarios = comentarios.replace("'"," ")
            consulta = "UPDATE avaliacoes SET comentario= %s WHERE token= %s "
            atualizar2(consulta, valores=[comentarios,token])
            consulta = "UPDATE avaliacoes SET c1= %s WHERE token= %s "
            atualizar2(consulta, valores=[c1,token])
            consulta = "UPDATE avaliacoes SET c2= %s WHERE token= %s "
            atualizar2(consulta, valores=[c2,token])
            consulta = "UPDATE avaliacoes SET c3= %s WHERE token= %s "
            atualizar2(consulta, valores=[c3,token])
            consulta = "UPDATE avaliacoes SET c4= %s WHERE token= %s "
            atualizar2(consulta, valores=[c4,token])
            consulta = "UPDATE avaliacoes SET c5= %s WHERE token= %s "
            atualizar2(consulta, valores=[c5,token])
            consulta = "UPDATE avaliacoes SET c6= %s WHERE token= %s "
            atualizar2(consulta, valores=[c6,token])
            consulta = "UPDATE avaliacoes SET c7= %s WHERE token= %s "
            atualizar2(consulta, valores=[c7,token])
            consulta = "UPDATE avaliacoes SET cepa= %s WHERE token= %s "
            atualizar2(consulta, valores=[comite,token])
            logger.info("[{}][/avaliar] Avaliação do projeto {} gravada com sucesso por {}", request.remote_addr,str(idProjeto),str(nome_avaliador))
            if modalidade==2:
                inovacao = str(request.form['inovacao'])
                consulta = "UPDATE avaliacoes SET inovacao= %s WHERE token= %s "
                atualizar2(consulta, valores=[inovacao,token])
        except Exception as e:
            logger.warning("[AVALIACAO] ERRO ao gravar a avaliação: {} - ({})", token, str(e))
            return("Não foi possível gravar a avaliação. Favor entrar contactar " + DEFAULT_SUPPORT)
        try:
            return (redirect(url_for('getDeclaracaoAvaliador',tokenAvaliacao=token)))
        except Exception as e:
            logger.warning("[/avaliar] ERRO ao gerar a declaração: {} - ({})",token, str(e))
            return("Não foi possível gerar a declaração.")
    else:
        return("OK")

def descricaoEdital(codigoEdital):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    consulta = "SELECT id,nome FROM editais WHERE id=%s"
    cursor.execute(consulta, (codigoEdital,))
    linhas = cursor.fetchall()
    nomeEdital = "EDITAL NAO DEFINIDO"
    for linha in linhas:
        nomeEdital = str(linha[1])
    conn.close()
    return (nomeEdital)

def enviar_declaracao_avaliador(url,destinatario):
    with app.app_context():
        texto_email = render_template('email_declaracao_avaliador.html',url=url)
        if send_email_async(destinatario, "Plataforma Yoko - DECLARAÇÃO DE AVALIAÇÃO DE PROJETO DE PESQUISA", texto_email):
            logger.info("E-mail enfileirado com sucesso para o avaliador: {}", calcula_hash(destinatario))
        else:
            logger.warning("Erro ao enfileirar e-mail. [enviar declaração para avaliador]: {}", calcula_hash(destinatario))

@app.route("/declaracaoAvaliador/<tokenAvaliacao>", methods=['GET'])
@log_required
def getDeclaracaoAvaliador(tokenAvaliacao):
    """
    Gera a declaração de avaliação do avaliador via Lambda Overlay.
    """
    if not token_valido(tokenAvaliacao):
        logger.warning("[/declaracaoAvaliador] Token inválido: {}", tokenAvaliacao)
        return "Token inválido!"

    consulta = """
    SELECT nome_avaliador,idProjeto,avaliador FROM avaliacoes WHERE token=%s
    AND finalizado=1
    """
    linhas = consultar(consulta, (tokenAvaliacao,))
    nome_avaliador = "NAO INFORMADO"
    idProjeto = 0
    destinatario = None

    for linha in linhas:
        nome_avaliador = str(linha[0])
        idProjeto = str(linha[1])
        destinatario = str(linha[2])

    if idProjeto != 0 and idProjeto != "0":
        titulo = str(obterColunaUnica("editalProjeto", "titulo", "id", idProjeto))
        codigo_do_edital = str(obterColunaUnica("editalProjeto", "tipo", "id", idProjeto))
        descricao_do_edital = str(obterColunaUnica("editais", "nome", "id", codigo_do_edital))
        data_agora = getData()
        identificador = gerar_codigo_auth(idProjeto, titulo, 'declaracao_avaliador')

        if destinatario:
            url = url_for('getDeclaracaoAvaliador', tokenAvaliacao=tokenAvaliacao, _external=True)
            enviar_declaracao_avaliador(url, destinatario)

        try:
            # Montagem do texto idêntica ao declaracao_avaliador.html
            corpo = (
                f"Declaramos, para os devidos fins, que <b>{nome_avaliador}</b> participou, como consultor "
                f"<i>ad hoc</i>, da avaliação do projeto de pesquisa <b>\"#{idProjeto}\"</b>, "
                f"referente ao <b>\"{descricao_do_edital}\"</b>, do Programa Institucional de Iniciação Científica "
                f"e Tecnológica (PIICT) da Universidade Federal do Cariri (UFCA)."
            )

            return invocar_declaracao_overlay(
                corpo_html=corpo,
                data_extenso=data_agora,
                rotulo_id="ID do Projeto",
                id_ref=idProjeto,
                identificador=identificador,
                nome_arquivo_download=f"declaracao_avaliador_{idProjeto}.pdf",
                tipo_documento="DECLARAÇÃO"
            )

        except Exception as e:
            with logger.contextualize(ip=request.remote_addr, rota=request.path, erro=str(e), classe_erro=type(e).__name__):
                logger.warning("Erro ao gerar declaração de avaliador: {}", str(e))
            return "Erro ao gerar declaração. Tente novamente mais tarde."

    else:
        return "PROJETO AINDA NÃO AVALIADO OU INEXISTENTE!"
    
def consultar(consulta, valores=()):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    if valores==():
        cursor.execute(consulta)
    else:
        cursor.execute(consulta, tuple(valores))
    linhas = cursor.fetchall()
    conn.close()
    return (linhas)

@app.route("/recusarConvite", methods=['GET', 'POST'])
@log_required
def recusarConvite():
    if request.method == "GET":
        tokenAvaliacao = str(request.args.get('token'))
        if not token_valido(tokenAvaliacao):
            logger.warning("[/recusarConvite] Token inválido: {}", tokenAvaliacao)
            return "Token inválido!"
        consulta = "UPDATE avaliacoes SET aceitou=0 WHERE token=%s"
        atualizar2(consulta, valores=(tokenAvaliacao,))
        return("Avaliação cancelada com sucesso. Agradecemos a atenção.")
    else:
        return("OK")

@app.route("/admin/avaliacoesNegadas", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def avaliacoesNegadas():
    if request.method == "GET":
        conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
        conn.select_db(MYSQL_DATABASE)
        cursor  = conn.cursor()
        if 'edital' in request.args:
            codigoEdital = str(request.args.get('edital'))
            if not numero_valido(codigoEdital):
                logger.warning("[/avaliacoesNegadas] Código do edital inválido: {}", codigoEdital)
                return "Código do edital inválido!"
            if 'id' in request.args:
                idProjeto = str(request.args.get('id'))
                if not numero_valido(idProjeto):
                    logger.warning("[/avaliacoesNegadas] ID do projeto inválido: {}", idProjeto)
                    return "ID do projeto inválido!"
                consulta = "SELECT resumoGeralAvaliacoes.id,CONCAT(SUBSTRING(resumoGeralAvaliacoes.titulo,1,80),\" - (\",resumoGeralAvaliacoes.nome,\" )\"),(resumoGeralAvaliacoes.aceites+resumoGeralAvaliacoes.rejeicoes) as resultado,resumoGeralAvaliacoes.indefinido FROM resumoGeralAvaliacoes WHERE ((aceites+rejeicoes<10) OR (aceites=rejeicoes)) AND tipo=%s AND id = %s ORDER BY aceites+rejeicoes, id"
                parametros_consulta = (codigoEdital, idProjeto)
            else:
                consulta = "SELECT resumoGeralAvaliacoes.id,CONCAT(SUBSTRING(resumoGeralAvaliacoes.titulo,1,80),\" - (\",resumoGeralAvaliacoes.nome,\" )\"),(resumoGeralAvaliacoes.aceites+resumoGeralAvaliacoes.rejeicoes) as resultado,resumoGeralAvaliacoes.indefinido FROM resumoGeralAvaliacoes WHERE ((aceites+rejeicoes<2) OR (aceites=rejeicoes)) AND tipo=%s ORDER BY aceites+rejeicoes, id"
                parametros_consulta = (codigoEdital,)
            try:
                cursor.execute(consulta, parametros_consulta)
                linha = cursor.fetchall()
                total = cursor.rowcount
                conn.close()
                consulta_verificacao = """
                    SELECT avaliador,aceitou,finalizado,DATE_FORMAT(data_avaliacao,'%d/%m/%Y'),id from avaliacoes WHERE idProjeto = %s
                    ORDER BY aceitou DESC, finalizado DESC
                """
                avaliadores, totalAvaliadores = executarSelect2(consulta_verificacao,valores=[idProjeto])
                return(render_template('inserirAvaliador.html',listaProjetos=linha,totalDeLinhas=total,codigoEdital=codigoEdital,avaliadores=avaliadores))
            except Exception as e:
                logger.warning(e)
                logger.warning(consulta)
                conn.close()
                return(consulta)
        else:
            return ("OK")
    else:
        return("OK")

@app.route("/admin/inserirAvaliador", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def inserirAvaliador():
    """
    Atribuir avaliador a um projeto
    """
    if request.method == "POST":
        token = id_generator(40)
        idProjeto = int(request.form['txtProjeto'])
        avaliador1_email = str(request.form['txtEmail']).strip().rstrip('.')
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s.]+$', avaliador1_email):
            return("E-mail inválido.")
        consulta_verificacao = """
            SELECT avaliador from avaliacoes WHERE idProjeto = %s AND avaliador = %s 
        """
        linhas, total = executarSelect2(consulta_verificacao,valores=[idProjeto, avaliador1_email])
        if total > 0: #Já existe este avaliador para este projeto
            return("Avaliador já cadastrado para este projeto.")
        consulta = "INSERT INTO avaliacoes (aceitou,avaliador,token,idProjeto) VALUES (-1, %s, %s, %s)"
        atualizar2(consulta, valores=[avaliador1_email, token, str(idProjeto)])
        enviarPedidoAvaliacao(idProjeto)
        return_url = request.referrer or url_for('avaliacoesNegadas')
        return redirect(return_url)
    else:
        return("OK")

@app.route("/admin/excluirAvaliador", methods=['POST'])
@login_required(role='admin')
@log_required
def excluirAvaliador():
    id_avaliacao = str(request.form.get('id_avaliacao', '')).strip()
    if not numero_valido(id_avaliacao):
        logger.warning("[{}][/excluirAvaliador] ID inválido: {}", request.remote_addr, id_avaliacao)
        return "ID inválido."
    atualizar2("DELETE FROM avaliacoes WHERE id = %s", valores=[id_avaliacao])
    logger.info("[{}][/excluirAvaliador] Avaliação id={} excluída.", request.remote_addr, id_avaliacao)
    return_url = request.referrer or url_for('avaliacoesNegadas')
    return redirect(return_url)

#Retorna a quantidade de linhas da consulta
def quantidades(consulta, valores=()):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    if valores==():
        cursor.execute(consulta)
    else:
        cursor.execute(consulta, tuple(valores))
    total = cursor.rowcount
    conn.close()
    return (total)

@app.route("/admin/estatisticas", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def estatisticas():
    if request.method == "GET":
        try:
            codigoEdital = str(request.args.get('edital'))
        except Exception as e:
            logger.warning("[/estatisticas] Erro ao obter código do edital: {}", str(e))
            return "Código do edital não informado!"
        if not numero_valido(codigoEdital):
            return "Código do edital inválido!"
        #Resumo Geral
        consulta = "SELECT * FROM resumoGeralAvaliacoes WHERE tipo=%s ORDER BY ua, score DESC"
        conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
        conn.select_db(MYSQL_DATABASE)
        cursor  = conn.cursor()
        cursor.execute(consulta, (codigoEdital,))
        resumoGeral = cursor.fetchall()
        consulta = "SELECT * FROM resumoGeralAvaliacoes WHERE aceites>=2 AND aceites>rejeicoes AND tipo=%s ORDER BY ua, score DESC"
        cursor.execute(consulta, (codigoEdital,))
        aprovados = cursor.fetchall()
        consulta = "SELECT * FROM resumoGeralAvaliacoes WHERE ((aceites+rejeicoes<2) OR (aceites=rejeicoes)) AND tipo=%s ORDER BY ua, score DESC"
        cursor.execute(consulta, (codigoEdital,))
        pendentes = cursor.fetchall()
        consulta = "SELECT * FROM resumoGeralAvaliacoes WHERE rejeicoes>=2 AND rejeicoes>aceites AND tipo=%s ORDER BY ua, score DESC"
        cursor.execute(consulta, (codigoEdital,))
        reprovados = cursor.fetchall()
        consulta = "SELECT nome FROM editais WHERE id=%s"
        cursor.execute(consulta, (codigoEdital,))
        nomeEdital = cursor.fetchall()
        edital = ""
        if cursor.rowcount==1:
            for linha in nomeEdital:
                edital = linha[0]
        else:
            edital="CÓDIGO DE EDITAL INVÁLIDO"
        conn.close()
        return(render_template('estatisticas.html',nomeEdital=edital,linhasResumo=resumoGeral,projetosAprovados=aprovados,projetosPendentes=pendentes,projetosReprovados=reprovados))
        #return(codigoEdital)
    else:
        return("OK")

def cotaEstourada(codigoEdital,siape):
    if (codigoEdital=='1'): #Situação particular do edital 01: Checar os que tem 2 bolsas no edital 02/2018/CNPQ/UFCA
        consulta = "SELECT ua,nome,siape FROM resumoGeralClassificacao WHERE tipo=%s AND bolsas>0 AND siape=%s AND siape IN (SELECT siape FROM edital02_2018 WHERE situacao=\"ATIVO\" and modalidade=\"PIBIC\" GROUP BY siape HAVING count(id)=2 ORDER BY orientador) ORDER BY nome"
        total = quantidades(consulta, (codigoEdital, siape))
        if (total>0):
            return (True)
        else:
            return (False)
    else:
        return (False)

def distribuir_bolsas(demanda,codigoEdital):
    ## TODO: Incluir condição de cruzamento de dados
    '''
    Lista de quem tem 2 bolsas PIBIC, e não pode ganhar mais nenhuma bolsa!
    SELECT tipo,id,titulo,ua,nome FROM resumoGeralClassificacao WHERE resumoGeralClassificacao.tipo=1 AND resumoGeralClassificacao.siape IN (SELECT siape FROM edital02_2018 WHERE situacao="ATIVO" and modalidade="PIBIC" GROUP BY siape HAVING count(id)=2 ORDER BY ua,orientador)

    BOLSAS PIBIC POR ORIENTADOR
    SELECT siape,orientador,count(id),situacao FROM edital02_2018 WHERE situacao="ATIVO" and modalidade="PIBIC" GROUP BY siape HAVING count(id)=2 ORDER BY orientador;

    QUEM TEM BOLSA CONCEDIDA, MAS NÃO PODE TER!
    SELECT id,ua,nome,siape FROM resumoGeralClassificacao WHERE tipo=1 AND bolsas_concedidas>=1 AND siape IN (SELECT siape FROM resumoGeralClassificacao WHERE resumoGeralClassificacao.tipo=1 AND resumoGeralClassificacao.siape IN (SELECT siape FROM edital02_2018 WHERE situacao="ATIVO" and modalidade="PIBIC" GROUP BY siape HAVING count(id)=2 ORDER BY ua,orientador)) ORDER BY ua,nome

    '''
    #Iniciando a distribuição de bolsas
    consulta = "SELECT * FROM resumoGeralClassificacao WHERE tipo=%s ORDER BY ua, score DESC"
    linhas,total = executarSelect2(consulta,valores=(codigoEdital,))
    linhas = list(linhas)
    dados = []
    for linha in linhas:
        dados.append(list(linha))
    for i in (0,1):
        for linha in dados:
            ua = str(linha[3]) #Unidade Academica
            idProjeto = linha[1] #ID do projeto
            solicitadas = int(linha[10]) #Quantidade de bolsas solicitadas
            concedidas = int(linha[11]) #Quantidade de bolsas concedidas
            siape = str((linha[12]))  #Siape
            codigoEdital = str(linha[0]) #Codigo do Edital
            if (demanda[ua]>0): #Se a unidade ainda possui bolsas disponíveis
                if (solicitadas-concedidas)>0: #Se ainda existe demanda a ser atendida
                    if(not cotaEstourada(codigoEdital,siape)): #Se o orientador não estiver com a cota individual estourada
                        consulta = "UPDATE editalProjeto SET bolsas_concedidas=bolsas_concedidas+1 WHERE id=%s"
                        atualizar2(consulta, valores=(idProjeto,))
                        demanda[ua] = demanda[ua] - 1
                        linha[11] = str(int(linha[11]) + 1)
                        consulta = "UPDATE editalProjeto SET obs=\"BOLSA CONCEDIDA\" WHERE id=%s"
                        atualizar2(consulta, valores=(idProjeto,))
                    else: #Se o orientador estiver com a cota estourada
                        consulta = "UPDATE editalProjeto SET obs=\"BOLSA NÃO CONCEDIDA. ORIENTADOR NÃO PODE ULTRASSAR A COTA DE 2 BOLSISTAS POR MODALIDADE (Anexo XIV da Res. 01/2014/CONSUP, Art. 7 Inciso I)\" WHERE id=%s"
                        atualizar2(consulta, valores=(idProjeto,))
            else: # se a unidade não tem mais bolsas disponíveis em sua cota
                if concedidas>0: #Se o projeto já foi contemplado com bolsas
                    consulta = "UPDATE editalProjeto SET obs=\"CONCESSÃO PARCIAL. COTA DA UNIDADE ZERADA (Anexo XIV da Res. 01/2014/CONSUP, Art. 7 Inciso II)\" WHERE id=%s"
                else: #Se o projeto não foi contemplado com bolsas
                    consulta = "UPDATE editalProjeto SET obs=\"BOLSA NÃO CONCEDIDA. COTA DA UNIDADE ZERADA (Anexo XIV da Res. 01/2014/CONSUP, Art. 7 Inciso II)\" WHERE id=%s"
                atualizar2(consulta, valores=(idProjeto,))
        
def executarSelect(consulta,tipo=0):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    try:
        cursor.execute(consulta)
        total = cursor.rowcount
        if (tipo==0): #Retorna todas as linhas
            resultado = cursor.fetchall()
        else: #Retorna uma única linha
            resultado = cursor.fetchone()
        return (resultado,total)
    except Exception as e:
        logger.warning("ERRO Na função executarSelect: {}", str(e))
    finally:
        cursor.close()
        conn.close()

def executarSelect2(consulta,tipo=0,valores=()):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    try:
        if valores==():
            cursor.execute(consulta)
        else:
            cursor.execute(consulta,tuple(valores))
        total = cursor.rowcount
        if tipo==0: #Retorna todas as linhas
            resultado = cursor.fetchall()
        else: #Retorna uma única linha
            resultado = cursor.fetchone()
        return (resultado,total)
    except Exception as e:
        logger.warning("ERRO Na função executarSelect2: {}", str(e))
    finally:
        cursor.close()
        conn.close()

def avaliacoesEncerradas(codigoEdital):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    consulta = "SELECT deadline_avaliacao,CURRENT_TIMESTAMP() FROM editais WHERE CURRENT_TIMESTAMP()<deadline_avaliacao AND id=%s"
    cursor.execute(consulta, (codigoEdital,))
    total = cursor.rowcount
    conn.close()
    if (total>0): #Edital com avaliacoes encerradas
        return(False)
    else: #Edital com avaliacoes em andamento
        return(True)

@app.route("/admin/resultados", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def resultados():
    if request.method == "GET":
        #Recuperando o código do edital
        try:
            codigoEdital = str(request.args.get('edital'))
        except Exception as e:
            return "Código do edital não informado!"
        if not numero_valido(codigoEdital):
            return "Código do edital inválido!"
        #Recuperando o Resumo Geral
        consulta = "SELECT * FROM resumoGeralClassificacao WHERE tipo=%s ORDER BY ua, score DESC"
        conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
        conn.select_db(MYSQL_DATABASE)
        cursor  = conn.cursor()
        cursor.execute(consulta, (codigoEdital,))
        total = cursor.rowcount
        resumoGeral = cursor.fetchall()

        #Recuperando dados do edital
        consulta = "SELECT nome,deadline_avaliacao,quantidade_bolsas,mensagem,recursos,link FROM editais WHERE id=%s"
        cursor.execute(consulta, (codigoEdital,))
        nomeEdital = cursor.fetchall()
        edital = ""
        data_final_avaliacoes = ""
        qtde_bolsas = 0
        mensagem = ""
        recursos = ""
        link = ""
        if cursor.rowcount==1:
            for linha in nomeEdital:
                edital = str(linha[0])
                data_final_avaliacoes = str(linha[1])
                qtde_bolsas = int(linha[2])
                mensagem = str(linha[3])
                recursos = str(linha[4])
                link = str(linha[5])
        else:
            edital="CÓDIGO DE EDITAL INVÁLIDO"
        qtde_bolsas = str(qtde_bolsas)

        #Recuperando total de projetos: total_projetos e calculando total de bolsas por unidade
        total_projetos = str(quantidades("SELECT id FROM resumoGeralClassificacao WHERE tipo=%s", (codigoEdital,)))
        # bolsas_disponiveis é uma expressão SQL montada a partir de valores numéricos já validados/computados
        # internamente (não vêm diretamente de entrada do usuário), por isso é seguro concatená-la à consulta.
        bolsas_disponiveis = "floor((count(id)/" + total_projetos + ")*" + qtde_bolsas + ") "

        #Recuperando a demanda e oferta de Bolsas
        consulta = "SELECT ua,count(id)," + bolsas_disponiveis +  "as total_bolsas FROM editalProjeto WHERE valendo=1 AND tipo=%s GROUP BY ua"
        cursor.execute(consulta, (codigoEdital,))
        demanda = cursor.fetchall()

        #ZERANDO as concessões
        consulta = "UPDATE editalProjeto SET bolsas_concedidas=0 WHERE tipo=%s"
        atualizar2(consulta, valores=(codigoEdital,))

        #Recalculando resumoGeral
        consulta = "SELECT * FROM resumoGeralClassificacao WHERE tipo=%s ORDER BY ua, score DESC"
        resumoGeral,total = executarSelect2(consulta, valores=(codigoEdital,))

        #Distribuição de cota de bolsas
        unidades = {}
        for linha in demanda:
            unidades[str(linha[0])] = int(linha[2])
        distribuir_bolsas(unidades,codigoEdital)

        ## TODO: Redistribuir bolsas remanescentes baseado na classificação geral pelo lattes

        #Recalculando resumoGeral após distribuição
        consulta = "SELECT * FROM resumoGeralClassificacao WHERE tipo=%s ORDER BY ua, score DESC"
        resumoGeral,total = executarSelect2(consulta, valores=(codigoEdital,))

        #Total de bolsas distribuídas por unidade academica
        consulta = "SELECT ua,sum(bolsas) as solicitadas, sum(bolsas_concedidas) as concedidas,(sum(bolsas_concedidas)/sum(bolsas))*100 as percentual FROM resumoGeralClassificacao WHERE tipo=%s GROUP BY ua ORDER BY ua"
        cursor.execute(consulta, (codigoEdital,))
        somatorios = cursor.fetchall()
        app.logger.debug(consulta)

        #Verificando se as avaliacoes estão encerradas
        if avaliacoesEncerradas(codigoEdital):
            titulo = "Resultado Preliminar"
        else:
            titulo = "Resultado Parcial"

        #Calculando estatísticas de avaliações
        estatisticas = []
        consultaPorUnidade = "SELECT editalProjeto.ua,avg((TIMESTAMPDIFF(DAY,data_envio,data_avaliacao))) as media, min((TIMESTAMPDIFF(DAY,data_envio,data_avaliacao))) as minimo, max((TIMESTAMPDIFF(DAY,data_envio,data_avaliacao))) as maximo  FROM avaliacoes,editalProjeto WHERE editalProjeto.id=avaliacoes.idProjeto AND finalizado=1 AND editalProjeto.tipo=%s GROUP BY editalProjeto.ua ORDER BY editalProjeto.ua"
        consultaPorTotal = "SELECT avg((TIMESTAMPDIFF(DAY,data_envio,data_avaliacao))) as media, min((TIMESTAMPDIFF(DAY,data_envio,data_avaliacao))) as minimo, max((TIMESTAMPDIFF(DAY,data_envio,data_avaliacao))) as maximo  FROM avaliacoes,editalProjeto WHERE editalProjeto.id=avaliacoes.idProjeto AND finalizado=1 AND editalProjeto.tipo=%s"
        porUnidade,qtde = executarSelect2(consultaPorUnidade, valores=(codigoEdital,))
        porTotal,qtde = executarSelect2(consultaPorTotal, valores=(codigoEdital,))

        consultaAvaliacoesTotais = """SELECT
        (SELECT count(avaliacoes.id) FROM avaliacoes,editalProjeto WHERE finalizado=1 and editalProjeto.id=avaliacoes.idProjeto and editalProjeto.tipo=%s) as finalizados,
        (SELECT count(avaliacoes.id) FROM avaliacoes,editalProjeto WHERE finalizado=0 and aceitou=1 and editalProjeto.id=avaliacoes.idProjeto and editalProjeto.tipo=%s) as indefinidos,
        (SELECT count(avaliacoes.id) FROM avaliacoes,editalProjeto WHERE finalizado=0 and aceitou=0 and editalProjeto.id=avaliacoes.idProjeto and editalProjeto.tipo=%s) as negadas,
        (SELECT count(avaliacoes.id) FROM avaliacoes,editalProjeto WHERE editalProjeto.id=avaliacoes.idProjeto and editalProjeto.tipo=%s) as total
        FROM avaliacoes,editalProjeto WHERE editalProjeto.id=avaliacoes.idProjeto and editalProjeto.tipo=%s LIMIT 1"""
        avaliacoesTotais,qtde = executarSelect2(consultaAvaliacoesTotais, valores=(codigoEdital,codigoEdital,codigoEdital,codigoEdital,codigoEdital))
        retorno = (1,2,3,4)
        for avaliacoes in avaliacoesTotais:
            retorno = avaliacoes
        #Projetos novos e em andamento
        projetosNovos = quantidades("SELECT id FROM editalProjeto WHERE valendo=1 and categoria=1 AND tipo=%s", (codigoEdital,))
        projetosEmAndamento = quantidades("SELECT id FROM editalProjeto WHERE valendo=1 and categoria=0 AND tipo=%s", (codigoEdital,))
        #Finalizando...
        conn.close()
        data_agora = getData()
        return(render_template('resultados.html',projetosNovos=projetosNovos,projetosEmAndamento=projetosEmAndamento,avaliacoes=retorno,porUnidade=porUnidade,porTotal=porTotal,link=link,mensagem=mensagem,recursos=recursos,nomeEdital=edital,linhasResumo=resumoGeral,totalGeral=total,demanda=demanda,bolsas=qtde_bolsas,somatorios=somatorios,titulo=titulo,data=data_agora))
    else:
        return("OK")

def obterColunaUnica(tabela,coluna,colunaId,valorId):
    '''
    Retorna uma coluna de uma linha única dado uma chave primária

    tabela, coluna e colunaId são sempre identificadores fixos definidos no código;
    apenas valorId (que pode vir de entrada do usuário) é passado como parâmetro
    vinculado, para evitar SQL Injection.
    '''
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    consulta = "SELECT " + coluna + " FROM " + tabela + " WHERE " + colunaId + "=%s"
    resultado = "0"
    try:
        cursor.execute(consulta, (valorId,))
        linhas = cursor.fetchall()
        for linha in linhas:
            resultado = str(linha[0])
        return(resultado)
    except Exception as e:
        logger.warning("ERRO Na função obtercolunaUnica: {}", str(e))
    finally:
        cursor.close()
        conn.close()

def obterColunaUnica_str(tabela,coluna,colunaId,valorId):
    '''
    tabela, coluna e colunaId são sempre identificadores fixos definidos no código;
    apenas valorId (que pode vir de entrada do usuário) é passado como parâmetro
    vinculado, para evitar SQL Injection.
    '''
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    consulta = "SELECT " + coluna + " FROM " + tabela + " WHERE " + colunaId + "=%s"
    resultado = "0"
    try:
        cursor.execute(consulta, (valorId,))
        linhas = cursor.fetchall()
        for linha in linhas:
            resultado = str(linha[0])
        return(resultado)
    except:
        e = sys.exc_info()[0]
        logger.warning(e)
        logger.warning("ERRO Na função obtercolunaUnica. Ver consulta abaixo.")
        logger.warning(consulta)
    finally:
        cursor.close()
        conn.close()

@app.route("/admin/editalProjeto", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def editalProjeto():
    if not (autenticado() and int(session.get('permissao', -1)) == 0):
        return render_template('login.html', mensagem="É necessário autenticação para acessar a página solicitada")

    if request.method != "GET":
        return "OK"

    # Recuperando o código do edital
    if 'edital' not in request.args:
        return "OK"

    codigoEdital = str(request.args.get('edital'))
    session['edital'] = codigoEdital

    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
    conn.select_db(MYSQL_DATABASE)
    cursor = conn.cursor()

    try:
        tipo_classificacao = int(obterColunaUnica("editais", "classificacao", "id", codigoEdital))
        
        # ORDENA DE ACORDO COM O TIPO DE CLASSIFICAÇÃO: 1 - POR UA; 2 - POR LATTES
        if tipo_classificacao == 1:
            consulta = (
                "SELECT id,tipo,categoria,nome,email,ua,scorelattes,titulo,arquivo_projeto,"
                "arquivo_plano1,arquivo_plano2,arquivo_lattes_pdf,arquivo_comprovantes,"
                "DATE_FORMAT(data,\"%d/%m/%Y - %H:%i\") as data,DATE_FORMAT(inicio,\"%d/%m/%Y\") as inicio,"
                "DATE_FORMAT(fim,\"%d/%m/%Y\") as fim,"
                "if(produtividade=0,\"PROD. CNPq\",if(produtividade=1,\"BPI FUNCAP\",\"NORMAL\")) as prioridade,"
                "bolsas,bolsas_concedidas,obs,arquivo_plano3 "
                "FROM editalProjeto WHERE tipo=%s AND valendo=1 "
                "ORDER BY ua,produtividade,scorelattes DESC,nome"
            )
        else:
            consulta = (
                "SELECT id,tipo,categoria,nome,email,ua,scorelattes,titulo,arquivo_projeto,"
                "arquivo_plano1,arquivo_plano2,arquivo_lattes_pdf,arquivo_comprovantes,"
                "DATE_FORMAT(data,\"%d/%m/%Y - %H:%i\") as data,DATE_FORMAT(inicio,\"%d/%m/%Y\") as inicio,"
                "DATE_FORMAT(fim,\"%d/%m/%Y\") as fim,"
                "if(produtividade=0,\"PROD. CNPq\",if(produtividade=1,\"BPI FUNCAP\",\"NORMAL\")) as prioridade,"
                "bolsas,bolsas_concedidas,obs,arquivo_plano3 "
                "FROM editalProjeto WHERE tipo=%s AND valendo=1 "
                "ORDER BY produtividade,scorelattes DESC,nome"
            )

        consulta_novos = """
        SELECT editalProjeto.id,
        nome,
        ua,
        titulo,
        arquivo_projeto,
        IFNULL(GROUP_CONCAT(avaliacoes.avaliador ORDER BY avaliador SEPARATOR '<BR>'),"SEM AVALIADORES") as avaliadores,
        GROUP_CONCAT(IF(avaliacoes.recomendacao=1,'RECOMENDADO',IF(avaliacoes.recomendacao=0,'***NÃO RECOMENDADO***','EM AVALIAÇÃO')) ORDER BY avaliador SEPARATOR '<BR>') as recomendacoes, 
        IFNULL(GROUP_CONCAT(avaliacoes.enviado ORDER BY avaliador SEPARATOR '<BR>'),0) as enviado,
        GROUP_CONCAT(IF(avaliacoes.aceitou=1,'ACEITOU',IF(avaliacoes.aceitou=0,'REJEITOU','NÃO RESPONDEU')) ORDER BY avaliador SEPARATOR '<BR>') as aceitou,
        IFNULL(sum(avaliacoes.finalizado),0) as finalizados,
        IFNULL(sum(if(recomendacao=-1,1,0)),0), 
        sum(if(recomendacao=0,1,0)),
        sum(if(recomendacao=1,1,0)),palavras,
        IFNULL(sum(avaliacoes.inovacao),0) as inovacao
        FROM editalProjeto
        LEFT JOIN avaliacoes ON editalProjeto.id=avaliacoes.idProjeto
        WHERE tipo=%s
        AND valendo=1 AND categoria=1
        GROUP BY editalProjeto.id
        ORDER BY finalizados,editalProjeto.ua,editalProjeto.id
        """

        modalidade = int(obterColunaUnica("editais", "modalidade", "id", codigoEdital))
        demanda = """SELECT ua,count(id) FROM editalProjeto WHERE valendo=1 and tipo=%s GROUP BY ua ORDER BY ua"""
        bolsas_ufca = int(obterColunaUnica("editais", "quantidade_bolsas", "id", codigoEdital))
        bolsas_cnpq = int(obterColunaUnica("editais", "quantidade_bolsas_cnpq", "id", codigoEdital))

        cursor.execute(consulta, (codigoEdital,))
        total = cursor.rowcount
        linhas = cursor.fetchall()
        descricao = descricaoEdital(codigoEdital)

        cursor.execute(consulta_novos, (codigoEdital,))
        total_novos = cursor.rowcount
        linhas_novos = cursor.fetchall()

        cursor.execute(demanda, (codigoEdital,))
        linhas_demanda = cursor.fetchall()

        if 'resultado' in request.args:
            mensagem = str(obterColunaUnica("editais", "mensagem", "id", codigoEdital))
            
            # Geração do relatório em PDF via ReportLab Platypus
            if 'pdf' in request.args:
                pdf_bytes = gerar_pdf_resultado_edital(
                    descricao=descricao,
                    mensagem=mensagem,
                    lista_projetos=linhas,
                    total=total
                )
                return send_file(
                    io.BytesIO(pdf_bytes),
                    mimetype='application/pdf',
                    as_attachment=False,
                    download_name=f"resultado_edital_{codigoEdital}.pdf"
                )

            return render_template(
                'editalProjeto.html',
                listaProjetos=linhas,
                descricao=descricao,
                total=total,
                novos=linhas_novos,
                total_novos=total_novos,
                linhas_demanda=linhas_demanda,
                bolsas_ufca=bolsas_ufca,
                bolsas_cnpq=bolsas_cnpq,
                codigoEdital=codigoEdital,
                resultado=1,
                mensagem=mensagem,
                modalidade=modalidade
            )
        else:
            return render_template(
                'editalProjeto.html',
                listaProjetos=linhas,
                descricao=descricao,
                total=total,
                novos=linhas_novos,
                total_novos=total_novos,
                linhas_demanda=linhas_demanda,
                bolsas_ufca=bolsas_ufca,
                bolsas_cnpq=bolsas_cnpq,
                codigoEdital=codigoEdital,
                resultado=0,
                modalidade=modalidade
            )

    except Exception as e:
        logger.warning(f"ERRO Na função /editalProjeto: {e}")
        logger.warning(consulta_novos)
        return "ERRO!"
    finally:
        cursor.close()
        conn.close()

@app.route("/lattesDetalhado", methods=['GET', 'POST'])
@log_required
def lattesDetalhado():
    if request.method == "GET":
        #Recuperando o código do projeto
        if 'id' in request.args:
            idProjeto = str(request.args.get('id'))
            conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
            conn.select_db(MYSQL_DATABASE)
            cursor  = conn.cursor()
            consulta = "SELECT id,scorelattes_detalhado FROM editalProjeto WHERE id=%s AND valendo=1"
            cursor.execute(consulta, (idProjeto,))
            linhas = cursor.fetchall()
            texto = "INDISPONIVEL"
            for linha in linhas:
                lattes_detalhado = str(linha[1])
                if lattes_detalhado!="":
                    texto = lattes_detalhado
            conn.close()
            return(texto)
        else:
            return ("OK")


@app.route("/declaracoesPorServidor", methods=['GET', 'POST'])
@log_required
def declaracoesServidor():
    if request.method == "POST":
        if 'txtSiape' in request.form:
            siape = str(request.form['txtSiape'])
            consulta = ""
            try:
                consulta = "SELECT id,nome,evento,modalidade FROM declaracoes WHERE siape=%s"
                declaracoes,total = executarSelect2(consulta,valores=(siape,))
                return(render_template('declaracoes_servidor.html',listaDeclaracoes=declaracoes))
            except:
                e = sys.exc_info()[0]
                logger.warning(e)
                logger.warning("ERRO Na função /declaracoesPorServidor. Ver consulta abaixo.")
                logger.warning(consulta)
                return("ERRO!")
        else:
            return("OK")
    else:
        return("OK")

@app.route("/declaracaoEvento", methods=['GET', 'POST'])
@log_required
def declaracaoEvento():
    if request.method == "GET":
        #Recuperando o código da declaração
        if 'id' in request.args:
            idDeclaracao = str(request.args.get('id'))
            consulta = "SELECT nome,siape,participacao,evento,modalidade,periodo,local FROM declaracoes WHERE id=%s"
            linhas,total = executarSelect2(consulta,valores=(idDeclaracao,))
            if (total>0):
                texto = linhas[0]
                data_agora = getData()
                return(render_template('declaracao_evento.html',texto=texto,data=data_agora,identificador=idDeclaracao))
            else:
                return("Nenhuma declaração encontrada.")
        else:
            return ("OK")

@app.route("/meusProjetos", methods=['GET', 'POST'])
@login_required(role='user')
@log_required
def meusProjetos():
    if 'siape' in request.args and 'senha' in request.args:
            siape = str(request.args.get('siape'))
            senha = str(request.args.get('senha'))
            if verify_password(siape,senha):
                registrar_acesso(request.remote_addr,siape)
    if autenticado():        
        consulta = """SELECT id,nome_do_coordenador,orientador_lotacao,titulo_do_projeto,DATE_FORMAT(inicio,'%d/%m/%Y') as inicio,DATE_FORMAT(termino,'%d/%m/%Y') as fim,estudante_nome_completo,token FROM cadastro_geral WHERE siape=%s ORDER BY inicio,titulo_do_projeto"""
        projetos,total = executarSelect2(consulta,valores=(str(session['username']),))
        consulta_outros = """SELECT 
        editalProjeto.id,
        editais.nome,
        editalProjeto.nome,
        ua,
        titulo,
        DATE_FORMAT(inicio,'%d/%m/%Y') as inicio,
        DATE_FORMAT(fim,'%d/%m/%Y') as fim,
        categoria,
        arquivo_projeto,
        (SELECT COUNT(recomendacao) FROM `avaliacoes` WHERE finalizado=1 AND recomendacao=1 AND idProjeto=editalProjeto.id) as aprovados,
        (SELECT COUNT(recomendacao) FROM `avaliacoes` WHERE finalizado=1 AND recomendacao=0 AND idProjeto=editalProjeto.id) as reprovados,
        bolsas,
        bolsas_concedidas,
        categoria,
        editais.situacao,
        editais.id,
        (SELECT GROUP_CONCAT(CONCAT('(',id,') - ',nome,' (',IF(tipo_de_vaga=0,'VOLUNTARIO(A)','BOLSISTA'),')',' (',IF(situacao=0,'OK',IF(situacao=1,'DESLIGADO(A)','SUBSTITUIDO(A)')), ')') ORDER BY nome SEPARATOR '<BR><BR>') FROM indicacoes WHERE idProjeto=editalProjeto.id GROUP BY idProjeto) as orientandos,
        arquivo_plano3
         FROM editalProjeto,editais WHERE valendo=1 AND editalProjeto.tipo=editais.id AND siape=%s ORDER BY editalProjeto.data """
        projetos2019,total2019 = executarSelect2(consulta_outros,valores=(str(session['username']),))

        consulta_orientandos_atuais = """SELECT indicacoes.id,indicacoes.nome,DATE_FORMAT(indicacoes.inicio,'%d/%m/%Y'),IF(indicacoes.fomento=0,'UFCA',IF(indicacoes.fomento=1,'CNPq','FUNCAP')),IF(indicacoes.tipo_de_vaga=0,'VOLUNTÁRIO','BOLSISTA'),DATE_FORMAT(indicacoes.fim,'%d/%m/%Y'),IF(indicacoes.modalidade=1,'PIBIC',IF(indicacoes.modalidade=2,'PIBITI',IF(indicacoes.modalidade=3,'PIBIC-EM','PIBIC-AF'))),
        (SELECT GROUP_CONCAT(CONCAT_WS('/',mes,ano) SEPARATOR '<BR><BR>') FROM frequencias WHERE frequencias.idIndicacao=indicacoes.id) as enviadas, editalProjeto.titulo
        FROM indicacoes,editalProjeto
        WHERE editalProjeto.id=indicacoes.idProjeto AND indicacoes.fim>NOW() AND editalProjeto.siape=%s ORDER BY indicacoes.tipo_de_vaga,editalProjeto.titulo,indicacoes.nome """
        orientandos_atuais,totalOrientandos = executarSelect2(consulta_orientandos_atuais,valores=(str(session['username']),))

        consulta_orientandos_antigos = """SELECT indicacoes.id,indicacoes.nome,DATE_FORMAT(indicacoes.inicio,'%d/%m/%Y'),IF(indicacoes.fomento=0,'UFCA',IF(indicacoes.fomento=1,'CNPq','FUNCAP')),IF(indicacoes.tipo_de_vaga=0,'VOLUNTÁRIO','BOLSISTA'),DATE_FORMAT(indicacoes.fim,'%d/%m/%Y'),IF(indicacoes.modalidade=1,'PIBIC',IF(indicacoes.modalidade=2,'PIBITI',IF(indicacoes.modalidade=3,'PIBIC-EM','PIBIC-AF'))),
        (SELECT GROUP_CONCAT(CONCAT_WS('/',mes,ano) SEPARATOR '<BR><BR>') FROM frequencias WHERE frequencias.idIndicacao=indicacoes.id) as enviadas, editalProjeto.titulo
        FROM indicacoes,editalProjeto
        WHERE editalProjeto.id=indicacoes.idProjeto AND indicacoes.fim<NOW() AND editalProjeto.siape=%s ORDER BY indicacoes.tipo_de_vaga,editalProjeto.titulo,indicacoes.nome """
        orientandos_antigos,totalOrientandosAntigos = executarSelect2(consulta_orientandos_antigos,valores=(str(session['username']),))

        return(render_template('meusProjetos.html',projetos=projetos,total=total,projetos2019=projetos2019,total2019=total2019,permissao=session['permissao'],orientandos=orientandos_atuais,orientandos_antigos=orientandos_antigos))
    else:
        return(render_template('login.html',mensagem="É necessário autenticação para acessar a página solicitada"))

def invocar_declaracao_overlay(corpo_html, data_extenso, rotulo_id, id_ref, identificador, nome_arquivo_download, tipo_documento="DECLARAÇÃO"):
    payload = {
        "corpo_html": corpo_html,
        "data": f"Juazeiro do Norte, {data_extenso}",
        "rotulo_id": rotulo_id,
        "id_referencia": str(id_ref),
        "identificador": identificador,
        "url_validacao": "https://aws.yokoapps.com.br/pesquisa/verificarDeclaracao"
    }

    response = lambda_client.invoke(
        FunctionName='gerar-declaracao-overlay',
        InvocationType='RequestResponse',
        Payload=json.dumps(payload)
    )

    response_data = json.loads(response['Payload'].read().decode('utf-8'))

    if response_data.get('statusCode') != 200:
        detalhe = response_data.get('body', {})
        raise RuntimeError(f"Erro no serviço de declaração: {detalhe}")

    pdf_bytes = base64.b64decode(response_data['body'])
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=False,
        download_name=nome_arquivo_download
    )

@app.route("/minhaDeclaracaoOrientador", methods=['GET', 'POST'])
@log_required
def minhaDeclaracao():
    if not autenticado():
        return render_template('login.html', mensagem="É necessário autenticação para acessar a página solicitada")

    if request.method != "GET":
        return "OK"

    data_agora = getData()

    # Cenário 1: Busca por token
    if 'token' in request.args:
        token = str(request.args.get('token'))
        consulta = """SELECT 
            nome_do_coordenador,
            siape,
            titulo_do_projeto,
            DATE_FORMAT(estudante_inicio,'%d/%m/%Y') as inicio,
            DATE_FORMAT(estudante_fim,'%d/%m/%Y') as fim,
            estudante_nome_completo,
            token,
            if(estudante_fim<NOW(),"exerceu","exerce") as verbo
            FROM cadastro_geral WHERE token=%s ORDER BY inicio,titulo_do_projeto"""
        projeto, total = executarSelect2(consulta, tipo=1, valores=(token,))
        
        if total != 1:
            return "declaração inexistente!"

        identificador = gerar_codigo_auth(token, projeto[2])
        nome_arquivo = f"declaracao_{token}.pdf"
        id_referencia = token
        rotulo_id = "Token do Documento"

    # Cenário 2: Busca por ID do Projeto
    elif 'id' in request.args:
        idProjeto = str(request.args.get('id'))
        consulta = """SELECT DISTINCT 
            UPPER(editalProjeto.nome),
            editalProjeto.siape,
            UPPER(editalProjeto.titulo),
            DATE_FORMAT(editalProjeto.inicio,'%d/%m/%Y') as inicio,
            DATE_FORMAT(editalProjeto.fim,'%d/%m/%Y') as fim,
            (SELECT GROUP_CONCAT(indicacoes.nome,' (',year(indicacoes.inicio),'/',year(indicacoes.fim),') ' 
            ORDER BY indicacoes.nome SEPARATOR ', ') from indicacoes 
            WHERE indicacoes.idProjeto=editalProjeto.id GROUP BY indicacoes.idProjeto) as indicados,
            editalProjeto.id,
            if(editalProjeto.fim<NOW(),"exerceu","exerce") as verbo,
            UPPER(editalProjeto.pesquisadores_vinculados) as pesquisadores_vinculados
            FROM editalProjeto,indicacoes
            WHERE editalProjeto.id=indicacoes.idProjeto AND editalProjeto.id=%s ORDER BY fim DESC"""
        projeto, total = executarSelect2(consulta, tipo=1, valores=(idProjeto,))
        
        if total <= 0:
            return "declaracao inexistente..."

        identificador = gerar_codigo_auth(idProjeto, projeto[2])
        nome_arquivo = f"declaracao_projeto_{idProjeto}.pdf"
        id_referencia = str(idProjeto)
        rotulo_id = "ID do Projeto"

    # Cenário 3: Busca por ID do Aluno
    elif 'idAluno' in request.args:
        idAluno = str(request.args.get('idAluno'))
        idProjeto = obterColunaUnica("indicacoes", "idProjeto", "id", idAluno)
        consulta = """SELECT DISTINCT editalProjeto.nome,editalProjeto.siape,editalProjeto.titulo,
            DATE_FORMAT(indicacoes.inicio,'%d/%m/%Y') as inicio,DATE_FORMAT(indicacoes.fim,'%d/%m/%Y') as fim,
            indicacoes.nome as indicados,
            editalProjeto.id,if(indicacoes.fim<NOW(),"exerceu","exerce") as verbo
            FROM editalProjeto,indicacoes
            WHERE editalProjeto.id=indicacoes.idProjeto AND indicacoes.id=%s ORDER BY fim DESC"""
        projeto, total = executarSelect2(consulta, tipo=1, valores=(idAluno,))
        
        if total <= 0:
            return "declaracao inexistente..."

        identificador = gerar_codigo_auth(idProjeto, projeto[2])
        nome_arquivo = f"declaracao_aluno_{idAluno}.pdf"
        id_referencia = str(idProjeto)
        rotulo_id = "ID do Projeto"

    else:
        return "id nao informado"

    # Montagem do texto e chamada da função auxiliar
    try:
        pesquisadores = projeto[8] if len(projeto) > 8 and projeto[8] else "N/A"
        
        if "N/A" in str(pesquisadores) or not str(pesquisadores).strip():
            corpo = (
                f"Declaramos, para os devidos fins, que o(a) professor(a) <b>{projeto[0]}</b>, "
                f"SIAPE: <b>{projeto[1]}</b>, {projeto[7]} a função de <b>coordenador(a) do Projeto de Pesquisa</b> "
                f"intitulado <i>\"{projeto[2]}\"</i>, no período de <b>{projeto[3]} a {projeto[4]}</b>, "
                f"com orientação do(a)(s) bolsista(s): <i>{projeto[5]}</i>, no "
                f"Programa Institucional de Iniciação Científica e Tecnológica (PIICT)."
            )
        else:
            corpo = (
                f"Declaramos, para os devidos fins, que o(a) professor(a) <b>{projeto[0]}</b>, "
                f"SIAPE: <b>{projeto[1]}</b>, {projeto[7]} a função de <b>coordenador(a) do Projeto de Pesquisa</b> "
                f"intitulado <i>\"{projeto[2]}\"</i>, no período de <b>{projeto[3]} a {projeto[4]}</b>, "
                f"com orientação do(a)(s) bolsista(s): <i>{projeto[5]}</i>, no "
                f"Programa Institucional de Iniciação Científica e Tecnológica (PIICT), "
                f"com a participação dos(as) pesquisadores(as) {pesquisadores}."
            )

        return invocar_declaracao_overlay(
            corpo_html=corpo,
            data_extenso=data_agora,
            rotulo_id=rotulo_id,
            id_ref=id_referencia,
            identificador=identificador,
            nome_arquivo_download=nome_arquivo
        )

    except Exception as e:
        with logger.contextualize(ip=request.remote_addr, rota=request.path, erro=str(e), classe_erro=type(e).__name__):
            logger.warning("Erro ao gerar declaração: {}", str(e))
        return "Erro ao gerar declaração. Tente novamente mais tarde."

@app.route("/discente/minhaDeclaracao", methods=['GET', 'POST'])
@log_required
def minhaDeclaracaoDiscente():
    if request.method == "GET":
        # Recuperando o token da declaração
        if 'token' in request.args:
            token = str(request.args.get('token'))
            consulta = f"""SELECT estudante_nome_completo,{sql_decifra('cpf')},if(estudante_fim>NOW(),1,0) as verbo,estudante_modalidade,nome_do_coordenador,titulo_do_projeto,
                        ch_semanal,DATE_FORMAT(estudante_inicio,'%d/%m/%Y') as inicio,DATE_FORMAT(estudante_fim,'%d/%m/%Y') as final,id FROM cadastro_geral WHERE token=%s"""
            projeto, total = executarSelect2(consulta, tipo=1, valores=(AES_KEY, token))
            data_agora = getData()

            if total == 1:
                try:
                    identificador = gerar_codigo_auth(str(projeto[9]), projeto[5], 'declaracao_discente')

                    # Montagem da condicional do declaracao_discente.html
                    verbo = "é" if projeto[2] == 1 else "foi"
                    if projeto[2] == 1:
                        complemento = f"A participação do(a) discente em questão no referido Projeto de Pesquisa iniciou-se em {projeto[7]} e está em andamento."
                    else:
                        complemento = f"A participação do(a) discente em questão no referido Projeto de Pesquisa foi de {projeto[7]} a {projeto[8]}."

                    corpo = (
                        f"Declaramos, para os devidos fins, que <b>{projeto[0]}</b>, CPF: <b>{projeto[1]}</b>, "
                        f"{verbo} integrante do Programa Institucional de Bolsas de Iniciação Científica ({projeto[3]}), "
                        f"sob orientação do(a) professor(a) {projeto[4]}, com o projeto intitulado <i>\"{projeto[5]}\"</i>, "
                        f"desempenhando suas atividades com carga horária de {projeto[6]} horas semanais. {complemento}"
                    )

                    return invocar_declaracao_overlay(
                        corpo_html=corpo,
                        data_extenso=data_agora,
                        rotulo_id="ID da Indicação",
                        id_ref=projeto[9],
                        identificador=identificador,
                        nome_arquivo_download=f"declaracao_discente_{token}.pdf"
                    )

                except Exception as e:
                    with logger.contextualize(ip=request.remote_addr, rota=request.path, erro=str(e), classe_erro=type(e).__name__):
                        logger.warning("Erro ao gerar declaração: {}", str(e))
                    return "Erro ao gerar declaração. Tente novamente mais tarde."
            else:
                return "declaração inexistente!"
        else:
            return "OK"
    else:
        return "OK"

@app.route("/discente/meuCertificado2018", methods=['GET', 'POST'])
@log_required
def meuCertificado2018():
    if request.method == "GET":
        if 'token' in request.args:
            token = str(request.args.get('token'))
            consulta = f"""
            SELECT estudante_nome_completo,{sql_decifra('cpf')},estudante_tipo_de_vaga,estudante_modalidade,
            nome_do_coordenador,titulo_do_projeto,ch_semanal,DATE_FORMAT(estudante_inicio,'%d/%m/%Y'),
            DATE_FORMAT(estudante_fim,'%d/%m/%Y') ,
            ROUND((DATEDIFF(estudante_fim,estudante_inicio)/7)*ch_semanal) as ch_total
            FROM cadastro_geral WHERE token=%s"""
            consulta2 = """SELECT * from gestores ORDER BY id"""
            
            from datetime import datetime
            projeto, total = executarSelect2(consulta, tipo=1, valores=(AES_KEY, token))
            
            if total != 1:
                return "declaração inexistente!"

            gestores, total_gestores = executarSelect(consulta2)
            proreitor = gestores[0]
            coordenador = gestores[1]
            
            inicio = datetime.strptime(str(projeto[7]), '%d/%m/%Y')
            fim = datetime.strptime(str(projeto[8]), '%d/%m/%Y')
            agora = datetime.strptime(datetime.today().strftime("%d/%m/%Y"), '%d/%m/%Y')
            periodo = abs((fim - inicio).days)
            
            if periodo < 180:
                return 'Certificado indisponível. Período de bolsa inferior a 180 dias'
            
            if (fim - agora).days > 0:
                return 'Certificado disponível apenas após a conclusão do projeto em andamento: '

            data_agora = getData()

            try:
                # Monta o corpo idêntico ao certificado_discente_2018.html
                corpo = (
                    f"Certificamos que o(a) estudante <b>{projeto[0]}</b>, CPF: <b>{projeto[1]}</b> "
                    f"foi vinculado(a) ao Programa Institucional de Bolsas de Iniciação Científica e Tecnológica (PIICT) "
                    f"na condição de {projeto[2]}, modalidade {projeto[3]} sob orientação do(a) professor(a) "
                    f"<b>{projeto[4]}</b>, no projeto de pesquisa intitulado <b>\"{projeto[5]}\"</b>, "
                    f"desempenhando suas atividades com carga horária de {projeto[6]} horas semanais. "
                    f"A participação do(a) estudante no referido Projeto de Pesquisa se estendeu de {projeto[7]} a {projeto[8]}, "
                    f"contabilizando um total de {projeto[9]} horas."
                )

                return invocar_declaracao_overlay(
                    corpo_html=corpo,
                    data_extenso=data_agora,
                    rotulo_id="Token do Certificado",
                    id_ref=token,
                    identificador=token,
                    nome_arquivo_download=f"certificado_{token}.pdf",
                    tipo_documento="CERTIFICADO"
                )

            except Exception as e:
                with logger.contextualize(ip=request.remote_addr, rota=request.path, erro=str(e), classe_erro=type(e).__name__):
                    logger.warning("Erro ao gerar certificado: {}", str(e))
                return "Erro ao gerar declaração. Tente novamente mais tarde."
        else:
            return "OK"
    else:
        return "OK"

@app.route("/discente/meuCertificado", methods=['GET', 'POST'])
@log_required
def meuCertificado():
    if request.method == "GET":
        if 'id' in request.args:
            idIndicacao = str(request.args.get('id'))
            consulta = f"""SELECT i.nome,{sql_decifra('cpf', 'i')},
            IF(i.modalidade=1,'PIBIC',IF(i.modalidade=2,'PIBITI',IF(i.modalidade=3,'PIBIC-EM','PIBIC-AF'))) as modalidade,
            IF(i.tipo_de_vaga=1,'BOLSISTA','VOLUNTÁRIO') as vaga,
            e.nome,e.titulo,i.ch,DATE_FORMAT(i.inicio,'%d/%m/%Y') as inicio, DATE_FORMAT(i.fim,'%d/%m/%Y') as fim,
            ROUND((DATEDIFF(i.fim,i.inicio)/7)*i.ch) as ch_total
            FROM indicacoes i, editalProjeto e WHERE i.idProjeto=e.id and e.valendo=1 and i.id=%s"""
            consulta2 = """SELECT * from gestores ORDER BY id"""
            
            from datetime import datetime
            projeto, total = executarSelect2(consulta, tipo=1, valores=(AES_KEY, idIndicacao))
            
            if total != 1:
                return "declaração inexistente!"

            gestores, total_gestores = executarSelect(consulta2)
            proreitor = gestores[0]
            coordenador = gestores[1]
            
            inicio = datetime.strptime(str(projeto[7]), '%d/%m/%Y')
            fim = datetime.strptime(str(projeto[8]), '%d/%m/%Y')
            agora = datetime.strptime(datetime.today().strftime("%d/%m/%Y"), '%d/%m/%Y')
            periodo = abs((fim - inicio).days)
            
            if periodo < 180:
                return 'Certificado indisponível. Período de bolsa inferior a 180 dias'
            
            if (fim - agora).days > 0:
                return 'Certificado disponível apenas após a conclusão do projeto em andamento: '

            data_agora = getData()

            try:
                # Monta o corpo idêntico ao certificado_discente.html (vaga no índice 3, modalidade no índice 2)
                corpo = (
                    f"Certificamos que o(a) estudante <b>{projeto[0]}</b>, CPF: <b>{projeto[1]}</b> "
                    f"foi vinculado(a) ao Programa Institucional de Bolsas de Iniciação Científica e Tecnológica (PIICT) "
                    f"na condição de {projeto[3]}, modalidade {projeto[2]} sob orientação do(a) professor(a) "
                    f"<b>{projeto[4]}</b>, no projeto de pesquisa intitulado <b>\"{projeto[5]}\"</b>, "
                    f"desempenhando suas atividades com carga horária de {projeto[6]} horas semanais. "
                    f"A participação do(a) estudante no referido Projeto de Pesquisa se estendeu de {projeto[7]} a {projeto[8]}, "
                    f"contabilizando um total de {projeto[9]} horas."
                )

                return invocar_declaracao_overlay(
                    corpo_html=corpo,
                    data_extenso=data_agora,
                    rotulo_id="ID da Indicação",
                    id_ref=idIndicacao,
                    identificador=idIndicacao,
                    nome_arquivo_download=f"certificado_discente_{idIndicacao}.pdf",
                    tipo_documento="CERTIFICADO"
                )

            except Exception as e:
                with logger.contextualize(ip=request.remote_addr, rota=request.path, erro=str(e), classe_erro=type(e).__name__):
                    logger.warning("Erro ao gerar certificado: {}", str(e))
                return "Erro ao gerar declaração. Tente novamente mais tarde."
        else:
            return "OK"
    else:
        return "OK"


@app.route("/discente/minhaDeclaracao2019", methods=['GET', 'POST'])
@log_required
def minhaDeclaracaoDiscente2019():
    if request.method == "GET":
        if 'id' in request.args:
            idIndicacao = str(request.args.get('id'))
            consulta = f"""SELECT 
            indicacoes.nome,{sql_decifra('cpf', 'indicacoes')},if(indicacoes.fim>NOW(),1,0) as verbo,
            IF(indicacoes.modalidade=1,'PIBIC',
            IF(indicacoes.modalidade=2,'PIBITI',
            IF(indicacoes.modalidade=3,'PIBIC-EM','PIBIC-AF'))),
            editalProjeto.nome,editalProjeto.titulo,indicacoes.ch,
            DATE_FORMAT(indicacoes.inicio,'%d/%m/%Y'),
            DATE_FORMAT(indicacoes.fim,'%d/%m/%Y'), indicacoes.id 
            FROM indicacoes,editalProjeto 
            WHERE indicacoes.idProjeto=editalProjeto.id AND indicacoes.id=%s"""
            
            from datetime import datetime
            projeto, total = executarSelect2(consulta, tipo=1, valores=(AES_KEY, idIndicacao))
            
            if total != 1:
                return "declaração inexistente!"

            inicio = datetime.strptime(str(projeto[7]), '%d/%m/%Y')
            fim = datetime.strptime(str(projeto[8]), '%d/%m/%Y')
            periodo = abs((fim - inicio).days)
            # if periodo < 180:
            #     return 'Declaração indisponível. Período de bolsa inferior a 180 dias'
            
            data_agora = getData()

            try:
                identificador = gerar_codigo_auth(idIndicacao, projeto[5], 'declaracao_discente')

                # Montagem do texto idêntica ao template declaracao_discente.html
                verbo = "é" if projeto[2] == 1 else "foi"
                if projeto[2] == 1:
                    complemento = f"A participação do(a) discente em questão no referido Projeto de Pesquisa iniciou-se em {projeto[7]} e está em andamento."
                else:
                    complemento = f"A participação do(a) discente em questão no referido Projeto de Pesquisa foi de {projeto[7]} a {projeto[8]}."

                corpo = (
                    f"Declaramos, para os devidos fins, que <b>{projeto[0]}</b>, CPF: <b>{projeto[1]}</b>, "
                    f"{verbo} integrante do Programa Institucional de Bolsas de Iniciação Científica ({projeto[3]}), "
                    f"sob orientação do(a) professor(a) {projeto[4]}, com o projeto intitulado <i>\"{projeto[5]}\"</i>, "
                    f"desempenhando suas atividades com carga horária de {projeto[6]} horas semanais. {complemento}"
                )

                return invocar_declaracao_overlay(
                    corpo_html=corpo,
                    data_extenso=data_agora,
                    rotulo_id="ID da Indicação",
                    id_ref=idIndicacao,
                    identificador=identificador,
                    nome_arquivo_download=f"declaracao_discente_{idIndicacao}.pdf"
                )

            except Exception as e:
                with logger.contextualize(ip=request.remote_addr, rota=request.path, erro=str(e), classe_erro=type(e).__name__):
                    logger.warning("Erro ao gerar declaração: {}", str(e))
                return "Erro ao gerar declaração. Tente novamente mais tarde."
        else:
            return "OK"
    else:
        return "OK"

@app.route("/meusPareceres", methods=['GET', 'POST'])
@log_required
@login_required(role='user')
def meusPareceres():
    if request.method == "GET":
        #Recuperando o id do Projeto
        if 'id' in request.args:
            idProjeto = str(request.args.get('id'))
            if autenticado():
                tituloProjeto = str(obterColunaUnica("editalProjeto","titulo","id",idProjeto))
                if ('todos' in request.args) and (session['permissao']==0):
                    consulta = """SELECT avaliacoes.id,c1,c2,c3,c4,c5,c6,c7,(c1+c2+c3+c4+c5+c6+c7) as pontuacaoTotal, comentario, if(recomendacao=1,'RECOMENDADO','NÃO RECOMENDADO') as recomendacao, cepa,DATE_FORMAT(data_avaliacao,'%d/%m/%Y'),avaliacoes.inovacao FROM avaliacoes WHERE finalizado=1 AND idProjeto=%s ORDER BY data_avaliacao"""
                    parametros_consulta = (idProjeto,)
                else:
                    consulta = """SELECT avaliacoes.id,c1,c2,c3,c4,c5,c6,c7,(c1+c2+c3+c4+c5+c6+c7) as pontuacaoTotal, comentario, if(recomendacao=1,'RECOMENDADO','NÃO RECOMENDADO') as recomendacao, cepa,DATE_FORMAT(data_avaliacao,'%d/%m/%Y'),avaliacoes.inovacao FROM avaliacoes,editalProjeto WHERE editalProjeto.id=avaliacoes.idProjeto AND finalizado=1 AND idProjeto=%s AND siape=%s ORDER BY data_avaliacao"""
                    parametros_consulta = (idProjeto, str(session['username']))
                try:
                    pareceres,total = executarSelect2(consulta,valores=parametros_consulta)
                    return(render_template('meusPareceres.html',linhas=pareceres,total=total,titulo=tituloProjeto))
                except Exception as e:
                    logger.warning("Erro na função /meusPareceres")
                    logger.warning(str(e))
                    return("ERRO!")
            else:
                return(render_template('login.html',mensagem="É necessário autenticação para acessar a página solicitada"))
        else:
            return("OK")
    else:
        return("OK")

@app.route("/usuario", methods=['GET', 'POST'])
@log_required
def usuario():
    session['PRODUCAO'] = PRODUCAO
    if autenticado():
        if (session['permissao']==0):
            return(redirect(url_for('admin')))
        else:
            return(redirect(url_for('meusProjetos')))
    else:
        return(render_template('login.html',mensagem=''))

def registrar_acesso(ip,usuario):
    try:
        consulta = """
        INSERT INTO acessos(ip,username) VALUES (%s,%s)
        """
        valores = (str(ip),str(usuario))
        inserir(consulta,valores)
    except Exception as e:
        logger.warning("Erro ao registrar acesso: {}",str(e))

def pos_login(username, senha_vazada):
    """Etapas finais do login concluído (direto no /login ou após o código do MFA)."""
    registrar_acesso(request.remote_addr, username)
    if senha_vazada:
        session['senha_vazada'] = True
        with logger.contextualize(ip=request.remote_addr,username=username,rota=request.path,metodo=request.method,erro=""):
            logger.warning("Login com senha identificada como vazada (Cloudflare Leaked Credential Check)")
        flash("Sua senha foi identificada em um vazamento de dados conhecido. Por segurança, defina uma nova senha.","error")
        return redirect(url_for('nova_senha'))
    return redirect(url_for('home'))

@app.route("/login", methods=['POST','GET'])
@log_required
@limiter.limit("30/day;15/hour;3/minute",methods=["POST"])
@exigir_turnstile('login')
def login():
    '''
    Método que ativa a sessão com os dados do usuário
    '''
    if request.method == "POST":
        if (('siape' in request.form) and ('senha' in request.form)):
            siape = str(request.form['siape'])
            senha = str(request.form['senha'])
            senha = senha[:64]  # Limitar o tamanho da senha para evitar problemas ataques DoS
            resultado = autenticar_usuario(siape,senha)
            if resultado == 'desafio':
                flash("Defina sua senha para concluir o primeiro acesso.")
                return redirect(url_for('definir_senha'))
            if resultado == 'reset':
                flash("Sua senha foi redefinida. Use o código enviado para seu e-mail para definir uma nova senha.","error")
                return redirect(url_for('redefinir_senha'))
            if resultado == 'mfa':
                return redirect(url_for('mfa_verificar'))
            if resultado == 'politica':
                registrar_acesso(request.remote_addr,siape)
                flash("Sua senha não atende aos requisitos de segurança atuais. Defina uma nova senha.","error")
                return redirect(url_for('nova_senha'))
            if resultado == 'ok':
                return pos_login(siape, senha_vazada_detectada())
            else:
                flash("Usuário ou senha inválidos. Tente novamente.","error")
                return redirect(url_for('login'))
        else:
            flash("Usuário ou senha inválidos. Tente novamente.","error")
            return redirect(url_for('login'))
    else: #GET
        return render_template('login.html')

@app.route("/esqueciMinhaSenha", methods=['GET', 'POST'])
@log_required
def esqueciMinhaSenha():
    return(render_template('esqueciMinhaSenha.html'))

MENSAGEM_RECUPERACAO = "Se o e-mail estiver cadastrado, você receberá uma mensagem com as instruções para definir uma nova senha."

@app.route("/enviarMinhaSenha", methods=['GET', 'POST'])
@log_required
@limiter.limit("3/day;2/hour;1/minute",methods=["POST"])
@exigir_turnstile('esqueciMinhaSenha')
def enviarMinhaSenha():
    """Esqueci minha senha: em produção o Cognito envia o código (ou reenvia o convite).
    A resposta é sempre a mesma, para não revelar quais e-mails estão cadastrados."""
    if request.method == "POST":
        if ('email' in request.form):
            email = str(request.form['email']).strip()
            linha = buscar_usuario(email, 'email')
            if linha is None:
                with logger.contextualize(ip=request.remote_addr,rota=request.path,email=email):
                    logger.info("Redefinição de senha para e-mail não cadastrado")
            elif USAR_COGNITO:
                try:
                    cognito_iniciar_recuperacao(linha, origem='esqueci_senha')
                except (ClientError, BotoCoreError):
                    pass  # Já registrado no log; a resposta continua genérica
            else:
                with logger.contextualize(ip=request.remote_addr,rota=request.path,email=email):
                    logger.info("Esqueci minha senha em dev: nenhuma ação (Cognito só em produção)")
            flash(MENSAGEM_RECUPERACAO)
            if USAR_COGNITO:
                return redirect(url_for('redefinir_senha'))
            return redirect(url_for('login'))
        else:
            return("OK")
    else:
        return("OK")

def validar_nova_senha(nova, confirmar):
    """Retorna a mensagem de erro da nova senha ou None se estiver válida."""
    if nova != confirmar:
        return "A nova senha e a confirmação não coincidem."
    if not senha_segura_valida(nova):
        return "A nova senha deve ter no mínimo 12 caracteres e incluir letras maiúsculas, minúsculas, números e caracteres especiais."
    return None

@app.route("/redefinirSenha", methods=['GET', 'POST'])
@log_required
@limiter.limit("10/hour;3/minute",methods=["POST"])
def redefinir_senha():
    """Define a nova senha com o código enviado pelo Cognito (esqueci minha senha ou reset pelo admin)."""
    if not USAR_COGNITO:
        flash("A redefinição de senha por código está disponível apenas em produção.","error")
        return redirect(url_for('home'))
    if request.method == 'POST':
        siape = str(request.form.get('siape', '')).strip()
        codigo = str(request.form.get('codigo', '')).strip()
        nova = str(request.form.get('nova_senha', ''))[:64]
        confirmar = str(request.form.get('confirmar_senha', ''))[:64]
        if not username_valido(siape) or not codigo.isdigit():
            flash("SIAPE ou código inválido.", 'error')
            return redirect(url_for('redefinir_senha'))
        erro = validar_nova_senha(nova, confirmar)
        if erro:
            flash(erro, 'error')
            return redirect(url_for('redefinir_senha'))
        try:
            cognito.confirm_forgot_password(ClientId=COGNITO_APP_CLIENT_ID, Username=siape,
                                            ConfirmationCode=codigo, Password=nova)
        except (ClientError, BotoCoreError) as e:
            codigo_e = codigo_erro(e)
            mensagens = {
                'CodeMismatchException': "Código inválido. Confira o SIAPE e o código recebido.",
                'ExpiredCodeException': "Código expirado. Solicite um novo código em \"Esqueci minha senha\".",
                'InvalidPasswordException': "A nova senha não atende aos requisitos de segurança.",
                'LimitExceededException': "Muitas tentativas. Aguarde alguns minutos e tente novamente.",
            }
            log_migracao('redefinicao_senha_falha', siape, nivel='warning', origem='redefinir_senha', classe_erro=codigo_e)
            flash(mensagens.get(codigo_e, "Não foi possível redefinir a senha. Verifique os dados e tente novamente."), 'error')
            return redirect(url_for('redefinir_senha'))
        # Garante o espelho local caso a marcação da migração tenha falhado antes
        atualizar2("UPDATE users SET migrado=1 WHERE username=%s AND migrado=0", valores=[siape])
        log_migracao('senha_redefinida', siape, origem='redefinir_senha')
        flash("Senha redefinida com sucesso! Entre com a nova senha.")
        return redirect(url_for('login'))
    return render_template('redefinirSenha.html')

@app.route("/definirSenha", methods=['GET', 'POST'])
@log_required
@limiter.limit("10/hour;3/minute",methods=["POST"])
def definir_senha():
    """Primeiro acesso de usuário convidado: troca a senha provisória do convite do Cognito."""
    desafio = session.get('cognito_desafio')
    if not USAR_COGNITO or not desafio:
        return redirect(url_for('login'))
    if request.method == 'POST':
        nova = str(request.form.get('nova_senha', ''))[:64]
        confirmar = str(request.form.get('confirmar_senha', ''))[:64]
        erro = validar_nova_senha(nova, confirmar)
        if erro:
            flash(erro, 'error')
            return redirect(url_for('definir_senha'))
        username = desafio['username']
        try:
            resposta = cognito.admin_respond_to_auth_challenge(
                UserPoolId=COGNITO_USER_POOL_ID,
                ClientId=COGNITO_APP_CLIENT_ID,
                ChallengeName='NEW_PASSWORD_REQUIRED',
                Session=desafio['session'],
                ChallengeResponses={'USERNAME': username, 'NEW_PASSWORD': nova},
            )
        except (ClientError, BotoCoreError) as e:
            codigo_e = codigo_erro(e)
            if codigo_e == 'InvalidPasswordException':
                flash("A nova senha não atende aos requisitos de segurança.", 'error')
                return redirect(url_for('definir_senha'))
            session.pop('cognito_desafio', None)
            log_migracao('definir_senha_falha', username, nivel='warning', origem='primeiro_acesso', classe_erro=codigo_e)
            flash("Sessão expirada. Entre novamente com a senha provisória recebida por e-mail.", 'error')
            return redirect(url_for('login'))
        session.pop('cognito_desafio', None)
        if 'AuthenticationResult' not in resposta:
            log_migracao('definir_senha_falha', username, nivel='error', origem='primeiro_acesso',
                         classe_erro=resposta.get('ChallengeName'))
            flash("Não foi possível concluir o primeiro acesso. Tente entrar novamente.", 'error')
            return redirect(url_for('login'))
        try:
            concluir_login_cognito(username, resposta['AuthenticationResult'], via_mfa=False)
        except (ClientError, BotoCoreError) as e:
            log_migracao('login_falha_cognito', username, nivel='error', erro=str(e), classe_erro=codigo_erro(e))
            flash("Senha definida. Entre novamente com a nova senha.")
            return redirect(url_for('login'))
        registrar_acesso(request.remote_addr, username)
        log_migracao('senha_definida_primeiro_acesso', username, origem='primeiro_acesso')
        flash("Senha definida com sucesso! Agora configure a verificação em duas etapas (MFA).")
        return redirect(url_for('mfa_configurar'))
    return render_template('definirSenha.html')

@app.route("/logout", methods=['GET', 'POST'])
@log_required
def encerrarSessao():
    logout()
    return redirect(url_for('home'))

# ---------------------------------------------------------------------------
# MFA (somente produção/Cognito): app autenticador (TOTP) ou código por e-mail
# ---------------------------------------------------------------------------

def mascarar_email(email):
    nome, _, dominio = str(email or '').partition('@')
    return f"{nome[:2]}***@{dominio}" if dominio else ''

def sessao_mfa_expirada():
    """Sem access token válido não há como cadastrar o MFA: encerra e pede novo login."""
    logout()
    flash("Sua sessão expirou. Entre novamente para configurar a verificação em duas etapas.", 'error')
    return redirect(url_for('login'))

def metodos_mfa_ativos(access_token):
    """Métodos de MFA habilitados no Cognito (ex.: ['SOFTWARE_TOKEN_MFA']) e o e-mail do usuário."""
    usuario = cognito.get_user(AccessToken=access_token)
    email = atributos_para_dict(usuario.get('UserAttributes', [])).get('email', '')
    return usuario.get('UserMFASettingList', []), email

def definir_metodo_mfa(access_token, metodo):
    """Ativa o método escolhido como preferido e desativa o outro (um único método por
    usuário: assim o Cognito nunca pede SELECT_MFA_TYPE)."""
    ativos, _ = metodos_mfa_ativos(access_token)
    preferencias = {}
    if metodo == 'SOFTWARE_TOKEN_MFA':
        preferencias['SoftwareTokenMfaSettings'] = {'Enabled': True, 'PreferredMfa': True}
        if 'EMAIL_OTP' in ativos:
            preferencias['EmailMfaSettings'] = {'Enabled': False, 'PreferredMfa': False}
    else:
        preferencias['EmailMfaSettings'] = {'Enabled': True, 'PreferredMfa': True}
        if 'SOFTWARE_TOKEN_MFA' in ativos:
            preferencias['SoftwareTokenMfaSettings'] = {'Enabled': False, 'PreferredMfa': False}
    cognito.set_user_mfa_preference(AccessToken=access_token, **preferencias)

def qrcode_totp_svg(username, secret):
    """URI otpauth:// (padrão do Google Authenticator) e o QR code correspondente em SVG inline."""
    uri = (f"otpauth://totp/{quote(EMISSOR_TOTP)}:{quote(str(username))}"
           f"?secret={secret}&issuer={quote(EMISSOR_TOTP)}")
    buffer = io.BytesIO()
    pyqrcode.create(uri, error='M').svg(buffer, scale=5, xmldecl=False, svgns=True, omithw=True,
                                        background='#ffffff', title='QR code do MFA')
    return uri, buffer.getvalue().decode('utf-8')

@app.route("/mfa/configurar", methods=['GET'])
@login_required(role='user')
@log_required
def mfa_configurar():
    """Escolha do método de MFA (obrigatório no primeiro acesso após a migração; depois, troca de método)."""
    if not USAR_COGNITO:
        return redirect(url_for('home'))
    access_token = obter_access_token()
    if access_token is None:
        return sessao_mfa_expirada()
    try:
        ativos, email = metodos_mfa_ativos(access_token)
    except (ClientError, BotoCoreError) as e:
        log_migracao('mfa_falha', session['username'], nivel='error', etapa='get_user', classe_erro=codigo_erro(e))
        return sessao_mfa_expirada()
    return render_template('mfaConfigurar.html', ativos=ativos, email=mascarar_email(email),
                           pendente=bool(session.get('mfa_pendente')))

@app.route("/mfa/totp", methods=['GET', 'POST'])
@login_required(role='user')
@log_required
@limiter.limit("20/hour;5/minute", methods=["POST"])
def mfa_totp():
    """Cadastro do app autenticador: QR code (associate_software_token) e confirmação do código."""
    if not USAR_COGNITO:
        return redirect(url_for('home'))
    username = session['username']
    access_token = obter_access_token()
    if access_token is None:
        return sessao_mfa_expirada()
    if request.method == 'POST':
        codigo = str(request.form.get('codigo', '')).strip().replace(' ', '')
        secret = session.get('mfa_totp_secret')
        if not secret:
            return redirect(url_for('mfa_totp'))
        if not re.fullmatch(r'\d{6}', codigo):
            flash("Informe o código de 6 dígitos exibido no aplicativo.", 'error')
            return render_template('mfaTotp.html', secret=secret, qrcode=qrcode_totp_svg(username, secret)[1])
        try:
            resposta = cognito.verify_software_token(AccessToken=access_token, UserCode=codigo,
                                                     FriendlyDeviceName='Google Authenticator')
            if resposta.get('Status') != 'SUCCESS':
                raise ValueError('verify_software_token sem SUCCESS')
            definir_metodo_mfa(access_token, 'SOFTWARE_TOKEN_MFA')
        except (ClientError, ValueError) as e:
            classe = codigo_erro(e)
            log_migracao('mfa_codigo_invalido', username, nivel='warning', origem='cadastro_totp', classe_erro=classe)
            if classe in ('CodeMismatchException', 'EnableSoftwareTokenMFAException', 'ValueError'):
                flash("Código incorreto. Confira se a hora do celular está automática e tente o código atual.", 'error')
            else:
                flash("Não foi possível ativar o aplicativo autenticador. Tente novamente.", 'error')
            return render_template('mfaTotp.html', secret=secret, qrcode=qrcode_totp_svg(username, secret)[1])
        except BotoCoreError as e:
            log_migracao('mfa_falha', username, nivel='error', origem='cadastro_totp', classe_erro=codigo_erro(e))
            flash("Não foi possível ativar o aplicativo autenticador. Tente novamente.", 'error')
            return render_template('mfaTotp.html', secret=secret, qrcode=qrcode_totp_svg(username, secret)[1])
        session.pop('mfa_totp_secret', None)
        session.pop('mfa_pendente', None)
        log_migracao('mfa_cadastro_totp', username, origem='cadastro_totp')
        flash("Verificação em duas etapas ativada! A partir de agora, o código do aplicativo será pedido a cada login.")
        return redirect(url_for('home'))
    try:
        secret = cognito.associate_software_token(AccessToken=access_token)['SecretCode']
    except (ClientError, BotoCoreError) as e:
        log_migracao('mfa_falha', username, nivel='error', origem='cadastro_totp', etapa='associate_software_token',
                     classe_erro=codigo_erro(e))
        flash("Não foi possível iniciar o cadastro do aplicativo autenticador. Tente novamente.", 'error')
        return redirect(url_for('mfa_configurar'))
    session['mfa_totp_secret'] = secret
    return render_template('mfaTotp.html', secret=secret, qrcode=qrcode_totp_svg(username, secret)[1])

@app.route("/mfa/email", methods=['POST'])
@login_required(role='user')
@log_required
@limiter.limit("10/hour;3/minute", methods=["POST"])
def mfa_email():
    """Ativa o código por e-mail (EMAIL_OTP do Cognito) como método de MFA."""
    if not USAR_COGNITO:
        return redirect(url_for('home'))
    username = session['username']
    access_token = obter_access_token()
    if access_token is None:
        return sessao_mfa_expirada()
    try:
        definir_metodo_mfa(access_token, 'EMAIL_OTP')
    except (ClientError, BotoCoreError) as e:
        log_migracao('mfa_falha', username, nivel='error', origem='cadastro_email', classe_erro=codigo_erro(e))
        flash("Não foi possível ativar o código por e-mail. Tente novamente.", 'error')
        return redirect(url_for('mfa_configurar'))
    session.pop('mfa_totp_secret', None)
    session.pop('mfa_pendente', None)
    log_migracao('mfa_cadastro_email', username, origem='cadastro_email')
    flash("Verificação em duas etapas ativada! A partir de agora, um código será enviado ao seu e-mail a cada login.")
    return redirect(url_for('home'))

@app.route("/mfa/verificar", methods=['GET', 'POST'])
@log_required
@limiter.limit("30/hour;5/minute", methods=["POST"])
def mfa_verificar():
    """Segunda etapa do login: código do app autenticador ou do e-mail."""
    desafio = session.get('cognito_mfa')
    if not USAR_COGNITO or not desafio:
        return redirect(url_for('login'))
    username, tipo = desafio['username'], desafio['tipo']
    if request.method == 'POST':
        codigo = str(request.form.get('codigo', '')).strip().replace(' ', '')
        if not re.fullmatch(r'\d{6,8}', codigo):
            flash("Informe o código numérico recebido.", 'error')
            return redirect(url_for('mfa_verificar'))
        try:
            resposta = cognito.admin_respond_to_auth_challenge(
                UserPoolId=COGNITO_USER_POOL_ID,
                ClientId=COGNITO_APP_CLIENT_ID,
                ChallengeName=tipo,
                Session=desafio['session'],
                ChallengeResponses={'USERNAME': username, MFA_TIPOS[tipo]: codigo},
            )
        except (ClientError, BotoCoreError) as e:
            classe = codigo_erro(e)
            if classe == 'CodeMismatchException':
                log_migracao('mfa_codigo_invalido', username, nivel='warning', origem='login', etapa=tipo)
                flash("Código incorreto. Tente novamente.", 'error')
                return redirect(url_for('mfa_verificar'))
            session.pop('cognito_mfa', None)
            log_migracao('mfa_falha', username, nivel='warning', origem='login', etapa=tipo, classe_erro=classe)
            flash("Sessão de verificação expirada. Entre novamente com seu SIAPE e senha.", 'error')
            return redirect(url_for('login'))
        session.pop('cognito_mfa', None)
        if 'AuthenticationResult' not in resposta:
            log_migracao('login_desafio_nao_suportado', username, nivel='error', classe_erro=resposta.get('ChallengeName'))
            flash("Não foi possível concluir o login. Tente novamente.", 'error')
            return redirect(url_for('login'))
        try:
            concluir_login_cognito(username, resposta['AuthenticationResult'], via_mfa=True)
        except (ClientError, BotoCoreError) as e:
            log_migracao('login_falha_cognito', username, nivel='error', erro=str(e), classe_erro=codigo_erro(e))
            flash("Não foi possível concluir o login. Tente novamente.", 'error')
            return redirect(url_for('login'))
        log_migracao('mfa_ok', username, origem='login', etapa=tipo)
        with logger.contextualize(ip=request.remote_addr,username=username,rota=request.path,metodo=request.method,erro=""):
            logger.info("Usuário autenticado com sucesso (Cognito + MFA)")
        return pos_login(username, desafio.get('senha_vazada', False))
    return render_template('mfaVerificar.html', tipo=tipo, destino=desafio.get('destino', ''))

MFA_RECUPERACAO_VALIDADE = 600  # segundos
MFA_RECUPERACAO_TENTATIVAS = 5

def hash_codigo_recuperacao(codigo, sal):
    return hmac.new(bytes.fromhex(sal), codigo.encode(), hashlib.sha256).hexdigest()

@app.route("/mfa/recuperar", methods=['GET', 'POST'])
@log_required
@limiter.limit("3/hour", methods=["POST"])
def mfa_recuperar():
    """Perdeu o app autenticador: envia um código de uso único ao e-mail cadastrado.
    Só é possível no meio do login, depois de a senha ter sido validada pelo Cognito."""
    desafio = session.get('cognito_mfa')
    if not USAR_COGNITO or not desafio or desafio['tipo'] != 'SOFTWARE_TOKEN_MFA':
        return redirect(url_for('login'))
    username = desafio['username']
    if request.method == 'POST':
        linha = buscar_usuario(username)
        if linha is None or not linha[7]:
            log_migracao('mfa_falha', username, nivel='error', origem='recuperacao', etapa='email_ausente')
            flash("Não há e-mail cadastrado para a recuperação. Procure a coordenação de pesquisa.", 'error')
            return redirect(url_for('mfa_verificar'))
        codigo = f"{secrets.randbelow(10**8):08d}"
        sal = secrets.token_hex(16)
        session['mfa_recuperacao'] = {
            'username': username,
            'sal': sal,
            'hash': hash_codigo_recuperacao(codigo, sal),
            'expira': time.time() + MFA_RECUPERACAO_VALIDADE,
            'tentativas': 0,
        }
        corpo = render_template('email_mfa_recuperacao.html', codigo=codigo, username=username,
                                minutos=MFA_RECUPERACAO_VALIDADE // 60)
        if not send_email_async(str(linha[7]), "Plataforma Yoko - Código de recuperação da verificação em duas etapas", corpo):
            log_migracao('mfa_falha', username, nivel='error', origem='recuperacao', etapa='envio_email')
            flash("Não foi possível enviar o e-mail. Tente novamente mais tarde.", 'error')
            return redirect(url_for('mfa_verificar'))
        log_migracao('mfa_recuperacao_enviada', username, origem='recuperacao')
        flash(f"Enviamos um código para {mascarar_email(linha[7])}. Ele vale por {MFA_RECUPERACAO_VALIDADE // 60} minutos.")
        return redirect(url_for('mfa_recuperar_confirmar'))
    return render_template('mfaRecuperar.html', etapa='enviar')

@app.route("/mfa/recuperar/confirmar", methods=['GET', 'POST'])
@log_required
@limiter.limit("10/hour;3/minute", methods=["POST"])
def mfa_recuperar_confirmar():
    """Confere o código de recuperação e desativa o app autenticador no Cognito;
    no próximo login o usuário cadastra um novo método de MFA."""
    recuperacao = session.get('mfa_recuperacao')
    if not USAR_COGNITO or not recuperacao:
        return redirect(url_for('login'))
    username = recuperacao['username']
    if time.time() > recuperacao['expira'] or recuperacao['tentativas'] >= MFA_RECUPERACAO_TENTATIVAS:
        session.pop('mfa_recuperacao', None)
        session.pop('cognito_mfa', None)
        flash("Código de recuperação expirado ou bloqueado. Entre novamente para solicitar outro.", 'error')
        return redirect(url_for('login'))
    if request.method == 'POST':
        codigo = str(request.form.get('codigo', '')).strip().replace(' ', '')
        if not hmac.compare_digest(hash_codigo_recuperacao(codigo, recuperacao['sal']), recuperacao['hash']):
            recuperacao['tentativas'] += 1
            session['mfa_recuperacao'] = recuperacao
            log_migracao('mfa_codigo_invalido', username, nivel='warning', origem='recuperacao')
            flash("Código incorreto.", 'error')
            return redirect(url_for('mfa_recuperar_confirmar'))
        try:
            cognito.admin_set_user_mfa_preference(
                UserPoolId=COGNITO_USER_POOL_ID,
                Username=username,
                SoftwareTokenMfaSettings={'Enabled': False, 'PreferredMfa': False},
            )
        except (ClientError, BotoCoreError) as e:
            log_migracao('mfa_falha', username, nivel='error', origem='recuperacao',
                         etapa='admin_set_user_mfa_preference', erro=str(e), classe_erro=codigo_erro(e))
            flash("Não foi possível redefinir a verificação em duas etapas. Tente novamente mais tarde.", 'error')
            return redirect(url_for('mfa_recuperar_confirmar'))
        session.pop('mfa_recuperacao', None)
        session.pop('cognito_mfa', None)
        log_migracao('mfa_recuperacao_ok', username, origem='recuperacao')
        linha = buscar_usuario(username)
        if linha is not None and linha[7]:
            send_email_async(str(linha[7]), "Plataforma Yoko - Verificação em duas etapas redefinida",
                             render_template('email_mfa_redefinido.html', username=username))
        flash("O aplicativo autenticador foi desvinculado da sua conta. Entre novamente com seu SIAPE e senha para configurar um novo método de verificação.")
        return redirect(url_for('login'))
    return render_template('mfaRecuperar.html', etapa='confirmar')

def projetoAprovado(idProjeto):

    categoria = int(obterColunaUnica("editalProjeto","categoria","id",str(idProjeto)))

    if categoria==0:
        return (True)
    else:
        consulta = """SELECT sum(if(recomendacao=0,1,0)) as rejeitados, sum(if(recomendacao=1,1,0)) as aprovados FROM avaliacoes WHERE idProjeto=%s"""
        resultado,total = executarSelect2(consulta,tipo=1,valores=(str(idProjeto),))
        avaliacoes = int(resultado[0]) + int(resultado[1])
        if avaliacoes>1:
            if (resultado[1]>resultado[0]):
                return (True)
            else:
                return (False)
        else:
            return(False)

@app.route("/admin/prepararResultados", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def prepararResultados():
    if request.method == "GET":
        #Recuperando o código do edital
        if 'edital' in request.args:
            codigoEdital = str(request.args.get('edital'))
            if ((autenticado()) and (session['permissao']==0)):
                #ZERANDO as concessões
                consulta = "UPDATE editalProjeto SET bolsas_concedidas=0 WHERE tipo=%s"
                atualizar2(consulta, valores=(codigoEdital,))

                consulta = """UPDATE editalProjeto SET obs='' WHERE tipo=%s"""
                atualizar2(consulta, valores=(codigoEdital,))

                #Gerando projetos do edital
                tipo_classificacao = int(obterColunaUnica("editais","classificacao","id",codigoEdital))
                if (tipo_classificacao==1):
                    consulta = "SELECT id,tipo,categoria,ua,bolsas,bolsas_concedidas,siape,modalidade FROM editalProjeto WHERE tipo=%s AND valendo=1 ORDER BY ua, produtividade,scorelattes DESC"
                else:
                    consulta = "SELECT id,tipo,categoria,ua,bolsas,bolsas_concedidas,siape,modalidade FROM editalProjeto WHERE tipo=%s AND valendo=1 ORDER BY produtividade,scorelattes DESC"
                projetos,total = executarSelect2(consulta,valores=(codigoEdital,))
                total = float(total)
                #Recuperando demanda por unidade academica
                demanda = """SELECT ua,count(id) FROM editalProjeto WHERE valendo=1 and tipo=%s GROUP BY ua ORDER BY ua"""
                demandaQualificada,totalDemanda = executarSelect2(demanda,valores=(codigoEdital,))

                #Recuperando quantitativo de bolsas do edital
                bolsas_ufca = int(obterColunaUnica("editais","quantidade_bolsas","id",codigoEdital))
                bolsas_cnpq = int(obterColunaUnica("editais","quantidade_bolsas_cnpq","id",codigoEdital))
                #Montando os dados
                cnpqUnidade = {}
                ufcaUnidade = {}
                for linha in demandaQualificada:
                    ua = str(linha[0])
                    totalDeProjetosDaUnidade = int(linha[1])
                    bolsasCnpqParaUnidade = round((totalDeProjetosDaUnidade/total)*bolsas_cnpq)
                    bolsasUFCAParaUnidade = round((totalDeProjetosDaUnidade/total)*bolsas_ufca)
                    cnpqUnidade[ua] = bolsasCnpqParaUnidade
                    ufcaUnidade[ua] = bolsasUFCAParaUnidade
                #Distribuindo bolsas
                continua = True
                while(continua):
                    consulta = "SELECT id,tipo,categoria,ua,bolsas,bolsas_concedidas,siape,modalidade FROM editalProjeto WHERE tipo=%s AND valendo=1 ORDER BY ua, produtividade,scorelattes DESC"
                    projetos,total = executarSelect2(consulta,valores=(codigoEdital,))
                    for projeto in projetos:
                        ua = str(projeto[3]) #Unidade Academica
                        idProjeto = int(projeto[0]) #ID do projeto
                        solicitadas = int(projeto[4]) #Quantidade de bolsas solicitadas
                        concedidas = int(projeto[5]) #Quantidade de bolsas concedidas
                        siape = str((projeto[6]))  #Siape
                        codigoEdital = str(projeto[1]) #Codigo do Edital
                        categoria = int(projeto[2]) #Projeto novo(1) ou em andamento (0)
                        modalidade = int(projeto[7]) #PIBIC, PIBITI, PIBIC-EM

                        if (cnpqUnidade[ua]>0): #Se a unidade ainda possui bolsas disponíveis
                            if (solicitadas-concedidas)>0: #Se ainda existe demanda a ser atendida
                                if(not cotaEstourada(codigoEdital,siape)): #Se o orientador não estiver com a cota individual estourada
                                    if projetoAprovado(idProjeto): #Se o projeto estiver aprovado
                                        consulta = "UPDATE editalProjeto SET bolsas_concedidas=bolsas_concedidas+1 WHERE id=%s"
                                        atualizar2(consulta, valores=(idProjeto,))
                                        cnpqUnidade[ua] = cnpqUnidade[ua] - 1
                                        consulta = """UPDATE editalProjeto SET obs=CONCAT(obs,'<BR><BR>','BOLSA CNPq CONCEDIDA') WHERE id=%s"""
                                        atualizar2(consulta, valores=(idProjeto,))
                                    else: #Se o projeto não estiver aprovado
                                        consulta = "UPDATE editalProjeto SET obs=\"PROJETO NÃO FOI APROVADO.\" WHERE id=%s"
                                        atualizar2(consulta, valores=(idProjeto,))
                                else: #Se o orientador estiver com a cota estourada
                                    consulta = """UPDATE editalProjeto SET obs=CONCAT(obs,'<BR>','BOLSA NÃO CONCEDIDA. ORIENTADOR NÃO PODE ULTRASSAR A COTA DE 2 BOLSISTAS POR MODALIDADE (Anexo XIV da Res. 01/2014/CONSUP, Art. 7 Inciso I)') WHERE id=%s"""
                                    #atualizar2(consulta, valores=(idProjeto,))
                        elif (ufcaUnidade[ua]>0): #Bolsas UFCA
                            if (solicitadas-concedidas)>0: #Se ainda existe demanda a ser atendida
                                if(not cotaEstourada(codigoEdital,siape)): #Se o orientador não estiver com a cota individual estourada
                                    if projetoAprovado(idProjeto): #Se o projeto estiver aprovado
                                        consulta = "UPDATE editalProjeto SET bolsas_concedidas=bolsas_concedidas+1 WHERE id=%s"
                                        atualizar2(consulta, valores=(idProjeto,))
                                        ufcaUnidade[ua] = ufcaUnidade[ua] - 1
                                        consulta = """UPDATE editalProjeto SET obs=CONCAT(obs,'<BR><BR>','BOLSA UFCA CONCEDIDA') WHERE id=%s"""
                                        atualizar2(consulta, valores=(idProjeto,))
                                else: #Se o orientador estiver com a cota estourada
                                    consulta = """UPDATE editalProjeto SET obs=CONCAT(obs,'<BR>','BOLSA NÃO CONCEDIDA. ORIENTADOR NÃO PODE ULTRASSAR A COTA DE 2 BOLSISTAS POR MODALIDADE (Anexo XIV da Res. 01/2014/CONSUP, Art. 7 Inciso I)') WHERE id=%s"""
                                    #atualizar2(consulta, valores=(idProjeto,))

                        else: # se a unidade não tem mais bolsas disponíveis em sua cota
                            consulta = "UPDATE editalProjeto SET obs=CONCAT(obs,'<BR>','BOLSA NÃO CONCEDIDA. COTA DA UNIDADE ZERADA (Anexo XIV da Res. 01/2014/CONSUP, Art. 7 Inciso II)') WHERE id=%s"
                            #atualizar2(consulta, valores=(idProjeto,))
                    if (sum(ufcaUnidade.values())>0) or (sum(cnpqUnidade.values())>0):
                        continua = True
                    else:
                        continua = False

                return("Resultados preparados com sucesso!")
            else:
                return("Voce nao tem permissao para acessar este recurso.")
        else:
            return("OK")
    else:
        return("OK")

def tuplaDeEditais(ano):
    if not numero_valido(ano):
        return 0
    inicio = ano + "-03-01"
    fim = ano + "-12-31"
    consulta = """SELECT id FROM editais WHERE DATE(deadline)>%s AND DATE(deadline)<%s AND nome not like '%contínuo%'"""
    editais,total = executarSelect2(consulta,valores=(inicio,fim))
    codigos = []
    for linha in editais:
        codigos.append(int(linha[0]))
    if total>0:
        resultado = str(tuple(codigos))
        return (resultado)
    else:
        return (0)


@app.route("/admin/cruzarDados", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def cruzarDados():
    if request.method == "GET":
        #Recuperando o ano dos editais
        if 'ano' in request.args:
            ano = str(request.args.get('ano'))
            if ((autenticado()) and (session['permissao']==0)):
                editais = tuplaDeEditais(ano)
                if (editais!=0):
                    consulta = """SELECT siape,editalProjeto.nome,sum(bolsas_concedidas),GROUP_CONCAT(editais.nome ORDER BY tipo SEPARATOR '<BR>') as editais, GROUP_CONCAT(modalidades.descricao ORDER BY tipo SEPARATOR '<BR>') as tipos FROM editalProjeto,modalidades,editais WHERE modalidades.id=editalProjeto.modalidade AND editalProjeto.tipo=editais.id AND valendo=1 and tipo in """ + editais + """ AND modalidade in (1,2,3) GROUP BY siape ORDER BY nome"""
                    linhas,total = executarSelect(consulta)
                    return(render_template('bolsasPorAno.html',linhas=linhas,ano=ano,total=total))
                else:
                    return("Sem dados disponíveis!")
            else:
                return("Acesso negado!")
        else:
            return("OK")
    else:
        return("OK")

def idSiape(id,siape):
    siapeObtido = obterColunaUnica('editalProjeto','siape','id',id)
    if siape=="0":
        return (False)
    else:
        if (siapeObtido==siape):
            return(True)
        else:
            return(False)

def quantosVoluntariosIndicados(id):
    '''
    Verifica quantos voluntários já foram indicados para o id do projeto
    '''
    consulta = """SELECT count(id) FROM indicacoes WHERE tipo_de_vaga=0 AND idProjeto=%s"""
    linhas,total = executarSelect2(consulta,tipo=1,valores=(id,))
    numero = int(linhas[0])
    return (numero)

def quantosVoluntariosAdicionaisIndicados(id):
    '''
    Verifica quantos voluntários adicionais já foram indicados para o id do projeto
    '''
    consulta = """SELECT count(id) FROM indicacoes WHERE tipo_de_vaga=0 AND arquivo_plano!='N/A' AND situacao=0 AND idProjeto=%s"""
    linhas,total = executarSelect2(consulta,tipo=1,valores=(id,))
    numero = int(linhas[0])
    return (numero)

def podeIndicarVoluntariosAdicionais(id):
    '''
    Verifica se um projeto pode indicar voluntários adicionais
    '''
    voluntariosAdicionaisIndicados = quantosVoluntariosAdicionaisIndicados(id)
    if (voluntariosAdicionaisIndicados<=2):
        return (True)
    else:
        return (False)


def podeIndicarVoluntarios(idProjeto):
    '''
    Verifica se um projeto pode indicar voluntários
    '''
    bolsas_obtidas = int(obterColunaUnica('editalProjeto','bolsas_concedidas','id',idProjeto))
    bolsas_solicitadas = int(obterColunaUnica('editalProjeto','bolsas','id',idProjeto))
    bolsistasIndicados = quantosBolsistasIndicados(idProjeto)
    voluntariosIndicados = quantosVoluntariosIndicados(idProjeto)
    tem_arquivo_plano3 = obterColunaUnica('editalProjeto','arquivo_plano3','id',idProjeto)
    if tem_arquivo_plano3!='0':
        tem_arquivo_plano3 = 1
    else:
        tem_arquivo_plano3 = 0
    totalDeVoluntarios = bolsas_solicitadas-bolsas_obtidas + tem_arquivo_plano3
    if (voluntariosIndicados<totalDeVoluntarios):
        return (True)
    else:
        return (False)

def quantosBolsistasIndicados(id):
    '''
    Verifica quantos bolsistas já foram indicados para o id do projeto
    '''
    consulta = """SELECT count(id) FROM indicacoes WHERE tipo_de_vaga=1 AND idProjeto=%s"""
    linhas,total = executarSelect2(consulta,tipo=1,valores=(id,))
    numero = int(linhas[0])
    return (numero)


def podeIndicarBolsistas(id):
    '''
    Verifica se um projeto pode indicar bolsistas
    '''
    bolsas_obtidas = int(obterColunaUnica('editalProjeto','bolsas_concedidas','id',id))
    if bolsas_obtidas>0:
        #Verificar se ainda restam bolsistas a serem indicados
        if (quantosBolsistasIndicados(id)<bolsas_obtidas):
            return(True)
        else:
            return(False)
    else:
        return(False)

def dataDeIndicacao(codigoEdital):
    '''
    Verifica se o edital está no prazo para indicação de bolsistas/voluntários
    '''
    consulta = """SELECT id FROM editais WHERE NOW() BETWEEN indicacao_inicio AND indicacao_termino AND id=%s"""
    linhas,total = executarSelect2(consulta,valores=(codigoEdital,))
    if total==0:
        return (False)
    else:
        return (True)

def projeto_tem_impedimentos(idProjeto):
    '''
    Verifica se o projeto tem impedimentos
    '''
    consulta = """SELECT id FROM impedimentos WHERE idProjeto= %s AND resolvido=0"""
    linhas,total = executarSelect2(consulta,valores=[idProjeto])
    if total>0:
        return (True)
    else:
        return (False)

@app.route("/indicacao", methods=['GET', 'POST'])
@login_required(role='user')
@log_required
def indicacao():
    if request.method == "GET":
        #Recuperando o código do projeto
        if (('id' in request.args) and ('b' in request.args)):
            idProjeto = str(request.args.get('id'))
            if projeto_tem_impedimentos(idProjeto):
                return("Este projeto possui pendências. Favor entrar em contato com a PRPI para resolver a situação.")
            #b = 1 (bolsista); b = 0 (voluntário)
            b = int(request.args.get('b'))
            edital = int(obterColunaUnica('editalProjeto','tipo','id',idProjeto))
            indicacao_inicio = str(obterColunaUnica('editais',"""DATE_FORMAT(indicacao_inicio,'%d/%m/%Y')""",'id',str(edital)))
            indicacao_fim = str(obterColunaUnica('editais',"""DATE_FORMAT(indicacao_termino,'%d/%m/%Y')""",'id',str(edital)))
            modalidade = int(obterColunaUnica('editalProjeto','modalidade','id',idProjeto))
            if (autenticado()):
                if idSiape(idProjeto,session['username']) or 'admin' in session['roles']:
                    if dataDeIndicacao(str(edital)):
                        if b==1: #INDICAÇÃO DE BOLSISTA
                            if podeIndicarBolsistas(idProjeto):
                                return(render_template('indicacao.html',inicio=indicacao_inicio,fim=indicacao_fim,continua=1,modalidade=modalidade,vaga=b,idProjeto=idProjeto,plano=0,substituicao=0))
                            else:
                                return("Você já indicou todos os bolsistas do projeto. Caso tenha havido algum engano, favor entrar em contato com a PRPI.")
                        else: #INDICAÇÃO DE VOLUNTÁRIO
                            if podeIndicarVoluntarios(idProjeto):
                                return(render_template('indicacao.html',inicio=indicacao_inicio,fim=indicacao_fim,continua=1,modalidade=modalidade,vaga=b,idProjeto=idProjeto,plano=0,substituicao=0))
                            else:
                                return("Você já indicou todos os voluntários do projeto. Caso tenha havido algum engano, favor entrar em contato com a PRPI.")
                    else:
                        return(render_template('indicacao.html',inicio=indicacao_inicio,fim=indicacao_fim,continua=0,substituicao=0))
                else:
                    return("Acesso negado!")
            else:
                return(redirect(url_for('login')))
        else:
            return("OK")
    else:
        return("OK")

def podeSerIndicado(matricula):
    '''
    Verifica se o indicado já está indicado em outro projeto
    '''
    consulta = """
        SELECT * FROM indicacoes WHERE fim>date_add(now(), INTERVAL 75 DAY) and matricula= %s
    """
    linhas,total = executarSelect2(consulta,valores=[matricula])
    if total>0:
        return (False)
    else:
        return (True)

ASSINATURAS_ARQUIVOS = (
    (b"%PDF", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)

def tipo_do_arquivo(inicio):
    """ContentType pelo conteúdo (os nomes terminam em .pdf, mas as indicações aceitam fotos)."""
    for assinatura, content_type in ASSINATURAS_ARQUIVOS:
        if inicio.startswith(assinatura):
            return content_type
    return "application/octet-stream"

def enviar_arquivo_s3(arquivo, prefixo, nome):
    """
    Envia um arquivo do formulário (FileStorage) direto ao S3, em SSE-KMS com a chave aws/s3,
    sem gravar em disco e sem GPG (migracao.s3.md, fase 2). Retorna False se o envio falhar.

    put_object (e não upload_fileobj): um único PUT leva o cabeçalho de criptografia que a
    bucket policy exige; as partes de um multipart não o levam. O limite de 16 MB do app cabe.
    Em dev (PRODUCAO!=1) o arquivo é descartado, como antes: o dev nunca grava no bucket.
    """
    if not nome or secure_filename(nome) != nome:  # o nome vai para a chave no S3 e para a tabela
        logger.error("[S3] Nome de arquivo recusado: {!r}", nome)
        return False
    chave = 'pesquisa/' + PREFIXOS_ARQUIVOS[prefixo][0] + nome
    if PRODUCAO != 1:
        logger.info("PRODUCAO!=1: arquivo {} NÃO enviado ao S3", chave)
        return True
    try:
        arquivo.stream.seek(0)
        content_type = tipo_do_arquivo(arquivo.stream.read(8))
        arquivo.stream.seek(0)
        s3.put_object(
            Bucket=AWS_S3_BUCKET,
            Key=chave,
            Body=arquivo.stream,
            ContentType=content_type,
            ServerSideEncryption='aws:kms',  # sem SSEKMSKeyId: chave gerenciada pela AWS (aws/s3)
            Metadata={'enviado-por': 'app'},
        )
        logger.info("[S3] Arquivo {} enviado ({})", chave, content_type)
        return True
    except (ClientError, BotoCoreError, OSError, ValueError) as e:
        logger.error("[S3] Erro ao enviar o arquivo {}: {}", chave, e)
        return False

# Upload direto do navegador (migracao.s3.md, fase 3): o navegador envia a pesquisa/incoming/<prefixo>/<nome>,
# a Lambda validar-upload confere o tipo e move para pesquisa/<prefixo>/<nome>, e o formulário leva só o nome
# no campo oculto <campo>_s3. Se algo falhar no navegador, o formulário envia o arquivo ao app (fase 2).
UPLOAD_DIRETO_VALIDADE = 300  # segundos
UPLOAD_DIRETO_ESPERA = 15  # segundos esperando a Lambda mover o arquivo
CAMPOS_UPLOAD_DIRETO = {
    'submissoes': {'arquivo_projeto': 'projeto', 'arquivo_plano1': 'plano1', 'arquivo_plano2': 'plano2',
                   'arquivo_plano3': 'plano3', 'arquivo_comprovantes': 'Comprovantes'},
    'docs_indicacoes': {'termo': 'TERMO', 'rg_cpf': 'RG_CPF', 'extrato': 'EXTRATO',
                        'historico': 'HISTORICO', 'plano': 'PLANO'},
}
TIPOS_UPLOAD_DIRETO = {
    'submissoes': ('application/pdf',),
    'docs_indicacoes': ('application/pdf', 'image/jpeg', 'image/png'),
}
TIPOS_UPLOAD_DIRETO_TEXTO = {'submissoes': 'precisa ser PDF', 'docs_indicacoes': 'precisa ser PDF, JPEG ou PNG'}

def inicio_nome_upload_direto(prefixo, rotulo, siape, idProjeto):
    """Início obrigatório do nome: amarra o arquivo ao usuário (submissões) ou ao projeto (indicações)."""
    if prefixo == 'submissoes':
        return rotulo + '_' + str(siape) + '_'
    return rotulo + '.' + str(idProjeto) + '.'

@app.route("/arquivos/url_upload", methods=['POST'])
@login_required(role='user')
@limiter.limit("100 per hour")
def url_upload():
    """URL assinada (POST) para o navegador enviar um arquivo direto a pesquisa/incoming/. Em dev: 404."""
    if PRODUCAO != 1:
        return jsonify(erro="upload direto desativado fora de produção"), 404
    dados = request.get_json(silent=True) or {}
    prefixo = str(dados.get('tipo', ''))
    campo = str(dados.get('campo', ''))
    content_type = str(dados.get('content_type', ''))
    tamanho = dados.get('tamanho')
    idProjeto = str(dados.get('idProjeto', ''))
    siape = session['username']
    if campo not in CAMPOS_UPLOAD_DIRETO.get(prefixo, {}):
        return jsonify(erro="campo inválido"), 400
    if content_type not in TIPOS_UPLOAD_DIRETO[prefixo]:
        return jsonify(erro="tipo de arquivo não aceito no envio direto"), 415
    if type(tamanho) is not int or not 0 < tamanho <= app.config['MAX_CONTENT_LENGTH']:
        return jsonify(erro="tamanho inválido"), 413
    if prefixo == 'submissoes':
        if not getEditaisAbertos():
            return jsonify(erro="nenhum edital aberto"), 403
    elif not numero_valido(idProjeto) or not (idSiape(idProjeto, siape) or 'admin' in session['roles']):
        return jsonify(erro="projeto inválido"), 403
    nome = inicio_nome_upload_direto(prefixo, CAMPOS_UPLOAD_DIRETO[prefixo][campo], siape, idProjeto) \
        + id_generator(32) + '.pdf'
    if secure_filename(nome) != nome:
        return jsonify(erro="nome inválido"), 400
    chave = 'pesquisa/incoming/' + prefixo + '/' + nome
    try:
        post = s3.generate_presigned_post(
            AWS_S3_BUCKET, chave,
            Fields={'Content-Type': content_type, 'x-amz-server-side-encryption': 'aws:kms'},
            Conditions=[{'Content-Type': content_type},
                        {'x-amz-server-side-encryption': 'aws:kms'},
                        ['content-length-range', 1, app.config['MAX_CONTENT_LENGTH']]],
            ExpiresIn=UPLOAD_DIRETO_VALIDADE,
        )
    except (ClientError, BotoCoreError) as e:
        logger.error("[url_upload] Erro ao gerar a URL de upload {}: {}", chave, e)
        return jsonify(erro="erro ao gerar a URL de upload"), 500
    logger.info("[url_upload] {} vai enviar {} ({}, {} bytes)", siape, chave, content_type, tamanho)
    return jsonify(url=post['url'], fields=post['fields'], nome=nome)

def confirmar_upload_direto(prefixo, nome):
    """Espera a Lambda validar-upload mover o arquivo para pesquisa/<prefixo>/. False: recusado ou atrasado."""
    chave = 'pesquisa/' + PREFIXOS_ARQUIVOS[prefixo][0] + nome
    for tentativa in range(UPLOAD_DIRETO_ESPERA):
        try:
            if objeto_s3_existe(chave):
                return True
        except (ClientError, BotoCoreError) as e:
            logger.error("[upload direto] Erro ao conferir {}: {}", chave, e)
            return False
        time.sleep(1)
    logger.warning("[upload direto] {} não chegou ao prefixo final (recusado pela Lambda ou atrasado)", chave)
    return False

def uploads_diretos(prefixo, siape, idProjeto=''):
    """
    Arquivos que o navegador enviou direto ao S3 (campos ocultos <campo>_s3), conferidos ANTES de gravar
    qualquer coisa na tabela. Retorna ({campo: nome}, None) ou ({}, mensagem de erro para o usuário).
    """
    diretos = {}
    for campo, rotulo in CAMPOS_UPLOAD_DIRETO[prefixo].items():
        nome = str(request.form.get(campo + '_s3', ''))
        if not nome:
            continue
        inicio = inicio_nome_upload_direto(prefixo, rotulo, siape, idProjeto)
        if not re.fullmatch(re.escape(inicio) + r'[A-Za-z0-9]{32}\.pdf', nome):
            logger.warning("[upload direto] Nome recusado no campo {}: {!r}", campo, nome)
            return {}, "Arquivo inválido no campo '" + campo + "'. Nada foi gravado: envie o formulário de novo."
        if not confirmar_upload_direto(prefixo, nome):
            return {}, ("O arquivo do campo '" + campo + "' não foi aceito (" + TIPOS_UPLOAD_DIRETO_TEXTO[prefixo]
                        + ") ou ainda não terminou de ser processado. Nada foi gravado: confira o arquivo e "
                        + "envie o formulário de novo.")
        diretos[campo] = nome
    return diretos, None

@app.route("/efetivarIndicacao", methods=['GET', 'POST'])
@login_required(role='user')
@log_required
def efetivarIndicacao():
    if request.method == "POST":
        try:
            idProjeto = str(request.form['idProjeto'])
            vaga = int(request.form['vaga'])
            substituicao = int(request.form['substituicao'])
            substituido = int(request.form['substituido'])
            if ( ( (vaga==1)  and (podeIndicarBolsistas(idProjeto)) ) or ( (vaga==0)  and (podeIndicarVoluntarios(idProjeto)) ) or ( (vaga==0)  and (podeIndicarVoluntariosAdicionais(idProjeto)) ) ) or (substituicao==1):
                nome = str(request.form['nome'])
                fomento = int(request.form['fomento'])
                nascimento = str(request.form['nasc'])
                estado_civil = int(request.form['estado_civil'])
                sexo = int(request.form['sexo'])
                rg = str(request.form['rg'])
                orgao = str(request.form['orgao'])
                uf = str(request.form['uf'])
                cpf = str(request.form['cpf'])
                vaga = int(request.form['vaga'])
                modalidade = int(request.form['modalidade'])
                curso = str(request.form['curso'])
                matricula = str(request.form['matricula'])
                ingresso = int(request.form['ingresso'])
                lattes = str(request.form['lattes'])
                banco = ""
                agencia = ""
                conta = ""
                #if podeSerIndicado(matricula)==False:
                #    return("Indicado ja esta em outro projeto. Nao foi possivel efetivar a indicacao.") 

                if vaga==0:
                    banco = "N/A"
                    agencia = "N/A"
                    conta = "N/A"
                else:
                    banco = str(request.form['banco'])
                    agencia = str(request.form['agencia'])
                    conta = str(request.form['conta'])
                telefone = str(request.form['tel_fixo'])
                celular = str(request.form['tel_cel'])
                email = str(request.form['email'])
                endereco = str(request.form['endereco'])
                escola = str(request.form['escola'])
                conclusao = int(request.form['conclusao'])

                #ARQUIVOS ENVIADOS DIRETO AO S3 PELO NAVEGADOR: conferidos antes de gravar a indicação
                if not numero_valido(idProjeto):
                    return("Projeto inválido!")
                arquivos_diretos, erro_upload = uploads_diretos('docs_indicacoes', session['username'], idProjeto)
                if erro_upload:
                    return(erro_upload)

                nomeDoArquivoTermo = ""
                if 'termo' in request.files:
                    token = id_generator()
                    nomeDoArquivoTermo = "TERMO." + idProjeto + "." + token + ".pdf"
                    if not enviar_arquivo_s3(request.files['termo'], 'docs_indicacoes', nomeDoArquivoTermo):
                        return("Erro ao enviar o documento 'termo'. A indicação NÃO foi gravada: tente novamente.")
                nomeDoArquivoRg = ""
                if 'rg_cpf' in request.files:
                    token = id_generator()
                    nomeDoArquivoRg = "RG_CPF." + idProjeto + "." + token + ".pdf"
                    if not enviar_arquivo_s3(request.files['rg_cpf'], 'docs_indicacoes', nomeDoArquivoRg):
                        return("Erro ao enviar o documento 'rg_cpf'. A indicação NÃO foi gravada: tente novamente.")
                nomeDoArquivoExtrato = ""
                if 'extrato' in request.files:
                    token = id_generator()
                    nomeDoArquivoExtrato = "EXTRATO." + idProjeto + "." + token + ".pdf"
                    if not enviar_arquivo_s3(request.files['extrato'], 'docs_indicacoes', nomeDoArquivoExtrato):
                        return("Erro ao enviar o documento 'extrato'. A indicação NÃO foi gravada: tente novamente.")
                nomeDoArquivoHistorico = ""
                if 'historico' in request.files:
                    token = id_generator()
                    nomeDoArquivoHistorico = "HISTORICO." + idProjeto + "." + token + ".pdf"
                    if not enviar_arquivo_s3(request.files['historico'], 'docs_indicacoes', nomeDoArquivoHistorico):
                        return("Erro ao enviar o documento 'historico'. A indicação NÃO foi gravada: tente novamente.")
                nomeDoArquivoPlano = "N/A"
                if 'plano' in request.files:
                    token = id_generator()
                    nomeDoArquivoPlano = "PLANO." + idProjeto + "." + token + ".pdf"
                    if not enviar_arquivo_s3(request.files['plano'], 'docs_indicacoes', nomeDoArquivoPlano):
                        return("Erro ao enviar o documento 'plano'. A indicação NÃO foi gravada: tente novamente.")
                nomeDoArquivoTermo = arquivos_diretos.get('termo', nomeDoArquivoTermo)
                nomeDoArquivoRg = arquivos_diretos.get('rg_cpf', nomeDoArquivoRg)
                nomeDoArquivoExtrato = arquivos_diretos.get('extrato', nomeDoArquivoExtrato)
                nomeDoArquivoHistorico = arquivos_diretos.get('historico', nomeDoArquivoHistorico)
                nomeDoArquivoPlano = arquivos_diretos.get('plano', nomeDoArquivoPlano)
                codigoEdital = obterColunaUnica('editalProjeto','tipo','id',idProjeto)
                if (substituicao==1):
                    inicio = timestamp()
                else:
                    inicio = obterColunaUnica('editais','discente_inicio','id',str(codigoEdital))
                    agora = timestamp()
                    if agora>inicio:
                        inicio=agora
                fim = obterColunaUnica('editais','discente_fim','id',str(codigoEdital))
                iv = secrets.token_urlsafe(16)
                campos = [('idProjeto', int(idProjeto)), ('nome', nome), ('nascimento', nascimento), ('estado_civil', estado_civil),
                          ('sexo', sexo), ('rg', rg), ('orgao_emissor', orgao), ('uf', uf), ('cpf', cpf), ('tipo_de_vaga', vaga),
                          ('modalidade', modalidade), ('curso', curso), ('matricula', matricula), ('ano_de_ingresso', ingresso),
                          ('lattes', lattes), ('nome_banco', banco), ('agencia', agencia), ('conta', conta), ('telefone', telefone),
                          ('celular', celular), ('email', email), ('endereco', endereco), ('escola', escola), ('ano_conclusao', conclusao),
                          ('arquivo_cpf_rg', nomeDoArquivoRg), ('arquivo_extrato', nomeDoArquivoExtrato),
                          ('arquivo_historico', nomeDoArquivoHistorico), ('arquivo_termo', nomeDoArquivoTermo), ('inicio', inicio),
                          ('fim', fim), ('arquivo_plano', nomeDoArquivoPlano), ('substituido', substituido), ('fomento', fomento), ('iv', iv)]
                consulta, valores = montar_insert_indicacao(campos, iv, cpf)
                inserir(consulta,valores)
                lastID = "SELECT id FROM indicacoes WHERE idProjeto=%s ORDER BY id DESC LIMIT 1"
                ultimo_id,total = executarSelect2(lastID,tipo=1,valores=(idProjeto,))
                idIndicacao = int(ultimo_id[0])
                titulo_projeto = obterColunaUnica('editalProjeto','titulo','id',idProjeto)
                orientador = obterColunaUnica('editalProjeto','nome','id',idProjeto)
                email = obterColunaUnica('editalProjeto','email','id',idProjeto)
                texto_email = render_template('confirmacao_indicacao.html',vaga=vaga,id_projeto=idProjeto,indicado=nome,proponente=orientador,titulo=titulo_projeto,email_proponente=email,idIndicacao=idIndicacao)
                assunto = "Plataforma Yoko - INDICAÇÃO DE BOLSISTA" if vaga==1 else "Plataforma Yoko - INDICAÇÃO DE VOLUNTARIO"
                if send_email_async([email, DEFAULT_INSTITUCIONAL], assunto, texto_email):
                    logger.info("E-mail enfileirado: {}", assunto)
                else:
                    logger.error("Erro ao enfileirar e-mail. Rota: /efetivarIndicacao")
                return(render_template('confirmacao_indicacao.html',vaga=vaga,id_projeto=idProjeto,indicado=nome,proponente=orientador,titulo=titulo_projeto,email_proponente=email,idIndicacao=idIndicacao))
            else:
                return ("Você já indicou todos os bolsistas/voluntários. Entrar em contato através do e-mail " + DEFAULT_SUPPORT)
        except Exception as e:
            logger.warning(e)
            return("ERRO!")
    else:
        return("OK")

@app.route("/admin/indicacoes", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def indicacoes():
    if request.method == "GET":
        #Recuperando código do edital
        if 'edital' in request.args:
            codigoEdital = str(request.args.get('edital'))
            descricao_edital = obterColunaUnica('editais','nome','id',codigoEdital)
            if 'tipo' in request.args:
                tipo_de_vaga = str(request.args.get('tipo'))
                consulta = f"""SELECT indicacoes.id,
                indicacoes.idProjeto, 
                indicacoes.nome,
                IF(indicacoes.modalidade=1,'PIBIC',IF(indicacoes.modalidade=2,'PIBITI','PIBIC-EM')),
                IF(tipo_de_vaga=1, 'BOLSISTA','VOLUNTÁRIO(A)'), 
                {sql_decifra('nome_banco', 'indicacoes')},
                {sql_decifra('agencia', 'indicacoes')},
                {sql_decifra('conta', 'indicacoes')}, 
                arquivo_cpf_rg,
                arquivo_extrato,
                arquivo_historico,
                arquivo_termo,
                DATE_FORMAT(indicacoes.inicio,'%d/%m/%Y'),
                DATE_FORMAT(indicacoes.fim,'%d/%m/%Y'), 
                editalProjeto.nome,
                editalProjeto.obs,
                editalProjeto.tipo,
                IF(indicacoes.fomento=0,'UFCA',IF(indicacoes.fomento=1,'CNPQ','FUNCAP')),
                CONVERT(AES_DECRYPT(FROM_BASE64(indicacoes.endereco),%s,iv,'AES-256-CBC'), CHAR),
                CONVERT(AES_DECRYPT(FROM_BASE64(indicacoes.celular),%s,iv,'AES-256-CBC'), CHAR),
                CONVERT(AES_DECRYPT(FROM_BASE64(indicacoes.telefone),%s,iv,'AES-256-CBC'), CHAR),
                DATE_FORMAT(CONVERT(AES_DECRYPT(FROM_BASE64(indicacoes.nascimento),%s,iv,'AES-256-CBC'), CHAR),'%d/%m/%Y'),
                CONVERT(AES_DECRYPT(FROM_BASE64(indicacoes.rg),%s,iv,'AES-256-CBC'), CHAR)
                FROM indicacoes,editalProjeto
                WHERE indicacoes.tipo_de_vaga=%s
                AND indicacoes.idProjeto=editalProjeto.id AND tipo=%s
                ORDER BY editalProjeto.tipo,editalProjeto.nome,indicacoes.id """
                parametros_consulta = (AES_KEY,) * 8 + (tipo_de_vaga, codigoEdital)
            else:
                consulta = f"""SELECT indicacoes.id,indicacoes.idProjeto, indicacoes.nome,IF(indicacoes.modalidade=1,'PIBIC',IF(indicacoes.modalidade=2,'PIBITI','PIBIC-EM')),
                IF(tipo_de_vaga=1, 'BOLSISTA','VOLUNTÁRIO(A)'), {sql_decifra('nome_banco', 'indicacoes')},{sql_decifra('agencia', 'indicacoes')},{sql_decifra('conta', 'indicacoes')}, arquivo_cpf_rg,arquivo_extrato,
                arquivo_historico,arquivo_termo,DATE_FORMAT(indicacoes.inicio,'%d/%m/%Y'),DATE_FORMAT(indicacoes.fim,'%d/%m/%Y'), editalProjeto.nome,editalProjeto.obs,
                editalProjeto.tipo,IF(indicacoes.fomento=0,'UFCA',IF(indicacoes.fomento=1,'CNPQ','FUNCAP'))
                FROM indicacoes,editalProjeto WHERE indicacoes.idProjeto=editalProjeto.id AND tipo=%s ORDER BY editalProjeto.tipo,editalProjeto.nome,indicacoes.id """
                parametros_consulta = (AES_KEY,) * 3 + (codigoEdital,)
            linhas,total = executarSelect2(consulta,valores=parametros_consulta)
            return(render_template('listar_indicacoes.html',listaIndicacoes=linhas,total=total,descricao=descricao_edital))
        else:
            return("OK")
    else:
        return("OK")

def esperar(arquivo):
    # Espera o tempo definido em segundos
    time.sleep(3)
    #check if file exists
    if os.path.exists(arquivo):
        #remove file
        try:
            os.remove(arquivo)
        except FileNotFoundError as e:
            logger.warning("Erro ao remover arquivo temporário (função esperar({})):{}",arquivo,str(e))
    if os.path.exists(arquivo + '.gpg'):
        #remove file
        try:
            os.remove(arquivo + '.gpg')
        except FileNotFoundError as e:
            logger.warning("Erro ao remover arquivo temporário (função esperar({})):{}",arquivo + '.gpg',str(e))

# prefixo no S3 -> (pasta local do caminho de transição, pasta absoluta do send_from_directory)
PREFIXOS_ARQUIVOS = {
    'submissoes': (SUBMISSOES_DIR, app.config['UPLOADED_SUBMISSOES_DEST']),
    'docs_indicacoes': (ATTACHMENTS_DIR, app.config['UPLOADED_DOCUMENTS_DEST']),
}
COLUNAS_ARQUIVOS_PROJETO = ('arquivo_projeto', 'arquivo_plano1', 'arquivo_plano2', 'arquivo_plano3',
                            'arquivo_lattes', 'arquivo_lattes_pdf', 'arquivo_comprovantes')

def objeto_s3_existe(chave):
    """head_object: 404 (ou 403, para credenciais sem s3:ListBucket, como as de dev) = não existe."""
    try:
        s3.head_object(Bucket=AWS_S3_BUCKET, Key=chave)
        return True
    except ClientError as e:
        if e.response.get('Error', {}).get('Code') in ('404', '403', 'NoSuchKey', 'NotFound'):
            return False
        raise

def url_download(prefixo, nome, quem):
    """
    Entrega um arquivo do S3 ('submissoes' ou 'docs_indicacoes'). Quem chama já autorizou o acesso.

    Caminho novo: objeto SSE-KMS sem .gpg -> redirect para URL assinada de 60 s.
    Caminho de transição: arquivo ainda em .gpg (enviado antes do deploy da fase 2) ->
    download, GPG em disco e remoção 3 s depois, como antes.
    """
    nome = secure_filename(nome)
    if not nome:
        return("Arquivo não encontrado!")
    pasta_local, pasta_envio = PREFIXOS_ARQUIVOS[prefixo]
    chave = 'pesquisa/' + pasta_local + nome
    try:
        if objeto_s3_existe(chave):
            url = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': AWS_S3_BUCKET, 'Key': chave,
                        'ResponseContentDisposition': f'inline; filename="{nome}"'},
                ExpiresIn=URL_DOWNLOAD_VALIDADE,
            )
            logger.info("[download] {} abriu {} (caminho novo)", quem, chave)
            return redirect(url)
        s3.download_file(AWS_S3_BUCKET, chave + '.gpg', pasta_local + nome + '.gpg')
        cripto.aes_gpg_decrypt_file(GPG_KEY, pasta_local + nome + '.gpg', pasta_local + nome)
        thread = threading.Thread(target=esperar, args=(pasta_local + nome,))
        thread.start()
        logger.info("[download] {} abriu {} (caminho antigo, .gpg)", quem, chave)
        return(send_from_directory(pasta_envio, nome))
    except Exception as e:
        logger.warning("[download] Erro ao recuperar arquivo {}: {}", chave, str(e))
        return("Arquivo não encontrado!")

def dono_do_arquivo(nome, siape):
    """True se o arquivo pertence a um projeto do siape (qualquer coluna de arquivo da editalProjeto)."""
    consulta = ("SELECT id FROM editalProjeto WHERE siape=%s AND %s IN ("
                + ",".join(COLUNAS_ARQUIVOS_PROJETO) + ") LIMIT 1")
    resultado = executarSelect2(consulta, valores=[siape, secure_filename(nome)])
    return resultado is not None and resultado[1] > 0

def link_arquivo_avaliador(nome):
    """Link de um arquivo de submissão para a página /avaliacao, válido por 30 dias."""
    return url_for('arquivo_assinado', token=assinador_arquivos.dumps({'p': 'submissoes', 'n': nome}))

@app.route("/admin/verArquivo", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def verArquivo():
    if request.method == "GET":
        #Recuperando arquivo
        if 'file' in request.args:
            return url_download('docs_indicacoes', str(request.args['file']), session['username'])
        else:
            return("OK")
    else:
        return("OK")

@app.route("/verArquivosProjeto/<filename>", methods=['GET'])
@log_required
def verArquivosProjeto(filename):
    """Arquivos dos projetos: só admin ou o dono do projeto. Avaliadores usam /arquivo/<token>."""
    if 'username' not in session:
        return render_template('login.html')
    if 'admin' not in session['roles'] and not dono_do_arquivo(filename, session['username']):
        flash('Você não tem permissão para acessar este recurso.','error')
        return redirect(url_for('home'))
    return url_download('submissoes', filename, session['username'])

@app.route("/arquivo/<token>", methods=['GET'])
@log_required
def arquivo_assinado(token):
    """Link dos avaliadores (gerado na página /avaliacao), sem login, válido por 30 dias."""
    try:
        dados = assinador_arquivos.loads(token, max_age=ARQUIVOS_LINK_VALIDADE)
        prefixo, nome = dados['p'], dados['n']
        if prefixo not in PREFIXOS_ARQUIVOS:
            raise BadSignature("prefixo inválido")
    except SignatureExpired:
        logger.info("[arquivo_assinado] Link expirado")
        return render_template('link_expirado.html'), 410
    except (BadSignature, KeyError, TypeError) as e:
        logger.warning("[arquivo_assinado] Link inválido: {}", str(e))
        return render_template('link_expirado.html'), 403
    quem = "avaliador " + hashlib.sha256(token.encode()).hexdigest()[:12]
    return url_download(prefixo, nome, quem)

@app.route("/admin/situacaoIndicacoes", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def situacaoIndicacoes():
    if request.method == "GET":
        if 'edital' in request.args:
            codigoEdital = str(request.args.get('edital'))
            descricao_edital = obterColunaUnica('editais','nome','id',codigoEdital)
            consulta = """(SELECT editalProjeto.tipo,editalProjeto.id,editalProjeto.nome,editalProjeto.ua,titulo,
                        bolsas,bolsas_concedidas,count(indicacoes.id) as nindicados,
                        GROUP_CONCAT(indicacoes.nome ORDER BY indicacoes.nome SEPARATOR '<BR><BR>') as indicados
                        FROM editalProjeto
                        LEFT JOIN indicacoes ON editalProjeto.id=indicacoes.idProjeto
                        WHERE tipo=%s AND valendo=1 AND bolsas_concedidas>0
                        AND indicacoes.tipo_de_vaga=1
                        GROUP BY editalProjeto.id) """
            consulta = consulta + """ UNION """
            consulta = consulta + """(SELECT editalProjeto.tipo,editalProjeto.id,editalProjeto.nome,editalProjeto.ua,titulo,
                                    bolsas,bolsas_concedidas,0 as nindicados,'SEM INDICAÇÕES' as indicados
                                    FROM editalProjeto LEFT JOIN indicacoes ON editalProjeto.id=indicacoes.idProjeto
                                    WHERE tipo=%s AND indicacoes.idProjeto is null
                                    AND valendo=1
                                    AND bolsas_concedidas>0)
                                    ORDER BY tipo,ua,bolsas_concedidas DESC, nindicados DESC,nome"""
            linhas,total = executarSelect2(consulta,valores=(codigoEdital,codigoEdital))
            return(render_template('situacaoIndicacoes.html',linhas=linhas,total=total,edital=descricao_edital))

        else:
            if 'ano' in request.args:
                ano = str(request.args.get('ano'))
                editais = tuplaDeEditais(ano)
                consulta = """(SELECT editalProjeto.tipo,editalProjeto.id,editalProjeto.nome,editalProjeto.ua,titulo,
                        bolsas,bolsas_concedidas,count(indicacoes.id) as nindicados,
                        GROUP_CONCAT(indicacoes.nome ORDER BY indicacoes.nome SEPARATOR '<BR><BR>') as indicados
                        FROM editalProjeto
                        LEFT JOIN indicacoes ON editalProjeto.id=indicacoes.idProjeto
                        WHERE tipo in """ + editais + """ AND valendo=1 AND bolsas_concedidas>0
                        AND indicacoes.tipo_de_vaga=1
                        GROUP BY editalProjeto.id) """
                consulta = consulta + """ UNION """
                consulta = consulta + """(SELECT editalProjeto.tipo,editalProjeto.id,editalProjeto.nome,editalProjeto.ua,titulo,
                                    bolsas,bolsas_concedidas,0 as nindicados,'SEM INDICAÇÕES' as indicados
                                    FROM editalProjeto LEFT JOIN indicacoes ON editalProjeto.id=indicacoes.idProjeto
                                    WHERE tipo in """ + editais + """ AND indicacoes.idProjeto is null
                                    AND valendo=1
                                    AND bolsas_concedidas>0)
                                    ORDER BY tipo,ua,bolsas_concedidas DESC, nindicados DESC,nome"""
                linhas,total = executarSelect(consulta)
                return(render_template('situacaoIndicacoes.html',linhas=linhas,total=total,edital=editais))
            else:
                return ("OK")
    else:
        return ("OK")


'''
Verifica se um determinado bolsista/voluntário é indicação do usuário que está logado atualmente.
'''
def verificarSiapeIndicacao(siape,idIndicacao):
    consulta = """SELECT indicacoes.id FROM indicacoes,editalProjeto WHERE indicacoes.idProjeto=editalProjeto.id AND editalProjeto.siape=%s
    AND indicacoes.id=%s"""

    linhas,total = executarSelect2(consulta,valores=(siape,idIndicacao))
    if (total>0):
        return (True)
    else:
        return(False)

'''
Verifica se a frequência do Mês atual já foi enviada
'''
def jaEnviouFrequenciaAtual(idAluno,mes,ano):
    consulta = """SELECT id FROM frequencias WHERE idIndicacao=%s AND mes=%s AND ano=%s"""
    linhas,total = executarSelect2(consulta,valores=(idAluno,mes,ano))
    if (total>0):
        return(True)
    else:
        return(False)


@app.route("/enviarFrequencia", methods=['GET', 'POST'])
@login_required(role='user')
@log_required
def enviarFrequencia():
    if request.method == "GET":
        if 'id' in request.args:
            idAluno = str(request.args.get('id'))
            siape = session['username']
            if verificarSiapeIndicacao(siape,idAluno): #O aluno é indicação do usuário atual
                from datetime import datetime
                nomeAluno = obterColunaUnica('indicacoes','nome','id',idAluno)
                idProjeto = obterColunaUnica('indicacoes','idProjeto','id',idAluno)
                titulo_projeto = obterColunaUnica('editalProjeto','titulo','id',idProjeto)
                codigoEdital = obterColunaUnica('editalProjeto','tipo','id',idProjeto)
                descricaoEdital = obterColunaUnica('editais','nome','id',codigoEdital)
                data_final = obterColunaUnica('indicacoes','ADDDATE(DATE(fim),INTERVAL 240 DAY)','id',idAluno)
                data_hoje = obterColunaUnica('indicacoes','DATE(NOW())','id',idAluno)
                if data_hoje>data_final:
                    return("Prazo para envio de frequencias expirado (%s)!" %(data_final))
                mes_ext = {1: 'janeiro', 2 : 'fevereiro', 3: 'marco', 4: 'abril', 5: 'maio', 6: 'junho', 7: 'julho',8: 'agosto', 9: 'setembro', 10: 'outubro', 11: 'novembro', 12: 'dezembro'}
                now = datetime.now()
                mesReferencia = now.month-1
                anoReferencia = now.year
                if (mesReferencia==0):
                    mesReferencia = 12
                    anoReferencia = anoReferencia-1
                #if jaEnviouFrequenciaAtual(idAluno,str(mesReferencia),str(anoReferencia)):
                #    return("A frequência atual já foi enviada, não é possível realizar um novo envio.")
                #else:
                return(render_template('frequencia.html',nomeAluno=nomeAluno,referencia=mes_ext[mesReferencia],ano=anoReferencia,idAluno=idAluno,titulo=titulo_projeto,mes=mesReferencia,edital=descricaoEdital))
            else:
                return("Permissão negada!")
        else:
            return("OK")
    else:
        return("OK")


@app.route("/cadastrarFrequencia", methods=['GET', 'POST'])
@login_required(role='user')
@log_required
def cadastrarFrequencia():
    if request.method == "POST":
        s1 = str(request.form['s1'])
        s2 = str(request.form['s2'])
        s3 = str(request.form['s3'])
        s4 = str(request.form['s4'])
        mes = str(request.form['mes'])
        ano = str(request.form['ano'])
        idAluno = str(request.form['idAluno'])
        obs = str(request.form['obs'])
        consulta_verificacao = """
        SELECT id FROM frequencias WHERE idIndicacao=%s AND mes=%s AND ano=%s
        """
        linhas,total = executarSelect2(consulta_verificacao,valores=(idAluno,mes,ano))
        if total>0:
            return("A frequência para o mes/ano solicitado já foi enviada anteriormente! Não é possível modificar!")
        consulta = """INSERT INTO frequencias (idIndicacao,mes,ano,s1,s2,s3,s4,obs) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"""
        valores = (idAluno,mes,ano,s1,s2,s3,s4,obs)
        inserir(consulta,valores)
        return redirect("/pesquisa/meusProjetos")
    else:
        return("OK")

def mes_ano_anterior():
    """Retorna (mes, ano) do mês anterior ao atual, como strings. Em janeiro, dezembro do ano anterior."""
    hoje = date.today()
    if hoje.month == 1:
        return "12", str(hoje.year - 1)
    return str(hoje.month - 1), str(hoje.year)

@app.route("/admin/listaNegra/<email>", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def listaNegra(email):
    mes, ano = mes_ano_anterior()
    consulta = """SELECT 
    indicacoes.id,
    indicacoes.nome,
    editalProjeto.nome,
    editalProjeto.email,
    indicacoes.email,
    editalProjeto.titulo,
    editalProjeto.id 
    FROM indicacoes,editalProjeto 
    WHERE indicacoes.idProjeto=editalProjeto.id AND indicacoes.fim>NOW() 
    ORDER BY editalProjeto.nome,indicacoes.id"""
    linhas,total = executarSelect(consulta)
    lista = []
    lista_emails = [DEFAULT_SUPPORT]
    lista_emails_discentes = []
    for linha in linhas:
        idIndicacao = str(linha[0])
        subconsulta = """SELECT id FROM frequencias WHERE mes=%s AND ano=%s AND idIndicacao=%s"""
        frequencias,totalFrequencias = executarSelect2(subconsulta,valores=(mes,ano,idIndicacao))
        dados = [str(linha[0]),str(linha[1]),str(linha[2])]
        if totalFrequencias==0:
            lista.append(dados)
            lista_emails.append(str(linha[3]))
            lista_emails_discentes.append(linha[4])
    
    if email=="1":
        t = threading.Thread(target=task_enviar_lembrete_frequencia)
        t.start()
        return("200")

    return(render_template('listaNegra.html',lista=tuple(lista),mes=mes,ano=ano,total=len(lista)))

def agora():
    from datetime import datetime as dt
    now = dt.now()
    tempo = now.strftime('%d/%m/%Y - %H:%M')
    return(tempo)

def timestamp():
    from datetime import datetime as dt
    now = dt.now()
    return(str(now))

@app.route("/desligarIndicacao/<id_indicacao>", methods=['GET', 'POST'])
@login_required(role='user')
@log_required
def desligarIndicacao(id_indicacao):
    idAluno = id_indicacao
    siape = session['username']
    if (autenticado()):
        if verificarSiapeIndicacao(siape,idAluno): #O aluno é indicação do usuário atual
            motivos = []
            for motivo in request.form:
                if 'op' in motivo:
                    motivos.append(str(request.form[motivo]))
            lista_motivos = ''
            for i in range(0,len(motivos),1):
                if motivos[i]!='' and motivos[i]!=' ':
                    if i<len(motivos)-1:
                        lista_motivos = lista_motivos + motivos[i] + ', '
                    else:
                        lista_motivos = lista_motivos + motivos[i]
            #atualizar coluna motivos em indicacoes
            consulta = "UPDATE indicacoes SET motivo=%s WHERE id=%s"
            atualizar2(consulta, valores=(lista_motivos, idAluno))

            #desligar a indicação
            idProjeto = obterColunaUnica('indicacoes','idProjeto','id',idAluno)
            orientador = obterColunaUnica('editalProjeto','nome','id',idProjeto)
            titulo = obterColunaUnica('editalProjeto','titulo','id',idProjeto)
            discente = obterColunaUnica('indicacoes','nome','id',idAluno)
            tipo_vaga = obterColunaUnica('indicacoes','tipo_de_vaga','id',idAluno)
            timestamp = agora()
            consulta = "UPDATE indicacoes SET situacao=1, fim=NOW() WHERE id=%s"
            atualizar2(consulta, valores=(idAluno,))
            email = obterColunaUnica('editalProjeto','email','id',idProjeto)
            texto_email = render_template('confirmacao_desligamento.html',vaga=tipo_vaga,id_projeto=idProjeto,proponente=orientador,titulo=titulo,indicado=discente,idIndicacao=idAluno,data=timestamp)
            assunto = "Plataforma Yoko - DESLIGAMENTO DE BOLSISTA" if tipo_vaga==1 else "Plataforma Yoko - DESLIGAMENTO DE VOLUNTARIO"
            enviar_email_desligamento_substituicao(email, assunto, texto_email)
            return(render_template('confirmacao_desligamento.html',vaga=tipo_vaga,id_projeto=idProjeto,proponente=orientador,titulo=titulo,indicado=discente,idIndicacao=idAluno,data=timestamp))
            
        else:
            return("ACESSO NEGADO")
    else:
        return(redirect(url_for('login')))

def enviar_email_desligamento_substituicao(email, assunto, texto_email):
    if send_email_async(email, assunto, texto_email):
        logger.info("E-mail enfileirado: {}", assunto)
    else:
        logger.error("Erro ao enfileirar e-mail. enviar_email_desligamento_substituicao")


@app.route("/substituirIndicacao/<id_indicacao>", methods=['GET', 'POST'])
@login_required(role='user')
@log_required
def substituirIndicacao(id_indicacao):
    idAluno = id_indicacao
    siape = session['username']
    if (autenticado()):
        if verificarSiapeIndicacao(siape,idAluno): #O aluno é indicação do usuário atual
            motivos = []
            for motivo in request.form:
                if 'op' in motivo:
                    motivos.append(str(request.form[motivo]))
            lista_motivos = ''
            for i in range(0,len(motivos),1):
                if motivos[i]!='' and motivos[i]!=' ':
                    if i<len(motivos)-1:
                        lista_motivos = lista_motivos + motivos[i] + ', '
                    else:
                        lista_motivos = lista_motivos + motivos[i]
            
            #atualizar coluna motivos em indicacoes
            consulta = "UPDATE indicacoes SET motivo=%s WHERE id=%s"
            atualizar2(consulta, valores=(lista_motivos, idAluno))

            idProjeto = obterColunaUnica('indicacoes','idProjeto','id',idAluno)
            orientador = obterColunaUnica('editalProjeto','nome','id',idProjeto)
            titulo = obterColunaUnica('editalProjeto','titulo','id',idProjeto)
            discente = obterColunaUnica('indicacoes','nome','id',idAluno)
            tipo_vaga = obterColunaUnica('indicacoes','tipo_de_vaga','id',idAluno)
            timestamp = agora()
            fomento = int(obterColunaUnica('indicacoes','fomento','id',idAluno))
            consulta = "UPDATE indicacoes SET situacao=2, fim=NOW() WHERE id=%s"
            atualizar2(consulta, valores=(idAluno,))
            email = obterColunaUnica('editalProjeto','email','id',idProjeto)
            texto_email = render_template('confirmacao_substituicao.html',vaga=tipo_vaga,id_projeto=idProjeto,proponente=orientador,titulo=titulo,indicado=discente,idIndicacao=idAluno,data=timestamp)
            assunto = "Plataforma Yoko - SUBSTITUIÇÃO DE BOLSISTA" if tipo_vaga=="1" else "Plataforma Yoko - SUBSTITUIÇÃO DE VOLUNTARIO"
            enviar_email_desligamento_substituicao(email, assunto, texto_email)
            edital = int(obterColunaUnica('editalProjeto','tipo','id',idProjeto))
            indicacao_inicio = str(obterColunaUnica('editais',"""DATE_FORMAT(indicacao_inicio,'%d/%m/%Y')""",'id',str(edital)))
            indicacao_fim = str(obterColunaUnica('editais',"""DATE_FORMAT(indicacao_termino,'%d/%m/%Y')""",'id',str(edital)))
            modalidade = int(obterColunaUnica('indicacoes','modalidade','id',idAluno))
            codigoSubstituido = int(idAluno)
            if (int(tipo_vaga)==1):
                return(render_template('indicacao.html',inicio=indicacao_inicio,fim=indicacao_fim,continua=1,modalidade=modalidade,vaga=1,idProjeto=idProjeto,plano=0,substituicao=1,substituido=codigoSubstituido))
            else:
                return(render_template('indicacao.html',inicio=indicacao_inicio,fim=indicacao_fim,continua=1,modalidade=modalidade,vaga=0,idProjeto=idProjeto,plano=0,substituicao=1,substituido=codigoSubstituido))
        else:
            return("ACESSO NEGADO")
    else:
        return(redirect(url_for('login')))


@app.route("/pub/consulta", methods=['GET', 'POST'])
@log_required
def consultas():
    if request.method == "POST":
        ua = str(request.form['ua'])
        inicio = str(request.form['inicio'])
        fim = str(request.form['fim'])
        exportacao = int(request.form['exportacao'])
        consulta = """

        SELECT editalProjeto.id,editais.nome,editalProjeto.ua,editalProjeto.titulo,editalProjeto.nome,
        GROUP_CONCAT('(',IF(indicacoes.fomento=0,'UFCA',IF(indicacoes.fomento=1,'CNPq','FUNCAP')),')',indicacoes.nome,' de ',date_format(indicacoes.inicio,'%d/%m/%Y'),' até ',date_format(indicacoes.fim,'%d/%m/%Y'),' (',IF(tipo_de_vaga=0,'VOLUNTÁRIO(A)','BOLSISTA'),') ' ORDER BY indicacoes.nome SEPARATOR '<BR><BR>') as discentes,
        (SELECT count(id) FROM indicacoes WHERE idProjeto=editalProjeto.id) as totalIndicacoes, DATE_FORMAT(editalProjeto.inicio,'%d/%m/%Y'),DATE_FORMAT(editalProjeto.fim,'%d/%m/%Y')

        FROM editalProjeto

        LEFT JOIN indicacoes on editalProjeto.id=indicacoes.idProjeto

		INNER JOIN editais on editalProjeto.tipo=editais.id

        """

        where = """ WHERE valendo=1 AND editalProjeto.fim>NOW() """
        valores = []

        if (ua!='TODOS'):
            where = where + " AND ua=%s "
            valores.append(ua)

        if ('andamento' in request.form):
            where = where + " AND editalProjeto.fim>NOW() "

        if (inicio!='TODOS'):
            where = where + " AND YEAR(editalProjeto.inicio)=%s "
            valores.append(inicio)

        if (fim!='TODOS'):
            where = where + " AND YEAR(editalProjeto.fim)=%s "
            valores.append(fim)

        final = """ GROUP BY editalProjeto.id ORDER BY ua,titulo"""

        consulta = consulta + where + final

        linhas,total = executarSelect2(consulta,valores=valores)

        if exportacao==0:
            return(render_template('resultados_consulta.html',linhas=linhas,total=total))
        else:
            try:
                import pandas as pd
                df = pd.DataFrame(list(linhas))
                df.to_csv(app.config['TEMP_FOLDER'] + 'resultados.csv', encoding="utf-8",header=['ID do projeto','EDITAL','UNIDADE ACADEMICA','TÍTULO','ORIENTADOR','INDICAÇÕES','TOTAL DE INDICAÇÕES','INICIO','FIM'])
                #df.to_csv(app.config['TEMP_FOLDER'] + 'resultados.csv', encoding="utf-8")
                return(send_from_directory(app.config['TEMP_FOLDER'], 'resultados.csv'))

            except:
                return("Erro!")
    else:
        return("OK")

@app.route("/admin/substituicoes", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def substituicoes():
    if 'id' in request.args:
        id = str(request.args.get('id'))
        descricao = obterColunaUnica('editais','nome','id',id)
        consulta1 = f"""SELECT indicacoes.id,idProjeto,editalProjeto.tipo,IF(tipo_de_vaga=1,'BOLSISTA','VOLUNARIO(A)') AS tipo,IF(indicacoes.situacao=1,'DESLIGADO(A)','SUBSTITUIDO(A)') AS tipo_situacao,indicacoes.nome,{sql_decifra('nome_banco', 'indicacoes')},{sql_decifra('agencia', 'indicacoes')},{sql_decifra('conta', 'indicacoes')}, DATE_FORMAT(indicacoes.inicio,'%d/%m/%Y') as inicio,
        DATE_FORMAT(indicacoes.fim,'%d/%m/%Y') as final,editalProjeto.nome FROM indicacoes,editalProjeto WHERE indicacoes.idProjeto=editalProjeto.id AND
        indicacoes.situacao in (1,2) AND editalProjeto.tipo=%s ORDER BY indicacoes.tipo_de_vaga DESC,indicacoes.fim DESC"""
        linhas,total = executarSelect2(consulta1,valores=(AES_KEY,) * 3 + (id,))


        consulta2 = f"""SELECT indicacoes.id,idProjeto,editalProjeto.tipo,IF(tipo_de_vaga=1,'BOLSISTA','VOLUNARIO(A)') AS tipo,IF(indicacoes.substituido!=0,'SUBSTITUTO(A)','N/A') AS tipo_situacao,indicacoes.nome,{sql_decifra('nome_banco', 'indicacoes')},{sql_decifra('agencia', 'indicacoes')},{sql_decifra('conta', 'indicacoes')}, DATE_FORMAT(indicacoes.inicio,'%d/%m/%Y') as inicio,
        DATE_FORMAT(indicacoes.fim,'%d/%m/%Y') as final,indicacoes.substituido,editalProjeto.nome FROM indicacoes,editalProjeto WHERE indicacoes.idProjeto=editalProjeto.id AND
        indicacoes.situacao in (0) AND indicacoes.substituido!=0 AND editalProjeto.tipo=%s ORDER BY indicacoes.tipo_de_vaga DESC,indicacoes.fim DESC"""

        linhas2,total2 = executarSelect2(consulta2,valores=(AES_KEY,) * 3 + (id,))
        return(render_template('substituicoes.html',linhas=linhas,linhas2=linhas2,total=total,total2=total2,edital=descricao))

    else:
        return("OK")

def gerarLinkAvaliacao():
    logger.info("Iniciando geração de links de avaliação...")
    consulta = """SELECT id,idProjeto,token FROM avaliacoes 
    WHERE idProjeto in (SELECT id FROM editalProjeto WHERE valendo=1) AND link="" ORDER BY id """
    linhas,total = executarSelect(consulta)
    for linha in linhas:
        id = str(linha[0])
        idProjeto = str(linha[1])
        token = str(linha[2])
        link = LINK_AVALIACAO + "?id=" + idProjeto + "&token=" + token
        consulta = "UPDATE avaliacoes SET link=%s WHERE id=%s"
        atualizar2(consulta, valores=(link, id))
    logger.info("Links de avaliação gerados com sucesso.")

@app.route("/admin/emailSolicitarAvaliacao", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
@limiter.limit("1 per day", key_func = lambda: 'global')
def email_solicitar_avaliacao():
    t = threading.Thread(target=task_enviar_email_avaliadores)
    t.start()
    return("Envio de e-mails iniciado!")
    
def enviarPedidoAvaliacao(idProjeto):
    gerarLinkAvaliacao()
    consulta = """
    SELECT e.id,e.titulo,e.resumo,a.avaliador,a.link,a.id,a.enviado,a.token,e.categoria,e.tipo
    FROM editalProjeto as e, avaliacoes as a WHERE e.id=a.idProjeto AND e.valendo=1
    AND a.finalizado=0 AND e.categoria=1 and e.id=%s
    ORDER BY a.id DESC LIMIT 1
    """
    linhas,total = executarSelect2(consulta,valores=(str(idProjeto),))
    
    for linha in linhas:
        titulo = str(linha[1])
        resumo = str(linha[2])
        link = str(linha[4])
        token = str(linha[7])
        email_avaliador = str(linha[3])
        link_recusa = ROOT_SITE + "/pesquisa/recusarConvite?token=" + token
        deadline = obterColunaUnica('editais',"DATE_FORMAT(deadline_avaliacao,'%d/%m/%Y')",'id',str(linha[9]))
        nome_longo = obterColunaUnica('editais','nome','id',str(linha[9]))
        with app.app_context():
            texto_email = render_template('email_avaliador.html',nome_longo=nome_longo,titulo=titulo,resumo=resumo,link=link,link_recusa=link_recusa,deadline=deadline)
            assunto = "CONVITE: AVALIAÇÃO DE PROJETO DE PESQUISA"
            if send_email_async(email_avaliador, assunto, texto_email):
                logger.info("E-mail enfileirado: {} para avaliador {}", assunto, email_avaliador)
            else:
                logger.error("EMAIL SOLICITANDO AVALIACAO FALHOU: {}", email_avaliador)

@app.route("/admin/arquivar/<id_projeto>", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def arquivar_projeto(id_projeto):
    projeto = str(id_projeto)
    consulta = "UPDATE editalProjeto SET valendo=0 WHERE id=%s"
    atualizar2(consulta, valores=(projeto,))
    edital = str(session['edital'])
    return(redirect(url_for('editalProjeto', edital=edital)))

@app.route("/admin/aprovar/projetos/<edital>", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def aprovar_projetos(edital):
    #RECOMENDADOS
    consulta1 = """UPDATE editalProjeto SET situacao=1
    WHERE id in (SELECT editalProjeto.id FROM editalProjeto,avaliacoes WHERE tipo=%s
    AND valendo=1 AND categoria=1 AND editalProjeto.id=avaliacoes.idProjeto
    GROUP BY editalProjeto.id
    HAVING sum(if(recomendacao=1,1,0))-sum(if(recomendacao=0,1,0))>0
    ORDER BY editalProjeto.ua,editalProjeto.id)
    """
    #NÃO RECOMENDADOS
    consulta2 = """UPDATE editalProjeto SET situacao=1
    WHERE id in (SELECT editalProjeto.id FROM editalProjeto,avaliacoes WHERE tipo=%s
    AND valendo=1 AND categoria=1 AND editalProjeto.id=avaliacoes.idProjeto
    GROUP BY editalProjeto.id
    HAVING sum(if(recomendacao=1,1,0))-sum(if(recomendacao=0,1,0))<=0
    ORDER BY editalProjeto.ua,editalProjeto.id)
    """

    atualizar2(consulta1, valores=(edital,))
    atualizar2(consulta2, valores=(edital,))
    flash("Projetos atualizados com sucesso")
    return(redirect("/pesquisa/admin"))

@app.route("/desligar/<id_indicacao>", methods=['GET', 'POST'])
@login_required(role='user')
@log_required
def desligar(id_indicacao):
    action = url_for('desligarIndicacao',id_indicacao=id_indicacao)
    return(render_template('desligamento_substituicao.html',id_indicacao=id_indicacao,operacao="DESLIGAMENTO",action=action))

@app.route("/substituir/<id_indicacao>", methods=['GET', 'POST'])
@login_required(role='user')
@log_required
def substituir(id_indicacao):
    action = url_for('substituirIndicacao',id_indicacao=id_indicacao)
    return(render_template('desligamento_substituicao.html',id_indicacao=id_indicacao,operacao="SUBSTITUIÇÃO",action=action))

@app.route("/get_bib/<siapes>", methods=['GET'])
@auth.login_required(role=['user'])
@log_required
def get_bib(siapes):
    lista_siapes = [s.strip() for s in siapes.split(',') if s.strip() != '']
    if not lista_siapes or not all(numero_valido(s) for s in lista_siapes):
        return "SIAPE inválido!"
    placeholders_siapes = ','.join(['%s'] * len(lista_siapes))
    consulta = """
    (SELECT UPPER(editalProjeto.nome),area_capes,UPPER(titulo), YEAR(editalProjeto.inicio) as ano,
    GROUP_CONCAT(IF(indicacoes.modalidade=1,'PIBIC',IF(indicacoes.modalidade=2,'PIBITI','PIBIC-EM')) LIMIT 1) as modalidade,
    palavras,bolsas as solicitadas,bolsas_concedidas as concedidas,
    (SELECT count(id) FROM indicacoes WHERE indicacoes.idProjeto=editalProjeto.id and indicacoes.tipo_de_vaga=1 and situacao=0) as bolsistas,
    (SELECT count(id) FROM indicacoes WHERE indicacoes.idProjeto=editalProjeto.id and indicacoes.tipo_de_vaga=0 and situacao=0) as voluntarios,
    (SELECT count(id)*400*12 FROM indicacoes WHERE indicacoes.idProjeto=editalProjeto.id and indicacoes.tipo_de_vaga=1 and situacao=0) as valores
    FROM `editalProjeto`
    LEFT JOIN indicacoes ON editalProjeto.id=indicacoes.idProjeto
    where valendo=1 and indicacoes.situacao=0
    and siape in (""" + placeholders_siapes + """)
    group by editalProjeto.id
    order by year(editalProjeto.inicio),editalProjeto.id)

    UNION

    (SELECT UPPER(nome_do_coordenador) as nome,
    "INDISPONÍVEL" as area_capes,
    UPPER(titulo_do_projeto) as titulo,
    YEAR(inicio) as ano,
    estudante_modalidade as modalidade,
    "INDISPONÍVEL" as palavras,
    "INDISPONÍVEL" as solicitadas,
    "INDISPONÍVEL" as concedidas,
    count(id) as bolsistas,
    "INDISPONÍVEL" as voluntarios,
    count(id)*400*12 as valores
    FROM cadastro_geral
    WHERE siape in (""" + placeholders_siapes + """) and estudante_tipo_de_vaga='BOLSISTA'
    GROUP BY titulo_do_projeto,ano
    ORDER BY ano,nome_do_coordenador)
    """
    linhas,total = executarSelect2(consulta,valores=lista_siapes + lista_siapes)
    dados = []
    for linha in linhas:
        dado = {'nome': linha[0],'area_capes': linha[1],'titulo': linha[2],'ano': linha[3],'modalidade': linha[4],'palavras': linha[5],'solicitadas': linha[6],'concedidas': linha[7],'bolsistas': linha[8],'voluntarios': linha[9],'valores': linha[10]}
        dados.append(dado)
    return Response(json.dumps(dados),  mimetype='application/json')

@app.route("/admin/auditoria_indicacoes", methods=['GET'])
@login_required(role='admin')
@log_required
def auditoria_indicacoes():
    
    from datetime import datetime
    ano_atual = str(datetime.now().year)
    consulta = """
        SELECT min(id) FROM `editais` WHERE year(deadline)=%s
    """
    linha,total = executarSelect2(consulta,valores=(ano_atual,))
    edital = str(linha[0][0])

    consulta = """
    SELECT GROUP_CONCAT(editalProjeto.tipo SEPARATOR ' - ') as editais,
    GROUP_CONCAT(indicacoes.idProjeto SEPARATOR ' - ') as ids_projetos,
    GROUP_CONCAT(IF(indicacoes.tipo_de_vaga=0,'VOLUNTARIO','BOLSISTA') SEPARATOR ' - ') as tipo_vaga,
    GROUP_CONCAT(IF(indicacoes.fomento=0,'UFCA',IF(indicacoes.fomento=1,'CNPq','FUNCAP')) SEPARATOR ' - ') as fomento,
    COUNT(indicacoes.id) as total,
    indicacoes.nome as indicado,
    GROUP_CONCAT(indicacoes.id SEPARATOR ' - ') as ids_indicados,
    GROUP_CONCAT(editalProjeto.titulo SEPARATOR ' - ') as titulos,
    GROUP_CONCAT(editalProjeto.nome SEPARATOR ' - ') as proponentes
    FROM `indicacoes`
    INNER JOIN editalProjeto ON indicacoes.idProjeto=editalProjeto.id
    WHERE editalProjeto.tipo>=%s and editalProjeto.valendo=1
    GROUP BY indicacoes.nome
    HAVING total>1
    """
    linhas,total = executarSelect2(consulta,valores=(edital,))
    
    return(render_template('indicacoes_duplicadas.html',linhas=linhas,total=total,edital=edital,ano=ano_atual))

@app.route("/indicacao/<cpf>", methods=['GET'])
@log_required
def get_dados_indicacao(cpf):
    cpf_corrigido = cpf
    cpf_corrigido = cpf_corrigido[:3] + '.' + cpf_corrigido[3:]
    cpf_corrigido = cpf_corrigido[:7] + '.' + cpf_corrigido[7:]
    cpf_corrigido = cpf_corrigido[:11] + '-' + cpf_corrigido[11:]
    consulta = f"""
    SELECT upper(indicacoes.nome),
    indicacoes.email,
    IF(indicacoes.modalidade=1,'PIBIC',IF(indicacoes.modalidade=2,'PIBITI','PIBIC-EM')) as modalidade,
    tipo_de_vaga,
    fomento,
    idProjeto,
    CONCAT('(',YEAR(editalProjeto.data),') ',editalProjeto.titulo,' (',upper(editalProjeto.nome),')') as dados
    FROM indicacoes
    INNER JOIN editalProjeto
    ON indicacoes.idProjeto=editalProjeto.id
    WHERE editalProjeto.valendo=1 AND
    {sql_busca_cpf('indicacoes')}
    ORDER BY indicacoes.id DESC
    """
    # O hash usa só os dígitos; o cpf_corrigido (com pontuação) serve às linhas ainda não cifradas
    linhas,total = executarSelect2(consulta,valores=valores_busca_cpf(cpf_corrigido)) if len(normalizar_cpf(cpf)) == 11 else ([], 0)
    dados = []
    for linha in linhas:
        dado = {'nome': linha[0],'email': linha[1],'modalidade': linha[2],'tipo_vinculo': linha[3],'fomento': linha[4],'idProjeto': linha[5],'dados': linha[6]}
        dados.append(dado)
    resp = Response(json.dumps(dados),  mimetype='application/json')
    resp.headers['Access-Control-Allow-Origin'] = '*'
    #return Response(json.dumps(dados),  mimetype='application/json')
    return resp

@app.route("/projetos_discente", methods=['GET','POST'])
@log_required
@limiter.limit("30/day;10/hour;3/minute",methods=["POST"])
@exigir_turnstile('get_projetos_discente')
def get_projetos_discente():
    if request.method == "GET":
        return (render_template('projetos.html'))
    else:
        try:
            if not nome_valido(str(request.form['txtNome'])):
                return "Nome inválido. Por favor, verifique o nome digitado."
            projetosAluno,projetosAluno2019 = gerarProjetosPorAluno(str(request.form['txtNome']))
            return render_template('alunos.html',listaProjetos=projetosAluno,lista2019=projetosAluno2019)
        except Exception as e:
            logger.warning("Erro ao gerar projetos por aluno")
            logger.warning(str(e))
            return render_template("Erro ao gerar projetos por aluno (/projetos_discente)")

@app.route("/admin/argon2", methods=['GET'])
@login_required(role='admin')
@log_required
def hash_passwords():
    consulta = """
    SELECT id,password FROM users 
    WHERE password not like "%argon%" 
    ORDER BY id
    """
    linhas,total = executarSelect(consulta)
    for linha in linhas:
        idUsuario = str(linha[0])
        password = str(linha[1])
        hashed_password = cripto.hash_argon2id(password)
        consulta = """UPDATE users SET password= %s WHERE id= %s"""
        atualizar2(consulta, valores=[hashed_password, idUsuario])
    return("OK\n")

def cadastrar_novo_usuario(siape, nome, email):
    """Cadastra o usuário na tabela users e, em produção, no Cognito, que envia o convite
    (senha provisória) por e-mail. A senha local é aleatória e descartada."""
    hashed_password = cripto.hash_argon2id(generate_secure_password())
    role = 'user'
    consulta = """INSERT INTO users (username,nome,email,password,roles) 
    VALUES (%s, %s, %s, %s, %s)"""
    atualizar2(consulta,valores=[siape, nome, email, hashed_password, role])
    if USAR_COGNITO:
        linha = buscar_usuario(siape)
        if linha is None:
            raise RuntimeError(f"Usuário {siape} não encontrado após o cadastro")
        cognito_convidar_usuario(linha)

@app.route("/admin/cadastrar_usuario", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def cadastrar_usuario():
    if request.method == 'POST':
        #Recebendo siape, nome e email do formulário
        siape = str(request.form['siape'])
        nome = str(request.form['nome'])
        email = str(request.form['email'])
        #Verificando se o usuário já existe
        consulta = """SELECT id FROM users WHERE username= %s """
        linhas,total = executarSelect2(consulta, valores=[siape])
        if total > 0:
            flash("Usuário já cadastrado!")
            return redirect(url_for('cadastrar_usuario'))
        #Verificando se o e-mail já está cadastrado
        consulta = """SELECT id FROM users WHERE email= %s """
        linhas,total = executarSelect2(consulta, valores=[email])
        if total > 0:
            flash("E-mail já cadastrado!")
            return redirect(url_for('cadastrar_usuario'))
        #Cadastrando novo usuário no banco de dados
        try:
            cadastrar_novo_usuario(siape, nome, email)
        except Exception as e:
            logger.warning("Erro ao cadastrar novo usuário")
            logger.warning(str(e))
            flash("Erro ao cadastrar usuário. Se ele aparecer na lista de usuários, use \"Redefinir senha\" em Alterar para enviar o acesso.")
            return redirect(url_for('cadastrar_usuario'))
        if USAR_COGNITO:
            flash("Usuário cadastrado com sucesso! O convite foi enviado por e-mail.")
        else:
            flash("Usuário cadastrado com sucesso!")
        return redirect(url_for('admin'))
    else:
        return render_template('cadastrar_usuario.html')

@app.route("/admin/cadastrar_usuarios_projetos/<edital>", methods=['GET'])
@login_required(role='admin')
@log_required
def cadastrar_usuarios_projetos(edital):
    """
    Cadastra novos usuários no sistema a partir dos dados dos 
    projetos do edital especificado.
    """
    consulta = """
    SELECT 
    nome,
    siape,
    email 
    FROM editalProjeto 
    WHERE tipo= %s AND 
    valendo=1 
    AND CONVERT(siape USING utf8) NOT IN (SELECT username FROM users) 
    AND email NOT IN (SELECT email FROM users) 
    ORDER BY id
    """
    linhas,total = executarSelect2(consulta,valores=[edital])
    if total > 0:
        for linha in linhas:
            siape = str(linha[1])
            nome = str(linha[0])
            email = str(linha[2])
            try:
                cadastrar_novo_usuario(siape, nome, email)
            except Exception as e:
                logger.warning("Erro ao cadastrar usuário do projeto")
                logger.warning(str(e))
                flash("Erro ao cadastrar usuário: " + nome + " (" + siape + ")")
        flash(f"{total} usuários cadastrados com sucesso!")
        return redirect(url_for('admin'))
    else:
        flash("Nenhum usuário encontrado para cadastro.")
        return redirect(url_for('admin'))

@app.route("/admin/listarUsuarios", methods=['GET'])
@login_required(role='admin')
@log_required
def listar_usuarios():
    """
    Lista todos os usuários cadastrados no sistema.
    """
    consulta = """SELECT id, username, nome, email, roles, migrado FROM users ORDER BY nome"""
    linhas, total = executarSelect2(consulta, valores=[])
    return render_template('listarUsuarios.html', usuarios=linhas, total=total)

@app.route("/admin/alterarUsuario/<int:id>", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def alterar_usuario(id):
    """
    Permite ao admin alterar dados de um usuário existente.
    """
    if request.method == 'POST':
        nome = str(request.form['nome'])
        email = str(request.form['email'])
        roles = str(request.form['roles'])
        resetar_senha = request.form.get('resetar_senha')
        consulta = """SELECT id FROM users WHERE email=%s AND id != %s"""
        linhas, total = executarSelect2(consulta, valores=[email, id])
        if total > 0:
            flash("E-mail já cadastrado para outro usuário.", 'error')
            return redirect(url_for('alterar_usuario', id=id))
        try:
            atualizar2("""UPDATE users SET nome=%s, email=%s, roles=%s WHERE id=%s""",
                       valores=[nome, email, roles, id])
        except Exception as e:
            logger.warning("Erro ao alterar usuário id={}: {}", id, str(e))
            flash("Erro ao alterar usuário.", 'error')
            return redirect(url_for('alterar_usuario', id=id))
        linha = buscar_usuario(id, 'id') if USAR_COGNITO else None
        if linha is not None and int(linha[5]) == 1:
            try:
                cognito_sincronizar_atributos(linha)
            except (ClientError, BotoCoreError):
                flash("Dados alterados localmente, mas houve erro ao atualizar o Cognito.", 'error')
        if resetar_senha:
            if not USAR_COGNITO:
                flash("A redefinição de senha pelo Cognito está disponível apenas em produção.", 'error')
            elif linha is not None:
                try:
                    tipo = cognito_iniciar_recuperacao(linha, origem='reset_admin')
                    if tipo == 'convite':
                        flash("O convite ainda não havia sido usado e foi reenviado por e-mail.")
                    else:
                        flash("Senha redefinida. Um código para definir a nova senha foi enviado ao e-mail do usuário.")
                except (ClientError, BotoCoreError):
                    flash("Erro ao redefinir a senha no Cognito.", 'error')
        flash("Usuário alterado com sucesso!")
        return redirect(url_for('listar_usuarios'))
    else:
        consulta = """SELECT id, username, nome, email, roles FROM users WHERE id=%s"""
        linhas, total = executarSelect2(consulta, valores=[id])
        if total == 0:
            flash("Usuário não encontrado.", 'error')
            return redirect(url_for('listar_usuarios'))
        return render_template('alterarUsuario.html', usuario=linhas[0])

@app.route("/admin/listarEditais", methods=['GET'])
@login_required(role='admin')
@log_required
def listar_editais():
    """
    Lista todos os editais cadastrados no sistema.
    """
    consulta = """SELECT id, nome,
        DATE_FORMAT(deadline,'%d/%m/%Y %H:%i'),
        DATE_FORMAT(indicacao_inicio,'%d/%m/%Y %H:%i'),
        DATE_FORMAT(indicacao_termino,'%d/%m/%Y %H:%i')
        FROM editais ORDER BY id DESC"""
    linhas, total = executarSelect2(consulta, valores=[])
    return render_template('listarEditais.html', editais=linhas, total=total)

@app.route("/admin/inserirEdital", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def inserir_edital():
    """
    Permite ao admin inserir um novo edital.
    """
    if request.method == 'POST':
        nome = str(request.form['nome'])
        deadline = str(request.form['deadline'])
        deadline_avaliacao = str(request.form['deadline_avaliacao'])
        setor = int(request.form['setor'])
        mensagem = str(request.form['mensagem'])
        indicacao_inicio = str(request.form['indicacao_inicio'])
        indicacao_termino = str(request.form['indicacao_termino'])
        discente_inicio = str(request.form['discente_inicio'])
        discente_fim = str(request.form['discente_fim'])
        try:
            consulta = """INSERT INTO editais
                (nome, deadline, deadline_avaliacao, setor, mensagem,
                 indicacao_inicio, indicacao_termino, discente_inicio, discente_fim)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            atualizar2(consulta, valores=[nome, deadline, deadline_avaliacao, setor, mensagem,
                indicacao_inicio, indicacao_termino, discente_inicio, discente_fim])
        except Exception as e:
            logger.warning("Erro ao inserir edital: {}", str(e))
            flash("Erro ao inserir edital.", 'error')
            return redirect(url_for('inserir_edital'))
        flash("Edital inserido com sucesso!")
        return redirect(url_for('listar_editais'))
    else:
        return render_template('inserirEdital.html')

@app.route("/admin/alterarEdital/<int:id>", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def alterar_edital(id):
    """
    Permite ao admin alterar os dados de um edital existente.
    """
    if request.method == 'POST':
        nome = str(request.form['nome'])
        deadline = str(request.form['deadline'])
        deadline_avaliacao = str(request.form['deadline_avaliacao'])
        setor = int(request.form['setor'])
        mensagem = str(request.form['mensagem'])
        indicacao_inicio = str(request.form['indicacao_inicio'])
        indicacao_termino = str(request.form['indicacao_termino'])
        discente_inicio = str(request.form['discente_inicio'])
        discente_fim = str(request.form['discente_fim'])
        try:
            consulta = """UPDATE editais
                SET nome=%s, deadline=%s, deadline_avaliacao=%s, setor=%s, mensagem=%s,
                    indicacao_inicio=%s, indicacao_termino=%s,
                    discente_inicio=%s, discente_fim=%s
                WHERE id=%s"""
            atualizar2(consulta, valores=[nome, deadline, deadline_avaliacao, setor, mensagem,
                indicacao_inicio, indicacao_termino, discente_inicio, discente_fim, id])
        except Exception as e:
            logger.warning("Erro ao alterar edital id={}: {}", id, str(e))
            flash("Erro ao alterar edital.", 'error')
            return redirect(url_for('alterar_edital', id=id))
        flash("Edital alterado com sucesso!")
        return redirect(url_for('listar_editais'))
    else:
        consulta = """SELECT id, nome, setor, mensagem,
            DATE_FORMAT(deadline,'%Y-%m-%dT%H:%i'),
            DATE_FORMAT(deadline_avaliacao,'%Y-%m-%dT%H:%i'),
            DATE_FORMAT(indicacao_inicio,'%Y-%m-%dT%H:%i'),
            DATE_FORMAT(indicacao_termino,'%Y-%m-%dT%H:%i'),
            DATE_FORMAT(discente_inicio,'%Y-%m-%dT%H:%i'),
            DATE_FORMAT(discente_fim,'%Y-%m-%dT%H:%i')
            FROM editais WHERE id=%s"""
        linhas, total = executarSelect2(consulta, valores=[id])
        if total == 0:
            flash("Edital não encontrado.", 'error')
            return redirect(url_for('listar_editais'))
        return render_template('alterarEdital.html', edital=linhas[0])

@app.route("/admin/listarProjetos", methods=['GET'])
@login_required(role='admin')
@log_required
def listar_projetos():
    """
    Lista os projetos de um edital (valendo=1), filtrado por ?edital=<id>.
    """
    codigoEdital = request.args.get('edital', '')
    if not codigoEdital:
        return redirect(url_for('admin'))
    consulta = """SELECT id, nome, siape, ua,
        LEFT(titulo, 60),
        CASE categoria WHEN 1 THEN 'Novo' WHEN 0 THEN 'Em andamento' ELSE '-' END,
        CASE situacao WHEN -1 THEN 'Não avaliado' WHEN 0 THEN 'Não recomendado'
            WHEN 1 THEN 'Recomendado' ELSE '-' END,
        IF(valendo=1,'Sim','Não'),
        scorelattes
        FROM editalProjeto WHERE tipo=%s AND valendo=1 ORDER BY ua, nome"""
    linhas, total = executarSelect2(consulta, valores=[codigoEdital])
    return render_template('listarProjetos.html', projetos=linhas, total=total, codigoEdital=codigoEdital)

@app.route("/admin/alterarProjeto/<int:id>", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def alterar_projeto(id):
    """
    Permite ao admin alterar os dados de um projeto existente.
    """
    if request.method == 'POST':
        nome = str(request.form['nome'])
        siape = int(request.form['siape'])
        email = str(request.form['email'])
        ua = str(request.form['ua'])
        grande_area = str(request.form['grande_area'])
        area_capes = str(request.form['area_capes'])
        grupo = str(request.form['grupo'])
        produtividade = int(request.form['produtividade'])
        scorelattes = float(request.form['scorelattes'])
        scorelattes_detalhado = str(request.form['scorelattes_detalhado'])
        titulo = str(request.form['titulo'])
        resumo = str(request.form['resumo'])
        palavras = str(request.form['palavras'])
        justificativa = str(request.form['justificativa'])
        ods = str(request.form['ods'])
        pesquisadores_vinculados = str(request.form['pesquisadores_vinculados'])
        autorizacoes = str(request.form['autorizacoes'])
        validade = int(request.form['validade'])
        categoria = int(request.form['categoria'])
        modalidade = int(request.form['modalidade'])
        inicio = str(request.form['inicio'])
        fim = str(request.form['fim'])
        bolsas = int(request.form['bolsas'])
        bolsas_concedidas = int(request.form['bolsas_concedidas'])
        transporte = int(request.form['transporte'])
        situacao = int(request.form['situacao'])
        inovacao = int(request.form['inovacao'])
        valendo = int(request.form['valendo'])
        obs = str(request.form['obs'])
        tipo = str(request.form.get('tipo_readonly', ''))
        try:
            consulta = """UPDATE editalProjeto SET
                nome=%s, siape=%s, email=%s, ua=%s, grande_area=%s, area_capes=%s, grupo=%s,
                produtividade=%s, scorelattes=%s, scorelattes_detalhado=%s,
                titulo=%s, resumo=%s, palavras=%s, justificativa=%s, ods=%s,
                pesquisadores_vinculados=%s, autorizacoes=%s, validade=%s,
                categoria=%s, modalidade=%s, inicio=%s, fim=%s,
                bolsas=%s, bolsas_concedidas=%s, transporte=%s,
                situacao=%s, inovacao=%s, valendo=%s, obs=%s
                WHERE id=%s"""
            atualizar2(consulta, valores=[nome, siape, email, ua, grande_area, area_capes, grupo,
                produtividade, scorelattes, scorelattes_detalhado,
                titulo, resumo, palavras, justificativa, ods,
                pesquisadores_vinculados, autorizacoes, validade,
                categoria, modalidade, inicio, fim,
                bolsas, bolsas_concedidas, transporte,
                situacao, inovacao, valendo, obs, id])
        except Exception as e:
            logger.warning("Erro ao alterar projeto id={}: {}", id, str(e))
            flash("Erro ao alterar projeto.", 'error')
            return redirect(url_for('alterar_projeto', id=id))
        # Processamento dos arquivos
        campos_arquivo = [
            ('arquivo_projeto',      'projeto'),
            ('arquivo_plano1',       'plano1'),
            ('arquivo_plano2',       'plano2'),
            ('arquivo_plano3',       'plano3'),
            ('arquivo_lattes',       'lattes'),
            ('arquivo_lattes_pdf',   'lattes_pdf'),
            ('arquivo_comprovantes', 'comprovantes'),
        ]
        for campo, prefixo in campos_arquivo:
            arq = request.files.get(campo)
            if arq and arq.filename != '' and allowed_file(arq.filename):
                filename_atual = str(request.form.get(campo + '_atual', '0'))
                if not filename_atual or filename_atual == '0' or filename_atual == 'None':
                    ext = arq.filename.rsplit('.', 1)[1].lower()
                    filename = prefixo + "_" + str(id) + "_" + str(siape) + "_" + id_generator() + "." + ext
                else:
                    filename = filename_atual
                arq.filename = filename
                filename = secure_filename(filename)
                try:
                    if not enviar_arquivo_s3(arq, 'submissoes', filename):
                        raise RuntimeError("envio ao S3 falhou")
                    atualizar2("UPDATE editalProjeto SET " + campo + "=%s WHERE id=%s", valores=[filename, id])
                except Exception as e:
                    logger.warning("Erro ao salvar arquivo {} do projeto id={}: {}", campo, id, str(e))
                    flash("Erro ao salvar arquivo " + campo + ".", 'error')
        flash("Projeto alterado com sucesso!")
        return redirect(url_for('listar_projetos', edital=tipo))
    else:
        consulta = """SELECT id, nome, siape, email, ua, grande_area, area_capes, grupo,
            produtividade, scorelattes, scorelattes_detalhado, titulo, resumo, palavras,
            justificativa, ods, pesquisadores_vinculados, autorizacoes, validade,
            categoria, modalidade,
            DATE_FORMAT(inicio,'%Y-%m-%d'), DATE_FORMAT(fim,'%Y-%m-%d'),
            bolsas, bolsas_concedidas, transporte, situacao, inovacao, valendo, obs, tipo,
            arquivo_projeto, arquivo_plano1, arquivo_plano2, arquivo_plano3,
            arquivo_lattes, arquivo_lattes_pdf, arquivo_comprovantes
            FROM editalProjeto WHERE id=%s"""
        linhas, total = executarSelect2(consulta, valores=[id])
        if total == 0:
            flash("Projeto não encontrado.", 'error')
            return redirect(url_for('admin'))
        return render_template('alterarProjeto.html', projeto=linhas[0])

@app.route("/admin/recalcularScoreLattes/<int:id>", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def recalcular_score_lattes(id):
    """
    Permite ao admin recalcular o scorelattes de um projeto informando o CPF ou IdLattes.
    """
    consulta = """SELECT area_capes, tipo FROM editalProjeto WHERE id=%s"""
    linhas, total = executarSelect2(consulta, valores=[id])
    if total == 0:
        flash("Projeto não encontrado.", 'error')
        return redirect(url_for('admin'))
    area_capes = str(linhas[0][0])
    tipo = str(linhas[0][1])
    if request.method == 'POST':
        cpf = str(request.form['cpf']).strip()
        t = threading.Thread(target=atualizarPontuacaoLattes, args=(cpf, area_capes, id,))
        t.start()
        logger.info("Recálculo de scorelattes solicitado para o projeto id={}", id)
        flash("Cálculo da pontuação Lattes solicitado. O valor será atualizado em breve.")
        return redirect(url_for('listar_projetos', edital=tipo))
    return render_template('recalcularScoreLattes.html', id=id, tipo=tipo)

def task_enviar_email_avaliadores():
    gerarLinkAvaliacao()
    consulta = """
    SELECT e.id,e.titulo,e.resumo,a.avaliador,a.link,a.id,a.enviado,a.token,e.categoria,
    e.tipo, DATEDIFF(NOW(),a.data_envio) as enviados,DATE_FORMAT(ed.deadline_avaliacao,'%d/%m/%Y') as deadline_avaliacao,ed.nome,
    e.justificativa
    FROM editalProjeto as e, avaliacoes as a,editais as ed WHERE e.id=a.idProjeto AND e.tipo=ed.id AND e.valendo=1
    AND a.finalizado=0 AND a.aceitou!=0 AND e.categoria=1 AND DATEDIFF(NOW(),a.data_envio)>1 
    AND a.idProjeto 
    IN (SELECT id FROM resumoGeralAvaliacoes WHERE ((aceites+rejeicoes<2) OR (aceites=rejeicoes)) 
    AND tipo in (SELECT id from editais WHERE deadline_avaliacao>now() AND ADDDATE(deadline,5)<now()))
    """
    linhas,total = executarSelect(consulta)
    assunto = "CONVITE: AVALIAÇÃO DE PROJETO DE PESQUISA"
    with app.app_context():
        for linha in linhas:
            titulo = str(linha[1])
            resumo = str(linha[2])
            link = str(linha[4])
            token = str(linha[7])
            email_avaliador = str(linha[3])
            justificativa = str(linha[13])
            if 'TESTE' in email_avaliador:
                continue
            link_recusa = ROOT_SITE + "/pesquisa/recusarConvite?token=" + token
            deadline = str(linha[11])
            nome_longo = str(linha[12])
            url_declaracao = SERVER_URL + URL_PREFIX + '/declaracaoAvaliador/' + token
            texto_email = render_template('email_avaliador.html',nome_longo=nome_longo,titulo=titulo,resumo=resumo,link=link,link_recusa=link_recusa,deadline=deadline,url_declaracao=url_declaracao,justificativa=justificativa)
            if send_email_async(email_avaliador, assunto, texto_email):
                logger.info("E-mail enfileirado: {} para o avaliador {}", assunto, email_avaliador)
                consulta_update = "UPDATE avaliacoes SET enviado=enviado+1,data_envio=NOW() WHERE id=%s"
                atualizar2(consulta_update, valores=(str(linha[5]),))
            else:
                logger.error("Erro ao enfileirar e-mail para {}", email_avaliador)
    logger.info("Tarefa de envio de e-mails para avaliadores concluída com sucesso.")

@scheduler.task('cron', id='do_job_enviar_email_avaliadores', week='*', day_of_week='2', hour='20', minute='05')
def job_enviar_email_avaliadores():
    """
    Tarefa agendada para enviar e-mails de solicitação de avaliação
    aos avaliadores cadastrados no sistema.
    """
    try:
        logger.info("Iniciando tarefa de envio de e-mails para avaliadores.")
        task_enviar_email_avaliadores()
    except Exception as e:
        logger.error("Erro ao executar tarefa de envio de e-mails para avaliadores: {}", str(e))

def task_enviar_lembrete_frequencia():
    mes, ano = mes_ano_anterior()
    nome_mes = {
            '1': 'janeiro',
            '2': 'fevereiro',
            '3': 'marco',
            '4': 'abril',
            '5': 'maio',
            '6': 'junho',
            '7': 'julho',
            '8': 'agosto',
            '9': 'setembro',
            '10': 'outubro',
            '11': 'novembro',
            '12': 'dezembro'
        }
    consulta = """SELECT
        GROUP_CONCAT(editalProjeto.id ORDER BY editalProjeto.id),
        editalProjeto.nome,
        GROUP_CONCAT(editalProjeto.titulo),
        GROUP_CONCAT(indicacoes.id ORDER BY indicacoes.idProjeto,indicacoes.id),
        editalProjeto.email,
        editalProjeto.siape
        from editalProjeto
        INNER JOIN indicacoes ON editalProjeto.id=indicacoes.idProjeto
        WHERE indicacoes.fim>NOW()
        AND indicacoes.situacao=0
        AND MONTH(indicacoes.inicio)!=Month(now())
        AND indicacoes.inicio<NOW()
        GROUP BY editalProjeto.nome"""
    linhas,total = executarSelect(consulta)
    assunto = "Plataforma Yoko PIICT- LEMBRETE DE ENVIO DE FREQUÊNCIA"
    with app.app_context():
        for linha in linhas:
            orientador = str(linha[1])
            siape = str(linha[5])
            indicacoes = str(linha[3]).split(',')
            nao_enviados = []
            for indicacao in indicacoes:
                subconsulta = """SELECT
                idIndicacao
                FROM frequencias
                WHERE mes=%s AND ano=%s AND idIndicacao=%s
                LIMIT 1
                """
                frequencias,totalFrequencias = executarSelect2(subconsulta,valores=(mes,ano,indicacao))
                if totalFrequencias==0: #Não foi enviada a frequência para este discente
                    nome_indicado = obterColunaUnica('indicacoes','nome','id',indicacao)
                    nao_enviados.append(nome_indicado)
            if len(nao_enviados)==0:
                continue
            texto_email = render_template('lembrete_frequencia.html',mes=str(nome_mes[str(mes)]),ano=ano,nomes=nao_enviados,usuario=siape)
            if send_email_async(str(linha[4]), assunto, texto_email):
                logger.info("E-mail enfileirado: Lembrete de frequência {}/{} para {}",nome_mes[str(mes)],ano,orientador)
            else:
                logger.error("Erro ao enfileirar e-mail. task_enviar_lembrete_frequencia: {}",orientador)

@scheduler.task('cron', id='do_job_cobrar_frequencia', week='*', day='5-30/10', hour='12', minute='10')
def job_cobrar_frequencia():
    """
    Tarefa agendada para enviar lembretes de frequência aos orientadores
    dos projetos de pesquisa.
    """
    try:
        logger.info("Iniciando tarefa de envio de lembretes de frequência.")
        task_enviar_lembrete_frequencia()
        logger.info("Tarefa de envio de lembretes de frequência concluída com sucesso.")
    except Exception as e:
        logger.error("Erro ao executar tarefa de envio de lembretes de frequência: {}", str(e))

@scheduler.task('cron', id='do_job_expurgo_retencao', day='1', hour='21', minute='0')
def job_expurgo_retencao():
    """
    Retenção de 6 anos após o fim da bolsa (modules/retencao.py): apaga os documentos da indicação no S3
    e anonimiza os dados pessoais dos estudantes. No máximo 500 linhas por tabela a cada mês.
    Também apaga da tabela acessos os registros com mais de 2 anos (o prazo dos logs).
    Em dev (PRODUCAO!=1) não toca no S3.
    """
    conectar = lambda: MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE, ssl="required")
    try:
        expurgar_dados_estudantes(conectar, s3=s3 if PRODUCAO == 1 else None, bucket=AWS_S3_BUCKET, limite=500)
    except Exception as e:
        logger.error("[retencao] Erro na tarefa de expurgo: {}", type(e).__name__)
    try:
        expurgar_acessos(conectar)
    except Exception as e:
        logger.error("[retencao] Erro no expurgo da tabela acessos: {}", type(e).__name__)

@app.route("/admin/ligarScheduler", methods=['GET'])
@login_required(role='admin')
@log_required
def ligar_scheduler():
    """
    Liga o scheduler para execução de tarefas agendadas.
    """
    if PRODUCAO==1:
        if not scheduler.running:
            scheduler.start()
            logger.info("Scheduler ligado.")
        return render_template('ligarScheduler.html', sucesso=True)
    else:
        return render_template('ligarScheduler.html', sucesso=False)

@app.route("/admin/desligarScheduler", methods=['GET'])
@login_required(role='admin')
@log_required
def desligar_scheduler():
    """
    Desliga o scheduler para não executar mais tarefas agendadas.
    """
    if PRODUCAO==1:
        scheduler.shutdown()
        logger.info("Scheduler desligado.")
        return render_template('desligarScheduler.html', sucesso=True)
    else:
        return render_template('desligarScheduler.html', sucesso=False)

@app.route("/admin/schedulerJobs", methods=['GET'])
@login_required(role='admin')
@log_required
def scheduler_jobs():
    """
    Retorna os jobs do scheduler e seu status.
    """
    if scheduler.running:
        jobs = scheduler.get_jobs()
        jobs_info = [
            {
                'id': job.id,
                'name': job.name,
                'next_run_time': str(job.next_run_time),
                'trigger': str(job.trigger),
            }
            for job in jobs
        ]
        return render_template('schedulerJobs.html', scheduler_running=True, jobs=jobs_info)
    else:
        return render_template('schedulerJobs.html', scheduler_running=False, jobs=[])

# Contadores do Flask-Limiter no Redis: LIMITS:LIMITER/<ip>/<rota>/<quantidade>/<múltiplo>/<período>
PREFIXO_CHAVES_LIMITADOR = "LIMITS:LIMITER/"

def log_limitador(acao, nivel='info', **extra):
    with logger.contextualize(ip=request.remote_addr, username=session.get('username', 'N/A'), rota=request.path,
                              metodo=request.method, acao=acao, **extra):
        logger.log(nivel.upper(), "Limitador de acessos: {}", acao)

@app.route("/admin/limitador", methods=['GET'])
@login_required(role='admin')
@log_required
def limitador():
    """
    Página para liberar os contadores do limitador de acessos (Flask-Limiter).
    """
    return render_template('limitador.html', ip_atual=request.remote_addr)

@app.route("/admin/limitador/liberar_ip", methods=['POST'])
@login_required(role='admin')
@log_required
def limitador_liberar_ip():
    """
    Zera os contadores do limitador de acessos de um único IP.
    """
    try:
        ip = str(ipaddress.ip_address(str(request.form.get('ip', '')).strip()))
    except ValueError:
        flash("Informe um endereço IP válido (IPv4 ou IPv6).", 'error')
        return redirect(url_for('limitador'))
    try:
        redis_limitador = app.config['SESSION_REDIS']
        chaves = list(redis_limitador.scan_iter(match=f"{PREFIXO_CHAVES_LIMITADOR}{ip}/*", count=1000))
        if chaves:
            redis_limitador.delete(*chaves)
    except Exception as e:
        log_limitador('liberar_ip', nivel='error', ip_liberado=ip, erro=str(e), classe_erro=type(e).__name__)
        flash("Não foi possível acessar o armazenamento do limitador. Tente novamente.", 'error')
        return redirect(url_for('limitador'))
    log_limitador('liberar_ip', ip_liberado=ip, contadores=len(chaves))
    if chaves:
        flash(f"Acessos do IP {ip} liberados ({len(chaves)} contador(es) zerado(s)).")
    else:
        flash(f"Nenhum contador encontrado para o IP {ip}.", 'error')
    return redirect(url_for('limitador'))

@app.route("/admin/limitador/zerar", methods=['POST'])
@login_required(role='admin')
@log_required
def limitador_zerar():
    """
    Zera todos os contadores do limitador de acessos.
    """
    try:
        limiter.storage.reset()
    except Exception as e:
        log_limitador('zerar_todos', nivel='error', erro=str(e), classe_erro=type(e).__name__)
        flash("Não foi possível zerar o limitador. Tente novamente.", 'error')
        return redirect(url_for('limitador'))
    log_limitador('zerar_todos', nivel='warning')
    flash("Todos os contadores do limitador de acessos foram zerados.")
    return redirect(url_for('limitador'))

def carregar_mensagens():
    """
    Carrega as mensagens do banco de dados para exibição.
    """
    consulta = """SELECT mensagem,validade,data,users.nome
    FROM mensagens LEFT JOIN users ON users.username=mensagens.autor
    WHERE validade>NOW() ORDER BY data DESC LIMIT 1"""
    linhas,total = executarSelect(consulta)
    lista = []
    for linha in linhas:
        mensagem = {
            'mensagem': linha[0],
            'validade': str(linha[1]),
            'data': str(linha[2]),
            'autor': linha[3] or '',
        }
        lista.append(mensagem)
    return lista

def ler_formulario_mensagem():
    """Valida o formulário de mensagem. Retorna (mensagem, validade, erro)."""
    mensagem = str(request.form.get('mensagem', '')).strip()
    validade = str(request.form.get('validade', '')).strip()
    if not mensagem:
        return mensagem, validade, "Informe o texto da mensagem."
    try:
        datetime.strptime(validade, '%Y-%m-%dT%H:%M')
    except ValueError:
        return mensagem, validade, "Informe uma data de validade válida."
    return mensagem, validade, None

def buscar_mensagem(id_mensagem):
    resultado = executarSelect2("SELECT id,mensagem,validade FROM mensagens WHERE id=%s", valores=(id_mensagem,))
    if resultado is None or resultado[1] == 0:
        return None
    return resultado[0][0]

@app.route("/admin/mensagens", methods=['GET'])
@login_required(role='admin')
@log_required
def mensagens():
    """
    Lista todas as mensagens gerais (ativas e vencidas) para gerenciamento.
    """
    consulta = """SELECT mensagens.id,mensagem,validade,data,validade>NOW() as ativa,autor,users.nome
    FROM mensagens LEFT JOIN users ON users.username=mensagens.autor
    ORDER BY data DESC"""
    resultado = executarSelect2(consulta)
    linhas, total = resultado if resultado is not None else ([], 0)
    return render_template('mensagens.html', linhas=linhas, total=total)

@app.route("/admin/mensagens/nova", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def mensagem_nova():
    """
    Cadastra uma mensagem geral, exibida no topo das páginas até a validade.
    """
    if request.method == 'POST':
        mensagem, validade, erro = ler_formulario_mensagem()
        if erro:
            flash(erro, 'error')
            return render_template('mensagemForm.html', mensagem=mensagem, validade=validade, id_mensagem=None)
        consulta = """INSERT INTO mensagens (mensagem,validade,autor)
        VALUES (%s, %s, %s)"""
        atualizar2(consulta, valores=[mensagem,validade,session['username']])
        flash("Mensagem cadastrada com sucesso!")
        return redirect(url_for('mensagens'))
    return render_template('mensagemForm.html', mensagem='', validade='', id_mensagem=None)

@app.route("/admin/mensagens/<int:id_mensagem>/editar", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def mensagem_editar(id_mensagem):
    """
    Altera o texto e a validade de uma mensagem geral.
    """
    linha = buscar_mensagem(id_mensagem)
    if linha is None:
        flash("Mensagem não encontrada.", 'error')
        return redirect(url_for('mensagens'))
    if request.method == 'POST':
        mensagem, validade, erro = ler_formulario_mensagem()
        if erro:
            flash(erro, 'error')
            return render_template('mensagemForm.html', mensagem=mensagem, validade=validade, id_mensagem=id_mensagem)
        atualizar2("UPDATE mensagens SET mensagem=%s, validade=%s WHERE id=%s",
                   valores=[mensagem, validade, id_mensagem])
        flash("Mensagem alterada com sucesso!")
        return redirect(url_for('mensagens'))
    return render_template('mensagemForm.html', mensagem=linha[1], validade=linha[2].strftime('%Y-%m-%dT%H:%M'),
                           id_mensagem=id_mensagem)

@app.route("/admin/mensagens/<int:id_mensagem>/remover", methods=['POST'])
@login_required(role='admin')
@log_required
def mensagem_remover(id_mensagem):
    """
    Remove uma mensagem geral.
    """
    if buscar_mensagem(id_mensagem) is None:
        flash("Mensagem não encontrada.", 'error')
        return redirect(url_for('mensagens'))
    atualizar2("DELETE FROM mensagens WHERE id=%s", valores=[id_mensagem])
    flash("Mensagem removida com sucesso!")
    return redirect(url_for('mensagens'))

def senha_segura_valida(senha):
    """Verifica se uma senha atende aos requisitos mínimos de segurança.

    Requisitos: 12 ou mais caracteres, com letras maiúsculas, minúsculas,
    números e caracteres especiais.
    """
    if len(senha) < 12:
        return False
    if not re.search(r'[a-z]', senha):
        return False
    if not re.search(r'[A-Z]', senha):
        return False
    if not re.search(r'[0-9]', senha):
        return False
    if not re.search(r'[^a-zA-Z0-9]', senha):
        return False
    return True

@app.route("/novaSenha", methods=['GET', 'POST'])
@login_required(role='user')
@log_required
def nova_senha():
    """
    Página para o usuário logado definir uma nova senha segura.
    """
    if request.method == 'POST':
        senha_atual = str(request.form.get('senha_atual', ''))[:64]
        nova = str(request.form.get('nova_senha', ''))[:64]
        confirmar = str(request.form.get('confirmar_senha', ''))[:64]

        username = session['username']
        linha = buscar_usuario(username)
        if linha is None:
            flash("Erro ao alterar a senha. Tente novamente.", 'error')
            return redirect(url_for('nova_senha'))
        no_cognito = USAR_COGNITO and int(linha[5]) == 1

        # No Cognito a senha atual é conferida pelo próprio change_password, com o access
        # token do login (reautenticar dispararia o desafio de MFA)
        access_token = None
        if no_cognito:
            access_token = obter_access_token()
            if access_token is None:
                logout()
                flash("Sua sessão expirou. Entre novamente para alterar a senha.", 'error')
                return redirect(url_for('login'))
        elif not verificar_senha_legado(linha, senha_atual):
            flash("Senha atual incorreta.", 'error')
            return redirect(url_for('nova_senha'))

        erro = validar_nova_senha(nova, confirmar)
        if erro:
            flash(erro, 'error')
            return redirect(url_for('nova_senha'))

        try:
            if no_cognito:
                cognito.change_password(PreviousPassword=senha_atual, ProposedPassword=nova, AccessToken=access_token)
                log_migracao('senha_alterada', username, origem='nova_senha')
            elif USAR_COGNITO:
                # Ainda não migrado (senha antiga fora da política): a troca conclui a migração
                cognito_migrar_usuario(linha, nova, origem='nova_senha')
                # Obtém os tokens com a nova senha; o usuário ainda não tem MFA e cai no cadastro
                try:
                    resposta = cognito_autenticar(username, nova)
                    if 'AuthenticationResult' in resposta:
                        concluir_login_cognito(username, resposta['AuthenticationResult'], via_mfa=False)
                except (ClientError, BotoCoreError) as e:
                    # A senha já foi trocada; o MFA será exigido no próximo login
                    log_migracao('mfa_falha', username, nivel='warning', origem='nova_senha',
                                 etapa='login_pos_migracao', classe_erro=codigo_erro(e))
            else:
                hash_nova_senha = cripto.hash_argon2id(nova)
                consulta = """UPDATE users SET password=%s WHERE username=%s"""
                atualizar2(consulta, valores=[hash_nova_senha, username])
            with logger.contextualize(ip=request.remote_addr,username=username,rota=request.path,metodo=request.method,erro=""):
                logger.info("Usuário alterou a própria senha")
        except (ClientError, BotoCoreError) as e:
            if codigo_erro(e) == 'InvalidPasswordException':
                flash("A nova senha não atende aos requisitos de segurança.", 'error')
            elif no_cognito and codigo_erro(e) == 'NotAuthorizedException':
                flash("Senha atual incorreta.", 'error')
            elif no_cognito and codigo_erro(e) == 'LimitExceededException':
                flash("Muitas tentativas. Aguarde alguns minutos e tente novamente.", 'error')
            else:
                log_migracao('troca_senha_falha_cognito', username, nivel='error', origem='nova_senha',
                             erro=str(e), classe_erro=codigo_erro(e))
                flash("Erro ao alterar a senha. Tente novamente.", 'error')
            return redirect(url_for('nova_senha'))
        except Exception as e:
            logger.warning("Erro ao alterar a senha do usuário {}: {}", username, str(e))
            flash("Erro ao alterar a senha. Tente novamente.", 'error')
            return redirect(url_for('nova_senha'))

        session.pop('senha_vazada', None)
        flash("Senha alterada com sucesso!")
        return redirect(url_for('home'))
    return render_template('novaSenha.html')

if PRODUCAO==1:
    scheduler.start()

if __name__ == "__main__":
    prefixo = os.getenv('URL_PREFIX','/pesquisa')
    threads = int(os.getenv('WAITRESS_THREADS', '2'))
    with logger.catch():
        serve(app, host='0.0.0.0', port=int(SERVER_PORT), url_prefix=prefixo,trusted_proxy='*',trusted_proxy_headers='x-forwarded-for x-forwarded-proto x-forwarded-port',threads=threads)
