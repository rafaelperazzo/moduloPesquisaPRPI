# -*- coding: utf-8 -*-
from flask import Flask
from flask import render_template
from flask import request,url_for,send_from_directory,redirect,Markup,session
from flask_httpauth import HTTPBasicAuth
from waitress import serve
import MySQLdb
from werkzeug.utils import secure_filename
import os
import string
import random
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import logging
import sys
import numpy as np
import pdfkit
from flask_mail import Mail
from flask_mail import Message
from flask_uploads import *
import pandas as pd
import configparser
import threading
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import zeep
import zipfile

WORKING_DIR='/home/perazzo/pesquisa/'
config = configparser.ConfigParser()
config.read(WORKING_DIR + 'config.ini')
SERVER_URL = config['DEFAULT']['server']
PRODUCAO = 1
try:
    PRODUCAO = config['DEFAULT']['producao']
    PRODUCAO = int(PRODUCAO)
except:
    PRODUCAO = 1

UPLOAD_FOLDER = '/home/perazzo/pesquisa/static/files'
ALLOWED_EXTENSIONS = set(['pdf','xml'])

PLOTS_DIR = '/home/perazzo/pesquisa/static/plots/'
CURRICULOS_DIR='/home/perazzo/pesquisa/static/files/'
XML_DIR = '/home/perazzo/pesquisa/xml/'
SITE = SERVER_URL + "/pesquisa/static/files/"
IMAGENS_URL = SERVER_URL + "/pesquisa/static/"
DECLARACOES_DIR = '/home/perazzo/pesquisa/pdfs/'
ROOT_SITE = SERVER_URL
USUARIO_SITE = ROOT_SITE + "/pesquisa/usuario"
ATTACHMENTS_DIR = '/home/perazzo/pesquisa/docs_indicacoes/'
MYSQL_DB = "db_pesquisa"
LINK_AVALIACAO = ROOT_SITE + "/pesquisa/avaliacao"
app = Flask(__name__)
auth = HTTPBasicAuth()
mail = Mail(app)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = 'pesquisa.prpi@ufca.edu.br'
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_DEFAULT_SENDER'] = 'pesquisa.prpi@ufca.edu.br'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['CURRICULOS_FOLDER'] = CURRICULOS_DIR
app.config['DECLARACOES_FOLDER'] = DECLARACOES_DIR
app.config['TEMP_FOLDER'] = DECLARACOES_DIR

## TODO: Preparar o log geral
logging.basicConfig(filename=WORKING_DIR + 'app.log', filemode='a', format='%(asctime)s %(name)s - %(levelname)s - %(message)s',level=logging.ERROR)
logging.getLogger('waitress')
#Obtendo senhas
lines = [line.rstrip('\n') for line in open(WORKING_DIR + 'senhas.pass')]
PASSWORD = lines[0]
GMAIL_PASSWORD = lines[1]
SESSION_SECRET_KEY = lines[2]
app.config['SECRET_KEY'] = SESSION_SECRET_KEY
app.config['MAIL_PASSWORD'] = GMAIL_PASSWORD
mail = Mail(app)

#Flask-flask_uploads
app.config['UPLOADED_DOCUMENTS_DEST'] = ATTACHMENTS_DIR
app.config['UPLOADS_DEFAULT_DEST'] = ATTACHMENTS_DIR
anexos = UploadSet('documents',ALL)
configure_uploads(app, anexos)
patch_request_class(app)

@app.before_first_request
def prepararInicializacao():
    session['PRODUCAO'] = PRODUCAO
    

def removerAspas(texto):
    resultado = texto.replace('"',' ')
    resultado = resultado.replace("'"," ")
    return(resultado)

def getID(cpf):
    wsdl = 'https://sci01-ter-jne.ufca.edu.br/cnpq'
    client = zeep.Client(wsdl=wsdl)
    idlattes = client.service.getIdentificadorCNPq(cpf,"","")
    return str(idlattes)

def salvarCV(id):
    wsdl = 'https://sci01-ter-jne.ufca.edu.br/cnpq'
    client = zeep.Client(wsdl=wsdl)
    resultado = client.service.getCurriculoCompactado(id)
    arquivo = open(id + '.zip','wb')
    arquivo.write(resultado)
    arquivo.close()
    with zipfile.ZipFile(id + '.zip','r') as zip_ref:
        zip_ref.extractall(XML_DIR)
    if os.path.exists(id + '.zip'):
        os.remove(id + '.zip')

def processarPontuacaoLattes(cpf,area,idProjeto,dados):
    idlattes = getID(cpf)
    salvarCV(idlattes)
    arquivo = XML_DIR + idlattes + ".xml"
    
    pontuacao = -100
    sumario = "---"
    try:
        from datetime import date
        ano_fim = date.today().year
        ano_inicio = ano_fim - 5
        s = calcularScoreLattes(0,area,str(ano_inicio),str(ano_fim),arquivo)
        pontuacao = float(s)
        sumario = calcularScoreLattes(1,area,str(ano_inicio),str(ano_fim),arquivo)
        sumario = sumario.decode('utf-8')
    except:
        e = sys.exc_info()[0]
        logging.error(e)
        logging.error(XML_DIR + arquivo)
        pontuacao = -1
        logging.error("Nao foi possivel calcular o scorelattes: " + str(e))

    try:
        consulta = "UPDATE editalProjeto SET scorelattes=" + str(pontuacao) + " WHERE id=" + str(idProjeto)
        atualizar(consulta)
    except:
        e = sys.exc_info()[0]
        logging.error(e)
        logging.error("Procedimento para o ID: " + str(idProjeto) + " finalizado. Erros ocorreram ao tentar atualizar o scorelattes.")
        logging.error(str(e))
    with app.app_context():
        try:
            #ENVIAR E-MAIL DE CONFIRMAÇÃO
            texto_email = render_template('confirmacao_submissao.html',email_proponente=dados[0],id_projeto=idProjeto,proponente=dados[1],titulo_projeto=dados[2],resumo_projeto=dados[3],score=pontuacao,sumario=sumario)
            msg = Message(subject = "Plataforma Yoko - CONFIRMAÇÃO DE SUBMISSAO DE PROJETO DE PESQUISA",recipients=[dados[0]],html=texto_email,reply_to="NAO-RESPONDA@ufca.edu.br")
            mail.send(msg)
        except:
            e = sys.exc_info()[0]
            logging.error(e)
            logging.error("Procedimento para o ID: " + str(idProjeto) + " finalizado. Erros ocorreram ao enviar e-mail.")        

def calcularScoreLattes(tipo,area,since,until,arquivo):
    #Tipo = 0: Apenas pontuacao; Tipo = 1: Sumário
    pasta = WORKING_DIR + "modules/"
    if tipo==1:
        command = "python " + pasta + "scorerun.py -v -p 2016 -s " +  since + " -u " + until + " \"" + area + "\" " +  arquivo
    else:
        command = "python " + pasta + "scorerun.py -p 2016 -s " +  since + " -u " + until + " \"" + area + "\" " +  arquivo
    s = os.popen(command).read()
    return (s)

def enviarEmail(to,subject,body):
    gmail_user = 'pesquisa.prpi@ufca.edu.br'
    gmail_password = GMAIL_PASSWORD
    sent_from = gmail_user
    para = [to]
    #msg = MIMEMultipart()
    msg = MIMEText(body,'plain','utf-8')
    msg['From'] = gmail_user
    msg['To'] = to
    msg['Subject'] = Header(subject, "utf-8")
    msg['Cc'] = "rafael.mota@ufca.edu.br"
    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.ehlo()
        server.login(gmail_user, gmail_password)
        server.sendmail(sent_from, to, msg.as_string())
        server.close()
        logging.debug("E-Mail enviado com sucesso.")
        return (True)
    except:
        e = sys.exc_info()[0]
        logging.debug("Erro ao enviar e-mail: " + str(e))
        return (False)

def atualizar(consulta):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
    conn.autocommit(True)
    conn.select_db('pesquisa')
    cursor  = conn.cursor()
    try:
        cursor.execute(consulta)
        conn.commit()
    except MySQLdb.Error as e:
        #e = sys.exc_info()[0]
        logging.debug(e)
        logging.debug(consulta)
        #conn.rollback()
    finally:
        cursor.close()
        conn.close()

def inserir(consulta,valores):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
    conn.autocommit(True)
    conn.select_db('pesquisa')
    cursor  = conn.cursor()
    try:
        cursor.execute(consulta,valores)
        conn.commit()
    except MySQLdb.Error as e:
        #e = sys.exc_info()[0]
        logging.error(e)
        logging.debug(consulta)
        logging.error("Erro ao inserir registro")
        logging.error(valores)
        #conn.rollback()
    finally:
        cursor.close()
        conn.close()


def id_generator(size=20, chars=string.ascii_uppercase + string.digits + string.ascii_lowercase):
        return ''.join(random.choice(chars) for _ in range(size))

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def getData():
    import datetime
    Meses=('janeiro','fevereiro',u'março','abril','maio','junho',
       'julho','agosto','setembro','outubro','novembro','dezembro')
    agora = datetime.date.today()
    dia = agora.day
    mes=(agora.month-1)
    mesExtenso = Meses[mes]
    ano = agora.year
    resultado = str(dia) + " de " + mesExtenso + " de " + str(ano) + "."
    return resultado


def gerarDeclaracao(identificador):
    #CONEXÃO COM BD
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
    conn.select_db('pesquisa')
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
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
    conn.select_db('pesquisa')
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
		frase_bolsistas = frase_bolsistas + unicode(bolsista[0])
	else: #Se nao for o ultimo bolsista
		frase_bolsistas = frase_bolsistas + unicode(bolsista[0]) + ", "
	i = i + 1
    conn.close()
    return (linha,frase_bolsistas)


def gerarProjetosPorAluno(cpf):
    try:
        conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
        conn.select_db('pesquisa')
        cursor  = conn.cursor()
        consulta = """SELECT estudante_nome_completo,cpf,estudante_modalidade,nome_do_coordenador,titulo_do_projeto,estudante_inicio,estudante_fim,token FROM cadastro_geral WHERE cpf = '""" + cpf + """'"""
        cursor.execute(consulta)
        linhas = cursor.fetchall()
        consulta = """SELECT indicacoes.nome,indicacoes.cpf,IF(indicacoes.modalidade=1,'PIBIC',IF(indicacoes.modalidade=2,'PIBITI','PIBIC-EM')),editalProjeto.nome,editalProjeto.titulo,indicacoes.inicio,indicacoes.fim,indicacoes.id
                    FROM indicacoes,editalProjeto
                    WHERE indicacoes.idProjeto=editalProjeto.id AND indicacoes.cpf='""" + cpf + """'"""
        cursor.execute(consulta)
        linhas2019 = cursor.fetchall()
        return (linhas,linhas2019)
    except:
        e = sys.exc_info()[0]
        logging.error(e)
        logging.error("ERRO Na função gerarProjetosPorAluno. Ver consulta abaixo.")
        logging.error(consulta)
    finally:
        cursor.close()
        conn.close()


def gerarProjetosPorOrientador(identificador):
    #CONEXÃO COM BD
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
    conn.select_db('pesquisa')
    cursor  = conn.cursor()
    consulta = "SELECT id,coordenador,titulo,inicio,fim FROM projetos WHERE SIAPE=" + str(identificador)
    cursor.execute(consulta)
    linhas = cursor.fetchall()
    conn.close()
    return (linhas)


