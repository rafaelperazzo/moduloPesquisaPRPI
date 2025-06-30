# -*- coding: utf-8 -*-
from flask import Flask
from flask import render_template
from flask import request,url_for,send_from_directory,redirect,session,flash
from flask_httpauth import HTTPBasicAuth
from waitress import serve
import mariadb as MySQLdb
from werkzeug.utils import secure_filename
import hashlib
import os
import string
import random
import sys
import re
import pdfkit
from flask_mail import Mail
from flask_mail import Message
from flask_uploads import UploadSet, configure_uploads, ALL, DOCUMENTS
import pandas as pd
import threading
import zeep
import zipfile
import time
from flask import Response
import json
from flask_wtf.csrf import CSRFProtect
from modules import scorerun
from brseclabcripto.cripto3 import SecCripto
from git import Repo
import secrets
from functools import wraps
from datetime import timedelta
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.loguru import LoguruIntegration
from sentry_sdk.integrations.loguru import LoggingLevels
from sentry_sdk.integrations.logging import ignore_logger
from logtail import LogtailHandler
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
SERVER_URL = os.getenv("SERVER_URL", "http://localhost")
PRODUCAO=0
try:
    PRODUCAO = int(os.getenv("PRODUCAO", "0"))
except ValueError as e:
    PRODUCAO = 0

UPLOAD_FOLDER = 'static/files'
ALLOWED_EXTENSIONS = set(['pdf','xml'])
URL_PREFIX = os.getenv('URL_PREFIX','/pesquisa')
PLOTS_DIR = 'static/plots/'
CURRICULOS_DIR='static/files/'
XML_DIR = 'xml/'
SITE = SERVER_URL + "static/files/"
IMAGENS_URL = SERVER_URL + "static/"
DECLARACOES_DIR = 'pdfs/'
ROOT_SITE = SERVER_URL
USUARIO_SITE = ROOT_SITE + URL_PREFIX + "/usuario"
ATTACHMENTS_DIR = 'docs_indicacoes/'
SUBMISSOES_DIR = 'submissoes/'
MYSQL_DB = os.getenv("MYSQL_HOST", "localhost")
if PRODUCAO==1:
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "pesquisa")
else:
    MYSQL_DATABASE = os.getenv("MYSQL_TEST_DATABASE", "pesquisa_test")
EMAIL_TESTES = os.getenv("EMAIL_TESTES","test@123.com")
DEFAULT_EMAIL = os.getenv("DEFAULT_EMAIL","teste@test.com")
LINK_AVALIACAO = ROOT_SITE + URL_PREFIX + "/avaliacao"
DSN_SENTRY = os.getenv("DSN_SENTRY", "")
BS_SOURCE_TOKEN = os.getenv("BS_SOURCE_TOKEN", "")
BS_HOST = os.getenv("BS_HOST", "")

if PRODUCAO==1:
    # CONFIGURANDO SENTRY
    ignore_logger("waitress")
    ignore_logger("waitress.queue")
    sentry_sdk.init(
        dsn=DSN_SENTRY,
        _experiments={
            "enable_logs": True
        },
        integrations = [
            FlaskIntegration(
                transaction_style="url",
            ),
            LoguruIntegration(
                level=LoggingLevels.INFO.value,
                event_level=LoggingLevels.ERROR.value,
                #sentry_logs_level=LoggingLevels.INFO.value,
            ),
        ],
        send_default_pii=True,
    )
    ignore_logger("waitress")
    ignore_logger("waitress.queue")
    
app = Flask(__name__)
auth = HTTPBasicAuth()
csrf = CSRFProtect(app)
app.config['producao'] = PRODUCAO
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_REDIS'] = Redis.from_url('redis://redis:6379')
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
    storage_uri="redis://redis:6379",
    default_limits=["300 per day", "80 per hour"],
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

mail = Mail(app)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = DEFAULT_EMAIL
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_DEFAULT_SENDER'] = DEFAULT_EMAIL

if PRODUCAO==1:
    app.config['MAIL_SUPPRESS_SEND'] = False
else:
    app.config['MAIL_SUPPRESS_SEND'] = True

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['CURRICULOS_FOLDER'] = CURRICULOS_DIR
app.config['DECLARACOES_FOLDER'] = DECLARACOES_DIR
app.config['TEMP_FOLDER'] = DECLARACOES_DIR

AES_KEY = os.getenv("AES_KEY", "000000")
GPG_KEY = os.getenv("GPG_KEY", "000000")
cripto = SecCripto(AES_KEY)

#logger = logging.getLogger('pesquisa')

if PRODUCAO==1:
    handler = LogtailHandler(
        source_token=BS_SOURCE_TOKEN,
        host=BS_HOST,
    )
    logger.add("app.json", rotation="20 MB", retention=30, backtrace=False,
               diagnose=False, level="INFO", serialize=True,mode='a',
               format="{time} | {name} | {level} | {message} | {extra}",
               compression='gz')
    logger.add(handler, format="{time} | {name} | {level} | {message} | {extra}", level="INFO",
               serialize=True,backtrace=False, diagnose=False)
else:
    logger.add("app.log", rotation="20 MB", retention=30, backtrace=False,
               diagnose=False, level="INFO", serialize=False,mode='w',
               format="{time} | {name} | {level} | {message} | {extra}",
               compression='gz')

logger.enable("")
logger.disable("waitress")
logger.disable("waitress.queue")

#Obtendo senhas
PASSWORD = os.getenv("DB_PASSWORD", "World")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD", "World")
app.config['SECRET_KEY'] = secrets.token_hex()
app.config['MAIL_PASSWORD'] = GMAIL_PASSWORD
app.config['MAX_CONTENT_LENGTH'] = 16 * 1000 * 1000

mail = Mail(app)

#Flask-flask_uploads
app.config['UPLOADED_DOCUMENTS_DEST'] = ATTACHMENTS_DIR
app.config['UPLOADS_DEFAULT_DEST'] = ATTACHMENTS_DIR
anexos = UploadSet('documents',ALL)
app.config['UPLOADED_SUBMISSOES_DEST'] = SUBMISSOES_DIR
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

def log_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('username') is None:
            logger.info("{} | {} | {} | N/A | N/A",request.remote_addr,request.path,request.method)
        else:
            with logger.contextualize(username=session['username']):
                logger.info("{} | {} | {} | N/A",request.remote_addr,request.path,request.method)
        return f(*args, **kwargs)
    return decorated_function

def calcula_hash(mensagem):
    """
    Calcula o hash SHA-256 de uma mensagem.
    """
    hash_cripto = hashlib.sha224()
    hash_cripto.update(mensagem.encode('utf-8'))
    return hash_cripto.hexdigest()

def generate_secure_password(length=16, include_uppercase=True,
                             include_numbers=True, include_special_chars=True):
    # Define character sets
    lowercase_letters = string.ascii_lowercase
    uppercase_letters = string.ascii_uppercase if include_uppercase else ""
    digits = string.digits if include_numbers else ""
    special_chars = string.punctuation if include_special_chars else ""

    # Combine character sets and create a password
    all_characters = lowercase_letters + uppercase_letters + digits + special_chars
    if len(all_characters) == 0:
        raise ValueError("At least one character set must be included")

    password = ''.join(secrets.choice(all_characters) for _ in range(length))
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

def processarPontuacaoLattes(cpf,area,idProjeto,dados):
    processou_scoreLattes = False
    try:
        idlattes = getID(cpf)
        salvarCV(idlattes)
        arquivo = XML_DIR + idlattes + ".xml"
        pontuacao = -100
        sumario = "---"
        processou_scoreLattes = True
    except Exception as e:
        with app.app_context():
            logger.error("Erro ao BAIXAR O XML: {}", e)
            logger.error("Tentativa de BAIXAR o XML com o CPF: {}", cpf)
        processou_scoreLattes = False
    try:
        if processou_scoreLattes:
            from datetime import date
            ano_fim = date.today().year
            ano_inicio = ano_fim - 5
            if os.path.exists(arquivo):
                score = scorerun.Score(arquivo, ano_inicio, ano_fim, area,2017,0,False)
                pontuacao = float(score.get_score())
                sumario = str(score.sumario())
            else:
                pontuacao = -1
                sumario = "ERRO AO PROCESSAR O SCORELATTES. Erro ao digitar o CPF ?"
        else:
            pontuacao = -1
            sumario = "ERRO AO PROCESSAR O SCORELATTES"
    except Exception as e:
        with app.app_context():
            logger.error("Erro ao processar o scorelattes: {}", e)
            logger.error("Tentativa de processar o scorelattes com CPF: {}", cpf)
        pontuacao = -1
        sumario = "ERRO AO PROCESSAR O SCORELATTES"

    try:
        consulta = """UPDATE editalProjeto 
        SET scorelattes= ? WHERE id= ?"""
        atualizar2(consulta,valores=[pontuacao,idProjeto])
    except Exception as e:
        with app.app_context():
            logger.error("Erro ao atualizar o scorelattes: {}", str(e))
            logger.error("Tentativa de atualizar o scorelattes com CPF: {}", str(cpf))
    with app.app_context():
        try:
            #ENVIAR E-MAIL DE CONFIRMAÇÃO
            texto_email = render_template('confirmacao_submissao.html',email_proponente=dados[0],id_projeto=idProjeto,proponente=dados[1],titulo_projeto=dados[2],resumo_projeto=dados[3],score=pontuacao,sumario=sumario)
            if PRODUCAO==1:
                msg = Message(subject = "Plataforma Yoko - CONFIRMAÇÃO DE SUBMISSAO DE PROJETO DE PESQUISA",recipients=[dados[0]],html=texto_email,reply_to="NAO-RESPONDA@ufca.edu.br")
            else:
                msg = Message(subject = "Plataforma Yoko - CONFIRMAÇÃO DE SUBMISSAO DE PROJETO DE PESQUISA",recipients=["pesquisapython3.display999@passmail.net"],html=texto_email,reply_to="NAO-RESPONDA@ufca.edu.br")
            try:
                mail.send(msg)
                logger.info("Email enviado com sucesso. processarPontuacaoLattes - IdProjeto: {}", idProjeto)
            except Exception as e:
                logger.error("Erro ao enviar e-mail. processarPontuacaoLattes")
                logger.error(str(e))
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
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE) 
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    try:
        cursor.execute(consulta)
        conn.commit()
    except MySQLdb.Error as e:
        logger.error(e)
        logger.error(consulta)
    finally:
        cursor.close()
        conn.close()

def atualizar2(consulta,valores=()):
    """Função para UPDATE, INSERT e DELETE no banco de dados.

    Args:
        consulta (str): consulta SQL
        valores (list, optional): Valores para consulta. Defaults to ().
    """
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE) 
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
        logger.error(e)
        logger.error(consulta)
    finally:
        cursor.close()
        conn.close()

def inserir(consulta,valores):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE)
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    try:
        cursor.execute(consulta,valores)
        conn.commit()
    except MySQLdb.Error as e:
        logger.error(e)
        logger.error("Erro ao inserir registro")
        logger.error(valores)
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
    return ''.join(random.choice(chars) for _ in range(size))

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
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE)
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    consulta = "SELECT nome,cpf,modalidade,orientador,projeto,inicio,fim,id,ch FROM alunos WHERE id=" + str(identificador)
    cursor.execute(consulta)
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

    consulta = "INSERT INTO autenticacao (idAluno,codigo,data) VALUES (" + str(identificador) + ",FLOOR(RAND()*(100000000-10000+1))+10000,NOW())"
    cursor.execute(consulta)
    conn.commit()
    conn.commit()
    conn.close()
    return (linha)

def gerarDeclaracaoOrientador(identificador):
    #CONEXÃO COM BD
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE)
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    consulta = "SELECT id,coordenador,siape,titulo,inicio,fim FROM projetos WHERE id=" + identificador
    cursor.execute(consulta)
    linha = cursor.fetchone()
    consultaBolsistas = "SELECT a.nome FROM alunos a, projetos p WHERE a.projeto=p.titulo AND p.id=" + str(identificador)
    cursor.execute(consultaBolsistas)
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
    try:
        conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE)
        conn.select_db(MYSQL_DATABASE)
        cursor  = conn.cursor()
        consulta = """SELECT estudante_nome_completo,cpf,estudante_modalidade,nome_do_coordenador,titulo_do_projeto,estudante_inicio,estudante_fim,token FROM cadastro_geral WHERE cpf = ? """
        cursor.execute(consulta, (cpf,))
        linhas = cursor.fetchall()
        consulta = """SELECT indicacoes.nome,indicacoes.cpf,IF(indicacoes.modalidade=1,'PIBIC',IF(indicacoes.modalidade=2,'PIBITI','PIBIC-EM')),editalProjeto.nome,editalProjeto.titulo,indicacoes.inicio,indicacoes.fim,indicacoes.id
                    FROM indicacoes,editalProjeto
                    WHERE indicacoes.idProjeto=editalProjeto.id AND indicacoes.cpf= ? """
        cursor.execute(consulta, (cpf,))
        linhas2019 = cursor.fetchall()
        return (linhas,linhas2019)
    except Exception as e:
        logger.error(e)
        logger.error("ERRO Na função gerarProjetosPorAluno. Ver consulta abaixo.")
        logger.error(consulta)
    finally:
        cursor.close()
        conn.close()

def gerarProjetosPorOrientador(identificador):
    #CONEXÃO COM BD
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE)
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    consulta = "SELECT id,coordenador,titulo,inicio,fim FROM projetos WHERE SIAPE=" + str(identificador)
    cursor.execute(consulta)
    linhas = cursor.fetchall()
    conn.close()
    return (linhas)

def gerarAutenticacao(identificador):
    #CONEXÃO COM BD
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE)
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    consulta = "SELECT a.nome,a.cpf,a.modalidade,a.orientador,a.projeto,a.inicio,a.fim,b.codigo FROM alunos a, autenticacao b WHERE a.id=b.idAluno and b.codigo=" + identificador + " ORDER BY b.data DESC LIMIT 1"
    cursor.execute(consulta)
    linha = cursor.fetchone()
    conn.close()
    return (linha)

def getEditaisAbertos():
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE)
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    consulta = """SELECT id,nome,DATE_FORMAT(deadline,'%d/%m/%Y - %H:%i') FROM editais WHERE now()<deadline ORDER BY id DESC"""
    cursor.execute(consulta)
    linhas = cursor.fetchall()
    cursor.close()
    conn.close()
    return linhas

@auth.verify_password
def verify_password(username, password):
    """This function is called to check if a username /
    password combination is valid.
    """
    try:
        if not username_valido(username):
            return False
        consulta2 = """
        SELECT id,
        username,
        permission,
        roles,
        password 
        FROM users 
        WHERE username=? LIMIT 1 """
        continuar = False
        resultado,total_usuarios = executarSelect2(consulta2,valores=[username])
        if total_usuarios>0:
            linha = resultado[0]
            hash_senha = str(linha[4])
            try:
                if cripto.hash_argon2id_verify(hash_senha, password):
                    continuar = True
                    logger.info(f"{request.remote_addr} | {request.path} | {request.method} | {username} | AUTENTICADO")
                else:
                    continuar = False
                    logger.warning(f"{request.remote_addr} | {request.path} | {request.method} | {username} | SENHA INVÁLIDA")
            except Exception:
                continuar = False
                logger.warning(f"{request.remote_addr} | {request.path} | {request.method} | {username} | VERIFICAÇÃO COM ARGON2")
        else:
            continuar = False
        if continuar is False: #Usuário inexistente ou senha inválida
            return False
        else: #Usuário e senha válidos
            linha = resultado[0]
            session['username'] = str(linha[1])
            session['permissao'] = int(linha[2])
            roles = str(linha[3])
            roles = roles.split(',')
            session['roles'] = roles
            session['edital'] = 0
            return username
    except Exception as e:
        logger.error("ERRO Na função verify_password: {}. Ver consulta: {}", str(e), consulta2)

@auth.get_user_roles
def get_user_roles(user):
    consulta = """SELECT roles FROM users WHERE username='""" + auth.username() + """'"""
    linhas,total = executarSelect(consulta)
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
    return render_template('root.html')

@app.route("/version")
def version():
    return jsonify({"version": __version__})

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
                logger.error(e)
                logger.error("Nao foi possivel gerar o PDF da declaração.")
                return "Erro ao gerar o PDF da declaração. Verifique os logs para mais detalhes."
        else:
            return "OK"

@app.route("/projetosAluno", methods=['POST'])
@log_required
def projetos():
    try:
        projetosAluno,projetosAluno2019 = gerarProjetosPorAluno(str(request.form['txtNome']))
        return render_template('alunos.html',listaProjetos=projetosAluno,
                               lista2019=projetosAluno2019)
    except Exception as e:
        logger.error(e)
        logger.error("Nao foi possivel gerar os projetos do aluno.")
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

