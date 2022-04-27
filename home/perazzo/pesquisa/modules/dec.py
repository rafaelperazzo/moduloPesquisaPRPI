# -*- coding: utf-8 -*-
from fpdf import FPDF
import datetime
import sqlite3
import MySQLdb
#import logging
import os
#import sys

pasta = "/home/perazzo/flask/projetos/pesquisa/modules/"
pasta_declaracoes = "/home/perazzo/flask/projetos/pesquisa/static/pdf/"
def imprimirData():
    Meses=('janeiro','fevereiro','mar','abril','maio','junho',
       'julho','agosto','setembro','outubro','novembro','dezembro')
    agora = datetime.date.today()
    dia = agora.day
    mes=(agora.month-1)
    mesExtenso = Meses[mes]
    ano = agora.year
    resultado = str(dia) + " de " + mesExtenso + " de " + str(ano) + "."
    return resultado

class PDF(FPDF):
    def header(self):
        
		# Logo
        self.image(pasta + 'cabecalho.png', 90, 8, 33)
        # Arial bold 15
        self.set_font('Arial', 'B', 10)
        # Move to the right
        # Title
        self.ln(35)
        self.cell(70)
        self.cell(50, 5, u'MINISTÉRIO DA EDUCAÇÃO', 0, 1, 'C')
        self.cell(70)
        self.cell(50, 5, u'UNIVERSIDADE FEDERAL DO CARIRI', 0, 1, 'C')
        self.cell(70)
        # Line break
        self.cell(50, 5, u'PRÓ-REITORIA DE PESQUISA, PÓS-GRADUAÇÃO E INOVAÇÃO', 0, 1, 'C')
        self.cell(70)
        self.cell(50, 5, u'COORDENADORIA DE PESQUISA', 0, 1, 'C')

    # Page footer
    def footer(self):
        # Position at 1.5 cm from bottom
        self.set_y(-55)
        # Arial italic 8
        self.set_font('Arial', 'I', 8)
        # Page number
        #self.cell(0, 10, 'Page ' + str(self.page_no()) + '/{nb}', 0, 0, 'C')
        
        self.image(pasta + 'rodape.png', 5, 250, 200)
        self.cell(0, 5, 'DOCUMENTO ASSINADO DIGITALMENTE: ' , 0, 1, 'C')
        self.cell(0, 5, 'Autenticidade pode ser verificada em: http://prpi.ufca.edu.br ' , 0, 1, 'C')

# Instantiation of inherited class
'''
Identificador = CPF
'''
def gerarDeclaracao(identificador):
    pdf = PDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_font('Times', '', 12)
    ## TODO: Ajustar margens
    pdf.set_margins(20,20,20)

    #CONEXÃO COM BD
    
    #conn = sqlite3.connect(pasta + 'dados.sqlite3')
    conn = MySQLdb.connect(host="localhost", user="pesquisa", passwd="h5YACshdpuHfXx84", db="pesquisa", charset="utf8", use_unicode=True)
    conn.select_db('pesquisa')
    cursor  = conn.cursor()
    consulta = "SELECT * FROM alunos WHERE id=" + str(identificador)
    cursor.execute(consulta)
    linha = cursor.fetchone()

    #RECUPERANDO DADOS
    nome = linha[4]
    cpf = linha[5]
    orientador = linha[9]
    projeto = linha[11]
    ch = "12 horas"
    vigencia_inicio = linha[7]
    vigencia_fim = linha[8]
    modalidade = linha[2]

    pdf.ln(10)
    pdf.set_font('Times', 'B', 16)
    pdf.cell(0, 10, u'DECLARAÇÃO ', 0, 1,'C')
    pdf.ln(10)
    pdf.set_font('Times', '', 12)
    texto = u'Declaramos para os devidos fins que ' + nome + ', CPF: ' + cpf
    texto = texto + u", foi bolsista do Programa Institucional de Bolsas de Iniciação Científica (" + modalidade + "), "
    texto = texto + u"sob orientação do professor(a) " + orientador + u" com o projeto intitulado " + projeto
    texto = texto + u", desempenhando suas atividades com carga horária de " + ch + u" semanais.\n"
    texto = texto + u"A participação do(a) discente em questão no referido Projeto de Pesquisa foi de " + vigencia_inicio + " a " + vigencia_fim + "."
    pdf.multi_cell(170, 10, texto, 0, 1,'J')

    pdf.ln(20)

    pdf.cell(0,5,u"Juazeiro do Norte, " + imprimirData(),0,1,'R')
    
    pdf.image(pasta + 'assinatura.jpg', 70, 185, 66)
    pdf.line(60,200,150,200)
    pdf.ln(20)
    pdf.cell(0,5,u"RAFAEL PERAZZO BARBOSA MOTA",0,1,'C')
    pdf.cell(0,5,u"COORDENADOR DE PESQUISA",0,1,'C')
    pdf.cell(0,5,u"SIAPE: 1570709",0,1,'C')
    pdf.output(pasta_declaracoes + identificador + '.pdf', 'F')
    #return (pasta_declaracoes + identificador + '.pdf')
    #return (pasta_declaracoes)
    conn.close()
    return (texto)