def gerarAutenticacao(identificador):
    #CONEXÃO COM BD
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
    conn.select_db('pesquisa')
    cursor  = conn.cursor()
    consulta = "SELECT a.nome,a.cpf,a.modalidade,a.orientador,a.projeto,a.inicio,a.fim,b.codigo FROM alunos a, autenticacao b WHERE a.id=b.idAluno and b.codigo=" + identificador + " ORDER BY b.data DESC LIMIT 1"
    cursor.execute(consulta)
    linha = cursor.fetchone()
    conn.close()
    return (linha)

def getEditaisAbertos():
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
    conn.select_db('pesquisa')
    cursor  = conn.cursor()
    consulta = """SELECT id,nome,DATE_FORMAT(deadline,'%d/%m/%Y - %H:%i') FROM editais WHERE now()<deadline ORDER BY id DESC"""
    cursor.execute(consulta)
    linhas = cursor.fetchall()
    cursor.close()
    conn.close()
    return(linhas)

'''
INÍCIO AUTENTICAÇÃO
**************************************************************
'''
@auth.verify_password
def verify_password(username, password):
    """This function is called to check if a username /
    password combination is valid.
    """
    try:
        conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
        conn.select_db('pesquisa')
        cursor  = conn.cursor()
        consulta = """SELECT id,username,permission,roles FROM users WHERE username='""" + username + """' AND password=('""" + password + """')"""
        cursor.execute(consulta)
        total = cursor.rowcount
        if (total==0):
            return (False)
        else:
            linha = cursor.fetchone()
            session['username'] = str(linha[1])
            session['permissao'] = int(linha[2])
            roles = str(linha[3])
            roles = roles.split(',')
            session['roles'] = roles
            session['edital'] = 0
            return (username)
    except:
        e = sys.exc_info()[0]
        logging.error(e)
        logging.error("ERRO Na função check_auth. Ver consulta abaixo.")
        logging.error(consulta)
    finally:
        cursor.close()
        conn.close()

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

'''
FIM AUTENTICAÇÃO
**************************************************************
'''

@app.route('/segredo')
@auth.login_required
def secret_page():
    return (session['username'])

@app.route("/")
def home():
    editaisAbertos = getEditaisAbertos()
    session['PRODUCAO'] = PRODUCAO
    return (render_template('cadastrarProjeto.html',abertos=editaisAbertos))

@app.route("/admin")
def admin():
    if (autenticado() and int(session['permissao'])==0):
        consulta = """SELECT id,nome FROM editais ORDER BY id"""
        editais,total = executarSelect(consulta)
        return (render_template('index.html',editais=editais))
    else:
        return(render_template('login.html',mensagem=u"É necessário autenticação para acessar a página solicitada"))

@app.route("/declaracao", methods=['GET', 'POST'])
def declaracao():
    if request.method == "GET":
        if 'idProjeto' in request.args:
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
                arquivoDeclaracao = app.config['DECLARACOES_FOLDER'] + 'declaracao.pdf'
                #pdfkit.from_string(render_template('a4.html',texto=texto_declaracao,data=data_agora,identificador=texto_declaracao[7],raiz=ROOT_SITE),arquivoDeclaracao)
                #return send_from_directory(app.config['DECLARACOES_FOLDER'], 'declaracao.pdf')
                #return send_file(arquivoDeclaracao, attachment_filename='arquivo.pdf')
            except:
                e = sys.exc_info()[0]
                logging.error(e)
                logging.error(arquivoDeclaracao)
                logging.error("Nao foi possivel gerar o PDF da declaração.")
            finally:
                return render_template('a4.html',texto=texto_declaracao,data=data_agora,identificador=texto_declaracao[7],raiz=ROOT_SITE)
        else:
            logging.debug("Tentativa de gerar declaração, sem o id do projeto!")
            return("OK")

@app.route("/projetosAluno", methods=['GET', 'POST'])
def projetos():
    try:
        projetosAluno,projetosAluno2019 = gerarProjetosPorAluno(unicode(request.form['txtNome']))
        return render_template('alunos.html',listaProjetos=projetosAluno,lista2019=projetosAluno2019)
    except:
        e = sys.exc_info()[0]
        logging.error(e)
        logging.error("Nao foi possivel gerar os projetos do aluno.")
        return("Erro! Não utilize acentos ou caracteres especiais na busca.")

@app.route("/autenticacao", methods=['GET', 'POST'])
def autenticar():
    #dadosAutenticacao = gerarAutenticacao(str(request.form['txtCodigo']))
    #return render_template('autenticacao.html',linha=dadosAutenticacao)
    tipo = int(request.form['tipo'])
    codigo = str(request.form['codigo'])
    if tipo==0:
	    return redirect("/pesquisa/orientadorDeclaracao?idProjeto=" + codigo)
    else:
	    return redirect("/pesquisa/declaracao?idProjeto=" + codigo)


@app.route("/projetosPorOrientador", methods=['GET', 'POST'])
def projetosOrientador():
    projetosOrientador = gerarProjetosPorOrientador(str(request.form['txtSiape']))
    return render_template('projetos_orientador.html',listaProjetos=projetosOrientador)

@app.route("/orientadorDeclaracao", methods=['GET', 'POST'])
def declaracaoOrientador():
    resultados = gerarDeclaracaoOrientador(str(request.args['idProjeto']))
    texto_declaracao = resultados[0]
    bolsistas = resultados[1]
    data_agora = getData()
    return render_template('orientador.html',texto=texto_declaracao,data=data_agora,identificador=texto_declaracao[0],bolsistas=bolsistas)

@app.route("/cadastrarProjeto", methods=['GET', 'POST'])
def cadastrarProjeto():

    #CADASTRAR DADOS DO PROPONENTE
    tipo = int(request.form['tipo'])
    nome = unicode(request.form['nome'])
    categoria_projeto = int(request.form['categoria_projeto'])
    siape = int(request.form['siape'])
    email = unicode(request.form['email'])
    ua = unicode(request.form['ua'])
    area_capes = unicode(request.form['area_capes'])
    grande_area = unicode(request.form['grande_area'])
    grupo = unicode(request.form['grupo'])
    ods_projeto = unicode(request.form['ods_projeto'])
    cpf = unicode(request.form['cpf'])
    #CONEXÃO COM BD
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
    conn.autocommit(True)
    conn.select_db('pesquisa')
    cursor  = conn.cursor()

    #DADOS PESSOAIS E BÁSICOS DO PROJETO
    consulta = "INSERT INTO editalProjeto (categoria,tipo,nome,siape,email,ua,area_capes,grande_area,grupo,data,ods) VALUES (" + str(categoria_projeto) + "," + str(tipo) + "," +  "\"" + nome + "\"," + str(siape) + "," + "\"" + email + "\"," + "\"" + ua + "\"," + "\"" + area_capes + "\"," + "\"" + grande_area + "\"," + "\"" + grupo + "\"," + "CURRENT_TIMESTAMP()," + ods_projeto + ")"
    #atualizar(consulta)
    try:
        cursor.execute(consulta)
        conn.commit()
    except MySQLdb.Error as e:
        logging.error(str(e))
        logging.error(consulta)
        #conn.rollback()
        return(str(e))

    getID = "SELECT LAST_INSERT_ID()"
    cursor.execute(getID)
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

    logging.debug("Projeto [" + tipo_str + "] [" + categoria_str + "] com ID: " + ultimo_id_str + " cadastrado. Proponente: " + nome)
    #CADASTRAR DADOS DO PROJETO

    titulo = unicode(request.form['titulo'])
    titulo = removerAspas(titulo)
    validade = int(request.form['validade'])
    palavras_chave = unicode(request.form['palavras_chave'])
    palavras_chave = removerAspas(palavras_chave)
    descricao_resumida = unicode(request.form['descricao_resumida'])
    descricao_resumida = removerAspas(descricao_resumida)
    if 'numero_bolsas' in request.form:
        bolsas = int(request.form['numero_bolsas'])
    else:
        bolsas = 0
    transporte = unicode(request.form['transporte'])
    consulta = "UPDATE editalProjeto SET titulo=\"" + titulo + "\", validade=" + str(validade) + ", palavras=\"" + palavras_chave + "\", resumo=\"" + descricao_resumida + "\", bolsas=" + str(bolsas) +  " WHERE id=" + str(ultimo_id)
    logging.debug("Preparando para atualizar dados do projeto.")
    atualizar(consulta)
    consulta = "UPDATE editalProjeto SET transporte=" + transporte + " WHERE id=" + str(ultimo_id)
    atualizar(consulta)
    inicio = unicode(request.form['inicio'])
    fim = unicode(request.form['fim'])
    consulta = "UPDATE editalProjeto SET inicio=\"" + inicio + "\" WHERE id=" + str(ultimo_id)
    atualizar(consulta)
    consulta = "UPDATE editalProjeto SET fim=\"" + fim + "\" WHERE id=" + str(ultimo_id)
    atualizar(consulta)
    logging.debug("Dados do projeto cadastrados.")
    codigo = id_generator()

    if ('arquivo_projeto' in request.files):
        arquivo_projeto = request.files['arquivo_projeto']
        if arquivo_projeto and allowed_file(arquivo_projeto.filename) :
            arquivo_projeto.filename = "projeto_" + ultimo_id_str + "_" + str(siape) + "_" + codigo + ".pdf"
            filename = secure_filename(arquivo_projeto.filename)
            arquivo_projeto.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            caminho = str(app.config['UPLOAD_FOLDER'] + "/" + filename)
            consulta = "UPDATE editalProjeto SET arquivo_projeto=\"" + filename + "\" WHERE id=" + str(ultimo_id)
            atualizar(consulta)
            logging.debug("Arquivo de projeto cadastrado.")
        elif not allowed_file(arquivo_projeto.filename):
    		return ("Arquivo de projeto não permitido")
    else:
        logging.debug("Não foi incluído um arquivo de projeto")


    if ('arquivo_plano1' in request.files):

        arquivo_plano1 = request.files['arquivo_plano1']
        if arquivo_plano1 and allowed_file(arquivo_plano1.filename):
            arquivo_plano1.filename = "plano1_" + ultimo_id_str + "_" + str(siape) + "_" + codigo + ".pdf"
            filename = secure_filename(arquivo_plano1.filename)
            arquivo_plano1.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            caminho = str(app.config['UPLOAD_FOLDER'] + "/" + filename)
            consulta = "UPDATE editalProjeto SET arquivo_plano1=\"" + filename + "\" WHERE id=" + str(ultimo_id)
            atualizar(consulta)
            logging.debug("Arquivo Plano 1 cadastrado.")
        elif not allowed_file(arquivo_plano1.filename):
    		return ("Arquivo de plano 1 de trabalho não permitido")
    else:
        logging.debug("Não foi incluído um arquivo de plano 1")


    if ('arquivo_plano2' in request.files):
        arquivo_plano2 = request.files['arquivo_plano2']
        if arquivo_plano2 and allowed_file(arquivo_plano2.filename):
            arquivo_plano2.filename = "plano2_" + ultimo_id_str + "_" + str(siape) + "_" + codigo + ".pdf"
            filename = secure_filename(arquivo_plano2.filename)
            arquivo_plano2.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            caminho = str(app.config['UPLOAD_FOLDER'] + "/" + filename)
            consulta = "UPDATE editalProjeto SET arquivo_plano2=\"" + filename + "\" WHERE id=" + str(ultimo_id)
            atualizar(consulta)
            logging.debug("Arquivo Plano 2 cadastrado.")
        elif not allowed_file(arquivo_plano2.filename):
    		return ("Arquivo de plano 2 de trabalho não permitido")
    else:
        logging.debug("Não foi incluído um arquivo de plano 2")

    #ARQUIVO DE COMPROVANTES
    if ('arquivo_comprovantes' in request.files):
        arquivo_comprovantes = request.files['arquivo_comprovantes']
        if allowed_file(arquivo_comprovantes.filename):
            arquivo_comprovantes.filename = "Comprovantes_" + ultimo_id_str + "_" + str(siape) + "_" + codigo + ".pdf"
            filename = secure_filename(arquivo_comprovantes.filename)
            arquivo_comprovantes.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            caminho = str(app.config['UPLOAD_FOLDER'] + "/" + filename)
            consulta = "UPDATE editalProjeto SET arquivo_comprovantes=\"" + filename + "\" WHERE id=" + str(ultimo_id)
            atualizar(consulta)
            logging.debug("Arquivo COMPROVANTES cadastrado.")
        #elif not allowed_file(arquivo_comprovantes.filename):
    	#	return ("Arquivo de COMPROVANTES não permitido")
    else:
        logging.debug("Não foi incluído um arquivo de COMPROVANTES")

    #CADASTRAR AVALIADORES SUGERIDOS
    avaliador1_email = unicode(request.form['avaliador1_email'])
    if avaliador1_email!='':
        token = id_generator(40)
        consulta = "INSERT INTO avaliacoes (avaliador,token,idProjeto) VALUES (\"" + avaliador1_email + "\", \"" + token + "\", " + str(ultimo_id) + ")"
        atualizar(consulta)
        logging.debug("Avaliador 1 sugerido cadastrado.")

    avaliador2_email = unicode(request.form['avaliador2_email'])
    if avaliador2_email!='':
        token = id_generator(40)
        consulta = "INSERT INTO avaliacoes (avaliador,token,idProjeto) VALUES (\"" + avaliador2_email + "\", \"" + token + "\", " + str(ultimo_id) + ")"
        atualizar(consulta)
        logging.debug("Avaliador 2 sugerido cadastrado.")

    avaliador3_email = unicode(request.form['avaliador3_email'])
    if avaliador3_email!='':
        token = id_generator(40)
        consulta = "INSERT INTO avaliacoes (avaliador,token,idProjeto) VALUES (\"" + avaliador3_email + "\", \"" + token + "\", " + str(ultimo_id) + ")"
        atualizar(consulta)
        logging.debug("Avaliador 3 sugerido cadastrado.")

    #CALCULANDO scorelattes
    dados = [email,nome,titulo,descricao_resumida]
    t = threading.Thread(target=processarPontuacaoLattes,args=(cpf,area_capes,ultimo_id,dados,))
    t.start()
    #processarPontuacaoLattes(cpf,area_capes,ultimo_id,dados)
    return("Verifique a confirmação de sua submissão no e-mail, em alguns minutos. ESTA PÁGINA JÁ PODE SER FECHADA COM SEGURANÇA.")