@app.route("/cadastrarProjeto", methods=['GET', 'POST'])
@login_required(role='user')
@log_required
def cadastrarProjeto():
    if request.method == "POST":
        #CADASTRAR DADOS DO PROPONENTE
        tipo = int(request.form['tipo'])
        nome = str(request.form['nome'])
        categoria_projeto = int(request.form['categoria_projeto'])
        try:
            siape = int(removerTravessao(request.form['siape']))
        except ValueError as e:
            logger.error("Erro ao converter SIAPE para inteiro.")
            logger.error(e)
            siape = 0
        email = str(request.form['email'])
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
        cpf = str(request.form['cpf'])
        #CONEXÃO COM BD
        conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE)
        
        conn.select_db(MYSQL_DATABASE)
        cursor  = conn.cursor()

        #DADOS PESSOAIS E BÁSICOS DO PROJETO
        consulta = """INSERT INTO editalProjeto 
        (categoria,tipo,nome,siape,email,ua,area_capes,grande_area,grupo,data,ods,inovacao,justificativa) 
        VALUES (?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP(),?,?,?)"""
        atualizar2(consulta, valores=[categoria_projeto,tipo,nome,siape,email,ua,area_capes,grande_area,grupo,ods_projeto,inovacao,justificativa])
        
        lastID = "SELECT LAST_INSERT_ID()"
        cursor.execute(lastID)
        ultimo_id = int(cursor.fetchone()[0])
        ultimo_id_str = "%03d" % (ultimo_id)
        if tipo==0:
            tipo_str = "Fluxo Continuo"
        else:
            tipo_str= "Edital"

        if categoria_projeto==0:
            categoria_str = "Projeto em andamento"
        else:
            categoria_str= "Projeto Novo"

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
        consulta = """UPDATE editalProjeto 
        SET titulo= ?, validade= ? , palavras= ? , resumo= ? , bolsas= ? WHERE id= ? """
        atualizar2(consulta, valores=[titulo,validade,palavras_chave,descricao_resumida,bolsas,ultimo_id])
        consulta = "UPDATE editalProjeto SET transporte= ? WHERE id= ?"
        atualizar2(consulta, valores=[transporte,ultimo_id])
        inicio = str(request.form['inicio'])
        fim = str(request.form['fim'])
        consulta = "UPDATE editalProjeto SET inicio= ? WHERE id= ? "
        atualizar2(consulta, valores=[inicio,ultimo_id])
        consulta = "UPDATE editalProjeto SET fim= ? WHERE id= ? "
        atualizar2(consulta, valores=[fim,ultimo_id])
        codigo = id_generator()

        if ('arquivo_projeto' in request.files):
            arquivo_projeto = request.files['arquivo_projeto']
            if arquivo_projeto and allowed_file(arquivo_projeto.filename) :
                arquivo_projeto.filename = "projeto_" + ultimo_id_str + "_" + str(siape) + "_" + codigo + ".pdf"
                filename = secure_filename(arquivo_projeto.filename)
                submissoes.save(arquivo_projeto, name=filename)
                encripta_e_apaga(SUBMISSOES_DIR + filename)
                consulta = "UPDATE editalProjeto SET arquivo_projeto= ? WHERE id= ? "
                atualizar2(consulta, valores=[filename,ultimo_id])
            elif not allowed_file(arquivo_projeto.filename):
                return ("Arquivo de projeto não permitido")

        if ('arquivo_plano1' in request.files):

            arquivo_plano1 = request.files['arquivo_plano1']
            if arquivo_plano1 and allowed_file(arquivo_plano1.filename):
                arquivo_plano1.filename = "plano1_" + ultimo_id_str + "_" + str(siape) + "_" + codigo + ".pdf"
                filename = secure_filename(arquivo_plano1.filename)
                submissoes.save(arquivo_plano1, name=filename)
                encripta_e_apaga(SUBMISSOES_DIR + filename)
                consulta = "UPDATE editalProjeto SET arquivo_plano1= ? WHERE id= ? "
                atualizar2(consulta, valores=[filename,ultimo_id])
            elif not allowed_file(arquivo_plano1.filename):
                return ("Arquivo de plano 1 de trabalho não permitido")

        if ('arquivo_plano2' in request.files):
            arquivo_plano2 = request.files['arquivo_plano2']
            if arquivo_plano2 and allowed_file(arquivo_plano2.filename):
                arquivo_plano2.filename = "plano2_" + ultimo_id_str + "_" + str(siape) + "_" + codigo + ".pdf"
                filename = secure_filename(arquivo_plano2.filename)
                submissoes.save(arquivo_plano2, name=filename)
                encripta_e_apaga(SUBMISSOES_DIR + filename)
                consulta = "UPDATE editalProjeto SET arquivo_plano2= ? WHERE id= ? "
                atualizar2(consulta, valores=[filename,ultimo_id])
            elif not allowed_file(arquivo_plano2.filename):
                return ("Arquivo de plano 2 de trabalho não permitido")

        if ('arquivo_plano3' in request.files):
            arquivo_plano3 = request.files['arquivo_plano3']
            if arquivo_plano3 and allowed_file(arquivo_plano3.filename):
                arquivo_plano3.filename = "plano3_" + ultimo_id_str + "_" + str(siape) + "_" + codigo + ".pdf"
                filename = secure_filename(arquivo_plano3.filename)
                submissoes.save(arquivo_plano3, name=filename)
                encripta_e_apaga(SUBMISSOES_DIR + filename)
                consulta = "UPDATE editalProjeto SET arquivo_plano3= ? WHERE id= ? "
                atualizar2(consulta, valores=[filename,ultimo_id])
            elif not allowed_file(arquivo_plano3.filename):
                    return ("Arquivo de plano 3 de trabalho não permitido")

        #ARQUIVO DE COMPROVANTES
        if ('arquivo_comprovantes' in request.files):
            arquivo_comprovantes = request.files['arquivo_comprovantes']
            if allowed_file(arquivo_comprovantes.filename):
                arquivo_comprovantes.filename = "Comprovantes_" + ultimo_id_str + "_" + str(siape) + "_" + codigo + ".pdf"
                filename = secure_filename(arquivo_comprovantes.filename)
                submissoes.save(arquivo_comprovantes, name=filename)
                encripta_e_apaga(SUBMISSOES_DIR + filename)
                consulta = "UPDATE editalProjeto SET arquivo_comprovantes= ? WHERE id= ? "
                atualizar2(consulta, valores=[filename,ultimo_id])

        #CADASTRAR AVALIADORES SUGERIDOS
        if 'avaliador1_email' in request.form:
            avaliador1_email = str(request.form['avaliador1_email'])
            if avaliador1_email!='':
                token = id_generator(40)
                consulta = "INSERT INTO avaliacoes (avaliador,token,idProjeto) VALUES (?,?,?)"
                atualizar2(consulta, valores=[avaliador1_email,token,ultimo_id])

        if 'avaliador2_email' in request.form:
            avaliador2_email = str(request.form['avaliador2_email'])
            if avaliador2_email!='':
                token = id_generator(40)
                consulta = "INSERT INTO avaliacoes (avaliador,token,idProjeto) VALUES (?,?,?)"
                atualizar2(consulta, valores=[avaliador2_email,token,ultimo_id])

        if 'avaliador3_email' in request.form:
            avaliador3_email = str(request.form['avaliador3_email'])
            if avaliador3_email!='':
                token = id_generator(40)
                consulta = "INSERT INTO avaliacoes (avaliador,token,idProjeto) VALUES (?,?,?)"
                atualizar2(consulta, valores=[avaliador3_email,token,ultimo_id])
        #Incluir avaliador teste em caso de não inclusão
        if ('avaliador1_email' not in request.form and 'avaliador2_email' not in request.form and 'avaliador3_email' not in request.form):
            token = id_generator(40)
            consulta = """INSERT INTO avaliacoes (avaliador,token,idProjeto) VALUES ("TESTE@IGNORAR.COM", ?, ?)"""
            atualizar2(consulta, valores=[token, ultimo_id])
        elif avaliador1_email=="" and avaliador2_email=="" and avaliador3_email=="":
            token = id_generator(40)
            consulta = """INSERT INTO avaliacoes (avaliador,token,idProjeto) VALUES ("TESTE@IGNORAR.COM", ?, ?)"""
            atualizar2(consulta, valores=[token, ultimo_id])
        #CALCULANDO scorelattes
        dados = [email,nome,titulo,descricao_resumida]
        t = threading.Thread(target=processarPontuacaoLattes,args=(cpf,area_capes,ultimo_id,dados,))
        t.start()
        return("Submissão realizada com sucesso. ESTA PÁGINA JÁ PODE SER FECHADA COM SEGURANÇA.")
    else:
        editaisAbertos = getEditaisAbertos()
        session['PRODUCAO'] = PRODUCAO
        return render_template('cadastrarProjeto.html',abertos=editaisAbertos)

@app.route("/scorelattes", methods=['GET'])
@log_required
def calcularScorelattesFromID():
    return (render_template('scorelattes.html'))

@app.route("/score", methods=['GET', 'POST'])
@log_required
@limiter.limit("30/day;10/hour;3/minute",methods=["POST"])
def getScoreLattesFromFile():
    area_capes = str(request.form['area_capes'])
    idlattes = str(request.form['idlattes'])
    if not token_valido(idlattes):
        return "IDLattes inválido! Informe um IDLattes válido."
    periodo = int(str(request.form['periodo']))
    if not numero_valido(periodo) or periodo not in [5,7]:
        return "Período inválido! Informe um número inteiro positivo."
    try:
        salvarCV(idlattes)
    except Exception as e:
        logger.warning("[/SCORE] Nao foi possivel baixar o curriculo do IDlattes ({}). Erro: {}",str(idlattes),str(e))
        return("[/SCORE] Não foi possível baixar o currículo. IDLattes inválido, ou problemas na comunicação com o CNPq. Tente novamente.")
    arquivo = XML_DIR + idlattes + ".xml"
    try:
        from datetime import date
        ano_fim = date.today().year
        ano_inicio = ano_fim - periodo
        score = scorerun.Score(arquivo, ano_inicio, ano_fim, area_capes,2017,0,False)
        sumario = str(score.sumario())
        return(sumario)
    except Exception as e:
        logger.error("[SCORELATTES] Erro ao calcular o scorelattes: {}", str(e))
        return("Erro ao calcular pontuacao!")

#Devolve os nomes dos arquivos do projeto e dos planos, caso existam
def getFiles(idProjeto):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE)
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    consulta = "SELECT arquivo_projeto,arquivo_plano1,arquivo_plano2 FROM editalProjeto WHERE id=" + idProjeto
    cursor.execute(consulta)
    linha = cursor.fetchone()
    conn.close()
    return(linha)

def naoEstaFinalizado(token):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE)
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    consulta = "SELECT finalizado FROM avaliacoes WHERE token=\"" + token + "\""
    cursor.execute(consulta)
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
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE)
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    #consulta = "SELECT deadline_avaliacao,CURRENT_TIMESTAMP() FROM editais WHERE CURRENT_TIMESTAMP()<deadline_avaliacao AND id=" + codigoEdital
    consulta = "SELECT e.id as codigoEdital,e.deadline_avaliacao,p.id FROM editais e, editalProjeto p WHERE p.tipo=e.id and deadline_avaliacao>CURRENT_TIMESTAMP() AND p.id=" + idProjeto
    cursor.execute(consulta)
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
                link_projeto = url_for('verArquivosProjeto',filename=str(arquivos[0]))
            if str(arquivos[1])!="0":
                link_plano1 = url_for('verArquivosProjeto',filename=str(arquivos[1]))
            if str(arquivos[2])!="0":
                link_plano2 = url_for('verArquivosProjeto',filename=str(arquivos[2]))
            links = ""
            if 'link_projeto' in locals():
                links = links + "<a href=\"" + link_projeto + "\" target=\"_blank\">PROJETO</a><BR>"
            if 'link_plano1' in locals():
                links = links + "<a href=\"" + link_plano1 + "\" target=\"_blank\">PLANO DE TRABALHO 1</a><BR>"
            if 'link_plano2' in locals():
                links = links + "<a href=\"" + link_plano2 + "\" target=\"_blank\">PLANO DE TRABALHO 2</a><BR>"
            links = links + "<input type=\"hidden\" id=\"token\" name=\"token\" value=\"" + tokenAvaliacao + "\">"
            if naoEstaFinalizado(tokenAvaliacao):
                consulta = "UPDATE avaliacoes SET aceitou=1 WHERE token=\"" + tokenAvaliacao + "\""
                atualizar(consulta)
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
            consulta = "UPDATE avaliacoes SET recomendacao= ? WHERE token= ? "
            atualizar2(consulta, valores=[recomendacao,token])
            consulta = "UPDATE avaliacoes SET finalizado=1 WHERE token= ? "
            atualizar2(consulta, valores=[token])
            consulta = "UPDATE avaliacoes SET data_avaliacao=CURRENT_TIMESTAMP() WHERE token= ? "
            atualizar2(consulta, valores=[token])
            consulta = "UPDATE avaliacoes SET nome_avaliador= ? WHERE token= ?"
            atualizar2(consulta, valores=[nome_avaliador,token])
            comentarios = comentarios.replace('"',' ')
            comentarios = comentarios.replace("'"," ")
            consulta = "UPDATE avaliacoes SET comentario= ? WHERE token= ? "
            atualizar2(consulta, valores=[comentarios,token])
            consulta = "UPDATE avaliacoes SET c1= ? WHERE token= ? "
            atualizar2(consulta, valores=[c1,token])
            consulta = "UPDATE avaliacoes SET c2= ? WHERE token= ? "
            atualizar2(consulta, valores=[c2,token])
            consulta = "UPDATE avaliacoes SET c3= ? WHERE token= ? "
            atualizar2(consulta, valores=[c3,token])
            consulta = "UPDATE avaliacoes SET c4= ? WHERE token= ? "
            atualizar2(consulta, valores=[c4,token])
            consulta = "UPDATE avaliacoes SET c5= ? WHERE token= ? "
            atualizar2(consulta, valores=[c5,token])
            consulta = "UPDATE avaliacoes SET c6= ? WHERE token= ? "
            atualizar2(consulta, valores=[c6,token])
            consulta = "UPDATE avaliacoes SET c7= ? WHERE token= ? "
            atualizar2(consulta, valores=[c7,token])
            consulta = "UPDATE avaliacoes SET cepa= ? WHERE token= ? "
            atualizar2(consulta, valores=[comite,token])
            logger.info("[{}][/avaliar] Avaliação do projeto {} gravada com sucesso por {}", request.remote_addr,str(idProjeto),str(nome_avaliador))
            if modalidade==2:
                inovacao = str(request.form['inovacao'])
                consulta = "UPDATE avaliacoes SET inovacao= ? WHERE token= ? "
                atualizar2(consulta, valores=[inovacao,token])
        except Exception as e:
            logger.error("[AVALIACAO] ERRO ao gravar a avaliação: {} - ({})", token, str(e))
            return("Não foi possível gravar a avaliação. Favor entrar contactar " + DEFAULT_EMAIL)
        try:
            return (redirect(url_for('getDeclaracaoAvaliador',tokenAvaliacao=token)))
        except Exception as e:
            logger.error("[/avaliar] ERRO ao gerar a declaração: {} - ({})",token, str(e))
            return("Não foi possível gerar a declaração.")
    else:
        return("OK")

def descricaoEdital(codigoEdital):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE)
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    consulta = "SELECT id,nome FROM editais WHERE id=" + codigoEdital
    cursor.execute(consulta)
    linhas = cursor.fetchall()
    nomeEdital = "EDITAL NAO DEFINIDO"
    for linha in linhas:
        nomeEdital = str(linha[1])
    conn.close()
    return (nomeEdital)

def enviar_declaracao_avaliador(url,destinatario):
    with app.app_context():
        texto_email = render_template('email_declaracao_avaliador.html',url=url)
        if PRODUCAO==1:
            msg = Message(subject = "Plataforma Yoko - DECLARAÇÃO DE AVALIAÇÃO DE PROJETO DE PESQUISA",recipients=[destinatario],html=texto_email,reply_to="NAO-RESPONDA@ufca.edu.br")
        else:
            msg = Message(subject = "Plataforma Yoko - DECLARAÇÃO DE AVALIAÇÃO DE PROJETO DE PESQUISA",recipients=["pesquisapython3.display999@passmail.net"],html=texto_email,reply_to="NAO-RESPONDA@ufca.edu.br")
        try:
            mail.send(msg)
            logger.info("E-mail enviado com sucesso para o avaliador: {}", calcula_hash(destinatario))
        except Exception as e:
            logger.warning("Erro ao enviar e-mail: {}. [enviar declaração para avaliador]: {}", destinatario,str(e))

@app.route("/declaracaoAvaliador/<tokenAvaliacao>", methods=['GET'])
@log_required
def getDeclaracaoAvaliador(tokenAvaliacao):
    """
    Gera a declaração de avaliação do avaliador.
    """
    if not token_valido(tokenAvaliacao):
        logger.error("[/declaracaoAvaliador] Token inválido: {}", tokenAvaliacao)
        return "Token inválido!"
    consulta = f"""
    SELECT nome_avaliador,idProjeto,avaliador FROM avaliacoes WHERE token="{tokenAvaliacao}" 
    AND finalizado=1
    """
    linhas = consultar(consulta)
    nome_avaliador = "NAO INFORMADO"
    idProjeto = 0
    for linha in linhas:
        nome_avaliador = str(linha[0])
        idProjeto = str(linha[1])
        destinatario = str(linha[2])
    if idProjeto!=0:
        titulo = str(obterColunaUnica("editalProjeto","titulo","id",idProjeto))
        codigo_do_edital = str(obterColunaUnica("editalProjeto","tipo","id",idProjeto))
        descricao_do_edital = str(obterColunaUnica("editais","nome","id",codigo_do_edital))
        data_agora = getData()
        url = url_for('getDeclaracaoAvaliador',tokenAvaliacao=tokenAvaliacao, _external=True)
        thread = threading.Thread(target=enviar_declaracao_avaliador,args=(url,destinatario,))
        thread.start()
        return render_template('declaracao_avaliador.html',
                               nome=nome_avaliador,data=data_agora,edital=descricao_do_edital,
                               titulo=titulo,idProjeto=idProjeto)
    else:
        return "PROJETO AINDA NÃO AVALIADO OU INEXISTENTE!"
    
