# -*- coding: utf-8 -*-
#https://stackoverflow.com/questions/8329741/issue-with-smtplib-sending-mail-with-unicode-characters-in-python-3-1
#https://mariadb.com/kb/en/library/timestampdiff/
import logging
import os
import sys
import MySQLdb
import string
import random

SITE = "https://sci01-ter-jne.ufca.edu.br/pesquisa/avaliacao"
LINK_RECUSA = "https://sci01-ter-jne.ufca.edu.br/pesquisa/"
LINK_HOME = "https://sci01-ter-jne.ufca.edu.br/pesquisa/"
UPLOAD_FOLDER = '/home/perazzo/pesquisa/static/files/'
ALLOWED_EXTENSIONS = set(['pdf','xml'])
WORKING_DIR='/home/perazzo/pesquisa/'
CURRICULOS_DIR='/home/perazzo/pesquisa/static/files/'
DOCUMENTOS_DIR='/home/perazzo/pesquisa/documentos/'
#Obtendo senhas
lines = [line.rstrip('\n') for line in open(WORKING_DIR + 'senhas.pass')]
PASSWORD = lines[0]
GMAIL_PASSWORD = lines[1]


def atualizar(consulta,valores):
    conn = MySQLdb.connect(host="db", user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
    conn.autocommit(False)
    conn.select_db('pesquisa')
    cursor  = conn.cursor()
    try:
        cursor.execute(consulta,valores)
        conn.commit()
    except MySQLdb.Error, e:
        e = sys.exc_info()[0]
        print(e)
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def executarSelect(consulta,tipo=0):
    conn = MySQLdb.connect(host="db", user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
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


def verificarEmails(codigoEdital):
    consulta = """SELECT email,nome,id FROM editalProjeto WHERE email not like "%@ufca%" and valendo=1 and tipo=""" + codigoEdital
    linhas, total = executarSelect(consulta)
    print("VERIFICANDO E-MAILS QUE NÃO SÃO DA UFCA")
    print("*****************************")
    for linha in linhas:
        print("[" + str(linha[2]) + "] " + linha[1] + " - " + linha[0])
    print("*****************************")

def verificarProjetosEmAndamento(codigoEdital):
    consulta = """SELECT id,nome,titulo,if(categoria=1,"PROJETO NOVO","PROJETO EM ANDAMENTO") as categoria FROM editalProjeto
    WHERE
    NOT
    (titulo in (SELECT titulo FROM editalProjeto WHERE categoria=1 and valendo=1 and tipo=1)
    OR
    titulo in (SELECT titulo_do_projeto FROM cadastro_geral))
    and valendo=1 and categoria=0 and tipo=""" + codigoEdital + """ ORDER BY NOME"""
    linhas, total = executarSelect(consulta)
    print("VERIFICANDO PROJETOS EM ANDAMENTO, QUE NÃO FORAM ENCONTRADOS")
    print("*****************************")
    for linha in linhas:
        print("[" + str(linha[0]) + "] " + unicode(linha[1]) + " - " + unicode(linha[2]))
    print("*****************************")

def id_generator(size=20, chars=string.ascii_uppercase + string.digits + string.ascii_lowercase):
        return ''.join(random.choice(chars) for _ in range(size))

def cadastrarUsuarios(codigoEdital):
    consulta = """SELECT nome,email,siape FROM editalProjeto WHERE valendo=1 AND tipo=""" + codigoEdital + """ ORDER BY nome"""
    linhas,total = executarSelect(consulta)
    for linha in linhas:
        senha = id_generator(8)
        inserir = """INSERT INTO users (nome,email,username,password) VALUES (%s,%s,%s,%s)"""
        valores = (unicode(linha[0]),unicode(linha[1]),unicode(linha[2]),senha)
        atualizar(inserir,valores)

def cadastrarUsuariosAntigos():
    consulta = """SELECT nome_do_coordenador,orientador_email,siape FROM cadastro_geral ORDER BY nome_do_coordenador"""
    linhas,total = executarSelect(consulta)
    for linha in linhas:
        senha = id_generator(8)
        inserir = """INSERT INTO users (nome,email,username,password) VALUES (%s,%s,%s,%s)"""
        valores = (unicode(linha[0]),unicode(linha[1]),unicode(linha[2]),senha)
        atualizar(inserir,valores)

def atualizarSenhas(codigoEdital):
    consulta = """SELECT username FROM users ORDER BY nome"""
    linhas,total = executarSelect(consulta)
    for linha in linhas:
        senha = id_generator(8)
        update = """UPDATE users SET password=%s WHERE username=%s"""
        valores = (senha,str(linha[0]))
        atualizar(update,valores)

def main():
    verificarEmails(codigoEdital)
    #verificarProjetosEmAndamento(codigoEdital)
    #cadastrarUsuarios(codigoEdital)
    #atualizarSenhas(codigoEdital)
    cadastrarUsuariosAntigos()

if (len(sys.argv)==2):
    codigoEdital = str(sys.argv[1])
else:
    codigoEdital = "0"
main()
