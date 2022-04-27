# -*- coding: utf-8 -*-
import MySQLdb
import os
import logging
import sys
from validate_email import validate_email
import string
import random

WORKING_DIR='/home/perazzo/flask/projetos/pesquisa/'
logging.basicConfig(filename=WORKING_DIR + 'atualizar_email.log', filemode='w', format='%(name)s - %(levelname)s - %(message)s',level=logging.DEBUG)

#Obtendo senhas
lines = [line.rstrip('\n') for line in open(WORKING_DIR + 'senhas.pass')]
PASSWORD = lines[0]

def atualizar(consulta):
    conn = MySQLdb.connect(host="db", user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
    conn.autocommit(False)
    conn.select_db('pesquisa')
    cursor  = conn.cursor()
    try:
        cursor.execute(consulta)
        conn.commit()
    except MySQLdb.Error, e:
        logging.debug(e)
        conn.rollback()
    finally:
        conn.close()

def id_generator(size=20, chars=string.ascii_uppercase + string.digits + string.ascii_lowercase):
        return ''.join(random.choice(chars) for _ in range(size))


#CONEXÃO COM BD
conn = MySQLdb.connect(host="db", user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
conn.select_db('pesquisa')
cursor  = conn.cursor()
consulta = "SELECT docente,siape FROM docentes WHERE email is null ORDER BY docente DESC"
cursor.execute(consulta)
linhas = cursor.fetchall()
continua = True
for linha in linhas:
    try:
        token = id_generator()
        nome = unicode(linha[0])
        siape = int(linha[1])
        palavras = nome.split()
        for i in range(0,len(palavras)):
            for j in range(i+1,len(palavras)):
                primeiro = palavras[i]
                ultimo = palavras[j]
                email = primeiro + "." + ultimo + "@ufca.edu.br"
                #logging.debug("Testando o email: " + email)
                is_valid = validate_email(email,verify=True)
                if is_valid:
                    logging.debug("Atualizando e-mail: " + email)
		    print("Atualizando e-mail: " + email)
                    consulta_update = "UPDATE docentes SET email=\"" + email + "\" WHERE siape=" + str(siape)
                    atualizar(consulta_update)
                    continua = False
                    break
            if not continua:
                break
        consulta_update = "UPDATE docentes SET token=\"" + token + "\" WHERE siape=" + str(siape)
        atualizar(consulta_update)
    except:
        e = sys.exc_info()[0]
        logging.error(e)
conn.close()
logging.info("FINAL")