def consultar(consulta):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE)
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    cursor.execute(consulta)
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
        consulta = "UPDATE avaliacoes SET aceitou=0 WHERE token=\"" + tokenAvaliacao + "\""
        atualizar(consulta)
        return("Avaliação cancelada com sucesso. Agradecemos a atenção.")
    else:
        return("OK")

@app.route("/avaliacoesNegadas", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def avaliacoesNegadas():
    if request.method == "GET":
        conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE)
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
                consulta = "SELECT resumoGeralAvaliacoes.id,CONCAT(SUBSTRING(resumoGeralAvaliacoes.titulo,1,80),\" - (\",resumoGeralAvaliacoes.nome,\" )\"),(resumoGeralAvaliacoes.aceites+resumoGeralAvaliacoes.rejeicoes) as resultado,resumoGeralAvaliacoes.indefinido FROM resumoGeralAvaliacoes WHERE ((aceites+rejeicoes<10) OR (aceites=rejeicoes)) AND tipo=" + codigoEdital + " AND id = " + idProjeto +" ORDER BY aceites+rejeicoes, id"
            else:
                consulta = "SELECT resumoGeralAvaliacoes.id,CONCAT(SUBSTRING(resumoGeralAvaliacoes.titulo,1,80),\" - (\",resumoGeralAvaliacoes.nome,\" )\"),(resumoGeralAvaliacoes.aceites+resumoGeralAvaliacoes.rejeicoes) as resultado,resumoGeralAvaliacoes.indefinido FROM resumoGeralAvaliacoes WHERE ((aceites+rejeicoes<2) OR (aceites=rejeicoes)) AND tipo=" + codigoEdital + " ORDER BY aceites+rejeicoes, id"
            try:
                cursor.execute(consulta)
                linha = cursor.fetchall()
                total = cursor.rowcount
                conn.close()
                return(render_template('inserirAvaliador.html',listaProjetos=linha,totalDeLinhas=total,codigoEdital=codigoEdital))
            except Exception as e:
                logger.error(e)
                logger.error(consulta)
                conn.close()
                return(consulta)
        else:
            return ("OK")
    else:
        return("OK")

@app.route("/inserirAvaliador", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def inserirAvaliador():
    """
    Atribuir avaliador a um projeto
    """
    if request.method == "POST":
        token = id_generator(40)
        idProjeto = int(request.form['txtProjeto'])
        avaliador1_email = str(request.form['txtEmail'])
        consulta_verificacao = """
            SELECT avaliador from avaliacoes WHERE idProjeto = ? AND avaliador = ? 
        """
        linhas, total = executarSelect2(consulta_verificacao,valores=[idProjeto, avaliador1_email])
        if total > 0: #Já existe este avaliador para este projeto
            return("Avaliador já cadastrado para este projeto.")
        consulta = "INSERT INTO avaliacoes (aceitou,avaliador,token,idProjeto) VALUES (-1, ?, ?, ?)"
        atualizar2(consulta, valores=[avaliador1_email, token, str(idProjeto)])
        t = threading.Thread(target=enviarPedidoAvaliacao,args=(idProjeto,))
        t.start()
        return("Avaliador cadastrado com sucesso.")
    else:
        return("OK")

#Retorna a quantidade de linhas da consulta
def quantidades(consulta):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE)
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    cursor.execute(consulta)
    total = cursor.rowcount
    conn.close()
    return (total)

@app.route("/estatisticas", methods=['GET', 'POST'])
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
        consulta = "SELECT * FROM resumoGeralAvaliacoes WHERE tipo=" + codigoEdital + " ORDER BY ua, score DESC"
        conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE)
        conn.select_db(MYSQL_DATABASE)
        cursor  = conn.cursor()
        cursor.execute(consulta)
        resumoGeral = cursor.fetchall()
        consulta = "SELECT * FROM resumoGeralAvaliacoes WHERE aceites>=2 AND aceites>rejeicoes AND tipo=" + codigoEdital + " ORDER BY ua, score DESC"
        cursor.execute(consulta)
        aprovados = cursor.fetchall()
        consulta = "SELECT * FROM resumoGeralAvaliacoes WHERE ((aceites+rejeicoes<2) OR (aceites=rejeicoes)) AND tipo=" + codigoEdital + " ORDER BY ua, score DESC"
        #consulta = "SELECT e.id,e.titulo,e.resumo,a.avaliador,a.link,a.id,a.enviado,a.token,e.categoria,e.tipo FROM editalProjeto as e, avaliacoes as a WHERE e.id=a.idProjeto AND e.valendo=1 AND a.finalizado=0 AND a.aceitou!=0 AND e.categoria=1 AND e.tipo=1 AND a.idProjeto IN (SELECT id FROM resumoGeralAvaliacoes WHERE ((aceites+rejeicoes<2) OR (aceites=rejeicoes)) AND tipo=" + codigoEdital + ")"
        cursor.execute(consulta)
        pendentes = cursor.fetchall()
        consulta = "SELECT * FROM resumoGeralAvaliacoes WHERE rejeicoes>=2 AND rejeicoes>aceites AND tipo=" + codigoEdital + " ORDER BY ua, score DESC"
        cursor.execute(consulta)
        reprovados = cursor.fetchall()
        consulta = "SELECT nome FROM editais WHERE id=" + codigoEdital
        cursor.execute(consulta)
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
        consulta = "SELECT ua,nome,siape FROM resumoGeralClassificacao WHERE tipo=" + codigoEdital + " AND bolsas>0 AND siape=" + siape + " AND siape IN (SELECT siape FROM edital02_2018 WHERE situacao=\"ATIVO\" and modalidade=\"PIBIC\" GROUP BY siape HAVING count(id)=2 ORDER BY orientador) ORDER BY nome"
        total = quantidades(consulta)
        if (total>0):
            return (True)
        else:
            return (False)
    else:
        return (False)

def distribuir_bolsas(demanda,consulta):
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
    linhas,total = executarSelect(consulta)
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
                        consulta = "UPDATE editalProjeto SET bolsas_concedidas=bolsas_concedidas+1 WHERE id=" + str(idProjeto)
                        atualizar(consulta)
                        demanda[ua] = demanda[ua] - 1
                        linha[11] = str(int(linha[11]) + 1)
                        consulta = "UPDATE editalProjeto SET obs=\"BOLSA CONCEDIDA\" WHERE id=" + str(idProjeto)
                        atualizar(consulta)
                    else: #Se o orientador estiver com a cota estourada
                        consulta = "UPDATE editalProjeto SET obs=\"BOLSA NÃO CONCEDIDA. ORIENTADOR NÃO PODE ULTRASSAR A COTA DE 2 BOLSISTAS POR MODALIDADE (Anexo XIV da Res. 01/2014/CONSUP, Art. 7 Inciso I)\" WHERE id=" + str(idProjeto)
                        atualizar(consulta)
            else: # se a unidade não tem mais bolsas disponíveis em sua cota
                if concedidas>0: #Se o projeto já foi contemplado com bolsas
                    consulta = "UPDATE editalProjeto SET obs=\"CONCESSÃO PARCIAL. COTA DA UNIDADE ZERADA (Anexo XIV da Res. 01/2014/CONSUP, Art. 7 Inciso II)\" WHERE id=" + str(idProjeto)
                else: #Se o projeto não foi contemplado com bolsas
                    consulta = "UPDATE editalProjeto SET obs=\"BOLSA NÃO CONCEDIDA. COTA DA UNIDADE ZERADA (Anexo XIV da Res. 01/2014/CONSUP, Art. 7 Inciso II)\" WHERE id=" + str(idProjeto)
                atualizar(consulta)
        
def executarSelect(consulta,tipo=0):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE)
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
        logger.error("ERRO Na função executarSelect: {}", str(e))
    finally:
        cursor.close()
        conn.close()

def executarSelect2(consulta,tipo=0,valores=()):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE)
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
        logger.error("ERRO Na função executarSelect2: {}", str(e))
    finally:
        cursor.close()
        conn.close()

def avaliacoesEncerradas(codigoEdital):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE)
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    consulta = "SELECT deadline_avaliacao,CURRENT_TIMESTAMP() FROM editais WHERE CURRENT_TIMESTAMP()<deadline_avaliacao AND id=" + codigoEdital
    cursor.execute(consulta)
    total = cursor.rowcount
    conn.close()
    if (total>0): #Edital com avaliacoes encerradas
        return(False)
    else: #Edital com avaliacoes em andamento
        return(True)

@app.route("/resultados", methods=['GET', 'POST'])
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
        consulta = "SELECT * FROM resumoGeralClassificacao WHERE tipo=" + codigoEdital + " ORDER BY ua, score DESC"
        conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE)
        conn.select_db(MYSQL_DATABASE)
        cursor  = conn.cursor()
        cursor.execute(consulta)
        total = cursor.rowcount
        resumoGeral = cursor.fetchall()

        #Recuperando dados do edital
        consulta = "SELECT nome,deadline_avaliacao,quantidade_bolsas,mensagem,recursos,link FROM editais WHERE id=" + codigoEdital
        cursor.execute(consulta)
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
        total_projetos = str(quantidades("SELECT id FROM resumoGeralClassificacao WHERE tipo=" + codigoEdital))
        bolsas_disponiveis = "floor((count(id)/" + total_projetos + ")*" + qtde_bolsas + ") "

        #Recuperando a demanda e oferta de Bolsas
        consulta = "SELECT ua,count(id)," + bolsas_disponiveis +  "as total_bolsas FROM editalProjeto WHERE valendo=1 AND tipo=" + codigoEdital +  " GROUP BY ua"
        cursor.execute(consulta)
        demanda = cursor.fetchall()

        #ZERANDO as concessões
        consulta = "UPDATE editalProjeto SET bolsas_concedidas=0 WHERE tipo=" + codigoEdital
        atualizar(consulta)

        #Recalculando resumoGeral
        consulta = "SELECT * FROM resumoGeralClassificacao WHERE tipo=" + codigoEdital + " ORDER BY ua, score DESC"
        resumoGeral,total = executarSelect(consulta)

        #Distribuição de cota de bolsas
        unidades = {}
        for linha in demanda:
            unidades[str(linha[0])] = int(linha[2])
        distribuir_bolsas(unidades,consulta)

        ## TODO: Redistribuir bolsas remanescentes baseado na classificação geral pelo lattes

        #Recalculando resumoGeral após distribuição
        consulta = "SELECT * FROM resumoGeralClassificacao WHERE tipo=" + codigoEdital + " ORDER BY ua, score DESC"
        resumoGeral,total = executarSelect(consulta)

        #Total de bolsas distribuídas por unidade academica
        consulta = "SELECT ua,sum(bolsas) as solicitadas, sum(bolsas_concedidas) as concedidas,(sum(bolsas_concedidas)/sum(bolsas))*100 as percentual FROM resumoGeralClassificacao WHERE tipo=" + codigoEdital + " GROUP BY ua ORDER BY ua"
        cursor.execute(consulta)
        somatorios = cursor.fetchall()
        app.logger.debug(consulta)

        #Verificando se as avaliacoes estão encerradas
        if avaliacoesEncerradas(codigoEdital):
            titulo = "Resultado Preliminar"
        else:
            titulo = "Resultado Parcial"

        #Calculando estatísticas de avaliações
        estatisticas = []
        consultaPorUnidade = "SELECT editalProjeto.ua,avg((TIMESTAMPDIFF(DAY,data_envio,data_avaliacao))) as media, min((TIMESTAMPDIFF(DAY,data_envio,data_avaliacao))) as minimo, max((TIMESTAMPDIFF(DAY,data_envio,data_avaliacao))) as maximo  FROM avaliacoes,editalProjeto WHERE editalProjeto.id=avaliacoes.idProjeto AND finalizado=1 AND editalProjeto.tipo=" + codigoEdital +  " GROUP BY editalProjeto.ua ORDER BY editalProjeto.ua"
        consultaPorTotal = "SELECT avg((TIMESTAMPDIFF(DAY,data_envio,data_avaliacao))) as media, min((TIMESTAMPDIFF(DAY,data_envio,data_avaliacao))) as minimo, max((TIMESTAMPDIFF(DAY,data_envio,data_avaliacao))) as maximo  FROM avaliacoes,editalProjeto WHERE editalProjeto.id=avaliacoes.idProjeto AND finalizado=1 AND editalProjeto.tipo=" + codigoEdital
        porUnidade,qtde = executarSelect(consultaPorUnidade)
        porTotal,qtde = executarSelect(consultaPorTotal)

        consultaAvaliacoesTotais = """SELECT
        (SELECT count(avaliacoes.id) FROM avaliacoes,editalProjeto WHERE finalizado=1 and editalProjeto.id=avaliacoes.idProjeto and editalProjeto.tipo=1) as finalizados,
        (SELECT count(avaliacoes.id) FROM avaliacoes,editalProjeto WHERE finalizado=0 and aceitou=1 and editalProjeto.id=avaliacoes.idProjeto and editalProjeto.tipo=1) as indefinidos,
        (SELECT count(avaliacoes.id) FROM avaliacoes,editalProjeto WHERE finalizado=0 and aceitou=0 and editalProjeto.id=avaliacoes.idProjeto and editalProjeto.tipo=1) as negadas,
        (SELECT count(avaliacoes.id) FROM avaliacoes,editalProjeto WHERE editalProjeto.id=avaliacoes.idProjeto and editalProjeto.tipo=1) as total
        FROM avaliacoes,editalProjeto WHERE editalProjeto.id=avaliacoes.idProjeto and editalProjeto.tipo=1 LIMIT 1"""
        consultaAvaliacoesTotais.replace(".tipo=1",".tipo=" + codigoEdital)
        avaliacoesTotais,qtde = executarSelect(consultaAvaliacoesTotais)
        retorno = (1,2,3,4)
        for avaliacoes in avaliacoesTotais:
            retorno = avaliacoes
        #Projetos novos e em andamento
        projetosNovos = quantidades("SELECT id FROM editalProjeto WHERE valendo=1 and categoria=1 AND tipo=" + codigoEdital)
        projetosEmAndamento = quantidades("SELECT id FROM editalProjeto WHERE valendo=1 and categoria=0 AND tipo=" + codigoEdital)
        #Finalizando...
        conn.close()
        data_agora = getData()
        return(render_template('resultados.html',projetosNovos=projetosNovos,projetosEmAndamento=projetosEmAndamento,avaliacoes=retorno,porUnidade=porUnidade,porTotal=porTotal,link=link,mensagem=mensagem,recursos=recursos,nomeEdital=edital,linhasResumo=resumoGeral,totalGeral=total,demanda=demanda,bolsas=qtde_bolsas,somatorios=somatorios,titulo=titulo,data=data_agora))
    else:
        return("OK")

#TODO: Parametrizar consulta (sqli)
def obterColunaUnica(tabela,coluna,colunaId,valorId):
    '''
    Retorna uma coluna de uma linha única dado uma chave primária
    '''
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE)
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    consulta = "SELECT " + coluna + " FROM " + tabela + " WHERE " + colunaId + "=" + valorId
    resultado = "0"
    try:
        cursor.execute(consulta)
        linhas = cursor.fetchall()
        for linha in linhas:
            resultado = str(linha[0])
        return(resultado)
    except Exception as e:
        logger.error("ERRO Na função obtercolunaUnica: {}", str(e))
    finally:
        cursor.close()
        conn.close()
        
def obterColunaUnica_str(tabela,coluna,colunaId,valorId):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE)
    conn.select_db(MYSQL_DATABASE)
    cursor  = conn.cursor()
    consulta = "SELECT " + coluna + " FROM " + tabela + " WHERE " + colunaId + "=\"" + valorId + "\""
    resultado = "0"
    try:
        cursor.execute(consulta)
        linhas = cursor.fetchall()
        for linha in linhas:
            resultado = str(linha[0])
        return(resultado)
    except:
        e = sys.exc_info()[0]
        logger.error(e)
        logger.error("ERRO Na função obtercolunaUnica. Ver consulta abaixo.")
        logger.error(consulta)
    finally:
        cursor.close()
        conn.close()


def gerarPDF(template):
    try:
        arquivoDeclaracao = app.config['TEMP_FOLDER'] + 'resultados.pdf'
        options = {
            'page-size': 'A4',
            'margin-top': '2cm',
            'margin-right': '2cm',
            'margin-bottom': '1cm',
            'margin-left': '2cm',
        }
        pdfkit.from_string(template,arquivoDeclaracao,options=options)
    except:
        e = sys.exc_info()[0]
        logger.error(e)
        logger.error("ERRO Na função gerarPDF")
    #return send_from_directory(app.config['TEMP_FOLDER'], 'resultados.pdf')