@app.route("/score", methods=['GET', 'POST'])
def getScoreLattesFromFile():
    area_capes = unicode(request.form['area_capes'])
    idlattes = unicode(request.form['idlattes'])
    salvarCV(idlattes)
    arquivo = XML_DIR + idlattes + ".xml"
    try:
        from datetime import date
        ano_fim = date.today().year
        ano_inicio = ano_fim - 5
        s = calcularScoreLattes(1,area_capes,str(ano_inicio),str(ano_fim),arquivo)
        return(s)
    except:
        e = sys.exc_info()[0]
        logging.error("[SCORELATTES] Erro ao calcular o scorelattes.")
        logging.error(e)
        return("Erro ao calcular pontuacao! Favor, comunicar para o e-mail: atendimento.prpi@ufca.edu.br")

#Devolve os nomes dos arquivos do projeto e dos planos, caso existam
def getFiles(idProjeto):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
    conn.select_db('pesquisa')
    cursor  = conn.cursor()
    consulta = "SELECT arquivo_projeto,arquivo_plano1,arquivo_plano2 FROM editalProjeto WHERE id=" + idProjeto
    cursor.execute(consulta)
    linha = cursor.fetchone()
    conn.close()
    return(linha)

def naoEstaFinalizado(token):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
    conn.select_db('pesquisa')
    cursor  = conn.cursor()
    consulta = "SELECT finalizado FROM avaliacoes WHERE token=\"" + token + "\""
    cursor.execute(consulta)
    linha = cursor.fetchone()
    finalizado = int(linha[0])
    conn.close()
    if finalizado==0:
        return (True)
    else:
        return (False)

def podeAvaliar(idProjeto):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
    conn.select_db('pesquisa')
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

#Gerar pagina de avaliacao (testes) para o avaliador
@app.route("/testes", methods=['GET', 'POST'])
def getPaginaAvaliacaoTeste():
    arquivos = "TESTE"
    #msg = Message(subject = "Hello",recipients=["rafael.mota@ufca.edu.br"],body="teste...")
    #msg.body("Teste...")
    #mail.send(msg)
    return render_template('avaliacao.html',arquivos=arquivos)

#Gerar pagina de avaliacao para o avaliador
@app.route("/avaliacao", methods=['GET', 'POST'])
def getPaginaAvaliacao():
    if request.method == "GET":
        idProjeto = str(request.args.get('id'))
        if podeAvaliar(idProjeto): #Se ainda está no prazo para receber avaliações
            tokenAvaliacao = str(request.args.get('token'))
            arquivos = getFiles(idProjeto)
            if str(arquivos[0])!="0":
                link_projeto = SITE + str(arquivos[0])
            if str(arquivos[1])!="0":
                link_plano1 = SITE + str(arquivos[1])
            if str(arquivos[2])!="0":
                link_plano2 = SITE + str(arquivos[2])
            links = ""
            if 'link_projeto' in locals():
                links = links + "<a href=\"" + link_projeto + "\">PROJETO</a><BR>"
            if 'link_plano1' in locals():
                links = links + "<a href=\"" + link_plano1 + "\">PLANO DE TRABALHO 1</a><BR>"
            if 'link_plano2' in locals():
                links = links + "<a href=\"" + link_plano2 + "\">PLANO DE TRABALHO 2</a><BR>"
            links = links + "<input type=\"hidden\" id=\"token\" name=\"token\" value=\"" + tokenAvaliacao + "\">"
            links = Markup(links)
            if naoEstaFinalizado(tokenAvaliacao):
                consulta = "UPDATE avaliacoes SET aceitou=1 WHERE token=\"" + tokenAvaliacao + "\""
                atualizar(consulta)
                return render_template('avaliacao.html',arquivos=links)
            else:
                logging.debug("[AVALIACAO] Tentativa de reavaliar projeto")
                return("Projeto já foi avaliado! Não é possível modificar a avaliação!")
        else:
            return("Prazo de avaliação expirado!")
#Gravar avaliacao gerada pelo avaliador
@app.route("/avaliar", methods=['GET', 'POST'])
def enviarAvaliacao():
    if request.method == "POST":
        comentarios = unicode(request.form['txtComentarios'])
        recomendacao = str(request.form['txtRecomendacao'])
        nome_avaliador = unicode(request.form['txtNome'])
        token = str(request.form['token'])
        c1 = str(request.form['c1'])
        c2 = str(request.form['c2'])
        c3 = str(request.form['c3'])
        c4 = str(request.form['c4'])
        c5 = str(request.form['c5'])
        c6 = str(request.form['c6'])
        c7 = str(request.form['c7'])
        comite = str(request.form['comite'])
        try:
            consulta = "UPDATE avaliacoes SET recomendacao=" + recomendacao + " WHERE token=\"" + token + "\""
            atualizar(consulta)
            consulta = "UPDATE avaliacoes SET finalizado=1" + " WHERE token=\"" + token + "\""
            atualizar(consulta)
            consulta = "UPDATE avaliacoes SET data_avaliacao=CURRENT_TIMESTAMP()" + " WHERE token=\"" + token + "\""
            atualizar(consulta)
            consulta = "UPDATE avaliacoes SET nome_avaliador=\"" + nome_avaliador + "\"" + " WHERE token=\"" + token + "\""
            atualizar(consulta)
            comentarios = comentarios.replace('"',' ')
            comentarios = comentarios.replace("'"," ")
            consulta = "UPDATE avaliacoes SET comentario=\"" + comentarios + "\"" + " WHERE token=\"" + token + "\""
            atualizar(consulta)
            consulta = "UPDATE avaliacoes SET c1=" + c1 + " WHERE token=\"" + token + "\""
            atualizar(consulta)
            consulta = "UPDATE avaliacoes SET c2=" + c2 + " WHERE token=\"" + token + "\""
            atualizar(consulta)
            consulta = "UPDATE avaliacoes SET c3=" + c3 + " WHERE token=\"" + token + "\""
            atualizar(consulta)
            consulta = "UPDATE avaliacoes SET c4=" + c4 + " WHERE token=\"" + token + "\""
            atualizar(consulta)
            consulta = "UPDATE avaliacoes SET c5=" + c5 + " WHERE token=\"" + token + "\""
            atualizar(consulta)
            consulta = "UPDATE avaliacoes SET c6=" + c6 + " WHERE token=\"" + token + "\""
            atualizar(consulta)
            consulta = "UPDATE avaliacoes SET c7=" + c7 + " WHERE token=\"" + token + "\""
            atualizar(consulta)
            consulta = "UPDATE avaliacoes SET cepa=" + comite + " WHERE token=\"" + token + "\""
            atualizar(consulta)
        except:
            e = sys.exc_info()[0]
            logging.error(e)
            logging.error("[AVALIACAO] ERRO ao gravar a avaliação: " + token)
            return("Não foi possível gravar a avaliação. Favor entrar contactar pesquisa.prpi@ufca.edu.br.")
        data_agora = getData()
        consulta = "SELECT editais.id,editais.nome FROM editais,avaliacoes,editalProjeto WHERE avaliacoes.idProjeto=editalProjeto.id AND editalProjeto.tipo=editais.id AND avaliacoes.token=\"" + token + "\""
        linhas = consultar(consulta)
        for linha in linhas:
            descricaoEdital = unicode(linha[1])
        return(render_template('declaracao_avaliador.html',nome=nome_avaliador,data=data_agora,edital=descricaoEdital))
    else:
        return("OK")

## TODO: Revisar função abaixo
def descricaoEdital(codigoEdital):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
    conn.select_db('pesquisa')
    cursor  = conn.cursor()
    consulta = "SELECT id,nome FROM editais WHERE id=" + codigoEdital
    cursor.execute(consulta)
    linhas = cursor.fetchall()
    nomeEdital = "EDITAL NAO DEFINIDO"
    for linha in linhas:
        nomeEdital = unicode(linha[1])
    conn.close()
    return (nomeEdital)

#Gerar declaração do avaliador
@app.route("/declaracaoAvaliador", methods=['GET', 'POST'])
def getDeclaracaoAvaliador():
    if request.method == "GET":
        tokenAvaliacao = str(request.args.get('token'))
        consulta = "SELECT nome_avaliador FROM avaliacoes WHERE token=\"" + tokenAvaliacao + "\""
        linhas = consultar(consulta)
        nome_avaliador = "NAO INFORMADO"
        for linha in linhas:
            nome_avaliador = unicode(linha[0])
        data_agora = getData()
        #Recuperando descrição do edital
        consulta = "SELECT editais.id,editais.nome FROM editais,avaliacoes,editalProjeto WHERE avaliacoes.idProjeto=editalProjeto.id AND editalProjeto.tipo=editais.id AND avaliacoes.token=\"" + tokenAvaliacao + "\""
        linhas = consultar(consulta)
        for linha in linhas:
            descricaoEdital = unicode(linha[1])
        return(render_template('declaracao_avaliador.html',nome=nome_avaliador,data=data_agora,edital=descricaoEdital))
    else:
        return("OK")

def consultar(consulta):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
    conn.select_db('pesquisa')
    cursor  = conn.cursor()
    cursor.execute(consulta)
    linhas = cursor.fetchall()
    conn.close()
    return (linhas)

