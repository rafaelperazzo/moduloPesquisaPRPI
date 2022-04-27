# -*- coding: utf-8 -*-
import logging
import os
import sys
import MySQLdb
import string
import random


WORKING_DIR='/home/perazzo/pesquisa/'
CURRICULOS_DIR='/home/perazzo/pesquisa/static/files/'
lines = [line.rstrip('\n') for line in open(WORKING_DIR + 'senhas.pass')]
PASSWORD = lines[0]

def id_generator(size=20, chars=string.ascii_uppercase + string.digits + string.ascii_lowercase):
        return ''.join(random.choice(chars) for _ in range(size))

def atualizar(consulta):
    conn = MySQLdb.connect(host="db", user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
    conn.autocommit(True)
    conn.select_db('pesquisa')
    cursor  = conn.cursor()
    try:
        cursor.execute(consulta)
        conn.commit()
    except MySQLdb.Error, e:
        e = sys.exc_info()[0]
        logging.debug(e)
    finally:
        cursor.close()
        conn.close()

try:
    conn = MySQLdb.connect(host="db", user="pesquisa", passwd=PASSWORD, db="pesquisa", charset="utf8", use_unicode=True)
    conn.autocommit(False)
    conn.select_db('pesquisa')
    cursor  = conn.cursor()
    consulta = "SELECT id as identificador FROM cadastro_geral WHERE token is null"
    cursor.execute(consulta)
    linhas = cursor.fetchall()
    for linha in linhas:
        idCadastro = str(linha[0])
        token = id_generator()
        update = "UPDATE cadastro_geral SET token=\"" + token + "\" WHERE id=" + idCadastro
        atualizar(update)

except:
    print("Erro!")
    e = sys.exc_info()[0]
    print(e)
finally:
    cursor.close()
    conn.close()