@app.route("/editalProjeto", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def editalProjeto():
    if (autenticado() and int(session['permissao'])==0):
        if request.method == "GET":
            #Recuperando o código do edital
            if 'edital' in request.args:
                codigoEdital = str(request.args.get('edital'))
                session['edital'] = codigoEdital
                conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE)
                conn.select_db(MYSQL_DATABASE)
                cursor  = conn.cursor()
                tipo_classificacao = int(obterColunaUnica("editais","classificacao","id",codigoEdital))
                #ORDENA DE ACORDO COM O TIPO DE CLASSIFICAÇÃO: 1 - POR UA; 2 - POR LATTES
                if (tipo_classificacao==1):
                    consulta = "SELECT id,tipo,categoria,nome,email,ua,scorelattes,titulo,arquivo_projeto,arquivo_plano1,arquivo_plano2,arquivo_lattes_pdf,arquivo_comprovantes,DATE_FORMAT(data,\"%d/%m/%Y - %H:%i\") as data,DATE_FORMAT(inicio,\"%d/%m/%Y\") as inicio,DATE_FORMAT(fim,\"%d/%m/%Y\") as fim,if(produtividade=0,\"PROD. CNPq\",if(produtividade=1,\"BPI FUNCAP\",\"NORMAL\")) as prioridade,bolsas,bolsas_concedidas,obs,arquivo_plano3 FROM editalProjeto WHERE tipo=" + codigoEdital + " AND valendo=1 ORDER BY ua,produtividade,scorelattes DESC,nome"
                else:
                    consulta = "SELECT id,tipo,categoria,nome,email,ua,scorelattes,titulo,arquivo_projeto,arquivo_plano1,arquivo_plano2,arquivo_lattes_pdf,arquivo_comprovantes,DATE_FORMAT(data,\"%d/%m/%Y - %H:%i\") as data,DATE_FORMAT(inicio,\"%d/%m/%Y\") as inicio,DATE_FORMAT(fim,\"%d/%m/%Y\") as fim,if(produtividade=0,\"PROD. CNPq\",if(produtividade=1,\"BPI FUNCAP\",\"NORMAL\")) as prioridade,bolsas,bolsas_concedidas,obs,arquivo_plano3 FROM editalProjeto WHERE tipo=" + codigoEdital + " AND valendo=1 ORDER BY produtividade,scorelattes DESC,nome"
                
                consulta_novos = """
                SELECT editalProjeto.id,
                nome,
                ua,
                titulo,
                arquivo_projeto,
                GROUP_CONCAT(avaliacoes.avaliador ORDER BY avaliador SEPARATOR '<BR>') as avaliadores,
                GROUP_CONCAT(IF(avaliacoes.recomendacao=1,'RECOMENDADO',IF(avaliacoes.recomendacao=0,'***NÃO RECOMENDADO***','EM AVALIAÇÃO')) ORDER BY avaliador SEPARATOR '<BR>') as recomendacoes, 
                GROUP_CONCAT(avaliacoes.enviado ORDER BY avaliador SEPARATOR '<BR>') as enviado,
                GROUP_CONCAT(IF(avaliacoes.aceitou=1,'ACEITOU',IF(avaliacoes.aceitou=0,'REJEITOU','NÃO RESPONDEU')) ORDER BY avaliador SEPARATOR '<BR>') as aceitou,
                sum(avaliacoes.finalizado) as finalizados,
                sum(if(recomendacao=-1,1,0)), 
                sum(if(recomendacao=0,1,0)),
                sum(if(recomendacao=1,1,0)),palavras,
                sum(avaliacoes.inovacao) as inovacao
                FROM editalProjeto
                LEFT JOIN avaliacoes ON editalProjeto.id=avaliacoes.idProjeto
                WHERE tipo=%s
                AND valendo=1 AND categoria=1 
                GROUP BY editalProjeto.id 
                ORDER BY finalizados,editalProjeto.ua,editalProjeto.id
                """ % (codigoEdital)
                modalidade = int(obterColunaUnica("editais","modalidade","id",codigoEdital))
                demanda = """SELECT ua,count(id) FROM editalProjeto WHERE valendo=1 and tipo=""" + codigoEdital + """ GROUP BY ua 
                ORDER BY ua"""
                
                bolsas_ufca = int(obterColunaUnica("editais","quantidade_bolsas","id",codigoEdital))
                bolsas_cnpq = int(obterColunaUnica("editais","quantidade_bolsas_cnpq","id",codigoEdital))
                
                try:
                    cursor.execute(consulta)
                    total = cursor.rowcount
                    linhas = cursor.fetchall()
                    descricao = descricaoEdital(codigoEdital)
                    cursor.execute(consulta_novos)
                    total_novos = cursor.rowcount
                    linhas_novos = cursor.fetchall()
                    cursor.execute(demanda)
                    linhas_demanda = cursor.fetchall()
                    
                    if 'resultado' in request.args:
                        if 'pdf' in request.args:
                            mensagem = str(obterColunaUnica("editais","mensagem","id",codigoEdital))
                            gerarPDF(render_template('editalProjeto.html',listaProjetos=linhas,descricao=descricao,total=total,novos=linhas_novos,total_novos=total_novos,linhas_demanda=linhas_demanda,bolsas_ufca=bolsas_ufca,bolsas_cnpq=bolsas_cnpq,codigoEdital=codigoEdital,resultado=1,mensagem=mensagem,modalidade=modalidade))
                            return(send_from_directory(app.config['TEMP_FOLDER'], 'resultados.pdf'))

                        else:
                            mensagem = str(obterColunaUnica("editais","mensagem","id",codigoEdital))
                            return(render_template('editalProjeto.html',listaProjetos=linhas,descricao=descricao,total=total,novos=linhas_novos,total_novos=total_novos,linhas_demanda=linhas_demanda,bolsas_ufca=bolsas_ufca,bolsas_cnpq=bolsas_cnpq,codigoEdital=codigoEdital,resultado=1,mensagem=mensagem,modalidade=modalidade))
                    else:
                        mensagem = ""
                        return(render_template('editalProjeto.html',listaProjetos=linhas,descricao=descricao,total=total,novos=linhas_novos,total_novos=total_novos,linhas_demanda=linhas_demanda,bolsas_ufca=bolsas_ufca,bolsas_cnpq=bolsas_cnpq,codigoEdital=codigoEdital,resultado=0,modalidade=modalidade))
                except Exception as e:
                    logger.error(str(e))
                    logger.error("ERRO Na função /editalProjeto. Ver consulta abaixo.")
                    logger.error(consulta)
                    return("ERRO!")
                finally:
                    cursor.close()
                    conn.close()

            else:
                return ("OK")
    else:
        return(render_template('login.html',mensagem="É necessário autenticação para acessar a página solicitada"))