@app.route("/recusarConvite", methods=['GET', 'POST'])
def recusarConvite():
    if request.method == "GET":
        tokenAvaliacao = str(request.args.get('token'))
        consulta = "UPDATE avaliacoes SET aceitou=0 WHERE token=\"" + tokenAvaliacao + "\""
        atualizar(consulta)
        #SELECT editalProjeto.titulo,editalProjeto.nome FROM editalProjeto,avaliacoes WHERE editalProjeto.id=avaliacoes.idProjeto AND avaliacoes.token="DL7tueygfszlgqVc2V6HTgN7fSaDjsIPq7O2LpWT"
        #body = "O avaliador de token " + tokenAvaliacao + " recusou o convite de avaliacao."
        #enviarEmail("pesquisa.prpi@ufca.edu.br","[PIICT - RECUSA] Recusa de convite para avaliacao",body)
        return("Avaliação cancelada com sucesso. Agradecemos a atenção.")
    else:
        return("OK")

@app.route("/avaliacoesNegadas", methods=['GET', 'POST'])
def avaliacoesNegadas():
    if request.method == "GET":
        conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
        conn.select_db('pesquisa')
        cursor  = conn.cursor()
        if 'edital' in request.args:
            codigoEdital = str(request.args.get('edital'))
            if 'id' in request.args:
                idProjeto = str(request.args.get('id'))
                consulta = "SELECT resumoGeralAvaliacoes.id,CONCAT(SUBSTRING(resumoGeralAvaliacoes.titulo,1,80),\" - (\",resumoGeralAvaliacoes.nome,\" )\"),(resumoGeralAvaliacoes.aceites+resumoGeralAvaliacoes.rejeicoes) as resultado,resumoGeralAvaliacoes.indefinido FROM resumoGeralAvaliacoes WHERE ((aceites+rejeicoes<10) OR (aceites=rejeicoes)) AND tipo=" + codigoEdital + " AND id = " + idProjeto +" ORDER BY aceites+rejeicoes, id"
            else:
                consulta = "SELECT resumoGeralAvaliacoes.id,CONCAT(SUBSTRING(resumoGeralAvaliacoes.titulo,1,80),\" - (\",resumoGeralAvaliacoes.nome,\" )\"),(resumoGeralAvaliacoes.aceites+resumoGeralAvaliacoes.rejeicoes) as resultado,resumoGeralAvaliacoes.indefinido FROM resumoGeralAvaliacoes WHERE ((aceites+rejeicoes<2) OR (aceites=rejeicoes)) AND tipo=" + codigoEdital + " ORDER BY aceites+rejeicoes, id"
            try:
                cursor.execute(consulta)
                linha = cursor.fetchall()
                total = cursor.rowcount
                conn.close()
                return(render_template('inserirAvaliador.html',listaProjetos=linha,totalDeLinhas=total,codigoEdital=codigoEdital))
            except:
                e = sys.exc_info()[0]
                logging.error(e)
                logging.error(consulta)
                conn.close()
                return(consulta)
        else:
            return ("OK")
    else:
        return("OK")

@app.route("/inserirAvaliador", methods=['GET', 'POST'])
def inserirAvaliador():
    if request.method == "POST":
        token = id_generator(40)
        idProjeto = int(request.form['txtProjeto'])
        avaliador1_email = str(request.form['txtEmail'])
        consulta = "INSERT INTO avaliacoes (aceitou,avaliador,token,idProjeto) VALUES (-1,\"" + avaliador1_email + "\", \"" + token + "\", " + str(idProjeto) + ")"
        atualizar(consulta)
        t = threading.Thread(target=enviarPedidoAvaliacao,args=(idProjeto,))
        t.start()
        return("Avaliador cadastrado com sucesso.")
    else:
        return("OK")

#Retorna a quantidade de linhas da consulta
def quantidades(consulta):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
    conn.select_db('pesquisa')
    cursor  = conn.cursor()
    cursor.execute(consulta)
    total = cursor.rowcount
    conn.close()
    return (total)

## TODO: Finalizar as estatisticas - Projetos aprovados devem ser vir da tabela editalProjeto
@app.route("/estatisticas", methods=['GET', 'POST'])
def estatisticas():
    if request.method == "GET":
        codigoEdital = str(request.args.get('edital'))
        #Resumo Geral
        consulta = "SELECT * FROM resumoGeralAvaliacoes WHERE tipo=" + codigoEdital + " ORDER BY ua, score DESC"
        conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
        conn.select_db('pesquisa')
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
            edital=u"CÓDIGO DE EDITAL INVÁLIDO"
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

'''
demanda: Quantidade de bolsas por unidade academica
dados: projetos ordenados por Unidade Academica e Lattes
'''
def distribuir_bolsas(demanda,dados):
    ## TODO: Incluir condição de cruzamento de dados
    '''
    Lista de quem tem 2 bolsas PIBIC, e não pode ganhar mais nenhuma bolsa!
    SELECT tipo,id,titulo,ua,nome FROM resumoGeralClassificacao WHERE resumoGeralClassificacao.tipo=1 AND resumoGeralClassificacao.siape IN (SELECT siape FROM edital02_2018 WHERE situacao="ATIVO" and modalidade="PIBIC" GROUP BY siape HAVING count(id)=2 ORDER BY ua,orientador)

    BOLSAS PIBIC POR ORIENTADOR
    SELECT siape,orientador,count(id),situacao FROM edital02_2018 WHERE situacao="ATIVO" and modalidade="PIBIC" GROUP BY siape HAVING count(id)=2 ORDER BY orientador;

    QUEM TEM BOLSA CONCEDIDA, MAS NÃO PODE TER!
    SELECT id,ua,nome,siape FROM resumoGeralClassificacao WHERE tipo=1 AND bolsas_concedidas>=1 AND siape IN (SELECT siape FROM resumoGeralClassificacao WHERE resumoGeralClassificacao.tipo=1 AND resumoGeralClassificacao.siape IN (SELECT siape FROM edital02_2018 WHERE situacao="ATIVO" and modalidade="PIBIC" GROUP BY siape HAVING count(id)=2 ORDER BY ua,orientador)) ORDER BY ua,nome

    '''
    #Iniciando a distribuição
    continua = True
    while (continua):
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
                        consulta = "UPDATE editalProjeto SET obs=\"BOLSA CONCEDIDA\" WHERE id=" + str(idProjeto)
                        atualizar(consulta)
                    else: #Se o orientador estiver com a cota estourada
                        consulta = "UPDATE editalProjeto SET obs=\"BOLSA NÃO CONCEDIDA. ORIENTADOR NÃO PODE ULTRASSAR A COTA DE 2 BOLSISTAS POR MODALIDADE (Anexo XIV da Res. 01/2014/CONSUP, Art. 7 Inciso I)\" WHERE id=" + str(idProjeto)
                        atualizar(consulta)
            else: # se a unidade não tem mais bolsas disponíveis em sua cota
                consulta = "UPDATE editalProjeto SET obs=\"BOLSA NÃO CONCEDIDA. COTA DA UNIDADE ZERADA (Anexo XIV da Res. 01/2014/CONSUP, Art. 7 Inciso II)\" WHERE id=" + str(idProjeto)
                atualizar(consulta)
        ## TODO: Ver abaixo
        #Verificar se ainda tem bolsas disponíveis para redistribuir dentro das unidades
        continua = False

def executarSelect(consulta,tipo=0):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
    conn.select_db('pesquisa')
    cursor  = conn.cursor()
    try:
        cursor.execute(consulta)
        total = cursor.rowcount
        if (tipo==0): #Retorna todas as linhas
            resultado = cursor.fetchall()
        else: #Retorna uma única linha
            resultado = cursor.fetchone()
        return (resultado,total)
    except:
        e = sys.exc_info()[0]
        logging.error(e)
        logging.error("ERRO Na função executarSelect. Ver consulta abaixo.")
        logging.error(consulta)
    finally:
        cursor.close()
        conn.close()


def avaliacoesEncerradas(codigoEdital):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
    conn.select_db('pesquisa')
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
@auth.login_required
def resultados():
    if request.method == "GET":

        #Recuperando o código do edital
        codigoEdital = str(request.args.get('edital'))

        #Recuperando o Resumo Geral
        consulta = "SELECT * FROM resumoGeralClassificacao WHERE tipo=" + codigoEdital + " ORDER BY ua, score DESC"
        conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
        conn.select_db('pesquisa')
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
                logging.debug(data_final_avaliacoes)
                qtde_bolsas = int(linha[2])
                mensagem = unicode(linha[3])
                recursos = str(linha[4])
                link = str(linha[5])
        else:
            edital=u"CÓDIGO DE EDITAL INVÁLIDO"
        qtde_bolsas = str(qtde_bolsas)

        #Recuperando total de projetos: total_projetos e calculando total de bolsas por unidade
        total_projetos = str(quantidades("SELECT id FROM resumoGeralClassificacao WHERE tipo=" + codigoEdital))
        bolsas_disponiveis = "round((count(id)/" + total_projetos + ")*" + qtde_bolsas + ") "

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
        distribuir_bolsas(unidades,resumoGeral)

        ## TODO: Redistribuir bolsas remanescentes baseado na classificação geral pelo lattes

        #Recalculando resumoGeral após distribuição
        consulta = "SELECT * FROM resumoGeralClassificacao WHERE tipo=" + codigoEdital + " ORDER BY ua, score DESC"
        resumoGeral,total = executarSelect(consulta)

        #Total de bolsas distribuídas por unidade academica
        consulta = "SELECT ua,sum(bolsas) as solicitadas, sum(bolsas_concedidas) as concedidas,(sum(bolsas_concedidas)/sum(bolsas))*100 as percentual FROM resumoGeralClassificacao WHERE tipo=" + codigoEdital + " GROUP BY ua ORDER BY ua"
        cursor.execute(consulta)
        somatorios = cursor.fetchall()

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

'''
Retorna uma coluna de uma linha única dado uma chave primária
'''
def obterColunaUnica(tabela,coluna,colunaId,valorId):
    conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
    conn.select_db('pesquisa')
    cursor  = conn.cursor()
    consulta = "SELECT " + coluna + " FROM " + tabela + " WHERE " + colunaId + "=" + valorId
    resultado = "0"
    try:
        cursor.execute(consulta)
        linhas = cursor.fetchall()
        for linha in linhas:
            resultado = unicode(linha[0])
        return(resultado)
    except:
        e = sys.exc_info()[0]
        logging.error(e)
        logging.error("ERRO Na função obtercolunaUnica. Ver consulta abaixo.")
        logging.error(consulta)
    finally:
        cursor.close()
        conn.close()

def gerarGraficos(demandas,grafico1,grafico2,rotacao=0):
    #import matplotlib
    #matplotlib.use('Agg')
    #import matplotlib.pyplot as plt
    unidades = []
    fatias = []
    for linha in demandas:
        unidades.append(unicode(linha[0]))
        fatias.append(float(linha[1]))

    fig1,ax1 = plt.subplots()
    ax1.pie(fatias,labels=unidades,autopct='%1.1f%%',shadow=True,startangle=90)
    ax1.axis('equal')
    plt.savefig(PLOTS_DIR + grafico1)

    plt.clf()
    y_pos = np.arange(len(unidades))
    bars = plt.bar(y_pos, fatias)
    for bar in bars:
        yval = bar.get_height()
        plt.text(bar.get_x(), yval + .005, int(yval),fontweight='bold')
    plt.xticks(y_pos, unidades,rotation=rotacao)
    plt.savefig(PLOTS_DIR + grafico2, bbox_inches = "tight")
    plt.close('all')