@app.route("/lattesDetalhado", methods=['GET', 'POST'])
@log_required
def lattesDetalhado():
    if request.method == "GET":
        #Recuperando o código do projeto
        if 'id' in request.args:
            idProjeto = str(request.args.get('id'))
            conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db=MYSQL_DATABASE)
            conn.select_db(MYSQL_DATABASE)
            cursor  = conn.cursor()
            consulta = "SELECT id,scorelattes_detalhado FROM editalProjeto WHERE id=" + idProjeto + " AND valendo=1"
            cursor.execute(consulta)
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
                consulta = "SELECT id,nome,evento,modalidade FROM declaracoes WHERE siape=" + siape
                declaracoes,total = executarSelect(consulta)
                return(render_template('declaracoes_servidor.html',listaDeclaracoes=declaracoes))
            except:
                e = sys.exc_info()[0]
                logger.error(e)
                logger.error("ERRO Na função /declaracoesPorServidor. Ver consulta abaixo.")
                logger.error(consulta)
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
            consulta = "SELECT nome,siape,participacao,evento,modalidade,periodo,local FROM declaracoes WHERE id=" + idDeclaracao
            linhas,total = executarSelect(consulta)
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
        consulta = """SELECT id,nome_do_coordenador,orientador_lotacao,titulo_do_projeto,DATE_FORMAT(inicio,'%d/%m/%Y') as inicio,DATE_FORMAT(termino,'%d/%m/%Y') as fim,estudante_nome_completo,token FROM cadastro_geral WHERE siape='""" + str(session['username']) + """' ORDER BY inicio,titulo_do_projeto"""
        projetos,total = executarSelect(consulta)
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
        (SELECT GROUP_CONCAT(CONCAT('(',id,') - ',nome,' (',IF(tipo_de_vaga=0,'VOLUNTARIO(A)','BOLSISTA'),')',' (',IF(situacao=0,'OK',IF(situacao=1,'DESLIGADO(A)','SUBSTITUIDO(A)')), ')') ORDER BY nome SEPARATOR '<BR><BR>') FROM indicacoes WHERE idProjeto=editalProjeto.id GROUP BY idProjeto) as orientandos
         FROM editalProjeto,editais WHERE valendo=1 AND editalProjeto.tipo=editais.id AND siape=""" + str(session['username']) + """ ORDER BY editalProjeto.data """
        projetos2019,total2019 = executarSelect(consulta_outros)

        consulta_orientandos_atuais = """SELECT indicacoes.id,indicacoes.nome,DATE_FORMAT(indicacoes.inicio,'%d/%m/%Y'),IF(indicacoes.fomento=0,'UFCA',IF(indicacoes.fomento=1,'CNPq','FUNCAP')),IF(indicacoes.tipo_de_vaga=0,'VOLUNTÁRIO','BOLSISTA'),DATE_FORMAT(indicacoes.fim,'%d/%m/%Y'),IF(indicacoes.modalidade=1,'PIBIC',IF(indicacoes.modalidade=2,'PIBITI',IF(indicacoes.modalidade=3,'PIBIC-EM','PIBIC-AF'))),
        (SELECT GROUP_CONCAT(CONCAT_WS('/',mes,ano) SEPARATOR '<BR><BR>') FROM frequencias WHERE frequencias.idIndicacao=indicacoes.id) as enviadas, editalProjeto.titulo
        FROM indicacoes,editalProjeto
        WHERE editalProjeto.id=indicacoes.idProjeto AND indicacoes.fim>NOW() AND editalProjeto.siape=""" + str(session['username']) + """ ORDER BY indicacoes.tipo_de_vaga,editalProjeto.titulo,indicacoes.nome """
        orientandos_atuais,totalOrientandos = executarSelect(consulta_orientandos_atuais)

        consulta_orientandos_antigos = """SELECT indicacoes.id,indicacoes.nome,DATE_FORMAT(indicacoes.inicio,'%d/%m/%Y'),IF(indicacoes.fomento=0,'UFCA',IF(indicacoes.fomento=1,'CNPq','FUNCAP')),IF(indicacoes.tipo_de_vaga=0,'VOLUNTÁRIO','BOLSISTA'),DATE_FORMAT(indicacoes.fim,'%d/%m/%Y'),IF(indicacoes.modalidade=1,'PIBIC',IF(indicacoes.modalidade=2,'PIBITI',IF(indicacoes.modalidade=3,'PIBIC-EM','PIBIC-AF'))),
        (SELECT GROUP_CONCAT(CONCAT_WS('/',mes,ano) SEPARATOR '<BR><BR>') FROM frequencias WHERE frequencias.idIndicacao=indicacoes.id) as enviadas, editalProjeto.titulo
        FROM indicacoes,editalProjeto
        WHERE editalProjeto.id=indicacoes.idProjeto AND indicacoes.fim<NOW() AND editalProjeto.siape=""" + str(session['username']) + """ ORDER BY indicacoes.tipo_de_vaga,editalProjeto.titulo,indicacoes.nome """
        orientandos_antigos,totalOrientandosAntigos = executarSelect(consulta_orientandos_antigos)

        return(render_template('meusProjetos.html',projetos=projetos,total=total,projetos2019=projetos2019,total2019=total2019,permissao=session['permissao'],orientandos=orientandos_atuais,orientandos_antigos=orientandos_antigos))
    else:
        return(render_template('login.html',mensagem="É necessário autenticação para acessar a página solicitada"))

@app.route("/minhaDeclaracaoOrientador", methods=['GET', 'POST'])
@log_required
def minhaDeclaracao():
    if autenticado():
        if request.method == "GET":
            #Recuperando o token da declaração
            if 'token' in request.args:
                token = str(request.args.get('token'))
                consulta = """SELECT nome_do_coordenador,siape,titulo_do_projeto,DATE_FORMAT(estudante_inicio,'%d/%m/%Y') as inicio,DATE_FORMAT(estudante_fim,'%d/%m/%Y') as fim,estudante_nome_completo,token,if(estudante_fim<NOW(),"exerceu","exerce") as verbo FROM cadastro_geral WHERE token='""" + token + """' ORDER BY inicio,titulo_do_projeto"""
                projeto,total = executarSelect(consulta,1)
                data_agora = getData()
                if total==1:
                    arquivoDeclaracao = app.config['DECLARACOES_FOLDER'] + 'declaracao.pdf'
                    options = {
                        'page-size': 'A4',
                        'margin-top': '2cm',
                        'margin-right': '2cm',
                        'margin-bottom': '1cm',
                        'margin-left': '2cm',
                    }
                    pdfkit.from_string(render_template('declaracao_orientador.html',texto=projeto,data=data_agora,identificador=token,raiz=ROOT_SITE),arquivoDeclaracao,options=options)
                    return send_from_directory(app.config['DECLARACOES_FOLDER'], 'declaracao.pdf')
                    
                else:
                    return("declaração inexistente!")
            else:
                if 'id' in request.args:
                    idProjeto = str(request.args.get('id'))
                    consulta = """SELECT DISTINCT editalProjeto.nome,editalProjeto.siape,editalProjeto.titulo,
                    DATE_FORMAT(editalProjeto.inicio,'%d/%m/%Y') as inicio,DATE_FORMAT(editalProjeto.fim,'%d/%m/%Y') as fim,
                    (SELECT GROUP_CONCAT(indicacoes.nome,' (',year(indicacoes.inicio),'/',year(indicacoes.fim),') ' ORDER BY indicacoes.nome SEPARATOR ', ') from indicacoes WHERE indicacoes.idProjeto=editalProjeto.id GROUP BY indicacoes.idProjeto) as indicados,
                    editalProjeto.id,if(editalProjeto.fim<NOW(),"exerceu","exerce") as verbo
                    FROM editalProjeto,indicacoes
                    WHERE editalProjeto.id=indicacoes.idProjeto AND editalProjeto.id=""" + idProjeto + """ ORDER BY fim DESC"""
                    projeto,total = executarSelect(consulta,1)
                    data_agora = getData()
                    if total>0:
                        arquivoDeclaracao = app.config['DECLARACOES_FOLDER'] + 'declaracao.pdf'
                        options = {
                            'page-size': 'A4',
                            'margin-top': '2cm',
                            'margin-right': '2cm',
                            'margin-bottom': '1cm',
                            'margin-left': '2cm',
                        }
                        pdfkit.from_string(render_template('declaracao_orientador.html',texto=projeto,data=data_agora,identificador=idProjeto,raiz=ROOT_SITE),arquivoDeclaracao,options=options)
                        return send_from_directory(app.config['DECLARACOES_FOLDER'], 'declaracao.pdf')
                    else:
                        return("declaracao inexistente...")

                if 'idAluno' in request.args:
                    idAluno = str(request.args.get('idAluno'))
                    idProjeto = obterColunaUnica("indicacoes","idProjeto","id",idAluno)
                    consulta = """SELECT DISTINCT editalProjeto.nome,editalProjeto.siape,editalProjeto.titulo,
                    DATE_FORMAT(indicacoes.inicio,'%d/%m/%Y') as inicio,DATE_FORMAT(indicacoes.fim,'%d/%m/%Y') as fim,
                    indicacoes.nome as indicados,
                    editalProjeto.id,if(indicacoes.fim<NOW(),"exerceu","exerce") as verbo
                    FROM editalProjeto,indicacoes
                    WHERE editalProjeto.id=indicacoes.idProjeto AND indicacoes.id=""" + idAluno + """ ORDER BY fim DESC"""
                    projeto,total = executarSelect(consulta,1)
                    data_agora = getData()
                    if total>0:
                        arquivoDeclaracao = app.config['DECLARACOES_FOLDER'] + 'declaracao.pdf'
                        options = {
                            'page-size': 'A4',
                            'margin-top': '2cm',
                            'margin-right': '2cm',
                            'margin-bottom': '1cm',
                            'margin-left': '2cm',
                        }
                        pdfkit.from_string(render_template('declaracao_orientador.html',texto=projeto,data=data_agora,identificador=idProjeto,raiz=ROOT_SITE),arquivoDeclaracao,options=options)
                        return send_from_directory(app.config['DECLARACOES_FOLDER'], 'declaracao.pdf')
                    else:
                        return("declaracao inexistente...")
                else:

                    return("id nao informado")
        else:
            return("OK")
    else:
        return(render_template('login.html',mensagem="É necessário autenticação para acessar a página solicitada"))

@app.route("/discente/minhaDeclaracao", methods=['GET', 'POST'])
@log_required
def minhaDeclaracaoDiscente():
    if request.method == "GET":
        #Recuperando o token da declaração
        if 'token' in request.args:
            token = str(request.args.get('token'))
            consulta = """SELECT estudante_nome_completo,cpf,if(estudante_fim>NOW(),1,0) as verbo,estudante_modalidade,nome_do_coordenador,titulo_do_projeto,
                        ch_semanal,DATE_FORMAT(estudante_inicio,'%d/%m/%Y') as inicio,DATE_FORMAT(estudante_fim,'%d/%m/%Y') as final FROM cadastro_geral WHERE token='""" + token + """'"""
            projeto,total = executarSelect(consulta,1)
            data_agora = getData()
            if total==1:
                arquivoDeclaracao = app.config['DECLARACOES_FOLDER'] + 'declaracao.pdf'
                options = {
                    'page-size': 'A4',
                    'margin-top': '2cm',
                    'margin-right': '2cm',
                    'margin-bottom': '1cm',
                    'margin-left': '2cm',
                }
                pdfkit.from_string(render_template('declaracao_discente.html',texto=projeto,data=data_agora,identificador=token,raiz=ROOT_SITE),arquivoDeclaracao,options=options)
                return send_from_directory(app.config['DECLARACOES_FOLDER'], 'declaracao.pdf')
                
            else:
                return("declaração inexistente!")
        else:
            return("OK")
    else:
        return("OK")

'''
qrcode_url = url_for('avaliacao_gerar_declaracao',ano=ano,periodo=periodo,token=token,_external=True)
qrcode = pyqrcode.create(qrcode_url)
qrcode.png(app.config['PNG_DIR'] + 'qrcode.png',scale=3)
'''

@app.route("/discente/meuCertificado2018", methods=['GET', 'POST'])
@log_required
def meuCertificado2018():
    if request.method == "GET":
        #Recuperando o token da declaração
        if 'token' in request.args:
            token = str(request.args.get('token'))
            consulta = """
            SELECT estudante_nome_completo,cpf,estudante_tipo_de_vaga,estudante_modalidade,
            nome_do_coordenador,titulo_do_projeto,ch_semanal,DATE_FORMAT(estudante_inicio,'%d/%m/%Y'),
            DATE_FORMAT(estudante_fim,'%d/%m/%Y') ,
            ROUND((DATEDIFF(estudante_fim,estudante_inicio)/7)*ch_semanal) as ch_total
            FROM cadastro_geral WHERE token=\"""" + token + """\""""
            consulta2 = """SELECT * from gestores ORDER BY id"""
            from datetime import datetime
            projeto,total = executarSelect(consulta,1)
            gestores,total_gestores = executarSelect(consulta2)
            proreitor = gestores[0]
            coordenador = gestores[1]
            inicio = datetime.strptime(str(projeto[7]),'%d/%m/%Y')
            fim = datetime.strptime(str(projeto[8]),'%d/%m/%Y')
            agora = datetime.strptime(datetime.today().strftime("%d/%m/%Y"),'%d/%m/%Y')
            periodo = abs((fim-inicio).days)
            if periodo<180:
                return('Certificado indisponível. Período de bolsa inferior a 180 dias')
            data_agora = getData()
            if ((fim-agora).days>0):
                return('Certificado disponível apenas após a conclusão do projeto em andamento: ')
            if total==1:
                arquivoDeclaracao = app.config['DECLARACOES_FOLDER'] + 'declaracao.pdf'
                options = {
                    'page-size': 'A4',
                    'orientation': 'landscape',
                    'margin-top': '0mm',
                    'margin-right': '0mm',
                    'margin-bottom': '0mm',
                    'margin-left': '0mm',
                    'encoding': "UTF-8",
                    'quiet': '',
                    'custom-header' : [
                    ('Accept-Encoding', 'gzip')
                    ],
                    'no-outline': None
                }
                pdfkit.from_string(render_template('certificado_discente_2018.html',conteudo=projeto,data="Juazeiro do Norte, " + data_agora,identificador=token,raiz=ROOT_SITE,coordenador=coordenador,proreitor=proreitor),arquivoDeclaracao,options=options)
                return send_from_directory(app.config['DECLARACOES_FOLDER'], 'declaracao.pdf')
            else:
                return("declaração inexistente!")
        else:
            return("OK")
    else:
        return("OK")

@app.route("/discente/meuCertificado", methods=['GET', 'POST'])
@log_required
def meuCertificado():
    if request.method == "GET":
        #Recuperando o token da declaração
        if 'id' in request.args:
            idIndicacao = str(request.args.get('id'))
            consulta = """SELECT i.nome,i.cpf,IF(i.modalidade=1,'PIBIC',IF(i.modalidade=2,'PIBITI','PIBIC-EM')) as modalidade,
            IF(i.tipo_de_vaga=1,'BOLSISTA','VOLUNTÁRIO') as vaga,
            e.nome,e.titulo,i.ch,DATE_FORMAT(i.inicio,'%d/%m/%Y') as inicio, DATE_FORMAT(i.fim,'%d/%m/%Y') as fim,
            ROUND((DATEDIFF(i.fim,i.inicio)/7)*i.ch) as ch_total
            FROM indicacoes i, editalProjeto e WHERE i.idProjeto=e.id and e.valendo=1 and i.id=""" + idIndicacao
            consulta2 = """SELECT * from gestores ORDER BY id"""
            from datetime import datetime
            projeto,total = executarSelect(consulta,1)
            gestores,total_gestores = executarSelect(consulta2)
            proreitor = gestores[0]
            coordenador = gestores[1]
            inicio = datetime.strptime(str(projeto[7]),'%d/%m/%Y')
            fim = datetime.strptime(str(projeto[8]),'%d/%m/%Y')
            agora = datetime.strptime(datetime.today().strftime("%d/%m/%Y"),'%d/%m/%Y')
            periodo = abs((fim-inicio).days)
            if periodo<180:
                return('Certificado indisponível. Período de bolsa inferior a 180 dias')
            data_agora = getData()
            if ((fim-agora).days>0):
                return('Certificado disponível apenas após a conclusão do projeto em andamento: ')
            if total==1:
                arquivoDeclaracao = app.config['DECLARACOES_FOLDER'] + 'declaracao.pdf'
                options = {
                    'page-size': 'A4',
                    'orientation': 'landscape',
                    'margin-top': '0mm',
                    'margin-right': '0mm',
                    'margin-bottom': '0mm',
                    'margin-left': '0mm',
                    'encoding': "UTF-8",
                    'quiet': '',
                    'custom-header' : [
                    ('Accept-Encoding', 'gzip')
                    ],
                    'no-outline': None
                }
                pdfkit.from_string(render_template('certificado_discente.html',conteudo=projeto,data="Juazeiro do Norte, " + data_agora,identificador=idIndicacao,raiz=ROOT_SITE,coordenador=coordenador,proreitor=proreitor),arquivoDeclaracao,options=options)
                return send_from_directory(app.config['DECLARACOES_FOLDER'], 'declaracao.pdf')
            else:
                return("declaração inexistente!")
        else:
            return("OK")
    else:
        return("OK")


@app.route("/discente/minhaDeclaracao2019", methods=['GET', 'POST'])
@log_required
def minhaDeclaracaoDiscente2019():
    if request.method == "GET":
        #Recuperando o token da declaração
        if 'id' in request.args:
            idIndicacao = str(request.args.get('id'))
            consulta = """SELECT indicacoes.nome,indicacoes.cpf,if(indicacoes.fim>NOW(),1,0) as verbo,IF(indicacoes.modalidade=1,'PIBIC',IF(indicacoes.modalidade=2,'PIBITI','PIBIC-EM')),editalProjeto.nome,editalProjeto.titulo,indicacoes.ch,DATE_FORMAT(indicacoes.inicio,'%d/%m/%Y'),DATE_FORMAT(indicacoes.fim,'%d/%m/%Y'), indicacoes.id
                        FROM indicacoes,editalProjeto
                        WHERE indicacoes.idProjeto=editalProjeto.id AND indicacoes.id=""" + idIndicacao
            from datetime import datetime
            projeto,total = executarSelect(consulta,1)
            inicio = datetime.strptime(str(projeto[7]),'%d/%m/%Y')
            fim = datetime.strptime(str(projeto[8]),'%d/%m/%Y')
            periodo = abs((fim-inicio).days)
            #if periodo<180:
            #    return('Declaração indisponível. Período de bolsa inferior a 180 dias')
            data_agora = getData()
            if total==1:
                arquivoDeclaracao = app.config['DECLARACOES_FOLDER'] + 'declaracao.pdf'
                options = {
                    'page-size': 'A4',
                    'margin-top': '2cm',
                    'margin-right': '2cm',
                    'margin-bottom': '1cm',
                    'margin-left': '2cm',
                }
                pdfkit.from_string(render_template('declaracao_discente.html',texto=projeto,data=data_agora,identificador=idIndicacao,raiz=ROOT_SITE),arquivoDeclaracao,options=options)
                return send_from_directory(app.config['DECLARACOES_FOLDER'], 'declaracao.pdf')
            else:
                return("declaração inexistente!")
        else:
            return("OK")
    else:
        return("OK")

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
                    consulta = """SELECT avaliacoes.id,c1,c2,c3,c4,c5,c6,c7,(c1+c2+c3+c4+c5+c6+c7) as pontuacaoTotal, comentario, if(recomendacao=1,'RECOMENDADO','NÃO RECOMENDADO') as recomendacao, cepa,DATE_FORMAT(data_avaliacao,'%d/%m/%Y'),avaliacoes.inovacao FROM avaliacoes WHERE finalizado=1 AND idProjeto=""" + idProjeto + """ ORDER BY data_avaliacao"""
                else:
                    consulta = """SELECT avaliacoes.id,c1,c2,c3,c4,c5,c6,c7,(c1+c2+c3+c4+c5+c6+c7) as pontuacaoTotal, comentario, if(recomendacao=1,'RECOMENDADO','NÃO RECOMENDADO') as recomendacao, cepa,DATE_FORMAT(data_avaliacao,'%d/%m/%Y'),avaliacoes.inovacao FROM avaliacoes,editalProjeto WHERE editalProjeto.id=avaliacoes.idProjeto AND finalizado=1 AND idProjeto=""" + idProjeto + """ AND siape=""" + str(session['username']) + """ ORDER BY data_avaliacao"""
                try:        
                    pareceres,total = executarSelect(consulta)
                    return(render_template('meusPareceres.html',linhas=pareceres,total=total,titulo=tituloProjeto))
                except Exception as e:
                    logger.error("Erro na função /meusPareceres")
                    logger.error(str(e))
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
        logger.error("Erro ao registrar acesso: {}",str(e))

@app.route("/login", methods=['POST','GET'])
@log_required
@limiter.limit("30/day;15/hour;5/minute",methods=["POST"])
def login():
    '''
    Método que ativa a sessão com os dados do usuário
    '''
    if request.method == "POST":
        if (('siape' in request.form) and ('senha' in request.form)):
            siape = str(request.form['siape'])
            senha = str(request.form['senha'])
            senha = senha[:64]  # Limitar o tamanho da senha para evitar problemas ataques DoS
            if verify_password(siape,senha):
                registrar_acesso(request.remote_addr,siape)
                return(redirect(url_for('home')))
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

def thread_enviar_senha(msg):
    with app.app_context():
        try:
            mail.send(msg)
            logger.info("E-mail enviado com sucesso. /enviarMinhaSenha")
        except Exception as e:
            logger.error("Erro ao enviar e-mail: {}. /enviarMinhaSenha", str(e))

@app.route("/enviarMinhaSenha", methods=['GET', 'POST'])
@log_required
@limiter.limit("3/day;2/hour;1/minute",methods=["POST"])
def enviarMinhaSenha():
    if request.method == "POST":
        if ('email' in request.form):
            email = str(request.form['email'])
            senha_forte = generate_secure_password()
            #ENVIAR E-MAIL
            consulta = """SELECT username,id FROM users WHERE email= ? """
            linhas,total = executarSelect2(consulta,1,valores=[email])
            if (total>0):
                username = str(linhas[0])
                idUsuario = str(linhas[1])
                senha = senha_forte
                hash_senha = cripto.hash_argon2id(senha)
                consulta = f"""UPDATE users SET password='{hash_senha}' WHERE id={idUsuario}"""
                atualizar(consulta)
                #Enviando e-mail
                texto_mensagem = "Usuario: " + username + "\nSenha: " + senha + "\n" + USUARIO_SITE
                msg = Message(subject = "Plataforma Yoko - Lembrete de senha",recipients=[email],body=texto_mensagem)
                thread = threading.Thread(target=thread_enviar_senha, args=(msg,))
                thread.start()
                #Redirecionando para a página de login
                return(render_template('login.html',mensagem='Senha enviada para o email: ' + email))
            else:
                logger.info("[{}][/enviarMinhaSenha]E-mail {} não cadastrado.", request.remote_addr, email)
                flash("E-mail não cadastrado. Solicite seu cadastro no setor responsável.","error")
                return redirect(url_for('home'))
        else:
            return("OK")
    else:
        return("OK")

@app.route("/logout", methods=['GET', 'POST'])
@log_required
def encerrarSessao():
    logout()
    return redirect(url_for('home'))

def projetoAprovado(idProjeto):

    categoria = int(obterColunaUnica("editalProjeto","categoria","id",str(idProjeto)))

    if categoria==0:
        return (True)
    else:
        consulta = """SELECT sum(if(recomendacao=0,1,0)) as rejeitados, sum(if(recomendacao=1,1,0)) as aprovados FROM avaliacoes WHERE idProjeto=""" + str(idProjeto)
        resultado,total = executarSelect(consulta,1)
        avaliacoes = int(resultado[0]) + int(resultado[1])
        if avaliacoes>1:
            if (resultado[1]>resultado[0]):
                return (True)
            else:
                return (False)
        else:
            return(False)

@app.route("/prepararResultados", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def prepararResultados():
    if request.method == "GET":
        #Recuperando o código do edital
        if 'edital' in request.args:
            codigoEdital = str(request.args.get('edital'))
            if ((autenticado()) and (session['permissao']==0)):
                #ZERANDO as concessões
                consulta = "UPDATE editalProjeto SET bolsas_concedidas=0 WHERE tipo=" + codigoEdital
                atualizar(consulta)

                consulta = """UPDATE editalProjeto SET obs='' WHERE tipo=""" + codigoEdital
                atualizar(consulta)

                #Gerando projetos do edital
                tipo_classificacao = int(obterColunaUnica("editais","classificacao","id",codigoEdital))
                if (tipo_classificacao==1):
                    consulta = "SELECT id,tipo,categoria,ua,bolsas,bolsas_concedidas,siape,modalidade FROM editalProjeto WHERE tipo=" + codigoEdital + " AND valendo=1 ORDER BY ua, produtividade,scorelattes DESC"
                else:
                    consulta = "SELECT id,tipo,categoria,ua,bolsas,bolsas_concedidas,siape,modalidade FROM editalProjeto WHERE tipo=" + codigoEdital + " AND valendo=1 ORDER BY produtividade,scorelattes DESC"
                projetos,total = executarSelect(consulta)
                total = float(total)
                #Recuperando demanda por unidade academica
                demanda = """SELECT ua,count(id) FROM editalProjeto WHERE valendo=1 and tipo=""" + codigoEdital + """ GROUP BY ua ORDER BY ua"""
                demandaQualificada,totalDemanda = executarSelect(demanda)

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
                    consulta = "SELECT id,tipo,categoria,ua,bolsas,bolsas_concedidas,siape,modalidade FROM editalProjeto WHERE tipo=" + codigoEdital + " AND valendo=1 ORDER BY ua, produtividade,scorelattes DESC"
                    projetos,total = executarSelect(consulta)
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
                                        consulta = "UPDATE editalProjeto SET bolsas_concedidas=bolsas_concedidas+1 WHERE id=" + str(idProjeto)
                                        atualizar(consulta)
                                        cnpqUnidade[ua] = cnpqUnidade[ua] - 1
                                        consulta = """UPDATE editalProjeto SET obs=CONCAT(obs,'<BR><BR>','BOLSA CNPq CONCEDIDA') WHERE id=""" + str(idProjeto)
                                        atualizar(consulta)
                                    else: #Se o projeto não estiver aprovado
                                        consulta = "UPDATE editalProjeto SET obs=\"PROJETO NÃO FOI APROVADO.\" WHERE id=" + str(idProjeto)
                                        atualizar(consulta)
                                else: #Se o orientador estiver com a cota estourada
                                    consulta = """UPDATE editalProjeto SET obs=CONCAT(obs,'<BR>','BOLSA NÃO CONCEDIDA. ORIENTADOR NÃO PODE ULTRASSAR A COTA DE 2 BOLSISTAS POR MODALIDADE (Anexo XIV da Res. 01/2014/CONSUP, Art. 7 Inciso I)') WHERE id=""" + str(idProjeto)
                                    #atualizar(consulta)
                        elif (ufcaUnidade[ua]>0): #Bolsas UFCA
                            if (solicitadas-concedidas)>0: #Se ainda existe demanda a ser atendida
                                if(not cotaEstourada(codigoEdital,siape)): #Se o orientador não estiver com a cota individual estourada
                                    if projetoAprovado(idProjeto): #Se o projeto estiver aprovado
                                        consulta = "UPDATE editalProjeto SET bolsas_concedidas=bolsas_concedidas+1 WHERE id=" + str(idProjeto)
                                        atualizar(consulta)
                                        ufcaUnidade[ua] = ufcaUnidade[ua] - 1
                                        consulta = """UPDATE editalProjeto SET obs=CONCAT(obs,'<BR><BR>','BOLSA UFCA CONCEDIDA') WHERE id=""" + str(idProjeto)
                                        atualizar(consulta)
                                else: #Se o orientador estiver com a cota estourada
                                    consulta = """UPDATE editalProjeto SET obs=CONCAT(obs,'<BR>','BOLSA NÃO CONCEDIDA. ORIENTADOR NÃO PODE ULTRASSAR A COTA DE 2 BOLSISTAS POR MODALIDADE (Anexo XIV da Res. 01/2014/CONSUP, Art. 7 Inciso I)') WHERE id=""" + str(idProjeto)
                                    #atualizar(consulta)

                        else: # se a unidade não tem mais bolsas disponíveis em sua cota
                            consulta = "UPDATE editalProjeto SET obs=CONCAT(obs,'<BR>','BOLSA NÃO CONCEDIDA. COTA DA UNIDADE ZERADA (Anexo XIV da Res. 01/2014/CONSUP, Art. 7 Inciso II)') WHERE id=" + str(idProjeto)
                            #atualizar(consulta)
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
    inicio = ano + "-03-01"
    fim = ano + "-12-31"
    consulta = """SELECT id FROM editais WHERE DATE(deadline)>'""" + inicio + """' AND DATE(deadline)<'""" + fim + """' AND nome not like '%contínuo%'"""
    editais,total = executarSelect(consulta)
    codigos = []
    for linha in editais:
        codigos.append(int(linha[0]))
    if total>0:
        resultado = str(tuple(codigos))
        return (resultado)
    else:
        return (0)


@app.route("/cruzarDados", methods=['GET', 'POST'])
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

'''
Verifica quantos voluntários já foram indicados para o id do projeto
'''
def quantosVoluntariosIndicados(id):
    consulta = """SELECT count(id) FROM indicacoes WHERE tipo_de_vaga=0 AND idProjeto=""" + id
    linhas,total = executarSelect(consulta,1)
    numero = int(linhas[0])
    return (numero)

'''
Verifica quantos voluntários adicionais já foram indicados para o id do projeto
'''
def quantosVoluntariosAdicionaisIndicados(id):
    consulta = """SELECT count(id) FROM indicacoes WHERE tipo_de_vaga=0 AND arquivo_plano!='N/A' AND situacao=0 AND idProjeto=""" + id
    linhas,total = executarSelect(consulta,1)
    numero = int(linhas[0])
    return (numero)


'''
Verifica se um projeto pode indicar voluntários adicionais
'''
def podeIndicarVoluntariosAdicionais(id):
    voluntariosAdicionaisIndicados = quantosVoluntariosAdicionaisIndicados(id)
    if (voluntariosAdicionaisIndicados<=2):
        return (True)
    else:
        return (False)

'''
Verifica se um projeto pode indicar voluntários
'''
def podeIndicarVoluntarios(id):
    bolsas_obtidas = int(obterColunaUnica('editalProjeto','bolsas_concedidas','id',id))
    bolsas_solicitadas = int(obterColunaUnica('editalProjeto','bolsas','id',id))
    bolsistasIndicados = quantosBolsistasIndicados(id)
    voluntariosIndicados = quantosVoluntariosIndicados(id)
    totalDeVoluntarios = bolsas_solicitadas-bolsas_obtidas
    if (voluntariosIndicados<totalDeVoluntarios):
        return (True)
    else:
        return (False)

'''
Verifica quantos bolsistas já foram indicados para o id do projeto
'''
def quantosBolsistasIndicados(id):
    consulta = """SELECT count(id) FROM indicacoes WHERE tipo_de_vaga=1 AND idProjeto=""" + id
    linhas,total = executarSelect(consulta,1)
    numero = int(linhas[0])
    return (numero)

'''
Verifica se um projeto pode indicar bolsistas
'''
def podeIndicarBolsistas(id):
    bolsas_obtidas = int(obterColunaUnica('editalProjeto','bolsas_concedidas','id',id))
    if bolsas_obtidas>0:
        #Verificar se ainda restam bolsistas a serem indicados
        if (quantosBolsistasIndicados(id)<bolsas_obtidas):
            return(True)
        else:
            return(False)
    else:
        return(False)

'''
Verifica se o edital está no prazo para indicação de bolsistas/voluntários
'''
def dataDeIndicacao(codigoEdital):
    consulta = """SELECT id FROM editais WHERE NOW() BETWEEN indicacao_inicio AND indicacao_termino AND id=""" + codigoEdital
    linhas,total = executarSelect(consulta)
    if total==0:
        return (False)
    else:
        return (True)

@app.route("/indicacao", methods=['GET', 'POST'])
@login_required(role='user')
@log_required
def indicacao():
    if request.method == "GET":
        #Recuperando o código do projeto
        if (('id' in request.args) and ('b' in request.args)):
            idProjeto = str(request.args.get('id'))
            #b = 1 (bolsista); b = 0 (voluntário)
            b = int(request.args.get('b'))
            edital = int(obterColunaUnica('editalProjeto','tipo','id',idProjeto))
            indicacao_inicio = str(obterColunaUnica('editais',"""DATE_FORMAT(indicacao_inicio,'%d/%m/%Y')""",'id',str(edital)))
            indicacao_fim = str(obterColunaUnica('editais',"""DATE_FORMAT(indicacao_termino,'%d/%m/%Y')""",'id',str(edital)))
            modalidade = int(obterColunaUnica('editalProjeto','modalidade','id',idProjeto))
            if (autenticado()):
                if idSiape(idProjeto,session['username']):
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
                                if podeIndicarVoluntariosAdicionais(idProjeto):
                                    return(render_template('indicacao.html',inicio=indicacao_inicio,fim=indicacao_fim,continua=1,modalidade=modalidade,vaga=b,idProjeto=idProjeto,plano=1,substituicao=0))
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
        SELECT * FROM `indicacoes` WHERE fim>now() and matricula=%s
    """ %(matricula)
    linhas,total = executarSelect(consulta)
    if total>0:
        return (False)
    else:
        return (True)

def encripta_e_apaga(arquivo):
    """
    Encripta e apaga o arquivo
    """
    cripto.aes_gpg_encrypt_file(GPG_KEY,arquivo, arquivo + ".gpg")
    os.remove(arquivo)

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
                if podeSerIndicado(matricula)==False:
                    return("Indicado ja esta em outro projeto. Nao foi possivel efetivar a indicacao.") 

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

                nomeDoArquivoTermo = ""
                if 'termo' in request.files:
                    token = id_generator()
                    nomeDoArquivoTermo = "TERMO." + idProjeto + "." + token + ".pdf"
                    filename = anexos.save(request.files['termo'],name=nomeDoArquivoTermo)
                    encripta_e_apaga(ATTACHMENTS_DIR + nomeDoArquivoTermo)
                nomeDoArquivoRg = ""
                if 'rg_cpf' in request.files:
                    token = id_generator()
                    nomeDoArquivoRg = "RG_CPF." + idProjeto + "." + token + ".pdf"
                    filename = anexos.save(request.files['rg_cpf'],name=nomeDoArquivoRg)
                    encripta_e_apaga(ATTACHMENTS_DIR + nomeDoArquivoRg)
                nomeDoArquivoExtrato = ""
                if 'extrato' in request.files:
                    token = id_generator()
                    nomeDoArquivoExtrato = "EXTRATO." + idProjeto + "." + token + ".pdf"
                    filename = anexos.save(request.files['extrato'],name=nomeDoArquivoExtrato)
                    encripta_e_apaga(ATTACHMENTS_DIR + nomeDoArquivoExtrato)
                nomeDoArquivoHistorico = ""
                if 'historico' in request.files:
                    token = id_generator()
                    nomeDoArquivoHistorico = "HISTORICO." + idProjeto + "." + token + ".pdf"
                    filename = anexos.save(request.files['historico'],name=nomeDoArquivoHistorico)
                    encripta_e_apaga(ATTACHMENTS_DIR + nomeDoArquivoHistorico)
                nomeDoArquivoPlano = "N/A"
                if 'plano' in request.files:
                    token = id_generator()
                    nomeDoArquivoPlano = "PLANO." + idProjeto + "." + token + ".pdf"
                    filename = anexos.save(request.files['plano'],name=nomeDoArquivoPlano)
                    encripta_e_apaga(ATTACHMENTS_DIR + nomeDoArquivoPlano)
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
                consulta = """INSERT INTO indicacoes (idProjeto,nome,nascimento,estado_civil,sexo,rg,orgao_emissor,uf,
                cpf,tipo_de_vaga,modalidade,curso,matricula,ano_de_ingresso,lattes,nome_banco,agencia,conta,telefone,celular,
                email,endereco,escola,ano_conclusao,arquivo_cpf_rg,arquivo_extrato,arquivo_historico,arquivo_termo,inicio,fim,arquivo_plano,substituido,fomento,iv)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) """
                valores = (int(idProjeto),nome,nascimento,estado_civil,sexo,rg,orgao,uf,cpf,vaga,modalidade,curso,matricula,ingresso,lattes,banco,agencia,conta,telefone,celular,email,endereco,escola,conclusao,nomeDoArquivoRg,nomeDoArquivoExtrato,nomeDoArquivoHistorico,nomeDoArquivoTermo,inicio,fim,nomeDoArquivoPlano,substituido,fomento,iv)
                inserir(consulta,valores)
                lastID = "SELECT id FROM indicacoes WHERE idProjeto=" + idProjeto + " ORDER BY id DESC LIMIT 1"
                ultimo_id,total = executarSelect(lastID,1)
                idIndicacao = int(ultimo_id[0])
                chave = AES_KEY
                consulta_criptografar = f"""
                UPDATE indicacoes SET 
                    rg=TO_BASE64(AES_ENCRYPT(rg,'{chave}',iv)),
                    nascimento=TO_BASE64(AES_ENCRYPT(nascimento,'{chave}',iv)),
                    telefone=TO_BASE64(AES_ENCRYPT(telefone,'{chave}',iv)),
                    celular=TO_BASE64(AES_ENCRYPT(celular,'{chave}',iv)),
                    endereco=TO_BASE64(AES_ENCRYPT(endereco,'{chave}',iv))
                WHERE id={idIndicacao};
                """
                atualizar(consulta_criptografar)
                titulo_projeto = obterColunaUnica('editalProjeto','titulo','id',idProjeto)
                orientador = obterColunaUnica('editalProjeto','nome','id',idProjeto)
                email = obterColunaUnica('editalProjeto','email','id',idProjeto)
                email2 = DEFAULT_EMAIL
                texto_email = render_template('confirmacao_indicacao.html',vaga=vaga,id_projeto=idProjeto,indicado=nome,proponente=orientador,titulo=titulo_projeto,email_proponente=email,idIndicacao=idIndicacao)
                if vaga==1:
                    msg = Message(subject = "Plataforma Yoko - INDICAÇÃO DE BOLSISTA",recipients=[email,email2],html=texto_email)
                else:
                    msg = Message(subject = "Plataforma Yoko - INDICAÇÃO DE VOLUNTARIO",recipients=[email,email2],html=texto_email)
                t1 = threading.Thread(target=thread_enviar_email, args=(msg,'/efetivarIndicacao',))
                t1.start()
                return(render_template('confirmacao_indicacao.html',vaga=vaga,id_projeto=idProjeto,indicado=nome,proponente=orientador,titulo=titulo_projeto,email_proponente=email,idIndicacao=idIndicacao))
            else:
                return ("Você já indicou todos os bolsistas/voluntários. Entrar em contato através do e-mail atendimento.prpi@ufca.edu.br")
        except Exception as e:
            logger.error(e)
            logger.error("ERRO Na função /efetivarIndicacao. Ver consulta abaixo.")
            logger.error(consulta)
            return("ERRO!")
    else:
        return("OK")

@app.route("/indicacoes", methods=['GET', 'POST'])
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
                consulta = """SELECT indicacoes.id,
                indicacoes.idProjeto, 
                indicacoes.nome,
                IF(indicacoes.modalidade=1,'PIBIC',IF(indicacoes.modalidade=2,'PIBITI','PIBIC-EM')),
                IF(tipo_de_vaga=1, 'BOLSISTA','VOLUNTÁRIO(A)'), 
                nome_banco,
                agencia,
                conta, 
                arquivo_cpf_rg,
                arquivo_extrato,
                arquivo_historico,
                arquivo_termo,
                DATE_FORMAT(indicacoes.inicio,'%d/%m/%Y'),
                DATE_FORMAT(indicacoes.fim,'%d/%m/%Y'), 
                editalProjeto.nome,
                editalProjeto.obs,
                editalProjeto.tipo,
                IF(indicacoes.fomento=0,'UFCA',IF(indicacoes.fomento=1,'CNPQ','FUNCAP'))
                FROM indicacoes,editalProjeto WHERE indicacoes.tipo_de_vaga=""" + tipo_de_vaga + """ AND indicacoes.idProjeto=editalProjeto.id AND tipo=""" + codigoEdital + """ ORDER BY editalProjeto.tipo,editalProjeto.nome,indicacoes.id """
            else:
                consulta = """SELECT indicacoes.id,indicacoes.idProjeto, indicacoes.nome,IF(indicacoes.modalidade=1,'PIBIC',IF(indicacoes.modalidade=2,'PIBITI','PIBIC-EM')),
                IF(tipo_de_vaga=1, 'BOLSISTA','VOLUNTÁRIO(A)'), nome_banco,agencia,conta, arquivo_cpf_rg,arquivo_extrato,
                arquivo_historico,arquivo_termo,DATE_FORMAT(indicacoes.inicio,'%d/%m/%Y'),DATE_FORMAT(indicacoes.fim,'%d/%m/%Y'), editalProjeto.nome,editalProjeto.obs,
                editalProjeto.tipo,IF(indicacoes.fomento=0,'UFCA',IF(indicacoes.fomento=1,'CNPQ','FUNCAP'))
                FROM indicacoes,editalProjeto WHERE indicacoes.idProjeto=editalProjeto.id AND tipo=""" + codigoEdital + """ ORDER BY editalProjeto.tipo,editalProjeto.nome,indicacoes.id """
            linhas,total = executarSelect(consulta)
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
            logger.error("Erro ao remover arquivo temporário (função esperar(arquivo)).")
            logger.error(str(e))

@app.route("/verArquivo", methods=['GET', 'POST'])
@auth.login_required(role=['admin'])
@log_required
def verArquivo():
    if request.method == "GET":
        #Recuperando arquivo
        if 'file' in request.args:
            arquivo = str(request.args['file'])
            arquivo = secure_filename(arquivo) + ".gpg"
            if os.path.isfile(ATTACHMENTS_DIR + arquivo):
                cripto.aes_gpg_decrypt_file(GPG_KEY,ATTACHMENTS_DIR + arquivo, ATTACHMENTS_DIR + arquivo.replace(".gpg",""))
                thread = threading.Thread(target=esperar,args=(ATTACHMENTS_DIR + arquivo.replace(".gpg",""),))
                thread.start()
                return(send_from_directory(app.config['UPLOADED_DOCUMENTS_DEST'], arquivo.replace(".gpg","")))
            else:
                return("Arquivo não encontrado!")
        else:
            return("OK")
    else:
        return("OK")
    
@app.route("/verArquivosProjeto/<filename>", methods=['GET', 'POST'])
@log_required
def verArquivosProjeto(filename):
    arquivo = secure_filename(filename) + ".gpg"
    if os.path.isfile(SUBMISSOES_DIR + arquivo):
        cripto.aes_gpg_decrypt_file(GPG_KEY,SUBMISSOES_DIR + arquivo, SUBMISSOES_DIR + arquivo.replace(".gpg",""))
        thread = threading.Thread(target=esperar,args=(SUBMISSOES_DIR + arquivo.replace(".gpg",""),))
        thread.start()
        return(send_from_directory(app.config['UPLOADED_SUBMISSOES_DEST'], arquivo.replace(".gpg","")))
    else:
        return("Arquivo não encontrado!")