def gerarPDF(template):
    logging.debug(type(template))
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
        logging.error(e)
        logging.error("ERRO Na função gerarPDF")
    #return send_from_directory(app.config['TEMP_FOLDER'], 'resultados.pdf')

@app.route("/editalProjeto", methods=['GET', 'POST'])
def editalProjeto():
    
    if (autenticado() and int(session['permissao'])==0):
        if request.method == "GET":
            #Recuperando o código do edital
            if 'edital' in request.args:
                codigoEdital = str(request.args.get('edital'))
                session['edital'] = codigoEdital
                conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
                conn.select_db('pesquisa')
                cursor  = conn.cursor()
                tipo_classificacao = int(obterColunaUnica("editais","classificacao","id",codigoEdital))
                #ORDENA DE ACORDO COM O TIPO DE CLASSIFICAÇÃO: 1 - POR UA; 2 - POR LATTES
                if (tipo_classificacao==1):
                    consulta = "SELECT id,tipo,categoria,nome,email,ua,scorelattes,titulo,arquivo_projeto,arquivo_plano1,arquivo_plano2,arquivo_lattes_pdf,arquivo_comprovantes,DATE_FORMAT(data,\"%d/%m/%Y - %H:%i\") as data,DATE_FORMAT(inicio,\"%d/%m/%Y\") as inicio,DATE_FORMAT(fim,\"%d/%m/%Y\") as fim,if(produtividade=0,\"PROD. CNPq\",if(produtividade=1,\"BPI FUNCAP\",\"NORMAL\")) as prioridade,bolsas,bolsas_concedidas,obs FROM editalProjeto WHERE tipo=" + codigoEdital + " AND valendo=1 ORDER BY ua,produtividade,scorelattes,nome DESC"
                else:
                    consulta = "SELECT id,tipo,categoria,nome,email,ua,scorelattes,titulo,arquivo_projeto,arquivo_plano1,arquivo_plano2,arquivo_lattes_pdf,arquivo_comprovantes,DATE_FORMAT(data,\"%d/%m/%Y - %H:%i\") as data,DATE_FORMAT(inicio,\"%d/%m/%Y\") as inicio,DATE_FORMAT(fim,\"%d/%m/%Y\") as fim,if(produtividade=0,\"PROD. CNPq\",if(produtividade=1,\"BPI FUNCAP\",\"NORMAL\")) as prioridade,bolsas,bolsas_concedidas,obs FROM editalProjeto WHERE tipo=" + codigoEdital + " AND valendo=1 ORDER BY produtividade,scorelattes,nome DESC"
                consulta_novos = """SELECT editalProjeto.id,nome,ua,titulo,arquivo_projeto,
                GROUP_CONCAT(avaliacoes.avaliador ORDER BY avaliador SEPARATOR '<BR>') as avaliadores,
                GROUP_CONCAT(IF(avaliacoes.recomendacao=1,'RECOMENDADO',IF(avaliacoes.recomendacao=0,'***NÃO RECOMENDADO***','EM AVALIAÇÃO')) ORDER BY avaliador SEPARATOR '<BR>') as recomendacoes, 
                GROUP_CONCAT(avaliacoes.enviado ORDER BY avaliador SEPARATOR '<BR>') as enviado,
                GROUP_CONCAT(IF(avaliacoes.aceitou=1,'ACEITOU',IF(avaliacoes.aceitou=0,'REJEITOU','NÃO RESPONDEU')) ORDER BY avaliador SEPARATOR '<BR>') as aceitou,
                sum(avaliacoes.finalizado) as finalizados,sum(if(recomendacao=-1,1,0)), 
                sum(if(recomendacao=0,1,0)),sum(if(recomendacao=1,1,0)),palavras"""
                consulta_novos = consulta_novos + """ FROM editalProjeto,avaliacoes WHERE tipo=""" + codigoEdital + """ 
                AND valendo=1 AND categoria=1 
                AND editalProjeto.id=avaliacoes.idProjeto GROUP BY editalProjeto.id 
                ORDER BY finalizados,editalProjeto.ua,editalProjeto.id"""
                demanda = """SELECT ua,count(id) FROM editalProjeto WHERE valendo=1 and tipo=""" + codigoEdital + """ GROUP BY ua 
                ORDER BY ua"""
                demanda_bolsas = """SELECT ua,sum(bolsas) FROM editalProjeto 
                WHERE valendo=1 and tipo=""" + codigoEdital + """ GROUP BY ua ORDER BY ua"""
                bolsas_ufca = int(obterColunaUnica("editais","quantidade_bolsas","id",codigoEdital))
                bolsas_cnpq = int(obterColunaUnica("editais","quantidade_bolsas_cnpq","id",codigoEdital))
                situacaoProjetosNovos = """SELECT if(situacao=1,"APROVADO",if(situacao=-1,"INDEFINIDO","NÃO APROVADO")) as situacaoD,count(id) FROM resumoProjetosNovos WHERE
                tipo=""" + codigoEdital + """ GROUP BY situacao ORDER BY situacao"""
                respostaAvaliadores = """ SELECT if(aceitou=1,"ACEITOU AVALIAR",if(aceitou=-1,"NÃO RESPONDEU","NÃO ACEITOU AVALIAR")) as resposta,count(avaliacoes.id) FROM avaliacoes,editalProjeto WHERE editalProjeto.id=avaliacoes.idProjeto AND
                tipo=""" + codigoEdital + """ AND valendo=1 AND categoria=1 GROUP BY aceitou"""
                dadosAvaliacoes = """SELECT if(finalizado=1,"FINALIZADO","EM AVALIAÇÃO/NÃO SINALIZOU") as finalizados,count(avaliacoes.id) FROM avaliacoes,editalProjeto WHERE editalProjeto.id=avaliacoes.idProjeto AND
                tipo=""" + codigoEdital + """ AND valendo=1 and categoria=1 AND aceitou!=0 GROUP BY finalizado"""
                dadosScoreLattes = """SELECT ua, ROUND(AVG(scorelattes)) as media FROM editalProjeto WHERE valendo=1 AND
                tipo=""" + codigoEdital + """ GROUP BY ua ORDER BY media"""
                dadosScoreLattesArea = """SELECT SUBSTRING(area_capes,1,30) as area, ROUND(AVG(scorelattes)) as media FROM editalProjeto WHERE valendo=1 AND
                tipo=""" + codigoEdital + """ GROUP BY area_capes ORDER BY area"""
                tempoAvaliacao = """SELECT TIMESTAMPDIFF(DAY,data_envio,data_avaliacao) as tempo,count(avaliacoes.id) total FROM avaliacoes,editalProjeto WHERE editalProjeto.id=avaliacoes.idProjeto AND valendo=1 and
                tipo=""" + codigoEdital + """ and finalizado=1 GROUP BY TIMESTAMPDIFF(DAY,data_envio,data_avaliacao)"""
                oferta_demanda = """(select "OFERTA", sum(quantidade_bolsas)+sum(quantidade_bolsas_cnpq) AS C2 FROM editais WHERE
                id=""" + codigoEdital + """) UNION (SELECT "DEMANDA", sum(bolsas) FROM editalProjeto WHERE valendo=1 and tipo=""" + codigoEdital + """)"""
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
                    cursor.execute(demanda_bolsas)
                    linhas_demanda_bolsas = cursor.fetchall()
                    cursor.execute(situacaoProjetosNovos)
                    dadosProjetosNovos = cursor.fetchall()
                    cursor.execute(respostaAvaliadores)
                    linhasRespostasAvaliadores = cursor.fetchall()
                    cursor.execute(dadosAvaliacoes)
                    linhasAvaliacoes = cursor.fetchall()
                    cursor.execute(dadosScoreLattes)
                    linhasScoreLattes = cursor.fetchall()
                    cursor.execute(dadosScoreLattesArea)
                    linhasScoreLattesArea = cursor.fetchall()
                    cursor.execute(tempoAvaliacao)
                    linhasTempoAvaliacao = cursor.fetchall()
                    cursor.execute(oferta_demanda)
                    linhas_oferta_demanda = cursor.fetchall()
                    if 'resultado' not in request.args:
                        gerarGraficos(linhas_demanda,"grafico-demanda.png","grafico-demanda-2.png")
                        gerarGraficos(linhas_oferta_demanda,"grafico-oferta-demanda.png","grafico-oferta-demanda-2.png")
                        gerarGraficos(linhas_demanda_bolsas,"grafico-demanda-bolsas-1.png","grafico-demanda-bolsas-2.png")
                        gerarGraficos(dadosProjetosNovos,"grafico-novos1.png","grafico-novos2.png")
                        gerarGraficos(linhasRespostasAvaliadores,"grafico-avaliadores1.png","grafico-avaliadores2.png")
                        gerarGraficos(linhasAvaliacoes,"grafico-avaliacoes1.png","grafico-avaliacoes2.png")
                        gerarGraficos(linhasScoreLattes,"grafico-score1.png","grafico-score2.png")
                        gerarGraficos(linhasScoreLattesArea,"grafico-scoreArea1.png","grafico-scoreArea2.png",90)
                        gerarGraficos(linhasTempoAvaliacao,"grafico-tempoAvaliacao1.png","grafico-tempoAvaliacao2.png")
                    if 'resultado' in request.args:
                        if 'pdf' in request.args:
                            mensagem = unicode(obterColunaUnica("editais","mensagem","id",codigoEdital))
                            gerarPDF(render_template('editalProjeto.html',listaProjetos=linhas,descricao=descricao,total=total,novos=linhas_novos,total_novos=total_novos,linhas_demanda=linhas_demanda,bolsas_ufca=bolsas_ufca,bolsas_cnpq=bolsas_cnpq,codigoEdital=codigoEdital,resultado=1,mensagem=mensagem))
                            return(send_from_directory(app.config['TEMP_FOLDER'], 'resultados.pdf'))

                        else:
                            mensagem = unicode(obterColunaUnica("editais","mensagem","id",codigoEdital))
                            return(render_template('editalProjeto.html',listaProjetos=linhas,descricao=descricao,total=total,novos=linhas_novos,total_novos=total_novos,linhas_demanda=linhas_demanda,bolsas_ufca=bolsas_ufca,bolsas_cnpq=bolsas_cnpq,codigoEdital=codigoEdital,resultado=1,mensagem=mensagem))
                    else:
                        mensagem = ""
                        return(render_template('editalProjeto.html',listaProjetos=linhas,descricao=descricao,total=total,novos=linhas_novos,total_novos=total_novos,linhas_demanda=linhas_demanda,bolsas_ufca=bolsas_ufca,bolsas_cnpq=bolsas_cnpq,codigoEdital=codigoEdital,resultado=0))
                except:
                    e = sys.exc_info()[0]
                    logging.error(e)
                    logging.error("ERRO Na função /editalProjeto. Ver consulta abaixo.")
                    logging.error(consulta)
                    return("ERRO!")
                finally:
                    cursor.close()
                    conn.close()

            else:
                return ("OK")
    else:
        return(render_template('login.html',mensagem=u"É necessário autenticação para acessar a página solicitada"))