@app.route("/situacaoIndicacoes", methods=['GET', 'POST'])
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
                        WHERE tipo=""" + codigoEdital + """ AND valendo=1 AND bolsas_concedidas>0
                        AND indicacoes.tipo_de_vaga=1
                        GROUP BY editalProjeto.id) """
            consulta = consulta + """ UNION """
            consulta = consulta + """(SELECT editalProjeto.tipo,editalProjeto.id,editalProjeto.nome,editalProjeto.ua,titulo,
                                    bolsas,bolsas_concedidas,0 as nindicados,'SEM INDICAÇÕES' as indicados
                                    FROM editalProjeto LEFT JOIN indicacoes ON editalProjeto.id=indicacoes.idProjeto
                                    WHERE tipo=""" + codigoEdital + """ AND indicacoes.idProjeto is null
                                    AND valendo=1
                                    AND bolsas_concedidas>0)
                                    ORDER BY tipo,ua,bolsas_concedidas DESC, nindicados DESC,nome"""
            linhas,total = executarSelect(consulta)
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
    consulta = """SELECT indicacoes.id FROM indicacoes,editalProjeto WHERE indicacoes.idProjeto=editalProjeto.id AND editalProjeto.siape=""" + siape + """
    AND indicacoes.id=""" + idIndicacao

    linhas,total = executarSelect(consulta)
    if (total>0):
        return (True)
    else:
        return(False)

'''
Verifica se a frequência do Mês atual já foi enviada
'''
def jaEnviouFrequenciaAtual(idAluno,mes,ano):
    consulta = """SELECT id FROM frequencias WHERE idIndicacao=""" + idAluno + """ AND mes=""" + mes + """ AND ano=""" + ano
    linhas,total = executarSelect(consulta)
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
                data_final = obterColunaUnica('indicacoes','ADDDATE(DATE(fim),INTERVAL 90 DAY)','id',idAluno)
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
        """ %(idAluno,mes,ano)
        linhas,total = executarSelect(consulta_verificacao)
        if total>0:
            return("A frequência para o mes/ano solicitado já foi enviada anteriormente! Não é possível modificar!")
        consulta = """INSERT INTO frequencias (idIndicacao,mes,ano,s1,s2,s3,s4,obs) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"""
        valores = (idAluno,mes,ano,s1,s2,s3,s4,obs)
        inserir(consulta,valores)
        return redirect("/pesquisa/meusProjetos")
    else:
        return("OK")

def thread_enviar_email(msg,rota):
    with app.app_context():
        try:
            mail.send(msg)
            logger.info("E-mail enviado: {}",msg.subject)
        except Exception as e:
            logger.error(str(e))
            logger.error("Erro ao enviar e-mail. Rota: " + rota)

def enviar_lembrete_frequencia():
    import datetime
    #Mes e ano atual
    ano = str(datetime.date.today().year)
    mes = str(datetime.date.today().month-1)
    if mes==1:
        ano = ano - 1
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
    with app.app_context():
        consulta = """SELECT 
        GROUP_CONCAT(editalProjeto.id ORDER BY editalProjeto.id),
        editalProjeto.nome,
        GROUP_CONCAT(editalProjeto.titulo), 
        GROUP_CONCAT(indicacoes.id ORDER BY indicacoes.idProjeto,indicacoes.id),
        editalProjeto.email,
        editalProjeto.siape
        from editalProjeto
        INNER JOIN indicacoes ON editalProjeto.id=indicacoes.idProjeto
        WHERE indicacoes.fim>NOW() AND indicacoes.situacao=0 and MONTH(indicacoes.inicio)!=Month(now())
        GROUP BY editalProjeto.nome"""
        linhas,total = executarSelect(consulta)
        for linha in linhas:
            id_projetos = str(linha[0]).split(',')
            orientador = str(linha[1])
            siape = str(linha[5])
            senha = obterColunaUnica('users','password','username',siape)
            titulos = str(linha[2]).split(',')
            indicacoes = str(linha[3]).split(',')
            nao_enviados = []
            for indicacao in indicacoes:
                subconsulta = """SELECT 
                idIndicacao 
                FROM frequencias 
                WHERE mes=%s AND ano=%s AND idIndicacao=%s 
                LIMIT 1
                """ % (mes,ano,indicacao)
                frequencias,totalFrequencias = executarSelect(subconsulta)
                if totalFrequencias==0: #Não foi enviada a frequência para este discente
                    nome_indicado = obterColunaUnica('indicacoes','nome','id',indicacao)
                    nao_enviados.append(nome_indicado)
            if (len(nao_enviados)!=0):
                
                texto_email = render_template('lembrete_frequencia.html',mes=str(nome_mes[str(mes)]),ano=ano,nomes=nao_enviados,usuario=siape,senha=senha)
                if PRODUCAO==1:
                    msg = Message(subject = "Plataforma Yoko PIICT- LEMBRETE DE ENVIO DE FREQUÊNCIA",recipients=[str(linha[4])],html=texto_email,reply_to="NAO-RESPONDA@ufca.edu.br")
                    try:
                        mail.send(msg)
                        logger.info("E-mail enviado: Lembrete de frequência para {}",orientador)
                    except Exception as e:
                        logger.error("Erro ao enviar e-mail. /enviar_lembrete_frequencia: {}",str(e))
                else:
                    msg = Message(subject = "Plataforma Yoko PIICT- LEMBRETE DE ENVIO DE FREQUÊNCIA",recipients=['pesquisapython3.display999@passmail.net'],html=texto_email,reply_to="NAO-RESPONDA@ufca.edu.br")
                    try:
                        mail.send(msg)
                        logger.info("E-mail enviado: Lembrete de frequência para {}",orientador)
                    except Exception as e:
                        logger.error("Erro ao enviar e-mail. /enviar_lembrete_frequencia")
                        logger.error(str(e))
                    finally:
                        continue
                    
@app.route("/listaNegra/<email>", methods=['GET', 'POST'])
@auth.login_required(role=['admin'])
@log_required
def listaNegra(email):
    import datetime
    #Mes e ano atual
    ano = str(datetime.date.today().year)
    mes = str(datetime.date.today().month-1)
    if mes==1:
        ano = ano - 1
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
    lista_emails = [DEFAULT_EMAIL]
    lista_emails_discentes = []
    for linha in linhas:
        idIndicacao = str(linha[0])
        subconsulta = """SELECT id FROM frequencias WHERE mes=""" + mes + """ AND ano=""" + ano + """ AND idIndicacao=""" + idIndicacao
        frequencias,totalFrequencias = executarSelect(subconsulta)
        dados = [str(linha[0]),str(linha[1]),str(linha[2])]
        if totalFrequencias==0:
            lista.append(dados)
            lista_emails.append(str(linha[3]))
            lista_emails_discentes.append(linha[4])
    
    if email=="1":
        t = threading.Thread(target=enviar_lembrete_frequencia)
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
            consulta = """
            UPDATE indicacoes SET motivo=\"""" + lista_motivos + """\" WHERE id=""" + idAluno
            atualizar(consulta)

            #desligar a indicação
            idProjeto = obterColunaUnica('indicacoes','idProjeto','id',idAluno)
            orientador = obterColunaUnica('editalProjeto','nome','id',idProjeto)
            titulo = obterColunaUnica('editalProjeto','titulo','id',idProjeto)
            discente = obterColunaUnica('indicacoes','nome','id',idAluno)
            tipo_vaga = obterColunaUnica('indicacoes','tipo_de_vaga','id',idAluno)
            timestamp = agora()
            consulta = "UPDATE indicacoes SET situacao=1, fim=NOW() WHERE id=" + idAluno
            atualizar(consulta)
            email = obterColunaUnica('editalProjeto','email','id',idProjeto)
            email2 = DEFAULT_EMAIL
            
            texto_email = render_template('confirmacao_desligamento.html',vaga=tipo_vaga,id_projeto=idProjeto,proponente=orientador,titulo=titulo,indicado=discente,idIndicacao=idAluno,data=timestamp)
            if tipo_vaga==1:
                msg = Message(subject = "Plataforma Yoko - DESLIGAMENTO DE BOLSISTA",recipients=[email,email2],html=texto_email)
            else:
                msg = Message(subject = "Plataforma Yoko - DESLIGAMENTO DE VOLUNTARIO",recipients=[email,email2],html=texto_email)
            if PRODUCAO==1:
                t = threading.Thread(target=enviar_email_desligamento_substituicao,args=(msg,))
                t.start()
            else:
                app.logger.debug('E-MAIL DE DESLIGAMENTO ENVIADO')
            return(render_template('confirmacao_desligamento.html',vaga=tipo_vaga,id_projeto=idProjeto,proponente=orientador,titulo=titulo,indicado=discente,idIndicacao=idAluno,data=timestamp))
            
        else:
            return("ACESSO NEGADO")
    else:
        return(redirect(url_for('login')))

def enviar_email_desligamento_substituicao(msg):
    with app.app_context():
        try:
            mail.send(msg)
            logger.info("E-mail enviado: {}",msg.subject)
        except Exception as e:
            logger.error("Erro ao enviar e-mail. enviar_email_desligamento_substituicao")
            logger.error(str(e))


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
            consulta = """
            UPDATE indicacoes SET motivo=\"""" + lista_motivos + """\" WHERE id=""" + idAluno
            atualizar(consulta)
            
            idProjeto = obterColunaUnica('indicacoes','idProjeto','id',idAluno)
            orientador = obterColunaUnica('editalProjeto','nome','id',idProjeto)
            titulo = obterColunaUnica('editalProjeto','titulo','id',idProjeto)
            discente = obterColunaUnica('indicacoes','nome','id',idAluno)
            tipo_vaga = obterColunaUnica('indicacoes','tipo_de_vaga','id',idAluno)
            timestamp = agora()
            fomento = int(obterColunaUnica('indicacoes','fomento','id',idAluno))
            consulta = "UPDATE indicacoes SET situacao=2, fim=NOW() WHERE id=" + idAluno
            atualizar(consulta)
            email = obterColunaUnica('editalProjeto','email','id',idProjeto)
            email2 = DEFAULT_EMAIL
            texto_email = render_template('confirmacao_substituicao.html',vaga=tipo_vaga,id_projeto=idProjeto,proponente=orientador,titulo=titulo,indicado=discente,idIndicacao=idAluno,data=timestamp)
            if tipo_vaga=="1":
                msg = Message(subject = "Plataforma Yoko - SUBSTITUIÇÃO DE BOLSISTA",recipients=[email,email2],html=texto_email)
            else:
                msg = Message(subject = "Plataforma Yoko - SUBSTITUIÇÃO DE VOLUNTARIO",recipients=[email,email2],html=texto_email)
            if PRODUCAO==1:
                t = threading.Thread(target=enviar_email_desligamento_substituicao,args=(msg,))
                t.start()
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

        if (ua!='TODOS'):
            where=where + """ AND ua='""" + ua + """' """

        if ('andamento' in request.form):
            where = where + " AND editalProjeto.fim>NOW() "

        if (inicio!='TODOS'):
            where = where + " AND YEAR(editalProjeto.inicio)=" + inicio

        if (fim!='TODOS'):
            where = where + " AND YEAR(editalProjeto.fim)=" + fim

        final = """ GROUP BY editalProjeto.id ORDER BY ua,titulo"""

        consulta = consulta + where + final

        linhas,total = executarSelect(consulta)

        if exportacao==0:
            return(render_template('resultados_consulta.html',linhas=linhas,total=total))
        else:
            try:
                df = pd.DataFrame(list(linhas))
                df.to_csv(app.config['TEMP_FOLDER'] + 'resultados.csv', encoding="utf-8",header=['ID do projeto','EDITAL','UNIDADE ACADEMICA','TÍTULO','ORIENTADOR','INDICAÇÕES','TOTAL DE INDICAÇÕES','INICIO','FIM'])
                #df.to_csv(app.config['TEMP_FOLDER'] + 'resultados.csv', encoding="utf-8")
                return(send_from_directory(app.config['TEMP_FOLDER'], 'resultados.csv'))

            except:
                return("Erro!")
    else:
        return("OK")

@app.route("/substituicoes", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def substituicoes():
    if 'id' in request.args:
        id = str(request.args.get('id'))
        descricao = obterColunaUnica('editais','nome','id',id)
        consulta1 = """SELECT indicacoes.id,idProjeto,editalProjeto.tipo,IF(tipo_de_vaga=1,'BOLSISTA','VOLUNARIO(A)') AS tipo,IF(indicacoes.situacao=1,'DESLIGADO(A)','SUBSTITUIDO(A)') AS tipo_situacao,indicacoes.nome,nome_banco,agencia,conta, DATE_FORMAT(indicacoes.inicio,'%d/%m/%Y') as inicio,
        DATE_FORMAT(indicacoes.fim,'%d/%m/%Y') as final,editalProjeto.nome FROM indicacoes,editalProjeto WHERE indicacoes.idProjeto=editalProjeto.id AND
        indicacoes.situacao in (1,2) AND editalProjeto.tipo=""" + id + """ ORDER BY indicacoes.tipo_de_vaga DESC,indicacoes.fim DESC"""
        linhas,total = executarSelect(consulta1)


        consulta2 = """SELECT indicacoes.id,idProjeto,editalProjeto.tipo,IF(tipo_de_vaga=1,'BOLSISTA','VOLUNARIO(A)') AS tipo,IF(indicacoes.substituido!=0,'SUBSTITUTO(A)','N/A') AS tipo_situacao,indicacoes.nome,nome_banco,agencia,conta, DATE_FORMAT(indicacoes.inicio,'%d/%m/%Y') as inicio,
        DATE_FORMAT(indicacoes.fim,'%d/%m/%Y') as final,indicacoes.substituido,editalProjeto.nome FROM indicacoes,editalProjeto WHERE indicacoes.idProjeto=editalProjeto.id AND
        indicacoes.situacao in (0) AND indicacoes.substituido!=0 AND editalProjeto.tipo=""" + id + """ ORDER BY indicacoes.tipo_de_vaga DESC,indicacoes.fim DESC"""

        linhas2,total2 = executarSelect(consulta2)
        return(render_template('substituicoes.html',linhas=linhas,linhas2=linhas2,total=total,total2=total2,edital=descricao))

    else:
        return("OK")

def gerarLinkAvaliacao():
    consulta = """SELECT id,idProjeto,token FROM avaliacoes 
    WHERE idProjeto in (SELECT id FROM editalProjeto WHERE valendo=1) ORDER BY id """
    linhas,total = executarSelect(consulta)
    for linha in linhas:
        id = str(linha[0])
        idProjeto = str(linha[1])
        token = str(linha[2])
        link = LINK_AVALIACAO + "?id=" + idProjeto + "&token=" + token
        consulta = "UPDATE avaliacoes SET link=\"" + link + "\"" + " WHERE id=" + id
        atualizar(consulta)

def enviar_email_avaliadores():
    gerarLinkAvaliacao()
    consulta = """
    SELECT e.id,e.titulo,e.resumo,a.avaliador,a.link,a.id,a.enviado,a.token,e.categoria,
    e.tipo, DATEDIFF(NOW(),a.data_envio) as enviados,DATE_FORMAT(ed.deadline_avaliacao,'%d/%m/%Y') as deadline_avaliacao,ed.nome 
    FROM editalProjeto as e, avaliacoes as a,editais as ed WHERE e.id=a.idProjeto AND e.tipo=ed.id AND e.valendo=1
    AND a.finalizado=0 AND a.aceitou!=0 AND e.categoria=1 AND DATEDIFF(NOW(),a.data_envio)>1 
    AND a.idProjeto 
    IN (SELECT id FROM resumoGeralAvaliacoes WHERE ((aceites+rejeicoes<2) OR (aceites=rejeicoes)) 
    AND tipo in (SELECT id from editais WHERE deadline_avaliacao>now() AND ADDDATE(deadline,5)<now()))
    """
    linhas,total = executarSelect(consulta)
    for linha in linhas:
        titulo = str(linha[1])
        resumo = str(linha[2])
        link = str(linha[4])
        token = str(linha[7])
        email_avaliador = str(linha[3])
        if 'TESTE' in email_avaliador:
            continue
        link_recusa = ROOT_SITE + "/pesquisa/recusarConvite?token=" + token
        deadline = str(linha[11])
        nome_longo = str(linha[12])
        with app.app_context():
            #url_declaracao = url_for('getDeclaracaoAvaliador',tokenAvaliacao=token, _external=True)
            url_declaracao = SERVER_URL + URL_PREFIX + '/declaracaoAvaliador/' + token
            texto_email = render_template('email_avaliador.html',nome_longo=nome_longo,titulo=titulo,resumo=resumo,link=link,link_recusa=link_recusa,deadline=deadline,url_declaracao=url_declaracao)
            msg = Message(subject = "CONVITE: AVALIAÇÃO DE PROJETO DE PESQUISA",bcc=[email_avaliador],reply_to="NAO-RESPONDA@ufca.edu.br",html=texto_email)
            try:
                try:
                    mail.send(msg)
                    logger.info("E-mail enviado: {}",msg.subject)
                except Exception as e:
                    logger.error("Erro ao enviar e-mail. enviar_email_avaliadores: {}",str(e))
                consulta = "UPDATE avaliacoes SET enviado=enviado+1,data_envio=NOW() WHERE id=" + str(linha[5])
                atualizar(consulta)    
            except Exception as e:
                logger.error("EMAIL SOLICITANDO AVALIACAO FALHOU: {} - ({})", email_avaliador,str(e))
                return("Erro! Verifique o log!")

@app.route("/emailSolicitarAvaliacao", methods=['GET', 'POST'])
@auth.login_required(role=['admin'])
@log_required
@limiter.limit("1 per day", key_func = lambda: 'global')
def email_solicitar_avaliacao():
    t = threading.Thread(target=enviar_email_avaliadores)
    t.start()
    return("Envio de e-mails iniciado!")
    
def enviarPedidoAvaliacao(idProjeto):
    gerarLinkAvaliacao()
    consulta = """
    SELECT e.id,e.titulo,e.resumo,a.avaliador,a.link,a.id,a.enviado,a.token,e.categoria,e.tipo 
    FROM editalProjeto as e, avaliacoes as a WHERE e.id=a.idProjeto AND e.valendo=1 
    AND a.finalizado=0 AND e.categoria=1 and e.id=""" + str(idProjeto) + """ 
    ORDER BY a.id DESC LIMIT 1
    """
    linhas,total = executarSelect(consulta)
    
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
            if PRODUCAO==1:
                msg = Message(subject = "CONVITE: AVALIAÇÃO DE PROJETO DE PESQUISA",bcc=[email_avaliador],reply_to="NAO-RESPONDA@ufca.edu.br",html=texto_email)
            else:
                msg = Message(subject = "CONVITE: AVALIAÇÃO DE PROJETO DE PESQUISA",bcc=[EMAIL_TESTES],reply_to="NAO-RESPONDA@ufca.edu.br",html=texto_email)
            try:
                mail.send(msg)
                logger.info("E-mail enviado: {}",msg.subject)
            except Exception as e:
                logger.error("EMAIL SOLICITANDO AVALIACAO FALHOU: {} - ({})", email_avaliador,str(e))

@app.route("/arquivar/<id_projeto>", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def arquivar_projeto(id_projeto):
    projeto = str(id_projeto)
    consulta = "UPDATE editalProjeto SET valendo=0 WHERE id=" + projeto
    atualizar(consulta)
    edital = str(session['edital'])
    return(redirect("/pesquisa/editalProjeto?edital=" + edital))

@app.route("/aprovar/projetos/<edital>", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def aprovar_projetos(edital):
    #RECOMENDADOS
    consulta1 = """UPDATE editalProjeto SET situacao=1 
    WHERE id in (SELECT editalProjeto.id FROM editalProjeto,avaliacoes WHERE tipo=""" + edital + """ 
    AND valendo=1 AND categoria=1 AND editalProjeto.id=avaliacoes.idProjeto 
    GROUP BY editalProjeto.id 
    HAVING sum(if(recomendacao=1,1,0))-sum(if(recomendacao=0,1,0))>0 
    ORDER BY editalProjeto.ua,editalProjeto.id)
    """
    #NÃO RECOMENDADOS
    consulta2 = """UPDATE editalProjeto SET situacao=1 
    WHERE id in (SELECT editalProjeto.id FROM editalProjeto,avaliacoes WHERE tipo=""" + edital + """ 
    AND valendo=1 AND categoria=1 AND editalProjeto.id=avaliacoes.idProjeto 
    GROUP BY editalProjeto.id 
    HAVING sum(if(recomendacao=1,1,0))-sum(if(recomendacao=0,1,0))<=0 
    ORDER BY editalProjeto.ua,editalProjeto.id)
    """

    atualizar(consulta1)
    atualizar(consulta2)
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
    consulta = """
    SELECT UPPER(editalProjeto.nome),area_capes,UPPER(titulo), YEAR(editalProjeto.inicio) as ano,
    GROUP_CONCAT(IF(indicacoes.modalidade=1,'PIBIC',IF(indicacoes.modalidade=2,'PIBITI','PIBIC-EM')) LIMIT 1) as modalidade,
    palavras,bolsas as solicitadas,bolsas_concedidas as concedidas,
    (SELECT count(id) FROM indicacoes WHERE indicacoes.idProjeto=editalProjeto.id and indicacoes.tipo_de_vaga=1 and situacao=0) as bolsistas,
    (SELECT count(id) FROM indicacoes WHERE indicacoes.idProjeto=editalProjeto.id and indicacoes.tipo_de_vaga=0 and situacao=0) as voluntarios,
    (SELECT count(id)*400*12 FROM indicacoes WHERE indicacoes.idProjeto=editalProjeto.id and indicacoes.tipo_de_vaga=1 and situacao=0) as valores
    FROM `editalProjeto` 
    LEFT JOIN indicacoes ON editalProjeto.id=indicacoes.idProjeto
    where valendo=1 and indicacoes.situacao=0
    and siape in (%s) 
    group by editalProjeto.id
    order by year(editalProjeto.inicio),editalProjeto.id
    """ % (siapes)
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
    and siape in (%s) 
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
    WHERE siape in (%s) and estudante_tipo_de_vaga='BOLSISTA'
    GROUP BY titulo_do_projeto,ano 
    ORDER BY ano,nome_do_coordenador)
    """ % (siapes,siapes)
    linhas,total = executarSelect(consulta)
    dados = []
    for linha in linhas:
        dado = {'nome': linha[0],'area_capes': linha[1],'titulo': linha[2],'ano': linha[3],'modalidade': linha[4],'palavras': linha[5],'solicitadas': linha[6],'concedidas': linha[7],'bolsistas': linha[8],'voluntarios': linha[9],'valores': linha[10]}
        dados.append(dado)
    return Response(json.dumps(dados),  mimetype='application/json')

@app.route("/auditoria_indicacoes", methods=['GET'])
@auth.login_required(role=['admin'])
@log_required
def auditoria_indicacoes():
    
    from datetime import datetime
    ano_atual = str(datetime.now().year)
    consulta = """
        SELECT min(id) FROM `editais` WHERE year(deadline)=%s
    """ % (ano_atual)
    
    linha,total = executarSelect(consulta)
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
    """ % (str(edital))
    linhas,total = executarSelect(consulta)
    
    return(render_template('indicacoes_duplicadas.html',linhas=linhas,total=total,edital=edital,ano=ano_atual))

@app.route("/indicacao/<cpf>", methods=['GET'])
@log_required
def get_dados_indicacao(cpf):
    cpf_corrigido = cpf
    cpf_corrigido = cpf_corrigido[:3] + '.' + cpf_corrigido[3:]
    cpf_corrigido = cpf_corrigido[:7] + '.' + cpf_corrigido[7:]
    cpf_corrigido = cpf_corrigido[:11] + '-' + cpf_corrigido[11:]
    consulta = """
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
    cpf="%s"
    ORDER BY indicacoes.id DESC
    """ % (cpf_corrigido)
    linhas,total = executarSelect(consulta)
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
            logger.error("Erro ao gerar projetos por aluno")
            logger.error(str(e))
            return render_template("Erro ao gerar projetos por aluno (/projetos_discente)")

@app.route("/argon2", methods=['GET'])
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
        consulta = """UPDATE users SET password= ? WHERE id= ?"""
        atualizar2(consulta, valores=[hashed_password, idUsuario])
    return("OK\n")

def cadastrar_novo_usuario(siape, nome, email):
    senha = generate_secure_password()
    hashed_password = cripto.hash_argon2id(senha)
    role = 'user'
    consulta = """INSERT INTO users (username,nome,email,password,roles) 
    VALUES (?, ?, ?, ?, ?)"""
    atualizar2(consulta,valores=[siape, nome, email, hashed_password, role])
    return senha

@app.route("/cadastrar_usuario", methods=['GET', 'POST'])
@login_required(role='admin')
@log_required
def cadastrar_usuario():
    if request.method == 'POST':
        #Recebendo siape, nome e email do formulário
        siape = str(request.form['siape'])
        nome = str(request.form['nome'])
        email = str(request.form['email'])
        #Verificando se o usuário já existe
        consulta = """SELECT id FROM users WHERE username= ? """
        linhas,total = executarSelect2(consulta, valores=[siape])
        if total > 0:
            flash("Usuário já cadastrado!")
            return redirect(url_for('cadastrar_usuario'))
        #Verificando se o e-mail já está cadastrado
        consulta = """SELECT id FROM users WHERE email= ? """
        linhas,total = executarSelect2(consulta, valores=[email])
        if total > 0:
            flash("E-mail já cadastrado!")
            return redirect(url_for('cadastrar_usuario'))
        #Cadastrando novo usuário no banco de dados
        try:
            senha = cadastrar_novo_usuario(siape, nome, email)
        except Exception as e:
            logger.error("Erro ao cadastrar novo usuário")
            logger.error(str(e))
            flash("Erro ao cadastrar usuário.")
            return redirect(url_for('cadastrar_usuario'))
        flash("Usuário cadastrado com sucesso!")
        #Enviando e-mail com as credenciais do usuário
        texto_mensagem = "Usuario: " + siape + "\nSenha: " + senha + "\n" + USUARIO_SITE
        msg = Message(subject = "Plataforma Yoko - Cadastro de Usuário",recipients=[email],body=texto_mensagem)
        thread = threading.Thread(target=thread_enviar_senha, args=(msg,))
        thread.start()
        return redirect(url_for('admin'))
    else:
        return render_template('cadastrar_usuario.html')

@app.route("/cadastrar_usuarios_projetos/<edital>", methods=['GET'])
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
    WHERE tipo= ? AND 
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
                senha = cadastrar_novo_usuario(siape, nome, email)
                texto_mensagem = "Usuario: " + siape + "\nSenha: " + senha + "\n" + USUARIO_SITE
                msg = Message(subject = "Plataforma Yoko - Cadastro de Usuário",recipients=[email],body=texto_mensagem)
                thread = threading.Thread(target=thread_enviar_senha, args=(msg,))
                thread.start()
            except Exception as e:
                logger.error("Erro ao cadastrar usuário do projeto")
                logger.error(str(e))
                flash("Erro ao cadastrar usuário: " + nome + " (" + siape + ")")
        flash(f"{total} usuários cadastrados com sucesso!")
        return redirect(url_for('admin'))
    else:
        flash("Nenhum usuário encontrado para cadastro.")
        return redirect(url_for('admin'))

def task_enviar_email_avaliadores():
    gerarLinkAvaliacao()
    consulta = """
    SELECT e.id,e.titulo,e.resumo,a.avaliador,a.link,a.id,a.enviado,a.token,e.categoria,
    e.tipo, DATEDIFF(NOW(),a.data_envio) as enviados,DATE_FORMAT(ed.deadline_avaliacao,'%d/%m/%Y') as deadline_avaliacao,ed.nome 
    FROM editalProjeto as e, avaliacoes as a,editais as ed WHERE e.id=a.idProjeto AND e.tipo=ed.id AND e.valendo=1
    AND a.finalizado=0 AND a.aceitou!=0 AND e.categoria=1 AND DATEDIFF(NOW(),a.data_envio)>1 
    AND a.idProjeto 
    IN (SELECT id FROM resumoGeralAvaliacoes WHERE ((aceites+rejeicoes<2) OR (aceites=rejeicoes)) 
    AND tipo in (SELECT id from editais WHERE deadline_avaliacao>now() AND ADDDATE(deadline,5)<now()))
    """
    linhas,total = executarSelect(consulta)
    for linha in linhas:
        titulo = str(linha[1])
        resumo = str(linha[2])
        link = str(linha[4])
        token = str(linha[7])
        email_avaliador = str(linha[3])
        if 'TESTE' in email_avaliador:
            continue
        link_recusa = ROOT_SITE + "/pesquisa/recusarConvite?token=" + token
        deadline = str(linha[11])
        nome_longo = str(linha[12])
        with scheduler.app.app_context():
            #url_declaracao = url_for('getDeclaracaoAvaliador',tokenAvaliacao=token, _external=True)
            url_declaracao = SERVER_URL + URL_PREFIX + '/declaracaoAvaliador/' + token
            texto_email = render_template('email_avaliador.html',nome_longo=nome_longo,titulo=titulo,resumo=resumo,link=link,link_recusa=link_recusa,deadline=deadline,url_declaracao=url_declaracao)
            msg = Message(subject = "CONVITE: AVALIAÇÃO DE PROJETO DE PESQUISA",bcc=[email_avaliador],reply_to="NAO-RESPONDA@ufca.edu.br",html=texto_email)
            try:
                try:
                    mail.send(msg)
                    logger.info("E-mail enviado: {}",msg.subject)
                except Exception as e:
                    logger.error("Erro ao enviar e-mail. enviar_email_avaliadores: {}",str(e))
                consulta = "UPDATE avaliacoes SET enviado=enviado+1,data_envio=NOW() WHERE id=" + str(linha[5])
                atualizar(consulta)
            except Exception as e:
                logger.error("EMAIL SOLICITANDO AVALIACAO FALHOU: {} - ({})", email_avaliador,str(e))
                continue
    logger.info("Tarefa de envio de e-mails para avaliadores concluída com sucesso.")

@scheduler.task('cron', id='do_job_enviar_email_avaliadores', week='*', day_of_week='2,4', hour='7', minute='45')
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
    import datetime
    #Mes e ano atual
    ano = str(datetime.date.today().year)
    mes = str(datetime.date.today().month-1)
    if mes==1:
        ano = ano - 1
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
    with scheduler.app.app_context():
        consulta = """SELECT 
        GROUP_CONCAT(editalProjeto.id ORDER BY editalProjeto.id),
        editalProjeto.nome,
        GROUP_CONCAT(editalProjeto.titulo), 
        GROUP_CONCAT(indicacoes.id ORDER BY indicacoes.idProjeto,indicacoes.id),
        editalProjeto.email,
        editalProjeto.siape
        from editalProjeto
        INNER JOIN indicacoes ON editalProjeto.id=indicacoes.idProjeto
        WHERE indicacoes.fim>NOW() AND indicacoes.situacao=0 and MONTH(indicacoes.inicio)!=Month(now())
        GROUP BY editalProjeto.nome"""
        linhas,total = executarSelect(consulta)
        for linha in linhas:
            id_projetos = str(linha[0]).split(',')
            orientador = str(linha[1])
            siape = str(linha[5])
            senha = obterColunaUnica('users','password','username',siape)
            titulos = str(linha[2]).split(',')
            indicacoes = str(linha[3]).split(',')
            nao_enviados = []
            for indicacao in indicacoes:
                subconsulta = """SELECT 
                idIndicacao 
                FROM frequencias 
                WHERE mes=%s AND ano=%s AND idIndicacao=%s 
                LIMIT 1
                """ % (mes,ano,indicacao)
                frequencias,totalFrequencias = executarSelect(subconsulta)
                if totalFrequencias==0: #Não foi enviada a frequência para este discente
                    nome_indicado = obterColunaUnica('indicacoes','nome','id',indicacao)
                    nao_enviados.append(nome_indicado)
            if (len(nao_enviados)!=0):
                
                texto_email = render_template('lembrete_frequencia.html',mes=str(nome_mes[str(mes)]),ano=ano,nomes=nao_enviados,usuario=siape,senha=senha)
                if PRODUCAO==1:
                    msg = Message(subject = "Plataforma Yoko PIICT- LEMBRETE DE ENVIO DE FREQUÊNCIA",recipients=[str(linha[4])],html=texto_email,reply_to="NAO-RESPONDA@ufca.edu.br")
                    try:
                        mail.send(msg)
                        logger.info("E-mail enviado: Lembrete de frequência {}/{} para {}",nome_mes[str(mes)],ano,orientador)
                    except Exception as e:
                        logger.error("Erro ao enviar e-mail. /enviar_lembrete_frequencia: {}",str(e))
                else:
                    msg = Message(subject = "Plataforma Yoko PIICT- LEMBRETE DE ENVIO DE FREQUÊNCIA",recipients=['pesquisapython3.display999@passmail.net'],html=texto_email,reply_to="NAO-RESPONDA@ufca.edu.br")
                    try:
                        mail.send(msg)
                        logger.info("E-mail enviado: Lembrete de frequência para {}",orientador)
                    except Exception as e:
                        logger.error("Erro ao enviar e-mail. /enviar_lembrete_frequencia: {}",str(e))
                    finally:
                        continue

@scheduler.task('cron', id='do_job_cobrar_frequencia', week='*', day='5-30/5', hour='7', minute='59')
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

@app.route("/ligarScheduler", methods=['GET'])
@login_required(role='admin')
@log_required
def ligar_scheduler():
    """
    Liga o scheduler para execução de tarefas agendadas.
    """
    if PRODUCAO==1:
        scheduler.start()
        logger.info("Scheduler ligado.")
        return "Scheduler ligado!"
    else:
        return "Scheduler não está ativo em ambiente de testes."

@app.route("/desligarScheduler", methods=['GET'])
@login_required(role='admin')
@log_required
def desligar_scheduler():
    """
    Desliga o scheduler para não executar mais tarefas agendadas.
    """
    if PRODUCAO==1:
        scheduler.shutdown()
        logger.info("Scheduler desligado.")
        return "Scheduler desligado!"
    else:
        return "Scheduler não está ativo em ambiente de testes."

@app.route("/schedulerJobs", methods=['GET'])
@login_required(role='admin')
@log_required
def scheduler_jobs():
    """
    Retorna os jobs do scheduler e seu status.
    """
    if scheduler.running:    
        jobs = scheduler.get_jobs()
        jobs_info = []
        for job in jobs:
            job_info = {
                'id': job.id,
                'name': job.name,
                'next_run_time': str(job.next_run_time),
                'trigger': str(job.trigger),
            }
            jobs_info.append(job_info)
        return jsonify(jobs_info)
    else:
        return jsonify({'message': 'Scheduler não está em execução.'})

if PRODUCAO==1:
    scheduler.start()

if __name__ == "__main__":
    prefixo = os.getenv('URL_PREFIX','/pesquisa')
    with logger.catch():
        serve(app, host='0.0.0.0', port=80, url_prefix=prefixo,trusted_proxy='*',trusted_proxy_headers='x-forwarded-for x-forwarded-proto x-forwarded-port')