@app.route("/lattesDetalhado", methods=['GET', 'POST'])
def lattesDetalhado():
    if request.method == "GET":
        #Recuperando o código do projeto
        if 'id' in request.args:
            idProjeto = str(request.args.get('id'))
            conn = MySQLdb.connect(host=MYSQL_DB, user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
            conn.select_db('pesquisa')
            cursor  = conn.cursor()
            consulta = "SELECT id,scorelattes_detalhado FROM editalProjeto WHERE id=" + idProjeto + " AND valendo=1"
            cursor.execute(consulta)
            linhas = cursor.fetchall()
            texto = "INDISPONIVEL"
            for linha in linhas:
                lattes_detalhado = unicode(linha[1])
                if lattes_detalhado!="":
                    texto = lattes_detalhado
            conn.close()
            return(texto)
        else:
            return ("OK")


@app.route("/declaracoesPorServidor", methods=['GET', 'POST'])
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
                logging.error(e)
                logging.error("ERRO Na função /declaracoesPorServidor. Ver consulta abaixo.")
                logging.error(consulta)
                return("ERRO!")
        else:
            return("OK")
    else:
        return("OK")

@app.route("/declaracaoEvento", methods=['GET', 'POST'])
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
                return(u"Nenhuma declaração encontrada.")
        else:
            return ("OK")

@app.route("/meusProjetos", methods=['GET', 'POST'])
def meusProjetos():
    if autenticado():
        gravando = "INSERT INTO acessos (username) VALUES ('" + str(session['username']) + "')"
        atualizar(gravando)
        ## TODO: CORRIGIR LISTA DE ORIENTANDO. TEM Q USAR GROUP CONCAT
        #consulta = """SELECT id,nome_do_coordenador,orientador_lotacao,titulo_do_projeto,DATE_FORMAT(inicio,'%d/%m/%Y') as inicio,DATE_FORMAT(termino,'%d/%m/%Y') as fim,GROUP_CONCAT(estudante_nome_completo SEPARATOR '<BR><BR>\n') as estudantes,token FROM cadastro_geral WHERE siape='""" + str(session['username']) + """' GROUP BY titulo_do_projeto ORDER BY inicio"""
        consulta = """SELECT id,nome_do_coordenador,orientador_lotacao,titulo_do_projeto,DATE_FORMAT(inicio,'%d/%m/%Y') as inicio,DATE_FORMAT(termino,'%d/%m/%Y') as fim,estudante_nome_completo,token FROM cadastro_geral WHERE siape='""" + str(session['username']) + """' ORDER BY inicio,titulo_do_projeto"""
        projetos,total = executarSelect(consulta)

        consulta_outros = """SELECT editalProjeto.id,editais.nome,editalProjeto.nome,ua,titulo,DATE_FORMAT(inicio,'%d/%m/%Y') as inicio,DATE_FORMAT(fim,'%d/%m/%Y') as fim,categoria,arquivo_projeto,
        (SELECT COUNT(recomendacao) FROM `avaliacoes` WHERE finalizado=1 AND recomendacao=1 AND idProjeto=editalProjeto.id) as aprovados,
        (SELECT COUNT(recomendacao) FROM `avaliacoes` WHERE finalizado=1 AND recomendacao=0 AND idProjeto=editalProjeto.id) as reprovados,bolsas,bolsas_concedidas,categoria,editais.situacao,editais.id,
        (SELECT GROUP_CONCAT(CONCAT('(',id,') - ',nome,' (',IF(tipo_de_vaga=0,'VOLUNTARIO(A)','BOLSISTA'),')',' (',IF(situacao=0,'OK',IF(situacao=1,'DESLIGADO(A)','SUBSTITUIDO(A)')), ')') ORDER BY nome SEPARATOR '<BR><BR>') FROM indicacoes WHERE idProjeto=editalProjeto.id GROUP BY idProjeto) as orientandos
         FROM editalProjeto,editais WHERE valendo=1 AND editalProjeto.tipo=editais.id AND siape=""" + str(session['username']) + """ ORDER BY editalProjeto.data """
        projetos2019,total2019 = executarSelect(consulta_outros)

        consulta_orientandos_atuais = """SELECT indicacoes.id,indicacoes.nome,DATE_FORMAT(indicacoes.inicio,'%d/%m/%Y'),IF(indicacoes.fomento=0,'UFCA',IF(indicacoes.fomento=1,'CNPq','FUNCAP')),IF(indicacoes.tipo_de_vaga=0,'VOLUNTÁRIO','BOLSISTA'),DATE_FORMAT(indicacoes.fim,'%d/%m/%Y'),IF(indicacoes.modalidade=1,'PIBIC',IF(indicacoes.modalidade=2,'PIBITI','PIBIC-EM')),
        (SELECT GROUP_CONCAT(CONCAT_WS('/',mes,ano) SEPARATOR '<BR><BR>') FROM frequencias WHERE frequencias.idIndicacao=indicacoes.id) as enviadas, editalProjeto.titulo
        FROM indicacoes,editalProjeto
        WHERE editalProjeto.id=indicacoes.idProjeto AND indicacoes.fim>NOW() AND editalProjeto.siape=""" + str(session['username']) + """ ORDER BY indicacoes.tipo_de_vaga,editalProjeto.titulo,indicacoes.nome """
        orientandos_atuais,totalOrientandos = executarSelect(consulta_orientandos_atuais)

        consulta_orientandos_antigos = """SELECT indicacoes.id,indicacoes.nome,DATE_FORMAT(indicacoes.inicio,'%d/%m/%Y'),IF(indicacoes.fomento=0,'UFCA',IF(indicacoes.fomento=1,'CNPq','FUNCAP')),IF(indicacoes.tipo_de_vaga=0,'VOLUNTÁRIO','BOLSISTA'),DATE_FORMAT(indicacoes.fim,'%d/%m/%Y'),IF(indicacoes.modalidade=1,'PIBIC',IF(indicacoes.modalidade=2,'PIBITI','PIBIC-EM')),
        (SELECT GROUP_CONCAT(CONCAT_WS('/',mes,ano) SEPARATOR '<BR><BR>') FROM frequencias WHERE frequencias.idIndicacao=indicacoes.id) as enviadas, editalProjeto.titulo
        FROM indicacoes,editalProjeto
        WHERE editalProjeto.id=indicacoes.idProjeto AND indicacoes.fim<NOW() AND editalProjeto.siape=""" + str(session['username']) + """ ORDER BY indicacoes.tipo_de_vaga,editalProjeto.titulo,indicacoes.nome """
        orientandos_antigos,totalOrientandosAntigos = executarSelect(consulta_orientandos_antigos)

        consulta_frequencias = ""

        return(render_template('meusProjetos.html',projetos=projetos,total=total,projetos2019=projetos2019,total2019=total2019,permissao=session['permissao'],orientandos=orientandos_atuais,orientandos_antigos=orientandos_antigos))
    else:
        return(render_template('login.html',mensagem=u"É necessário autenticação para acessar a página solicitada"))

@app.route("/minhaDeclaracaoOrientador", methods=['GET', 'POST'])
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
                    DATE_FORMAT(indicacoes.inicio,'%d/%m/%Y') as inicio,DATE_FORMAT(indicacoes.fim,'%d/%m/%Y') as fim,
                    (SELECT GROUP_CONCAT(indicacoes.nome ORDER BY indicacoes.nome SEPARATOR ', ') from indicacoes WHERE indicacoes.idProjeto=editalProjeto.id GROUP BY indicacoes.idProjeto) as indicados,
                    editalProjeto.id,if(indicacoes.fim<NOW(),"exerceu","exerce") as verbo
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
                    return("Em construcao...")
                else:

                    return("id nao informado")
        else:
            return("OK")
    else:
        return(render_template('login.html',mensagem=u"É necessário autenticação para acessar a página solicitada"))

@app.route("/discente/minhaDeclaracao", methods=['GET', 'POST'])
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
def meusPareceres():
    if request.method == "GET":
        #Recuperando o id do Projeto
        if 'id' in request.args:
            idProjeto = str(request.args.get('id'))
            if autenticado():
                tituloProjeto = unicode(obterColunaUnica("editalProjeto","titulo","id",idProjeto))
                if ('todos' in request.args) and (session['permissao']==0):
                    consulta = """SELECT avaliacoes.id,c1,c2,c3,c4,c5,c6,c7,(c1+c2+c3+c4+c5+c6+c7) as pontuacaoTotal, comentario, if(recomendacao=1,'RECOMENDADO','NÃO RECOMENDADO') as recomendacao, cepa,DATE_FORMAT(data_avaliacao,'%d/%m/%Y') FROM avaliacoes WHERE finalizado=1 AND idProjeto=""" + idProjeto + """ ORDER BY data_avaliacao"""
                else:
                    consulta = """SELECT avaliacoes.id,c1,c2,c3,c4,c5,c6,c7,(c1+c2+c3+c4+c5+c6+c7) as pontuacaoTotal, comentario, if(recomendacao=1,'RECOMENDADO','NÃO RECOMENDADO') as recomendacao, cepa,DATE_FORMAT(data_avaliacao,'%d/%m/%Y') FROM avaliacoes,editalProjeto WHERE editalProjeto.id=avaliacoes.idProjeto AND finalizado=1 AND idProjeto=""" + idProjeto + """ AND siape=""" + str(session['username']) + """ ORDER BY data_avaliacao"""
                pareceres,total = executarSelect(consulta)
                return(render_template('meusPareceres.html',linhas=pareceres,total=total,titulo=tituloProjeto))
            else:
                return(render_template('login.html',mensagem=u"É necessário autenticação para acessar a página solicitada"))
        else:
            return("OK")
    else:
        return("OK")

@app.route("/usuario", methods=['GET', 'POST'])
def usuario():
    if autenticado():
        if (session['permissao']==0):
            return(redirect(url_for('admin')))
        else:
            return(redirect(url_for('meusProjetos')))
    else:
        return(render_template('login.html',mensagem=''))

'''
Método que ativa a sessão com os dados do usuário
'''
@app.route("/login", methods=['POST'])
def login():
    if request.method == "POST":
        if (('siape' in request.form) and ('senha' in request.form)):
            siape = str(request.form['siape'])
            senha = str(request.form['senha'])
            if verify_password(siape,senha):
                return(redirect(url_for('usuario')))
            else:
                return(render_template('login.html',mensagem='Problemas com o usuario/senha.'))
        else:
            return(render_template('login.html',mensagem='Problemas com o usuario/senha.'))
    else:
        return(render_template('login.html',mensagem=''))

@app.route("/esqueciMinhaSenha", methods=['GET', 'POST'])
def esqueciMinhaSenha():
    return(render_template('esqueciMinhaSenha.html'))

@app.route("/enviarMinhaSenha", methods=['GET', 'POST'])
def enviarMinhaSenha():
    if request.method == "POST":
        if ('email' in request.form):
            email = unicode(request.form['email'])
            #ENVIAR E-MAIL
            consulta = """SELECT username,password FROM users WHERE email='""" + email + """' """
            linhas,total = executarSelect(consulta,1)

            if (total>0):
                usuario = unicode(linhas[0])
                senha = unicode(linhas[1])

                #logging.debug(senha)
                #logging.debug(usuario)
                texto_mensagem = "Usuario: " + usuario + "\nSenha: " + senha + "\n" + USUARIO_SITE
                msg = Message(subject = "Plataforma Yoko - Lembrete de senha",recipients=[email],body=texto_mensagem)
                mail.send(msg)
                return(render_template('login.html',mensagem='Senha enviada para o email: ' + email))
            else:
                return(render_template('login.html',mensagem=u'E-mail não cadastrado. Envie e-mail para atendimento.prpi@ufca.edu.br para solicitar sua senha.'))
        else:
            return("OK")
    else:
        return("OK")

@app.route("/logout", methods=['GET', 'POST'])
def encerrarSessao():
    logout()
    return(render_template('login.html',mensagem=''))

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
                    ua = unicode(linha[0])
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

@app.route("/efetivarIndicacao", methods=['GET', 'POST'])
def efetivarIndicacao():
    if request.method == "POST":
        try:
            idProjeto = str(request.form['idProjeto'])
            vaga = int(request.form['vaga'])
            substituicao = int(request.form['substituicao'])
            substituido = int(request.form['substituido'])
            if ( ( (vaga==1)  and (podeIndicarBolsistas(idProjeto)) ) or ( (vaga==0)  and (podeIndicarVoluntarios(idProjeto)) ) or ( (vaga==0)  and (podeIndicarVoluntariosAdicionais(idProjeto)) ) ) or (substituicao==1):
                nome = unicode(request.form['nome'])
                fomento = int(request.form['fomento'])
                nascimento = str(request.form['nasc'])
                estado_civil = int(request.form['estado_civil'])
                sexo = int(request.form['sexo'])
                rg = unicode(request.form['rg'])
                orgao = unicode(request.form['orgao'])
                uf = unicode(request.form['uf'])
                cpf = unicode(request.form['cpf'])
                vaga = int(request.form['vaga'])
                modalidade = int(request.form['modalidade'])
                curso = unicode(request.form['curso'])
                matricula = unicode(request.form['matricula'])
                ingresso = int(request.form['ingresso'])
                lattes = unicode(request.form['lattes'])
                banco = ""
                agencia = ""
                conta = ""
                if vaga==0:
                    banco = "N/A"
                    agencia = "N/A"
                    conta = "N/A"
                else:
                    banco = unicode(request.form['banco'])
                    agencia = unicode(request.form['agencia'])
                    conta = unicode(request.form['conta'])
                telefone = unicode(request.form['tel_fixo'])
                celular = unicode(request.form['tel_cel'])
                email = unicode(request.form['email'])
                endereco = unicode(request.form['endereco'])
                escola = unicode(request.form['escola'])
                conclusao = int(request.form['conclusao'])

                nomeDoArquivoTermo = ""
                if 'termo' in request.files:
                    token = id_generator()
                    nomeDoArquivoTermo = "TERMO." + idProjeto + "." + token + ".pdf"
                    filename = anexos.save(request.files['termo'],name=nomeDoArquivoTermo)

                nomeDoArquivoRg = ""
                if 'rg_cpf' in request.files:
                    token = id_generator()
                    nomeDoArquivoRg = "RG_CPF." + idProjeto + "." + token + ".pdf"
                    filename = anexos.save(request.files['rg_cpf'],name=nomeDoArquivoRg)

                nomeDoArquivoExtrato = ""
                if 'extrato' in request.files:
                    token = id_generator()
                    nomeDoArquivoExtrato = "EXTRATO." + idProjeto + "." + token + ".pdf"
                    filename = anexos.save(request.files['extrato'],name=nomeDoArquivoExtrato)

                nomeDoArquivoHistorico = ""
                if 'historico' in request.files:
                    token = id_generator()
                    nomeDoArquivoHistorico = "HISTORICO." + idProjeto + "." + token + ".pdf"
                    filename = anexos.save(request.files['historico'],name=nomeDoArquivoHistorico)

                nomeDoArquivoPlano = "N/A"
                if 'plano' in request.files:
                    token = id_generator()
                    nomeDoArquivoPlano = "PLANO." + idProjeto + "." + token + ".pdf"
                    filename = anexos.save(request.files['plano'],name=nomeDoArquivoPlano)

                codigoEdital = obterColunaUnica('editalProjeto','tipo','id',idProjeto)
                if (substituicao==1):
                    inicio = timestamp()
                else:
                    inicio = obterColunaUnica('editais','discente_inicio','id',str(codigoEdital))
                fim = obterColunaUnica('editais','discente_fim','id',str(codigoEdital))

                consulta = """INSERT INTO indicacoes (idProjeto,nome,nascimento,estado_civil,sexo,rg,orgao_emissor,uf,
                cpf,tipo_de_vaga,modalidade,curso,matricula,ano_de_ingresso,lattes,nome_banco,agencia,conta,telefone,celular,
                email,endereco,escola,ano_conclusao,arquivo_cpf_rg,arquivo_extrato,arquivo_historico,arquivo_termo,inicio,fim,arquivo_plano,substituido,fomento)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) """
                valores = (int(idProjeto),nome,nascimento,estado_civil,sexo,rg,orgao,uf,cpf,vaga,modalidade,curso,matricula,ingresso,lattes,banco,agencia,conta,telefone,celular,email,endereco,escola,conclusao,nomeDoArquivoRg,nomeDoArquivoExtrato,nomeDoArquivoHistorico,nomeDoArquivoTermo,inicio,fim,nomeDoArquivoPlano,substituido,fomento)
                inserir(consulta,valores)
                getID = "SELECT id FROM indicacoes WHERE idProjeto=" + idProjeto + " ORDER BY id DESC LIMIT 1"
                ultimo_id,total = executarSelect(getID,1)
                idIndicacao = int(ultimo_id[0])
                titulo_projeto = obterColunaUnica('editalProjeto','titulo','id',idProjeto)
                orientador = obterColunaUnica('editalProjeto','nome','id',idProjeto)
                email = obterColunaUnica('editalProjeto','email','id',idProjeto)
                email2 = "pesquisa.prpi@ufca.edu.br"
                texto_email = render_template('confirmacao_indicacao.html',vaga=vaga,id_projeto=idProjeto,indicado=nome,proponente=orientador,titulo=titulo_projeto,email_proponente=email,idIndicacao=idIndicacao)
                if vaga==1:
                    msg = Message(subject = "Plataforma Yoko - INDICAÇÃO DE BOLSISTA",recipients=[email,email2],html=texto_email)
                else:
                    msg = Message(subject = "Plataforma Yoko - INDICAÇÃO DE VOLUNTARIO",recipients=[email,email2],html=texto_email)
                mail.send(msg)
                return(render_template('confirmacao_indicacao.html',vaga=vaga,id_projeto=idProjeto,indicado=nome,proponente=orientador,titulo=titulo_projeto,email_proponente=email,idIndicacao=idIndicacao))
            else:
                return (u"Você já indicou todos os bolsistas/voluntários. Entrar em contato através do e-mail atendimento.prpi@ufca.edu.br")
        except:
            e = sys.exc_info()[0]
            logging.error(e)
            logging.error("ERRO Na função /efetivarIndicacao. Ver consulta abaixo.")
            return("ERRO!")

    else:
        return("OK")

@app.route("/indicacoes", methods=['GET', 'POST'])
def indicacoes():
    if request.method == "GET":
        #Recuperando código do edital
        if 'edital' in request.args:
            codigoEdital = str(request.args.get('edital'))
            descricao_edital = obterColunaUnica('editais','nome','id',codigoEdital)
            if 'tipo' in request.args:
                tipo_de_vaga = str(request.args.get('tipo'))
                consulta = """SELECT indicacoes.id,indicacoes.idProjeto, indicacoes.nome,IF(indicacoes.modalidade=1,'PIBIC',IF(indicacoes.modalidade=2,'PIBITI','PIBIC-EM')),
                IF(tipo_de_vaga=1, 'BOLSISTA','VOLUNTÁRIO(A)'), nome_banco,agencia,conta, arquivo_cpf_rg,arquivo_extrato,
                arquivo_historico,arquivo_termo,DATE_FORMAT(indicacoes.inicio,'%d/%m/%Y'),DATE_FORMAT(indicacoes.fim,'%d/%m/%Y'), editalProjeto.nome,editalProjeto.obs,
                editalProjeto.tipo
                FROM indicacoes,editalProjeto WHERE indicacoes.tipo_de_vaga=""" + tipo_de_vaga + """ AND indicacoes.idProjeto=editalProjeto.id AND tipo=""" + codigoEdital + """ ORDER BY editalProjeto.tipo,editalProjeto.nome,indicacoes.id """
            else:
                consulta = """SELECT indicacoes.id,indicacoes.idProjeto, indicacoes.nome,IF(indicacoes.modalidade=1,'PIBIC',IF(indicacoes.modalidade=2,'PIBITI','PIBIC-EM')),
                IF(tipo_de_vaga=1, 'BOLSISTA','VOLUNTÁRIO(A)'), nome_banco,agencia,conta, arquivo_cpf_rg,arquivo_extrato,
                arquivo_historico,arquivo_termo,DATE_FORMAT(indicacoes.inicio,'%d/%m/%Y'),DATE_FORMAT(indicacoes.fim,'%d/%m/%Y'), editalProjeto.nome,editalProjeto.obs,
                editalProjeto.tipo
                FROM indicacoes,editalProjeto WHERE indicacoes.idProjeto=editalProjeto.id AND tipo=""" + codigoEdital + """ ORDER BY editalProjeto.tipo,editalProjeto.nome,indicacoes.id """
            linhas,total = executarSelect(consulta)
            return(render_template('listar_indicacoes.html',listaIndicacoes=linhas,total=total,descricao=descricao_edital))
        else:
            return("OK")
    else:
        return("OK")

@app.route("/verArquivo", methods=['GET', 'POST'])
def verArquivo():
    if request.method == "GET":
        #Recuperando arquivo
        if 'file' in request.args:
            arquivo = str(request.args['file'])
            if os.path.isfile(ATTACHMENTS_DIR + arquivo):
                return(send_from_directory(app.config['UPLOADED_DOCUMENTS_DEST'], arquivo))
            else:
                return("Arquivo não encontrado!")
        else:
            return("OK")
    else:
        return("OK")

@app.route("/situacaoIndicacoes", methods=['GET', 'POST'])
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
                mes_ext = {1: 'janeiro', 2 : 'fevereiro', 3: 'marco', 4: 'abril', 5: 'maio', 6: 'junho', 7: 'julho',8: 'agosto', 9: 'setembro', 10: 'outubro', 11: 'novembro', 12: 'dezembro'}
                now = datetime.now()
                mesReferencia = now.month-1
                anoReferencia = now.year
                if (mesReferencia==0):
                    mesReferencia = 12
                    anoReferencia = anoReferencia-1
                if jaEnviouFrequenciaAtual(idAluno,str(mesReferencia),str(anoReferencia)):
                    return("A frequência atual já foi enviada, não é possível realizar um novo envio.")
                else:
                    return(render_template('frequencia.html',nomeAluno=nomeAluno,referencia=mes_ext[mesReferencia],ano=anoReferencia,idAluno=idAluno,titulo=titulo_projeto,mes=mesReferencia,edital=descricaoEdital))
            else:
                return("Permissão negada!")
        else:
            return("OK")
    else:
        return("OK")


@app.route("/cadastrarFrequencia", methods=['GET', 'POST'])
def cadastrarFrequencia():
    if request.method == "POST":
        s1 = unicode(request.form['s1'])
        s2 = unicode(request.form['s2'])
        s3 = unicode(request.form['s3'])
        s4 = unicode(request.form['s4'])
        mes = str(request.form['mes'])
        ano = str(request.form['ano'])
        idAluno = str(request.form['idAluno'])
        obs = unicode(request.form['obs'])
        consulta = """INSERT INTO frequencias (idIndicacao,mes,ano,s1,s2,s3,s4,obs) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"""
        valores = (idAluno,mes,ano,s1,s2,s3,s4,obs)
        inserir(consulta,valores)
        return redirect("/pesquisa/meusProjetos")
    else:
        return("OK")

@app.route("/listaNegra", methods=['GET', 'POST'])
@auth.login_required(role=['admin'])
def listaNegra():
    if request.method == "GET":
        if ('mes' in request.args) and ('ano' in request.args):
            mes = str(request.args.get('mes'))
            ano = str(request.args.get('ano'))
            consulta = """SELECT indicacoes.id,indicacoes.nome,editalProjeto.nome,editalProjeto.email,indicacoes.email FROM indicacoes,editalProjeto WHERE indicacoes.idProjeto=editalProjeto.id AND indicacoes.fim>NOW() ORDER BY editalProjeto.nome,indicacoes.id"""
            linhas,total = executarSelect(consulta)
            lista = []
            lista_emails = ['pesquisa.prpi@ufca.edu.br']
            lista_emails_discentes = []
            for linha in linhas:
                idIndicacao = str(linha[0])
                subconsulta = """SELECT id FROM frequencias WHERE mes=""" + mes + """ AND ano=""" + ano + """ AND idIndicacao=""" + idIndicacao
                frequencias,totalFrequencias = executarSelect(subconsulta)
                dados = [str(linha[0]),unicode(linha[1]),unicode(linha[2])]
                if totalFrequencias==0:
                    lista.append(dados)
                    lista_emails.append(str(linha[3]))
                    lista_emails_discentes.append(linha[4])
            if ('email' in request.args):
                enviarEmail = str(request.args.get('email'))
                if enviarEmail=="1":
                    texto_email = render_template('lembrete_frequencia.html')
                    msg = Message(subject = "Plataforma Yoko - LEMBRETE DE ENVIO DE FREQUÊNCIA",recipients=['pesquisa.prpi@ufca.edu.br','dic.prpi@ufca.edu.br'],bcc=lista_emails,html=texto_email,reply_to="NAO-RESPONDA@ufca.edu.br")
                    mail.send(msg)
                    pass

            return(render_template('listaNegra.html',lista=tuple(lista),mes=mes,ano=ano,total=len(lista)))
        else:
            return("Mes e ano nao informado...")
    else:
        return("OK")

def agora():
    from datetime import datetime as dt
    now = dt.now()
    tempo = now.strftime('%d/%m/%Y - %H:%M')
    return(tempo)

def timestamp():
    from datetime import datetime as dt
    now = dt.now()
    return(str(now))

@app.route("/desligarIndicacao", methods=['GET', 'POST'])
def desligarIndicacao():
    if request.method == "GET":
        if 'id' in request.args:
            idAluno = str(request.args.get('id'))
            siape = session['username']
            if (autenticado()):
                if verificarSiapeIndicacao(siape,idAluno): #O aluno é indicação do usuário atual
                    idProjeto = obterColunaUnica('indicacoes','idProjeto','id',idAluno)
                    logging.debug(idProjeto)
                    orientador = obterColunaUnica('editalProjeto','nome','id',idProjeto)
                    titulo = obterColunaUnica('editalProjeto','titulo','id',idProjeto)
                    discente = obterColunaUnica('indicacoes','nome','id',idAluno)
                    tipo_vaga = obterColunaUnica('indicacoes','tipo_de_vaga','id',idAluno)
                    timestamp = agora()
                    #return("Ainda não disponível. Favor aguardar até as 17:00 de 13/09/2019")
                    consulta = "UPDATE indicacoes SET situacao=1, fim=NOW() WHERE id=" + idAluno
                    atualizar(consulta)
                    email = obterColunaUnica('editalProjeto','email','id',idProjeto)
                    email2 = "pesquisa.prpi@ufca.edu.br"
                    email3 = "rafael.mota@ufca.edu.br"
                    texto_email = render_template('confirmacao_desligamento.html',vaga=tipo_vaga,id_projeto=idProjeto,proponente=orientador,titulo=titulo,indicado=discente,idIndicacao=idAluno,data=timestamp)
                    if tipo_vaga==1:
                        msg = Message(subject = "Plataforma Yoko - DESLIGAMENTO DE BOLSISTA",recipients=[email,email2,email3],html=texto_email)
                    else:
                        msg = Message(subject = "Plataforma Yoko - DESLIGAMENTO DE VOLUNTARIO",recipients=[email,email2,email3],html=texto_email)
                    mail.send(msg)
                    return(render_template('confirmacao_desligamento.html',vaga=tipo_vaga,id_projeto=idProjeto,proponente=orientador,titulo=titulo,indicado=discente,idIndicacao=idAluno,data=timestamp))
                else:
                    return("ACESSO NEGADO")
            else:
                return(redirect(url_for('login')))
        else:
            return("Erro: ID nao informado")
    else:
        return("ERRO: Metodo invalido")

@app.route("/substituirIndicacao", methods=['GET', 'POST'])
def substituirIndicacao():
    if request.method == "GET":
        if 'id' in request.args:
            idAluno = str(request.args.get('id'))
            siape = session['username']
            if (autenticado()):
                if verificarSiapeIndicacao(siape,idAluno): #O aluno é indicação do usuário atual
                    idProjeto = obterColunaUnica('indicacoes','idProjeto','id',idAluno)
                    logging.debug(idProjeto)
                    orientador = obterColunaUnica('editalProjeto','nome','id',idProjeto)
                    titulo = obterColunaUnica('editalProjeto','titulo','id',idProjeto)
                    discente = obterColunaUnica('indicacoes','nome','id',idAluno)
                    tipo_vaga = obterColunaUnica('indicacoes','tipo_de_vaga','id',idAluno)
                    timestamp = agora()
                    fomento = int(obterColunaUnica('indicacoes','fomento','id',idAluno))
                    #return("Ainda não disponível. Favor aguardar até as 17:00 de 13/09/2019")
                    consulta = "UPDATE indicacoes SET situacao=2, fim=NOW() WHERE id=" + idAluno
                    atualizar(consulta)
                    email = obterColunaUnica('editalProjeto','email','id',idProjeto)
                    email2 = "pesquisa.prpi@ufca.edu.br"
                    email3 = "rafael.mota@ufca.edu.br"
                    texto_email = render_template('confirmacao_substituicao.html',vaga=tipo_vaga,id_projeto=idProjeto,proponente=orientador,titulo=titulo,indicado=discente,idIndicacao=idAluno,data=timestamp)
                    if tipo_vaga=="1":
                        msg = Message(subject = "Plataforma Yoko - SUBSTITUIÇÃO DE BOLSISTA",recipients=[email,email2,email3],html=texto_email)
                    else:
                        msg = Message(subject = "Plataforma Yoko - SUBSTITUIÇÃO DE VOLUNTARIO",recipients=[email,email2,email3],html=texto_email)
                    mail.send(msg)

                    #return(render_template('confirmacao_substituicao.html',vaga=tipo_vaga,id_projeto=idProjeto,proponente=orientador,titulo=titulo,indicado=discente,idIndicacao=idAluno,data=timestamp))
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
        else:
            return("Erro: ID nao informado")
    else:
        return("ERRO: Metodo invalido")


@app.route("/pub/consulta", methods=['GET', 'POST'])
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
                logging.debug(sys.exc_info()[0])
                return("Erro!")
    else:
        return("OK")

'''
SELECT indicacoes.id,idProjeto,editalProjeto.tipo,IF(tipo_de_vaga=1,'BOLSISTA','VOLUNARIO(A)') AS tipo,IF(indicacoes.situacao=1,'DESLIGADO(A)','SUBSTITUIDO(A)') AS tipo_situacao,indicacoes.nome,nome_banco,agencia,conta, DATE_FORMAT(indicacoes.inicio,'%d/%m/%Y') as inicio,
DATE_FORMAT(indicacoes.fim,'%d/%m/%Y') as final FROM indicacoes,editalProjeto WHERE indicacoes.idProjeto=editalProjeto.id AND
indicacoes.situacao in (1,2) ORDER BY indicacoes.tipo_de_vaga DESC,indicacoes.fim DESC

SELECT indicacoes.id,idProjeto,editalProjeto.tipo,IF(tipo_de_vaga=1,'BOLSISTA','VOLUNARIO(A)') AS tipo,IF(indicacoes.substituido!=0,'SUBSTITUTO(A)','N/A') AS tipo_situacao,indicacoes.nome,nome_banco,agencia,conta, DATE_FORMAT(indicacoes.inicio,'%d/%m/%Y') as inicio,
DATE_FORMAT(indicacoes.fim,'%d/%m/%Y') as final FROM indicacoes,editalProjeto WHERE indicacoes.idProjeto=editalProjeto.id AND
indicacoes.situacao in (0) AND indicacoes.substituido!=0 ORDER BY indicacoes.tipo_de_vaga DESC,indicacoes.fim DESC
'''

@app.route("/substituicoes", methods=['GET', 'POST'])
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
        titulo = unicode(linha[1])
        resumo = unicode(linha[2])
        link = unicode(linha[4])
        token = unicode(linha[7])
        email_avaliador = unicode(linha[3])
        link_recusa = ROOT_SITE + "/pesquisa/recusarConvite?token=" + token
        deadline = str(linha[11])
        nome_longo = unicode(linha[12])
        with app.app_context():
            texto_email = render_template('email_avaliador.html',nome_longo=nome_longo,titulo=titulo,resumo=resumo,link=link,link_recusa=link_recusa,deadline=deadline)
            msg = Message(subject = u"CONVITE: AVALIAÇÃO DE PROJETO DE PESQUISA",bcc=[email_avaliador],reply_to="NAO-RESPONDA@ufca.edu.br",html=texto_email)
            try:
                mail.send(msg)
                consulta = "UPDATE avaliacoes SET enviado=enviado+1,data_envio=NOW() WHERE id=" + str(linha[5])
                atualizar(consulta)    
            except:
                logging.error("EMAIL SOLICITANDO AVALIACAO FALHOU: " + email_avaliador)
                return("Erro! Verifique o log!")

@app.route("/emailSolicitarAvaliacao", methods=['GET', 'POST'])
@auth.login_required(role=['admin'])
def email_solicitar_avaliacao():
    t = threading.Thread(target=enviar_email_avaliadores)
    t.start()
    return("Envio de e-mails iniciado!")
    
def enviarPedidoAvaliacao(id):
    gerarLinkAvaliacao()
    consulta = """
    SELECT e.id,e.titulo,e.resumo,a.avaliador,a.link,a.id,a.enviado,a.token,e.categoria,e.tipo 
    FROM editalProjeto as e, avaliacoes as a WHERE e.id=a.idProjeto AND e.valendo=1 
    AND a.finalizado=0 AND e.categoria=1 and e.id=""" + str(id) + """ 
    ORDER BY a.id DESC LIMIT 1
    """
    linhas,total = executarSelect(consulta)
    logging.debug("Enviado pedido de avaliacao para: " + str(total))
    
    for linha in linhas:
        titulo = unicode(linha[1])
        resumo = unicode(linha[2])
        link = unicode(linha[4])
        token = unicode(linha[7])
        email_avaliador = unicode(linha[3])
        link_recusa = ROOT_SITE + "/pesquisa/recusarConvite?token=" + token
        deadline = obterColunaUnica('editais',"DATE_FORMAT(deadline_avaliacao,'%d/%m/%Y')",'id',str(linha[9]))
        nome_longo = obterColunaUnica('editais','nome','id',str(linha[9]))
        with app.app_context():
            texto_email = render_template('email_avaliador.html',nome_longo=nome_longo,titulo=titulo,resumo=resumo,link=link,link_recusa=link_recusa,deadline=deadline)
            msg = Message(subject = u"CONVITE: AVALIAÇÃO DE PROJETO DE PESQUISA",bcc=[email_avaliador],reply_to="NAO-RESPONDA@ufca.edu.br",html=texto_email)
            try:
                mail.send(msg)
                logging.debug("E-MAIL ENVIADO COM SUCESSO.")    
            except:
                logging.error("EMAIL SOLICITANDO AVALIACAO FALHOU: " + email_avaliador)

@app.route("/arquivar/<id_projeto>", methods=['GET', 'POST'])
@auth.login_required(role=['admin'])
def arquivar_projeto(id_projeto):
    projeto = str(id_projeto)
    consulta = "UPDATE editalProjeto SET valendo=0 WHERE id=" + projeto
    atualizar(consulta)
    edital = str(session['edital'])
    return(redirect("/pesquisa/editalProjeto?edital=" + edital))

if __name__ == "__main__":
    #app.run()
    serve(app, host='0.0.0.0', port=80, url_prefix='/pesquisa')
