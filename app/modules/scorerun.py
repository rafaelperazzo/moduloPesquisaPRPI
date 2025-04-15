#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# This is the scoreLattes script.
#
# Copyright (C) 2017 Vicente Helano
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Author(s): Vicente Helano <vicente.sobrinho@ufca.edu.br>
#

from datetime import date
from datetime import datetime
import xml.etree.ElementTree as ET
import sys, time, argparse, csv, requests
from bs4 import BeautifulSoup

WORKING_DIR='/app/modules/'

weights = {
    'FORMACAO-ACADEMICA-TITULACAO' : {'POS-DOUTORADO': 4, 'LIVRE-DOCENCIA': 4, 'DOUTORADO': 7, 'MESTRADO': 3, 'ESPECIALIZACAO': 1},
    'MEMBRO-DE-CORPO-EDITORIAL' : {'REVISTA': 1},
    'PROJETO-DE-PESQUISA' : {'PESQUISA': 2, 'DESENVOLVIMENTO': 2, 'ENSINO': 1,'EXTENSAO':1},
    'PROJETO-DE-PESQUISA-SEM-FOMENTO' : {'PESQUISA': 1, 'DESENVOLVIMENTO': 1,'ENSINO': 1,'EXTENSAO':1},
    'PRODUCAO-BIBLIOGRAFICA' : {
        'ARTIGOS-PUBLICADOS': {'A1': 12, 'A2': 12, 'A3': 8, 'A4': 8, 'B1': 6, 'B2': 6, 'B3': 3, 'B4': 3, 'C': 0.5, 'NAO-ENCONTRADO': 0.5},
        'TRABALHOS-EM-EVENTOS': {
            'INTERNACIONAL': { 'COMPLETO': 2, 'RESUMO_EXPANDIDO': 2, 'RESUMO': 0.3 },
            'NACIONAL': { 'COMPLETO': 1, 'RESUMO_EXPANDIDO': 1, 'RESUMO': 0.2 },
            'REGIONAL': { 'COMPLETO': 0.3, 'RESUMO_EXPANDIDO': 0.3, 'RESUMO': 0.1 },
            'LOCAL': { 'COMPLETO': 0.3, 'RESUMO_EXPANDIDO': 0.3, 'RESUMO': 0.1 },
            'NAO_INFORMADO': { 'COMPLETO': 0, 'RESUMO_EXPANDIDO': 0, 'RESUMO': 0 },
        },
        'LIVROS-E-CAPITULOS': {
            'LIVRO-PUBLICADO-OU-ORGANIZADO': {
                'LIVRO_PUBLICADO': 10,
                'LIVRO_ORGANIZADO_OU_EDICAO': 6,
                'NAO_INFORMADO': 0,
            },
            'CAPITULO-DE-LIVRO-PUBLICADO': 4,
        },
        'DEMAIS-TIPOS-DE-PRODUCAO-BIBLIOGRAFICA': { 'TRADUCAO': 2 },
    },
    'PRODUCAO-TECNICA': {
        'SOFTWARE': 2,
        'PATENTE': {'DEPOSITADA': 2, 'CONCEDIDA': 10},
        'PRODUTO-TECNOLOGICO': 2,
        'PROCESSOS-OU-TECNICAS': 2,
        'TRABALHO-TECNICO': 0.5,
    },
    'OUTRA-PRODUCAO': {
        'PRODUCAO-ARTISTICA-CULTURAL': {
            'APRESENTACAO-DE-OBRA-ARTISTICA': 2,
            'COMPOSICAO-MUSICAL': 4,
            'OBRA-DE-ARTES-VISUAIS': 4,
            'MUSICA': 4,
            'ARTES-CENICAS': 4,
        },
        'ORIENTACOES-CONCLUIDAS': {
            'ORIENTACOES-CONCLUIDAS-PARA-POS-DOUTORADO': 5,
            'ORIENTACOES-CONCLUIDAS-PARA-DOUTORADO': {'ORIENTADOR_PRINCIPAL': 5, 'CO_ORIENTADOR': 2.5},
            'ORIENTACOES-CONCLUIDAS-PARA-MESTRADO': {'ORIENTADOR_PRINCIPAL': 2, 'CO_ORIENTADOR': 1},
            'OUTRAS-ORIENTACOES-CONCLUIDAS': {
                'MONOGRAFIA_DE_CONCLUSAO_DE_CURSO_APERFEICOAMENTO_E_ESPECIALIZACAO': 0.8,
                'TRABALHO_DE_CONCLUSAO_DE_CURSO_GRADUACAO': 0.5,
                'INICIACAO_CIENTIFICA': 0.5,
                'ORIENTACAO-DE-OUTRA-NATUREZA': 0,
            },
        },
        'ORIENTACOES-EM-ANDAMENTO': {
            'ORIENTACOES-EM-ANDAMENTO-PARA-POS-DOUTORADO': 5,
            'ORIENTACOES-EM-ANDAMENTO-PARA-DOUTORADO': {'ORIENTADOR_PRINCIPAL': 5, 'CO_ORIENTADOR': 2.5},
            'ORIENTACOES-EM-ANDAMENTO-PARA-MESTRADO': {'ORIENTADOR_PRINCIPAL': 2, 'CO_ORIENTADOR': 1},
            'OUTRAS-ORIENTACOES-EM-ANDAMENTO': {
                'MONOGRAFIA_DE_CONCLUSAO_DE_CURSO_APERFEICOAMENTO_E_ESPECIALIZACAO': 0.8,
                'TRABALHO_DE_CONCLUSAO_DE_CURSO_GRADUACAO': 0.5,
                'INICIACAO_CIENTIFICA': 0.5,
                'ORIENTACAO-DE-OUTRA-NATUREZA': 0,
            },
        },

    },
    'DADOS-COMPLEMENTARES': {
        'ORIENTACOES-EM-ANDAMENTO': {
            'ORIENTACOES-EM-ANDAMENTO-PARA-POS-DOUTORADO': 5,
            'ORIENTACOES-EM-ANDAMENTO-PARA-DOUTORADO': {'ORIENTADOR_PRINCIPAL': 5, 'CO_ORIENTADOR': 2.5},
            'ORIENTACOES-EM-ANDAMENTO-PARA-MESTRADO': {'ORIENTADOR_PRINCIPAL': 2, 'CO_ORIENTADOR': 1},
            'OUTRAS-ORIENTACOES-EM-ANDAMENTO': {
                'MONOGRAFIA_DE_CONCLUSAO_DE_CURSO_APERFEICOAMENTO_E_ESPECIALIZACAO': 0.8,
                'TRABALHO_DE_CONCLUSAO_DE_CURSO_GRADUACAO': 0.5,
                'INICIACAO_CIENTIFICA': 0.5,
                'ORIENTACAO-DE-OUTRA-NATUREZA': 0,
            },
        },
    },
}

bounds = {
    'FORMACAO-ACADEMICA-TITULACAO' : {'POS-DOUTORADO': 8, 'LIVRE-DOCENCIA': 8, 'DOUTORADO': 14, 'MESTRADO': 6, 'ESPECIALIZACAO': 3},
    'MEMBRO-DE-CORPO-EDITORIAL' : {'REVISTA': 2},
    'PROJETO-DE-PESQUISA' : {'PESQUISA': 8, 'DESENVOLVIMENTO': 8,'ENSINO': 3,'EXTENSAO':3},
    'PROJETO-DE-PESQUISA-SEM-FOMENTO' : {'PESQUISA': 4, 'DESENVOLVIMENTO': 4,'ENSINO': 3,'EXTENSAO':3},
    'PRODUCAO-BIBLIOGRAFICA' : {
        'ARTIGOS-PUBLICADOS': {'A1': 'inf', 'A2': 'inf', 'A3': 'inf', 'A4': 'inf', 'B1': 'inf', 'B2': 'inf', 'B3': 'inf', 'B4': 'inf', 'C': 'inf', 'NAO-ENCONTRADO': 'inf'},
        'TRABALHOS-EM-EVENTOS': {
            'INTERNACIONAL': { 'COMPLETO': 10, 'RESUMO_EXPANDIDO': 10, 'RESUMO': 1.5 },
            'NACIONAL': { 'COMPLETO': 5, 'RESUMO_EXPANDIDO': 5, 'RESUMO': 5 },
            'REGIONAL': { 'COMPLETO': 1.5, 'RESUMO_EXPANDIDO': 1.5, 'RESUMO': 0.5 },
            'LOCAL': { 'COMPLETO': 1.5, 'RESUMO_EXPANDIDO': 1.5, 'RESUMO': 0.5 },
            'NAO_INFORMADO': { 'COMPLETO': 'inf', 'RESUMO_EXPANDIDO': 'inf', 'RESUMO': 'inf' },
        },
        'LIVROS-E-CAPITULOS': {
            'LIVRO-PUBLICADO-OU-ORGANIZADO': {
                'LIVRO_PUBLICADO': 'inf',
                'LIVRO_ORGANIZADO_OU_EDICAO': 'inf',
                'NAO_INFORMADO': 'inf',
            },
            'CAPITULO-DE-LIVRO-PUBLICADO': 'inf',
        },
        'DEMAIS-TIPOS-DE-PRODUCAO-BIBLIOGRAFICA': { 'TRADUCAO': 'inf' },
    },
    'PRODUCAO-TECNICA': {
        'SOFTWARE': 6,
        'PATENTE': {'DEPOSITADA': 4, 'CONCEDIDA': 'inf'},
        'PRODUTO-TECNOLOGICO': 6,
        'PROCESSOS-OU-TECNICAS': 6,
        'TRABALHO-TECNICO': 2,
    },
    'OUTRA-PRODUCAO': {
        'PRODUCAO-ARTISTICA-CULTURAL': {
            'APRESENTACAO-DE-OBRA-ARTISTICA': 10,
            'COMPOSICAO-MUSICAL': 8,
            'OBRA-DE-ARTES-VISUAIS': 8,
            'MUSICA': 8,
            'ARTES-CENICAS': 8,
        },
        'ORIENTACOES-CONCLUIDAS': {
            'ORIENTACOES-CONCLUIDAS-PARA-POS-DOUTORADO': 'inf',
            'ORIENTACOES-CONCLUIDAS-PARA-DOUTORADO': {'ORIENTADOR_PRINCIPAL': 'inf', 'CO_ORIENTADOR': 'inf'},
            'ORIENTACOES-CONCLUIDAS-PARA-MESTRADO': {'ORIENTADOR_PRINCIPAL': 'inf', 'CO_ORIENTADOR': 'inf'},
            'OUTRAS-ORIENTACOES-CONCLUIDAS': {
                'MONOGRAFIA_DE_CONCLUSAO_DE_CURSO_APERFEICOAMENTO_E_ESPECIALIZACAO': 4,
                'TRABALHO_DE_CONCLUSAO_DE_CURSO_GRADUACAO': 5,
                'INICIACAO_CIENTIFICA': 5,
                'ORIENTACAO-DE-OUTRA-NATUREZA': 0,
            },
        },
        'ORIENTACOES-EM-ANDAMENTO': {
            'ORIENTACOES-EM-ANDAMENTO-PARA-POS-DOUTORADO': 'inf',
            'ORIENTACOES-EM-ANDAMENTO-PARA-DOUTORADO': {'ORIENTADOR_PRINCIPAL': 'inf', 'CO_ORIENTADOR': 'inf'},
            'ORIENTACOES-EM-ANDAMENTO-PARA-MESTRADO': {'ORIENTADOR_PRINCIPAL': 'inf', 'CO_ORIENTADOR': 'inf'},
            'OUTRAS-ORIENTACOES-EM-ANDAMENTO': {
                'MONOGRAFIA_DE_CONCLUSAO_DE_CURSO_APERFEICOAMENTO_E_ESPECIALIZACAO': 4,
                'TRABALHO_DE_CONCLUSAO_DE_CURSO_GRADUACAO': 5,
                'INICIACAO_CIENTIFICA': 5,
                'ORIENTACAO-DE-OUTRA-NATUREZA': 0,
            },
        },

    },
    'DADOS-COMPLEMENTARES': {
        'ORIENTACOES-EM-ANDAMENTO': {
            'ORIENTACOES-EM-ANDAMENTO-PARA-POS-DOUTORADO': 'inf',
            'ORIENTACOES-EM-ANDAMENTO-PARA-DOUTORADO': {'ORIENTADOR_PRINCIPAL': 'inf', 'CO_ORIENTADOR': 'inf'},
            'ORIENTACOES-EM-ANDAMENTO-PARA-MESTRADO': {'ORIENTADOR_PRINCIPAL': 'inf', 'CO_ORIENTADOR': 'inf'},
            'OUTRAS-ORIENTACOES-EM-ANDAMENTO': {
                'MONOGRAFIA_DE_CONCLUSAO_DE_CURSO_APERFEICOAMENTO_E_ESPECIALIZACAO': 4,
                'TRABALHO_DE_CONCLUSAO_DE_CURSO_GRADUACAO': 5,
                'INICIACAO_CIENTIFICA': 5,
                'ORIENTACAO-DE-OUTRA-NATUREZA': 0,
            },
        },
    },
}

class Score(object):
    """Pontuação do Currículo Lattes"""
    def __init__(self, xml_file, inicio, fim, area, ano_qualis_periodicos, verbose = 0, debug = False):
        # Período considerado para avaliação
        tree = ET.parse(xml_file)
        root = tree.getroot()
        self.__curriculo = root
        self.__numero_identificador = ''
        self.__nome_completo = ''
        self.__score = 0
        self.__licencas_maternidade = 0
        self.__verbose = verbose
        self.__debug = debug
        self.__ano_inicio = int(inicio)
        self.__ano_fim = int(fim)
        self.__area = area
        self.__ano_qualis_periodicos = ano_qualis_periodicos
        self.__qualis_periodicos = {}
        self.__qualis_periodicos_issn = {}
        self.__tabela_de_qualificacao = {
            'FORMACAO-ACADEMICA-TITULACAO' : {'POS-DOUTORADO': 0, 'LIVRE-DOCENCIA': 0, 'DOUTORADO': 0, 'MESTRADO': 0, 'ESPECIALIZACAO': 0},
            'MEMBRO-DE-CORPO-EDITORIAL' : {'REVISTA': 0},
            'PROJETO-DE-PESQUISA' : {'PESQUISA': 0, 'DESENVOLVIMENTO': 0,'ENSINO': 0,'EXTENSAO':0},
            'PROJETO-DE-PESQUISA-SEM-FOMENTO' : {'PESQUISA': 0, 'DESENVOLVIMENTO': 0,'ENSINO': 0,'EXTENSAO':0},
            'PRODUCAO-BIBLIOGRAFICA' : {
                'ARTIGOS-PUBLICADOS': {'A1': 0, 'A2': 0, 'A3': 0, 'A4': 0, 'B1': 0, 'B2': 0, 'B3': 0, 'B4': 0, 'C': 0, 'NAO-ENCONTRADO': 0},
                'TRABALHOS-EM-EVENTOS': {
                    'INTERNACIONAL': { 'COMPLETO': 0, 'RESUMO_EXPANDIDO': 0, 'RESUMO': 0 },
                    'NACIONAL': { 'COMPLETO': 0, 'RESUMO_EXPANDIDO': 0, 'RESUMO': 0 },
                    'REGIONAL': { 'COMPLETO': 0, 'RESUMO_EXPANDIDO': 0, 'RESUMO': 0 },
                    'LOCAL': { 'COMPLETO': 0, 'RESUMO_EXPANDIDO': 0, 'RESUMO': 0 },
                    'NAO_INFORMADO': { 'COMPLETO': 0, 'RESUMO_EXPANDIDO': 0, 'RESUMO': 0 },
                },
                'LIVROS-E-CAPITULOS': {
                    'LIVRO-PUBLICADO-OU-ORGANIZADO': {
                        'LIVRO_PUBLICADO': 0,
                        'LIVRO_ORGANIZADO_OU_EDICAO': 0,
                        'NAO_INFORMADO': 0,
                    },
                    'CAPITULO-DE-LIVRO-PUBLICADO': 0,
                },
                'DEMAIS-TIPOS-DE-PRODUCAO-BIBLIOGRAFICA': { 'TRADUCAO': 0 },
            },
            'PRODUCAO-TECNICA': {
                'SOFTWARE': 0,
                'PATENTE': {'DEPOSITADA': 0, 'CONCEDIDA': 0},
                'PRODUTO-TECNOLOGICO': 0,
                'PROCESSOS-OU-TECNICAS': 0,
                'TRABALHO-TECNICO': 0,
            },
            'OUTRA-PRODUCAO': {
                'PRODUCAO-ARTISTICA-CULTURAL': {
                    'APRESENTACAO-DE-OBRA-ARTISTICA': 0,
                    'COMPOSICAO-MUSICAL': 0,
                    'OBRA-DE-ARTES-VISUAIS': 0,
                    'MUSICA': 0,
                    'ARTES-CENICAS': 0,
                },
                'ORIENTACOES-CONCLUIDAS': {
                    'ORIENTACOES-CONCLUIDAS-PARA-POS-DOUTORADO': 0,
                    'ORIENTACOES-CONCLUIDAS-PARA-DOUTORADO': {'ORIENTADOR_PRINCIPAL': 0, 'CO_ORIENTADOR': 0},
                    'ORIENTACOES-CONCLUIDAS-PARA-MESTRADO': {'ORIENTADOR_PRINCIPAL': 0, 'CO_ORIENTADOR': 0},
                    'OUTRAS-ORIENTACOES-CONCLUIDAS': {
                        'MONOGRAFIA_DE_CONCLUSAO_DE_CURSO_APERFEICOAMENTO_E_ESPECIALIZACAO': 0,
                        'TRABALHO_DE_CONCLUSAO_DE_CURSO_GRADUACAO': 0,
                        'INICIACAO_CIENTIFICA': 0,
                        'ORIENTACAO-DE-OUTRA-NATUREZA': 0,
                    },
                },
                'ORIENTACOES-EM-ANDAMENTO': {
                    'ORIENTACOES-EM-ANDAMENTO-PARA-POS-DOUTORADO': 0,
                    'ORIENTACOES-EM-ANDAMENTO-PARA-DOUTORADO': {'ORIENTADOR_PRINCIPAL': 0, 'CO_ORIENTADOR': 0},
                    'ORIENTACOES-EM-ANDAMENTO-PARA-MESTRADO': {'ORIENTADOR_PRINCIPAL': 0, 'CO_ORIENTADOR': 0},
                    'OUTRAS-ORIENTACOES-EM-ANDAMENTO': {
                        'MONOGRAFIA_DE_CONCLUSAO_DE_CURSO_APERFEICOAMENTO_E_ESPECIALIZACAO': 0,
                        'TRABALHO_DE_CONCLUSAO_DE_CURSO_GRADUACAO': 0,
                        'INICIACAO_CIENTIFICA': 0,
                        'ORIENTACAO-DE-OUTRA-NATUREZA': 0,
                    },
                },

            },
            'DADOS-COMPLEMENTARES': {
                'ORIENTACOES-EM-ANDAMENTO': {
                    'ORIENTACOES-EM-ANDAMENTO-PARA-POS-DOUTORADO': 0,
                    'ORIENTACOES-EM-ANDAMENTO-PARA-DOUTORADO': {'ORIENTADOR_PRINCIPAL': 0, 'CO_ORIENTADOR': 0},
                    'ORIENTACOES-EM-ANDAMENTO-PARA-MESTRADO': {'ORIENTADOR_PRINCIPAL': 0, 'CO_ORIENTADOR': 0},
                    'OUTRAS-ORIENTACOES-EM-ANDAMENTO': {
                        'MONOGRAFIA_DE_CONCLUSAO_DE_CURSO_APERFEICOAMENTO_E_ESPECIALIZACAO': 0,
                        'TRABALHO_DE_CONCLUSAO_DE_CURSO_GRADUACAO': 0,
                        'INICIACAO_CIENTIFICA': 0,
                        'ORIENTACAO-DE-OUTRA-NATUREZA': 0,
                    },
                },
            },
        }

        # Calcula pontuação do currículo
        self.__dados_gerais()
        self.__formacao_academica_titulacao()
        self.__projetos_de_pesquisa()
        self.__producao_bibliografica()
        self.__producao_tecnica()
        self.__outra_producao()
        self.__membro_de_corpo_editorial()
        self.__pontuacao_acumulada()

    def __pontuacao_acumulada(self):
        self.__score  = sum( self.__tabela_de_qualificacao['FORMACAO-ACADEMICA-TITULACAO'].values() )
        self.__score += sum( self.__tabela_de_qualificacao['PROJETO-DE-PESQUISA'].values() )
        self.__score += sum( self.__tabela_de_qualificacao['PROJETO-DE-PESQUISA-SEM-FOMENTO'].values() )
        self.__score += sum( self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['ARTIGOS-PUBLICADOS'].values() )
        self.__score += sum( self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS']['INTERNACIONAL'].values() )
        self.__score += sum( self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS']['NACIONAL'].values() )
        self.__score += sum( self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS']['REGIONAL'].values() )
        self.__score += sum( self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS']['LOCAL'].values() )
        self.__score += sum( self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS']['NAO_INFORMADO'].values() )
        self.__score += sum( self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['LIVROS-E-CAPITULOS']['LIVRO-PUBLICADO-OU-ORGANIZADO'].values() )
        self.__score += self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['LIVROS-E-CAPITULOS']['CAPITULO-DE-LIVRO-PUBLICADO']
        self.__score += self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['DEMAIS-TIPOS-DE-PRODUCAO-BIBLIOGRAFICA']['TRADUCAO']
        self.__score += self.__tabela_de_qualificacao['PRODUCAO-TECNICA']['SOFTWARE']
        self.__score += sum( self.__tabela_de_qualificacao['PRODUCAO-TECNICA']['PATENTE'].values() )
        self.__score += self.__tabela_de_qualificacao['PRODUCAO-TECNICA']['PRODUTO-TECNOLOGICO']
        self.__score += self.__tabela_de_qualificacao['PRODUCAO-TECNICA']['PROCESSOS-OU-TECNICAS']
        self.__score += self.__tabela_de_qualificacao['PRODUCAO-TECNICA']['TRABALHO-TECNICO']
        self.__score += sum( self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['PRODUCAO-ARTISTICA-CULTURAL'].values() )
        self.__score += self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-CONCLUIDAS']['ORIENTACOES-CONCLUIDAS-PARA-POS-DOUTORADO']
        self.__score += sum( self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-CONCLUIDAS']['ORIENTACOES-CONCLUIDAS-PARA-DOUTORADO'].values() )
        self.__score += sum( self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-CONCLUIDAS']['ORIENTACOES-CONCLUIDAS-PARA-MESTRADO'].values() )
        self.__score += sum( self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-CONCLUIDAS']['OUTRAS-ORIENTACOES-CONCLUIDAS'].values() )
        self.__score += self.__tabela_de_qualificacao['MEMBRO-DE-CORPO-EDITORIAL']['REVISTA']                   
        self.__score += self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-EM-ANDAMENTO']['ORIENTACOES-EM-ANDAMENTO-PARA-POS-DOUTORADO']
        self.__score += sum( self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-EM-ANDAMENTO']['ORIENTACOES-EM-ANDAMENTO-PARA-DOUTORADO'].values() )
        self.__score += sum( self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-EM-ANDAMENTO']['ORIENTACOES-EM-ANDAMENTO-PARA-MESTRADO'].values() )
        self.__score += sum( self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-EM-ANDAMENTO']['OUTRAS-ORIENTACOES-EM-ANDAMENTO'].values() )

    def __dados_gerais(self):
        if 'NUMERO-IDENTIFICADOR' not in self.__curriculo.attrib:
            raise ValueError
        self.__numero_identificador = self.__curriculo.attrib['NUMERO-IDENTIFICADOR']

        dados = self.__curriculo.find('DADOS-GERAIS')
        self.__nome_completo = dados.attrib['NOME-COMPLETO']
        licencas = dados.find('LICENCAS')
        if licencas is not None:
            for licenca in licencas.findall('LICENCA'):
                if licenca.attrib['TIPO-LICENCA'] == 'MATERNIDADE':
                    try:
                        data_licenca = licenca.attrib['DATA-FIM-LICENCA']
                        ano_licenca = datetime.strptime(data_licenca, "%d%m%Y").year
                        #Se a licença for de até 5 anos atrás, considerar tempo adicional
                        if datetime.now().year - ano_licenca <=5:
                            self.__licencas_maternidade += 1
                            self.__ano_inicio = self.__ano_inicio - 2
                    except Exception as e:
                        self.__licencas_maternidade += 0

    def __formacao_academica_titulacao(self):
        dados = self.__curriculo.find('DADOS-GERAIS')
        formacao = dados.find('FORMACAO-ACADEMICA-TITULACAO')

        if formacao is None:
            return

        for key,value in weights['FORMACAO-ACADEMICA-TITULACAO'].items():
            results = formacao.findall(key)
            for result in results:
                if result is None:
                    continue
                if key == 'LIVRE-DOCENCIA': # neste caso, não há STATUS-DO-CURSO
                    self.__tabela_de_qualificacao['FORMACAO-ACADEMICA-TITULACAO'][key] = value
                elif result.attrib['STATUS-DO-CURSO'] == 'CONCLUIDO':
                    current = self.__tabela_de_qualificacao['FORMACAO-ACADEMICA-TITULACAO'][key]
                    weight = weights['FORMACAO-ACADEMICA-TITULACAO'][key]
                    bound = bounds['FORMACAO-ACADEMICA-TITULACAO'][key]
                    self.__tabela_de_qualificacao['FORMACAO-ACADEMICA-TITULACAO'][key] = self.__clamp(current+weight, bound)
                    #self.__tabela_de_qualificacao['FORMACAO-ACADEMICA-TITULACAO'][key] = value

        # Handle master of professional studies
        result = formacao.find('MESTRADO-PROFISSIONALIZANTE')
        if result is None:
            return

        if result.attrib['STATUS-DO-CURSO'] == 'CONCLUIDO':
            self.__tabela_de_qualificacao['FORMACAO-ACADEMICA-TITULACAO']['MESTRADO'] = weights['FORMACAO-ACADEMICA-TITULACAO']['MESTRADO']

    def __projetos_de_pesquisa(self):
        dados = self.__curriculo.find('DADOS-GERAIS')
        if dados.find('ATUACOES-PROFISSIONAIS') is None:
            return

        atuacoes = dados.find('ATUACOES-PROFISSIONAIS').findall('ATUACAO-PROFISSIONAL')
        for atuacao in atuacoes:
            atividade = atuacao.find('ATIVIDADES-DE-PARTICIPACAO-EM-PROJETO')
            if atividade is None:
                continue

            participacoes = atividade.findall('PARTICIPACAO-EM-PROJETO')
            for participacao in participacoes:
                projetos = participacao.findall('PROJETO-DE-PESQUISA')
                if projetos is None:
                    continue

                # O ano de início da participação em um projeto
                inicio_part = int(participacao.attrib['ANO-INICIO'])

                for projeto in projetos:

                    natureza = projeto.attrib['NATUREZA']
                    if natureza not in ['PESQUISA', 'DESENVOLVIMENTO','ENSINO','EXTENSAO']:
                        continue

                    # INICIO: Ignorar projeto ou participação em projeto iniciados após o período estipulado
                    if projeto.attrib['ANO-INICIO'] != "":
                        if int(projeto.attrib['ANO-INICIO']) > self.__ano_fim:
                            continue
                    else:
                        if inicio_part > self.__ano_fim:
                            continue

                    # FIM: Ignorar projeto ou participação em projeto finalizados antes do período estipulado
                    if projeto.attrib['ANO-FIM'] != "":
                        if int(projeto.attrib['ANO-FIM']) < self.__ano_inicio:
                            continue
                    else:
                        if participacao.attrib['ANO-FIM'] != "":
                            fim_part = int(participacao.attrib['ANO-FIM'])
                            if fim_part < self.__ano_inicio:
                                continue

                    # Ignorar se o proponente não for o coordenador do projeto
                    equipe = (projeto.find('EQUIPE-DO-PROJETO')).find('INTEGRANTES-DO-PROJETO')
                    if equipe.attrib['FLAG-RESPONSAVEL'] != str('SIM'):
                        continue

                    # Verifica se o projeto é financiado
                    financiamento = projeto.find('FINANCIADORES-DO-PROJETO')
                    '''
                    if financiamento is None:
                        continue
                    '''
                    # Verifica se há órgão financiador externo, diferente de UFC e UFCA
                    codigos = ['', 'JI7500000002', '001500000997', '008900000002']
                    #financiadores = financiamento.findall('FINANCIADOR-DO-PROJETO')
                    fomento_externo = False
                    if financiamento is not None:
                        financiadores = financiamento.findall('FINANCIADOR-DO-PROJETO')
                        for financiador in financiadores:
                            if financiador.attrib['CODIGO-INSTITUICAO'] not in codigos:
                                fomento_externo = True
                                #break
                    if not fomento_externo:
                        #print("*********VALIDO!!********")
                        #print(projeto.attrib['DESCRICAO-DO-PROJETO'])
                        #print("---")
                        current = self.__tabela_de_qualificacao['PROJETO-DE-PESQUISA-SEM-FOMENTO'][natureza]
                        weight = weights['PROJETO-DE-PESQUISA-SEM-FOMENTO'][natureza]
                        bound = bounds['PROJETO-DE-PESQUISA-SEM-FOMENTO'][natureza]
                        self.__tabela_de_qualificacao['PROJETO-DE-PESQUISA-SEM-FOMENTO'][natureza] = self.__clamp(current+weight, bound)
                    else:
                        #print("*********VALIDO!!********")
                        #print(projeto.attrib['DESCRICAO-DO-PROJETO'])
                        #print("---")
                        current = self.__tabela_de_qualificacao['PROJETO-DE-PESQUISA'][natureza]
                        weight = weights['PROJETO-DE-PESQUISA'][natureza]
                        bound = bounds['PROJETO-DE-PESQUISA'][natureza]
                        self.__tabela_de_qualificacao['PROJETO-DE-PESQUISA'][natureza] = self.__clamp(current+weight, bound)

    def __producao_bibliografica(self):
        producao = self.__curriculo.find('PRODUCAO-BIBLIOGRAFICA')
        if producao is None:
            return

        self.__artigos_publicados(producao)
        self.__trabalhos_em_eventos(producao)
        self.__livros_e_capitulos(producao)
        self.__demais_tipos_de_producao(producao)

    def __artigos_publicados(self, producao):
        artigos = producao.find('ARTIGOS-PUBLICADOS')
        if artigos is None:
            return

        self.__carrega_qualis_periodicos() # load Qualis Periodicos

        for artigo in artigos.findall('ARTIGO-PUBLICADO'):
            dados = artigo.find('DADOS-BASICOS-DO-ARTIGO')
            ano = int(dados.attrib['ANO-DO-ARTIGO'])
            if self.__ano_inicio <= ano <= self.__ano_fim: # somente os artigos durante o período estabelecido
                estrato = self.__get_qualis_periodicos(artigo)
                current = self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['ARTIGOS-PUBLICADOS'][estrato]
                weight = weights['PRODUCAO-BIBLIOGRAFICA']['ARTIGOS-PUBLICADOS'][estrato]
                bound = bounds['PRODUCAO-BIBLIOGRAFICA']['ARTIGOS-PUBLICADOS'][estrato]
                self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['ARTIGOS-PUBLICADOS'][estrato] = self.__clamp(current+weight, bound)

    def __format_area_name(self, area):
        area = area.strip().upper()
        area = str( area )
        area = area.replace('/', '')
        area = area.replace(',', '')
        area = area.replace('  ', ' ') # remove duplicate spaces
        area = area.replace(' ', '_')
        return area.replace('Ç', 'C')

    def __carrega_qualis_periodicos(self):
        WORKING_DIR='/app/modules/'
        QUALIS_FILENAME = WORKING_DIR + 'qualis-periodicos-'+str(self.__ano_qualis_periodicos)+'.csv'
        with open(QUALIS_FILENAME, 'r') as csvfile:
            reader = csv.reader(csvfile, delimiter=',', quotechar='"')
            next(reader) # skip headers

            for row in reader:
                issn = row[0]
                title = str(row[1]).split('(')[0]
                title = title.strip().upper()
                area = row[2]
                estrato = row[3]
                if self.__format_area_name(area) == self.__area:
                    self.__qualis_periodicos[issn] = estrato
                    self.__qualis_periodicos_issn[title] = issn

    # Important: number-only ISSN, i.e., without hyphen.
    def __get_qualis_periodicos_from_issn(self, issn):
        if issn != "":
            if issn in self.__qualis_periodicos:
                return self.__qualis_periodicos[issn]
        return 'NAO-ENCONTRADO'

    def __get_qualis_periodicos_from_title(self, title):
        if title != "" and title != None:
            if self.__debug == 1:
                print ('[' + title + ']')
            if title in self.__qualis_periodicos_issn:
                return self.__qualis_periodicos[ self.__qualis_periodicos_issn[title] ]
        return 'NAO-ENCONTRADO'

    def __get_qualis_periodicos(self, artigo):
        # first, try to extract qualis using the issn from xlm data
        issn = artigo.find('DETALHAMENTO-DO-ARTIGO').attrib['ISSN']
        estrato = self.__get_qualis_periodicos_from_issn(issn[0:4] + '-' + issn[4:])
        if estrato != 'NAO-ENCONTRADO':
            return estrato

        # If you reach here, the issn is not available in Qualis Periodicos.
        # Try to fetch issns from DOI, alternatively.
        if self.__debug == 1:
            print ('ISSN ' + issn + ' not found. Trying to fetch ISSNs from DOI')
        #print self.__nome_completo
        #print self.__numero_identificador
        #print issn
        doi_title = str()
        if 'DOI' in artigo.find('DADOS-BASICOS-DO-ARTIGO').attrib:
            doi = artigo.find('DADOS-BASICOS-DO-ARTIGO').attrib['DOI']
            url = 'https://dx.doi.org/' + doi
            estratos = ['NAO-ENCONTRADO']
            tries = 0
            done = False
            while not done and tries <= 5:
                tries += 1
                r = None
                try:
                    r = requests.get(url, timeout=20,allow_redirects=True)
                except requests.exceptions.RequestException as e:
                    if self.__debug == 1:
                        print('Oops... there\'s a missing Qualis.')

                if r == None:
                    continue

                if r.status_code != 200: # if we've got a error, try again, at most 5 times
                    time.sleep(3.0)
                    continue

                soup = BeautifulSoup(r.text, "html.parser")
                metas = soup.find_all('meta')
                issns = [ meta.attrs['content'] for meta in metas if 'name' in meta.attrs and meta.attrs['name'].upper() == 'CITATION_ISSN' ]
                if self.__debug == 1:
                    print('ISSNs found: ', issns)

                for issn in issns:
                    estratos.append(self.__get_qualis_periodicos_from_issn(issn))

                titles = [ meta.attrs['content'] for meta in metas if 'name' in meta.attrs and meta.attrs['name'].upper() == 'CITATION_JOURNAL_TITLE' ]
                if len(titles) > 0:
                    doi_title = titles[0]
                    doi_title = str( doi_title )
                    doi_title = doi_title.strip().upper()
                done = True
            estrato = min(estratos)
        else:
            print ('DOI does not exist.')

        # Last try.
        # We will search the article by the journal title.
        estratos = ['NAO-ENCONTRADO']
        if estrato == 'NAO-ENCONTRADO':
            if self.__debug == 1:
                print ('Trying to find Qualis by title...')
            title = str( (artigo.find('DETALHAMENTO-DO-ARTIGO').attrib['TITULO-DO-PERIODICO-OU-REVISTA']) ).split('(')[0]
            title = title.strip().upper()
            estratos.append( self.__get_qualis_periodicos_from_title(title) )
            estratos.append( self.__get_qualis_periodicos_from_title(doi_title) )
            estrato = min(estratos)


            if self.__debug == 1:
                if estrato == 'NAO-ENCONTRADO':
                    print ('Title not found: ' + title + '\n')
                else:
                    print ('Success. Qualis = ' + estrato + '\n')

        return estrato

    def __clamp(self,x,upper):
        return max(min(float(upper),x), 0)

    def __trabalhos_em_eventos(self, producao):
        trabalhos = producao.find('TRABALHOS-EM-EVENTOS')
        if trabalhos is None:
            return
        for trabalho in trabalhos.findall('TRABALHO-EM-EVENTOS'):
            ano = int(trabalho.find('DADOS-BASICOS-DO-TRABALHO').attrib['ANO-DO-TRABALHO'])
            if ano < self.__ano_inicio or ano > self.__ano_fim: # skip papers out-of-period
                continue

            abrangencia = trabalho.find('DETALHAMENTO-DO-TRABALHO').attrib['CLASSIFICACAO-DO-EVENTO']
            natureza = trabalho.find('DADOS-BASICOS-DO-TRABALHO').attrib['NATUREZA']

            current = self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS'][abrangencia][natureza]
            weight = weights['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS'][abrangencia][natureza]
            bound = bounds['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS'][abrangencia][natureza]
            self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS'][abrangencia][natureza] = self.__clamp(current+weight, bound)

    def __livros_e_capitulos(self, producao):
        itens = producao.find('LIVROS-E-CAPITULOS')
        if itens is None:
            return
        livros = itens.find('LIVROS-PUBLICADOS-OU-ORGANIZADOS')
        if livros != None:
            for livro in livros.findall('LIVRO-PUBLICADO-OU-ORGANIZADO'):
                ano = int(livro.find('DADOS-BASICOS-DO-LIVRO').attrib['ANO'])
                if ano < self.__ano_inicio or ano > self.__ano_fim: # skip out-of-allowed-period production
                    continue
                if livro.find('DETALHAMENTO-DO-LIVRO').attrib['NUMERO-DE-PAGINAS'] == "":
                    continue
                try:
                    paginas = int(livro.find('DETALHAMENTO-DO-LIVRO').attrib['NUMERO-DE-PAGINAS'])
                except ValueError:
                    paginas = 0
                if paginas > 49: # número mínimo de páginas para livros publicados e traduções
                    tipo = livro.find('DADOS-BASICOS-DO-LIVRO').attrib['TIPO']

                    current = self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['LIVROS-E-CAPITULOS']['LIVRO-PUBLICADO-OU-ORGANIZADO'][tipo]
                    weight = weights['PRODUCAO-BIBLIOGRAFICA']['LIVROS-E-CAPITULOS']['LIVRO-PUBLICADO-OU-ORGANIZADO'][tipo]
                    bound = bounds['PRODUCAO-BIBLIOGRAFICA']['LIVROS-E-CAPITULOS']['LIVRO-PUBLICADO-OU-ORGANIZADO'][tipo]

                    self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['LIVROS-E-CAPITULOS']['LIVRO-PUBLICADO-OU-ORGANIZADO'][tipo] = self.__clamp(current+weight, bound)

        capitulos = itens.find('CAPITULOS-DE-LIVROS-PUBLICADOS')
        if capitulos != None:
            for capitulo in capitulos.findall('CAPITULO-DE-LIVRO-PUBLICADO'):
                if capitulo.find('DADOS-BASICOS-DO-CAPITULO').attrib['ANO'] == "":
                    continue
                ano = int(capitulo.find('DADOS-BASICOS-DO-CAPITULO').attrib['ANO'])
                if ano < self.__ano_inicio or ano > self.__ano_fim: # skip out-of-allowed-period production
                    continue

                current = self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['LIVROS-E-CAPITULOS']['CAPITULO-DE-LIVRO-PUBLICADO']
                weight = weights['PRODUCAO-BIBLIOGRAFICA']['LIVROS-E-CAPITULOS']['CAPITULO-DE-LIVRO-PUBLICADO']
                bound = bounds['PRODUCAO-BIBLIOGRAFICA']['LIVROS-E-CAPITULOS']['CAPITULO-DE-LIVRO-PUBLICADO']

                self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['LIVROS-E-CAPITULOS']['CAPITULO-DE-LIVRO-PUBLICADO'] = self.__clamp(current+weight, bound)

    def __demais_tipos_de_producao(self, producao):
        itens = producao.find('DEMAIS-TIPOS-DE-PRODUCAO-BIBLIOGRAFICA')
        if itens is None:
            return
        traducoes = itens.findall('TRADUCAO')
        for traducao in traducoes:
            ano = int(traducao.find('DADOS-BASICOS-DA-TRADUCAO').attrib['ANO'])
            if ano < self.__ano_inicio or ano > self.__ano_fim: # skip out-of-allowed-period production
                continue
            if traducao.find('DETALHAMENTO-DA-TRADUCAO').attrib['NUMERO-DE-PAGINAS'] == "":
                continue
            paginas = int(traducao.find('DETALHAMENTO-DA-TRADUCAO').attrib['NUMERO-DE-PAGINAS'])
            if paginas > 49: # número mínimo de páginas para livros publicados e traduções
                current = self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['DEMAIS-TIPOS-DE-PRODUCAO-BIBLIOGRAFICA']['TRADUCAO']
                weight = weights['PRODUCAO-BIBLIOGRAFICA']['DEMAIS-TIPOS-DE-PRODUCAO-BIBLIOGRAFICA']['TRADUCAO']
                bound = bounds['PRODUCAO-BIBLIOGRAFICA']['DEMAIS-TIPOS-DE-PRODUCAO-BIBLIOGRAFICA']['TRADUCAO']

                self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['DEMAIS-TIPOS-DE-PRODUCAO-BIBLIOGRAFICA']['TRADUCAO'] = self.__clamp(current+weight, bound)

    def __producao_tecnica(self):
        producao = self.__curriculo.find('PRODUCAO-TECNICA')
        if producao is None:
            return

        self.__softwares(producao)
        self.__patentes(producao)
        self.__produtos_tecnologicos(producao)
        self.__processos_ou_tecnicas(producao)
        self.__trabalho_tecnico(producao)

    def __softwares(self, producao):
        softwares = producao.findall('SOFTWARE')
        if softwares is None:
            return
        for software in softwares:
            dados = software.find('DADOS-BASICOS-DO-SOFTWARE')
            ano = dados.attrib['ANO']
            if ano == "":
                continue
            elif self.__ano_inicio <= int(ano) <= self.__ano_fim: # somente os artigos dirante o período estipulado
                current = self.__tabela_de_qualificacao['PRODUCAO-TECNICA']['SOFTWARE']
                weight = weights['PRODUCAO-TECNICA']['SOFTWARE']
                bound = bounds['PRODUCAO-TECNICA']['SOFTWARE']

                self.__tabela_de_qualificacao['PRODUCAO-TECNICA']['SOFTWARE'] = self.__clamp(current+weight, bound)

    def __patentes(self, producao):
        patentes = producao.findall('PATENTE')
        if patentes is None:
            return
        for patente in patentes:
            detalhamento = patente.find('DETALHAMENTO-DA-PATENTE')
            registro = detalhamento.find('REGISTRO-OU-PATENTE')
            deposito = (registro.attrib['DATA-PEDIDO-DE-DEPOSITO'])[4:]
            concessao = (registro.attrib['DATA-DE-CONCESSAO'])[4:]
            if concessao != "":
                if self.__ano_inicio <= int(concessao) <= self.__ano_fim:
                    current = self.__tabela_de_qualificacao['PRODUCAO-TECNICA']['PATENTE']['CONCEDIDA']
                    weight = weights['PRODUCAO-TECNICA']['PATENTE']['CONCEDIDA']
                    bound = bounds['PRODUCAO-TECNICA']['PATENTE']['CONCEDIDA']
                    self.__tabela_de_qualificacao['PRODUCAO-TECNICA']['PATENTE']['CONCEDIDA'] = self.__clamp(current+weight, bound)
            elif deposito != "":
                if self.__ano_inicio <= int(deposito) <= self.__ano_fim:
                    current = self.__tabela_de_qualificacao['PRODUCAO-TECNICA']['PATENTE']['DEPOSITADA']
                    weight = weights['PRODUCAO-TECNICA']['PATENTE']['DEPOSITADA']
                    bound = bounds['PRODUCAO-TECNICA']['PATENTE']['DEPOSITADA']
                    self.__tabela_de_qualificacao['PRODUCAO-TECNICA']['PATENTE']['DEPOSITADA'] = self.__clamp(current+weight, bound)

    def __produtos_tecnologicos(self, producao):
        produtos = producao.findall('PRODUTO-TECNOLOGICO')
        if produtos is None:
            return
        for produto in produtos:
            dados = produto.find('DADOS-BASICOS-DO-PRODUTO-TECNOLOGICO')
            ano = dados.attrib['ANO']
            if ano == "":
                continue

            if self.__ano_inicio <= int(ano) <= self.__ano_fim:
                current = self.__tabela_de_qualificacao['PRODUCAO-TECNICA']['PRODUTO-TECNOLOGICO']
                weight = weights['PRODUCAO-TECNICA']['PRODUTO-TECNOLOGICO']
                bound = bounds['PRODUCAO-TECNICA']['PRODUTO-TECNOLOGICO']
                self.__tabela_de_qualificacao['PRODUCAO-TECNICA']['PRODUTO-TECNOLOGICO'] = self.__clamp(current+weight, bound)

    def __processos_ou_tecnicas(self, producao):
        processos = producao.findall('PROCESSOS-OU-TECNICAS')
        if processos is None:
            return
        for processo in processos:
            dados = processo.find('DADOS-BASICOS-DO-PROCESSOS-OU-TECNICAS')
            ano = dados.attrib['ANO']
            if ano == "":
                continue

            if self.__ano_inicio <= int(ano) <= self.__ano_fim:
                current = self.__tabela_de_qualificacao['PRODUCAO-TECNICA']['PROCESSOS-OU-TECNICAS']
                weight = weights['PRODUCAO-TECNICA']['PROCESSOS-OU-TECNICAS']
                bound = bounds['PRODUCAO-TECNICA']['PROCESSOS-OU-TECNICAS']
                self.__tabela_de_qualificacao['PRODUCAO-TECNICA']['PROCESSOS-OU-TECNICAS'] = self.__clamp(current+weight, bound)

    def __trabalho_tecnico(self, producao):
        trabalhos = producao.findall('TRABALHO-TECNICO')
        if trabalhos is None:
            return
        for trabalho in trabalhos:
            dados = trabalho.find('DADOS-BASICOS-DO-TRABALHO-TECNICO')
            ano = dados.attrib['ANO']
            if ano == "":
                continue

            if self.__ano_inicio <= int(ano) <= self.__ano_fim:
                current = self.__tabela_de_qualificacao['PRODUCAO-TECNICA']['TRABALHO-TECNICO']
                weight = weights['PRODUCAO-TECNICA']['TRABALHO-TECNICO']
                bound = bounds['PRODUCAO-TECNICA']['TRABALHO-TECNICO']
                self.__tabela_de_qualificacao['PRODUCAO-TECNICA']['TRABALHO-TECNICO'] = self.__clamp(current+weight, bound)

    def __outra_producao(self):
        producao = self.__curriculo.find('OUTRA-PRODUCAO')
        producao_em_andamento = self.__curriculo.find('DADOS-COMPLEMENTARES')
        '''
        for p in producao:
            print(p)
        '''
        if producao is None:
            return

        if self.__area == 'ARTES': # only counts for arts and musics projects
            self.__producao_artistica_cultural(producao)
        self.__orientacoes_concluidas(producao)
        self.__orientacoes_em_andamento(producao_em_andamento)

    def __producao_artistica_cultural(self, producao):
        obras = producao.find('PRODUCAO-ARTISTICA-CULTURAL')
        if obras is None:
            return

        self.__apresentacao_de_obra_artistica(obras)
        self.__composicao_musical(obras)
        self.__musica(obras)
        self.__obra_de_artes_visuais(obras)
        self.__artes_cenicas(obras)

    def __apresentacao_de_obra_artistica(self, obras):
        apresentacoes = obras.findall('APRESENTACAO-DE-OBRA-ARTISTICA')
        if apresentacoes is None:
            return

        for apresentacao in apresentacoes:
            dados = apresentacao.find('DADOS-BASICOS-DA-APRESENTACAO-DE-OBRA-ARTISTICA')
            ano = dados.attrib['ANO']
            if ano == "":
                continue

            if self.__ano_inicio <= int(ano) <= self.__ano_fim:
                current = self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['PRODUCAO-ARTISTICA-CULTURAL']['APRESENTACAO-DE-OBRA-ARTISTICA']
                weight = weights['OUTRA-PRODUCAO']['PRODUCAO-ARTISTICA-CULTURAL']['APRESENTACAO-DE-OBRA-ARTISTICA']
                bound = bounds['OUTRA-PRODUCAO']['PRODUCAO-ARTISTICA-CULTURAL']['APRESENTACAO-DE-OBRA-ARTISTICA']
                self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['PRODUCAO-ARTISTICA-CULTURAL']['APRESENTACAO-DE-OBRA-ARTISTICA'] = self.__clamp(current+weight, bound)

    def __composicao_musical(self, obras):
        composicoes = obras.findall('COMPOSICAO-MUSICAL')
        if composicoes is None:
            return

        for composicao in composicoes:
            dados = composicao.find('DADOS-BASICOS-DA-COMPOSICAO-MUSICAL')
            ano = dados.attrib['ANO']
            if ano == "":
                continue

            if self.__ano_inicio <= int(ano) <= self.__ano_fim:
                current = self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['PRODUCAO-ARTISTICA-CULTURAL']['COMPOSICAO-MUSICAL']
                weight = weights['OUTRA-PRODUCAO']['PRODUCAO-ARTISTICA-CULTURAL']['COMPOSICAO-MUSICAL']
                bound = bounds['OUTRA-PRODUCAO']['PRODUCAO-ARTISTICA-CULTURAL']['COMPOSICAO-MUSICAL']
                self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['PRODUCAO-ARTISTICA-CULTURAL']['COMPOSICAO-MUSICAL'] = self.__clamp(current+weight, bound)

    def __musica(self, obras):
        composicoes = obras.findall('MUSICA')
        if composicoes is None:
            return

        for composicao in composicoes:
            dados = composicao.find('DADOS-BASICOS-DA-MUSICA')
            ano = dados.attrib['ANO']
            if ano == "":
                continue

            if self.__ano_inicio <= int(ano) <= self.__ano_fim:
                current = self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['PRODUCAO-ARTISTICA-CULTURAL']['MUSICA']
                weight = weights['OUTRA-PRODUCAO']['PRODUCAO-ARTISTICA-CULTURAL']['MUSICA']
                bound = bounds['OUTRA-PRODUCAO']['PRODUCAO-ARTISTICA-CULTURAL']['MUSICA']
                self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['PRODUCAO-ARTISTICA-CULTURAL']['MUSICA'] = self.__clamp(current+weight, bound)

    def __artes_cenicas(self, obras):
        composicoes = obras.findall('ARTES-CENICAS')
        if composicoes is None:
            return

        for composicao in composicoes:
            dados = composicao.find('DADOS-BASICOS-DE-ARTES-CENICAS')
            ano = dados.attrib['ANO']
            if ano == "":
                continue

            if self.__ano_inicio <= int(ano) <= self.__ano_fim:
                current = self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['PRODUCAO-ARTISTICA-CULTURAL']['ARTES-CENICAS']
                weight = weights['OUTRA-PRODUCAO']['PRODUCAO-ARTISTICA-CULTURAL']['ARTES-CENICAS']
                bound = bounds['OUTRA-PRODUCAO']['PRODUCAO-ARTISTICA-CULTURAL']['ARTES-CENICAS']
                self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['PRODUCAO-ARTISTICA-CULTURAL']['ARTES-CENICAS'] = self.__clamp(current+weight, bound)


    def __obra_de_artes_visuais(self, obras):
        artes = obras.findall('OBRA-DE-ARTES-VISUAIS')
        if artes is None:
            return

        for arte in artes:
            dados = arte.find('DADOS-BASICOS-DA-OBRA-DE-ARTES-VISUAIS')
            ano = dados.attrib['ANO']
            if ano == "":
                continue

            if self.__ano_inicio <= int(ano) <= self.__ano_fim:
                current = self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['PRODUCAO-ARTISTICA-CULTURAL']['OBRA-DE-ARTES-VISUAIS']
                weight = weights['OUTRA-PRODUCAO']['PRODUCAO-ARTISTICA-CULTURAL']['OBRA-DE-ARTES-VISUAIS']
                bound = bounds['OUTRA-PRODUCAO']['PRODUCAO-ARTISTICA-CULTURAL']['OBRA-DE-ARTES-VISUAIS']
                self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['PRODUCAO-ARTISTICA-CULTURAL']['OBRA-DE-ARTES-VISUAIS'] = self.__clamp(current+weight, bound)

    def __orientacoes_concluidas(self, producao,situacao='CONCLUIDAS'):
        orientacoes = producao.find('ORIENTACOES-' + situacao)

        if orientacoes is None:
            return

        self.__orientacoes_pos_doutorado(orientacoes)
        self.__orientacoes_doutorado(orientacoes)
        self.__orientacoes_mestrado(orientacoes)
        self.__outras_orientacoes_concluidas(orientacoes)

    def __orientacoes_em_andamento(self, producao,situacao="EM-ANDAMENTO"):
        orientacoes = producao.find('ORIENTACOES-' + situacao)
        if orientacoes is None:
            return

        self.__orientacoes_pos_doutorado(orientacoes,"EM-ANDAMENTO")
        self.__orientacoes_doutorado(orientacoes,"EM-ANDAMENTO")
        self.__orientacoes_mestrado(orientacoes,"EM-ANDAMENTO")
        self.__outras_orientacoes_em_andamento(orientacoes,"EM-ANDAMENTO")

    def __orientacoes_pos_doutorado(self, orientacoes,situacao='CONCLUIDAS'):
        if situacao=='CONCLUIDAS':
            postdocs = orientacoes.findall('ORIENTACOES-' + situacao + '-PARA-POS-DOUTORADO')
        else:
            postdocs = orientacoes.findall('ORIENTACAO-' + situacao + '-DE-POS-DOUTORADO')

        if postdocs is None:
            return

        for postdoc in postdocs:
            if situacao=='CONCLUIDAS':
                dados = postdoc.find('DADOS-BASICOS-DE-ORIENTACOES-' + situacao + '-PARA-POS-DOUTORADO')
            else:
                dados = postdoc.find('DADOS-BASICOS-DA-ORIENTACAO-' + situacao + '-DE-POS-DOUTORADO')
            ano = dados.attrib['ANO']
            if ano == "":
                continue

            if self.__ano_inicio <= int(ano) <= self.__ano_fim:

                current = self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['ORIENTACOES-' + situacao + '-PARA-POS-DOUTORADO']
                weight = weights['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['ORIENTACOES-' + situacao + '-PARA-POS-DOUTORADO']
                bound = bounds['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['ORIENTACOES-' + situacao + '-PARA-POS-DOUTORADO']
                self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['ORIENTACOES-' + situacao + '-PARA-POS-DOUTORADO'] = self.__clamp(current+weight, bound)

    def __orientacoes_doutorado(self, orientacoes,situacao='CONCLUIDAS'):
        if situacao=='CONCLUIDAS':
            doutores = orientacoes.findall('ORIENTACOES-' + situacao + '-PARA-DOUTORADO')
        else:
            doutores = orientacoes.findall('ORIENTACAO-' + situacao + '-DE-DOUTORADO')
        if doutores is None:
            return

        for doutor in doutores:
            if situacao=='CONCLUIDAS':
                dados = doutor.find('DADOS-BASICOS-DE-ORIENTACOES-' + situacao + '-PARA-DOUTORADO')
            else:
                dados = doutor.find('DADOS-BASICOS-DA-ORIENTACAO-' + situacao + '-DE-DOUTORADO')
            ano = dados.attrib['ANO']
            if ano == "":
                continue

            if self.__ano_inicio <= int(ano) <= self.__ano_fim:
                if situacao=='CONCLUIDAS':

                    detalhamento = doutor.find('DETALHAMENTO-DE-ORIENTACOES-' + situacao + '-PARA-DOUTORADO')
                    tipo = detalhamento.attrib['TIPO-DE-ORIENTACAO']
                    current = self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['ORIENTACOES-' + situacao + '-PARA-DOUTORADO'][tipo]
                    weight = weights['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['ORIENTACOES-' + situacao + '-PARA-DOUTORADO'][tipo]
                    bound = bounds['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['ORIENTACOES-' + situacao + '-PARA-DOUTORADO'][tipo]
                    self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['ORIENTACOES-' + situacao + '-PARA-DOUTORADO'][tipo] = self.__clamp(current+weight, bound)
                else:

                    detalhamento = doutor.find('DETALHAMENTO-DA-ORIENTACAO-' + situacao + '-DE-DOUTORADO')
                    tipo = detalhamento.attrib['TIPO-DE-ORIENTACAO']
                    current = self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['ORIENTACOES-' + situacao + '-PARA-DOUTORADO'][tipo]
                    weight = weights['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['ORIENTACOES-' + situacao + '-PARA-DOUTORADO'][tipo]
                    bound = bounds['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['ORIENTACOES-' + situacao + '-PARA-DOUTORADO'][tipo]
                    self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['ORIENTACOES-' + situacao + '-PARA-DOUTORADO'][tipo] = self.__clamp(current+weight, bound)

    def __orientacoes_mestrado(self, orientacoes,situacao='CONCLUIDAS'):
        if situacao=='CONCLUIDAS':
            mestres = orientacoes.findall('ORIENTACOES-' + situacao + '-PARA-MESTRADO')
        else:
            mestres = orientacoes.findall('ORIENTACAO-' + situacao + '-DE-MESTRADO')
        if mestres is None:
            return

        for mestre in mestres:
            if situacao=='CONCLUIDAS':
                dados = mestre.find('DADOS-BASICOS-DE-ORIENTACOES-' + situacao + '-PARA-MESTRADO')
            else:
                dados = mestre.find('DADOS-BASICOS-DA-ORIENTACAO-' + situacao + '-DE-MESTRADO')
            ano = dados.attrib['ANO']
            if ano == "":
                continue

            if self.__ano_inicio <= int(ano) <= self.__ano_fim:
                if situacao=='CONCLUIDAS':

                    detalhamento = mestre.find('DETALHAMENTO-DE-ORIENTACOES-' + situacao + '-PARA-MESTRADO')
                    tipo = detalhamento.attrib['TIPO-DE-ORIENTACAO']
                    current = self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['ORIENTACOES-' + situacao + '-PARA-MESTRADO'][tipo]
                    weight = weights['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['ORIENTACOES-' + situacao + '-PARA-MESTRADO'][tipo]
                    bound = bounds['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['ORIENTACOES-' + situacao + '-PARA-MESTRADO'][tipo]
                    self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['ORIENTACOES-' + situacao + '-PARA-MESTRADO'][tipo] = self.__clamp(current+weight, bound)
                else:

                    detalhamento = mestre.find('DETALHAMENTO-DA-ORIENTACAO-' + situacao + '-DE-MESTRADO')
                    tipo = detalhamento.attrib['TIPO-DE-ORIENTACAO']
                    current = self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['ORIENTACOES-' + situacao + '-PARA-MESTRADO'][tipo]
                    weight = weights['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['ORIENTACOES-' + situacao + '-PARA-MESTRADO'][tipo]
                    bound = bounds['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['ORIENTACOES-' + situacao + '-PARA-MESTRADO'][tipo]
                    self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['ORIENTACOES-' + situacao + '-PARA-MESTRADO'][tipo] = self.__clamp(current+weight, bound)

    def __outras_orientacoes_concluidas(self, orientacoes,situacao='CONCLUIDAS'):
        estudantes = orientacoes.findall('OUTRAS-ORIENTACOES-CONCLUIDAS')
        if estudantes is None:
            return

        for estudante in estudantes:
            dados = estudante.find('DADOS-BASICOS-DE-OUTRAS-ORIENTACOES-CONCLUIDAS')
            ano = dados.attrib['ANO']
            #titulo = dados.attrib['TITULO']
            #print(titulo)
            if ano == "":
                continue

            if self.__ano_inicio <= int(ano) <= self.__ano_fim:
                natureza = dados.attrib['NATUREZA']
                current = self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['OUTRAS-ORIENTACOES-' + situacao][natureza]
                weight = weights['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['OUTRAS-ORIENTACOES-' + situacao][natureza]
                bound = bounds['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['OUTRAS-ORIENTACOES-' + situacao][natureza]
                self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['OUTRAS-ORIENTACOES-' + situacao][natureza] = self.__clamp(current+weight, bound)

    def __outras_orientacoes_em_andamento(self, orientacoes,situacao='EM-ANDAMENTO'):
        #********** INICIAÇÃO CIENTÍFICA ***************
        estudantes = orientacoes.findall('ORIENTACAO-EM-ANDAMENTO-DE-INICIACAO-CIENTIFICA')
        if estudantes is None:
            return

        for estudante in estudantes:
            dados = estudante.find('DADOS-BASICOS-DA-ORIENTACAO-EM-ANDAMENTO-DE-INICIACAO-CIENTIFICA')
            ano = dados.attrib['ANO']
            if ano == "":
                continue

            if self.__ano_inicio <= int(ano) <= self.__ano_fim:
                current = self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['OUTRAS-ORIENTACOES-' + situacao]['INICIACAO_CIENTIFICA']
                weight = weights['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['OUTRAS-ORIENTACOES-' + situacao]['INICIACAO_CIENTIFICA']
                bound = bounds['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['OUTRAS-ORIENTACOES-' + situacao]['INICIACAO_CIENTIFICA']
                self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['OUTRAS-ORIENTACOES-' + situacao]['INICIACAO_CIENTIFICA'] = self.__clamp(current+weight, bound)

        #********** GRADUAÇÃO - TCC ***************
        estudantes = orientacoes.findall('ORIENTACAO-EM-ANDAMENTO-DE-GRADUACAO')
        if estudantes is None:
            return

        for estudante in estudantes:
            dados = estudante.find('DADOS-BASICOS-DA-ORIENTACAO-EM-ANDAMENTO-DE-GRADUACAO')
            ano = dados.attrib['ANO']
            if ano == "":
                continue

            if self.__ano_inicio <= int(ano) <= self.__ano_fim:
                current = self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['OUTRAS-ORIENTACOES-' + situacao]['TRABALHO_DE_CONCLUSAO_DE_CURSO_GRADUACAO']
                weight = weights['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['OUTRAS-ORIENTACOES-' + situacao]['TRABALHO_DE_CONCLUSAO_DE_CURSO_GRADUACAO']
                bound = bounds['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['OUTRAS-ORIENTACOES-' + situacao]['TRABALHO_DE_CONCLUSAO_DE_CURSO_GRADUACAO']
                self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-' + situacao]['OUTRAS-ORIENTACOES-' + situacao]['TRABALHO_DE_CONCLUSAO_DE_CURSO_GRADUACAO'] = self.__clamp(current+weight, bound)

    def __membro_de_corpo_editorial(self):
        dados = self.__curriculo.find('DADOS-GERAIS')
        editorial = dados.find('ATUACOES-PROFISSIONAIS')

        for item in editorial:

            nome = item.attrib['NOME-INSTITUICAO']

            vinculos = item.findall('VINCULOS')
            if vinculos is None:
                continue

            for vinculo in vinculos:
                if vinculo.attrib['OUTRO-VINCULO-INFORMADO']=='Membro de corpo editorial':
                    ano = vinculo.attrib['ANO-FIM']
                    if ano!="":
                        ano = int(ano)
                    else:
                        ano = 0
                    if (self.__ano_inicio <= int(ano) <= self.__ano_fim) or (ano==0):
                        current = self.__tabela_de_qualificacao['MEMBRO-DE-CORPO-EDITORIAL']['REVISTA']
                        weight = weights['MEMBRO-DE-CORPO-EDITORIAL']['REVISTA']
                        bound = bounds['MEMBRO-DE-CORPO-EDITORIAL']['REVISTA']
                        self.__tabela_de_qualificacao['MEMBRO-DE-CORPO-EDITORIAL']['REVISTA'] = self.__clamp(current+weight, bound)
                    break


    def get_name(self):
        return self.__nome_completo

    def get_lattes_id(self):
        return self.__numero_identificador

    def get_detailed_score(self):
        return self.__tabela_de_qualificacao

    def get_score(self):
        return self.__score

    def sumario(self):
        resultado = ""
        resultado = resultado + "<h2>DADOS PESSOAIS</h2><BR>\n"
        resultado = resultado +  self.__nome_completo + "<BR>\n"
        resultado = resultado +  "ID Lattes: " + self.__numero_identificador + "<BR>\n"
        resultado = resultado +  "Area de avaliacao: " + self.__area + "<BR>\n"
        resultado = resultado +  "Ano de inicio: " + str(self.__ano_inicio) + "<BR>\n"
        resultado = resultado +  "Ano de fim: " + str(self.__ano_fim) + "<BR>\n"
        if (self.__licencas_maternidade!=0):
            resultado = resultado + "Quantidade de Licenças (maternidade) nos últimos 5 anos: " + str(self.__licencas_maternidade) + "<BR>\n"
            resultado = resultado + "Tempo adicional: " + str(self.__licencas_maternidade*2) + " anos <BR>\n"
        
        resultado = resultado + "<h2>1 - FORMAÇÃO ACADEMICA</h2><BR>\n"
        resultado = resultado +  "POS-DOUTORADO:                       " + str(self.__tabela_de_qualificacao['FORMACAO-ACADEMICA-TITULACAO']['POS-DOUTORADO']) + "<BR>\n"
        resultado = resultado +  "LIVRE-DOCENCIA:                      "  + str(self.__tabela_de_qualificacao['FORMACAO-ACADEMICA-TITULACAO']['LIVRE-DOCENCIA'])  + "<BR>\n"
        resultado = resultado +  "DOUTORADO:                           "  + str(self.__tabela_de_qualificacao['FORMACAO-ACADEMICA-TITULACAO']['DOUTORADO'])  + "<BR>\n"
        resultado = resultado +  "MESTRADO:                            "  + str(self.__tabela_de_qualificacao['FORMACAO-ACADEMICA-TITULACAO']['MESTRADO'])  + "<BR>\n"
        resultado = resultado +  "ESPECIALIZACAO:                            "  + str(self.__tabela_de_qualificacao['FORMACAO-ACADEMICA-TITULACAO']['ESPECIALIZACAO'])  + "<BR>\n"
        subtotal = self.__tabela_de_qualificacao['FORMACAO-ACADEMICA-TITULACAO']['POS-DOUTORADO'] + self.__tabela_de_qualificacao['FORMACAO-ACADEMICA-TITULACAO']['DOUTORADO'] + self.__tabela_de_qualificacao['FORMACAO-ACADEMICA-TITULACAO']['LIVRE-DOCENCIA']
        subtotal = subtotal + self.__tabela_de_qualificacao['FORMACAO-ACADEMICA-TITULACAO']['MESTRADO'] + self.__tabela_de_qualificacao['FORMACAO-ACADEMICA-TITULACAO']['ESPECIALIZACAO']
        resultado = resultado +  "<h4>sub-total:       "  + str(subtotal) + "</h4><BR>\n"

        resultado = resultado + "<h2>2.2 - ATIVIDADES DE PARTICIPAÇÃO EM PROJETO</h2><BR>\n"
        resultado = resultado +  "PROJETO-DE-PESQUISA-COM-FOMENTO-EXTERNO:                 "  + str(self.__tabela_de_qualificacao['PROJETO-DE-PESQUISA']['PESQUISA'])  + "<BR>\n"
        resultado = resultado +  "PROJETO-DE-DESENVOLVIMENTO-COM-FOMENTO-EXTERNO:          "  + str(self.__tabela_de_qualificacao['PROJETO-DE-PESQUISA']['DESENVOLVIMENTO'])  + "<BR>\n"
        resultado = resultado +  "PROJETO-DE-ENSINO-COM-FOMENTO-EXTERNO:          "  + str(self.__tabela_de_qualificacao['PROJETO-DE-PESQUISA']['ENSINO'])  + "<BR>\n"
        resultado = resultado +  "PROJETO-DE-EXTENSAO-COM-FOMENTO-EXTERNO:          "  + str(self.__tabela_de_qualificacao['PROJETO-DE-PESQUISA']['EXTENSAO'])  + "<BR>\n"
        resultado = resultado +  "PROJETO-DE-PESQUISA-SEM-FOMENTO-EXTERNO:                 "  + str(self.__tabela_de_qualificacao['PROJETO-DE-PESQUISA-SEM-FOMENTO']['PESQUISA'])  + "<BR>\n"
        resultado = resultado +  "PROJETO-DE-DESENVOLVIMENTO-SEM-FOMENTO-EXTERNO:          "  + str(self.__tabela_de_qualificacao['PROJETO-DE-PESQUISA-SEM-FOMENTO']['DESENVOLVIMENTO'])  + "<BR>\n"
        resultado = resultado +  "PROJETO-DE-ENSINO-SEM-FOMENTO-EXTERNO:          "  + str(self.__tabela_de_qualificacao['PROJETO-DE-PESQUISA-SEM-FOMENTO']['ENSINO'])  + "<BR>\n"
        resultado = resultado +  "PROJETO-DE-EXTENSAO-SEM-FOMENTO-EXTERNO:          "  + str(self.__tabela_de_qualificacao['PROJETO-DE-PESQUISA-SEM-FOMENTO']['EXTENSAO'])  + "<BR>\n"
        subtotal = self.__tabela_de_qualificacao['PROJETO-DE-PESQUISA']['PESQUISA'] + self.__tabela_de_qualificacao['PROJETO-DE-PESQUISA']['DESENVOLVIMENTO'] + self.__tabela_de_qualificacao['PROJETO-DE-PESQUISA']['ENSINO']
        subtotal = subtotal + self.__tabela_de_qualificacao['PROJETO-DE-PESQUISA']['EXTENSAO'] + self.__tabela_de_qualificacao['PROJETO-DE-PESQUISA-SEM-FOMENTO']['PESQUISA'] + self.__tabela_de_qualificacao['PROJETO-DE-PESQUISA-SEM-FOMENTO']['DESENVOLVIMENTO']
        subtotal = subtotal + self.__tabela_de_qualificacao['PROJETO-DE-PESQUISA-SEM-FOMENTO']['ENSINO'] + self.__tabela_de_qualificacao['PROJETO-DE-PESQUISA-SEM-FOMENTO']['EXTENSAO']
        resultado = resultado +  "<h4>sub-total:       "  + str(subtotal) + "</h4><BR>\n"

        resultado = resultado + "<h2>2.3 - MEMBRO DE CORPO EDITORIAL DE REVISTA CIENTÍFICA</h2><BR>\n"
        resultado = resultado +  "MEMBRO-DE-CORPO-EDITORIAL:                 "  + str(self.__tabela_de_qualificacao['MEMBRO-DE-CORPO-EDITORIAL']['REVISTA'])  + "<BR>\n"

        resultado = resultado + "<h2>4.1 - PRODUÇÃO BIBLIOGRÁFICA (ARTIGOS EM PERIÓDICOS)</h2><BR>\n"
        resultado = resultado +  "ARTIGOS-PUBLICADOS-QUALIS-A1:        "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['ARTIGOS-PUBLICADOS']['A1'])  + "<BR>\n"
        resultado = resultado +  "ARTIGOS-PUBLICADOS-QUALIS-A2:        "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['ARTIGOS-PUBLICADOS']['A2'])  + "<BR>\n"
        resultado = resultado +  "ARTIGOS-PUBLICADOS-QUALIS-A3:        "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['ARTIGOS-PUBLICADOS']['A3'])  + "<BR>\n"
        resultado = resultado +  "ARTIGOS-PUBLICADOS-QUALIS-A4:        "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['ARTIGOS-PUBLICADOS']['A4'])  + "<BR>\n"
        resultado = resultado +  "ARTIGOS-PUBLICADOS-QUALIS-B1:        "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['ARTIGOS-PUBLICADOS']['B1'])  + "<BR>\n"
        resultado = resultado +  "ARTIGOS-PUBLICADOS-QUALIS-B2:        "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['ARTIGOS-PUBLICADOS']['B2'])  + "<BR>\n"
        resultado = resultado +  "ARTIGOS-PUBLICADOS-QUALIS-B3:        "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['ARTIGOS-PUBLICADOS']['B3'])  + "<BR>\n"
        resultado = resultado +  "ARTIGOS-PUBLICADOS-QUALIS-B4:        "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['ARTIGOS-PUBLICADOS']['B4'])  + "<BR>\n"
        resultado = resultado +  "ARTIGOS-PUBLICADOS-QUALIS-C:         "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['ARTIGOS-PUBLICADOS']['C'])  + "<BR>\n"
        resultado = resultado +  "ARTIGOS-PUBLICADOS-SEM-QUALIS:       "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['ARTIGOS-PUBLICADOS']['NAO-ENCONTRADO']) + "<BR>\n"
        subtotal = self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['ARTIGOS-PUBLICADOS']['A1']
        subtotal = subtotal + self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['ARTIGOS-PUBLICADOS']['A2']
        subtotal = subtotal + self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['ARTIGOS-PUBLICADOS']['A3']
        subtotal = subtotal + self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['ARTIGOS-PUBLICADOS']['A4']
        subtotal = subtotal + self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['ARTIGOS-PUBLICADOS']['B1']
        subtotal = subtotal + self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['ARTIGOS-PUBLICADOS']['B2']
        subtotal = subtotal + self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['ARTIGOS-PUBLICADOS']['B3']
        subtotal = subtotal + self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['ARTIGOS-PUBLICADOS']['B4']
        subtotal = subtotal + self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['ARTIGOS-PUBLICADOS']['C']
        subtotal = subtotal + self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['ARTIGOS-PUBLICADOS']['NAO-ENCONTRADO']
        resultado = resultado +  "<h4>sub-total:       "  + str(subtotal) + "</h4><BR>\n"

        resultado = resultado + "<h2>4.2 -  TRABALHOS PUBLICADOS EM EVENTOS - TRABALHOS COMPLETOS</h2><BR>\n"
        resultado = resultado +  "TRABALHOS-COMPLETOS-INTERNACIONAIS:  "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS']['INTERNACIONAL']['COMPLETO'])  + "<BR>\n"
        resultado = resultado +  "TRABALHOS-COMPLETOS-NACIONAIS:       "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS']['NACIONAL']['COMPLETO'])  + "<BR>\n"
        resultado = resultado +  "TRABALHOS-COMPLETOS-REGIONAIS:       "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS']['REGIONAL']['COMPLETO'])  + "<BR>\n"
        resultado = resultado +  "TRABALHOS-COMPLETOS-LOCAIS:          "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS']['LOCAL']['COMPLETO'])  + "<BR>\n"
        resultado = resultado +  "TRABALHOS-COMPLETOS-NAO-INFORMADO:   "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS']['NAO_INFORMADO']['COMPLETO'])  + "<BR>\n"
        subtotal = self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS']['INTERNACIONAL']['COMPLETO'] + self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS']['NACIONAL']['COMPLETO']
        subtotal = subtotal + self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS']['REGIONAL']['COMPLETO'] + self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS']['LOCAL']['COMPLETO']
        subtotal = subtotal + self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS']['NAO_INFORMADO']['COMPLETO']
        resultado = resultado +  "<h4>sub-total:       "  + str(subtotal) + "</h4><BR>\n"

        resultado = resultado + "<h2>4.2 -  TRABALHOS PUBLICADOS EM EVENTOS - RESUMOS EXPANDIDOS</h2><BR>\n"
        resultado = resultado +  "TRABALHOS-EXPANDIDOS-INTERNACIONAIS: "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS']['INTERNACIONAL']['RESUMO_EXPANDIDO'])  + "<BR>\n"
        resultado = resultado +  "TRABALHOS-EXPANDIDOS-NACIONAIS:      "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS']['NACIONAL']['RESUMO_EXPANDIDO'])  + "<BR>\n"
        resultado = resultado +  "TRABALHOS-EXPANDIDOS-REGIONAIS:      "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS']['REGIONAL']['RESUMO_EXPANDIDO'])  + "<BR>\n"
        resultado = resultado +  "TRABALHOS-EXPANDIDOS-LOCAIS:         "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS']['LOCAL']['RESUMO_EXPANDIDO'])  + "<BR>\n"
        resultado = resultado +  "TRABALHOS-EXPANDIDOS-NAO-INFORMADO:  "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS']['NAO_INFORMADO']['RESUMO_EXPANDIDO'])  + "<BR>\n"

        resultado = resultado + "<h2>4.2 -  TRABALHOS PUBLICADOS EM EVENTOS - RESUMO SIMPLES</h2><BR>\n"
        resultado = resultado +  "TRABALHOS-RESUMOS-INTERNACIONAIS:    "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS']['INTERNACIONAL']['RESUMO'])  + "<BR>\n"
        resultado = resultado +  "TRABALHOS-RESUMOS-NACIONAIS:         "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS']['NACIONAL']['RESUMO'])  + "<BR>\n"
        resultado = resultado +  "TRABALHOS-RESUMOS-REGIONAIS:         "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS']['REGIONAL']['RESUMO'])  + "<BR>\n"
        resultado = resultado +  "TRABALHOS-RESUMOS-LOCAIS:            "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS']['LOCAL']['RESUMO'])  + "<BR>\n"
        resultado = resultado +  "TRABALHOS-RESUMOS-NAO-INFORMADO:     "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['TRABALHOS-EM-EVENTOS']['NAO_INFORMADO']['RESUMO'])  + "<BR>\n"

        resultado = resultado + "<h2>4.3 - LIVROS E CAPITULOS</h2><BR>\n"
        resultado = resultado +  "LIVROS-PUBLICADOS:                   "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['LIVROS-E-CAPITULOS']['LIVRO-PUBLICADO-OU-ORGANIZADO']['LIVRO_PUBLICADO'])  + "<BR>\n"
        resultado = resultado +  "LIVROS-ORGANIZADOS:                  "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['LIVROS-E-CAPITULOS']['LIVRO-PUBLICADO-OU-ORGANIZADO']['LIVRO_ORGANIZADO_OU_EDICAO']) + "<BR>\n"
        resultado = resultado +  "CAPITULO-DE-LIVRO-PUBLICADO:         "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['LIVROS-E-CAPITULOS']['CAPITULO-DE-LIVRO-PUBLICADO'])  + "<BR>\n"

        resultado = resultado + "<h2>4.4 - DEMAIS TIPOS DE PRODUÇÃO BIBLIOGRÁFICA</h2><BR>\n"
        resultado = resultado +  "TRADUCOES:                           "  + str(self.__tabela_de_qualificacao['PRODUCAO-BIBLIOGRAFICA']['DEMAIS-TIPOS-DE-PRODUCAO-BIBLIOGRAFICA']['TRADUCAO'])  + "<BR>\n"

        resultado = resultado + "<h2>5 - PRODUÇÃO TÉCNICA</h2><BR>\n"
        resultado = resultado +  "SOFTWARES:                           "  + str(self.__tabela_de_qualificacao['PRODUCAO-TECNICA']['SOFTWARE'])  + "<BR>\n"
        resultado = resultado +  "PATENTES-DEPOSITADAS:                "  + str(self.__tabela_de_qualificacao['PRODUCAO-TECNICA']['PATENTE']['DEPOSITADA'])  + "<BR>\n"
        resultado = resultado +  "PATENTES-CONCEDIDAS:                 "  + str(self.__tabela_de_qualificacao['PRODUCAO-TECNICA']['PATENTE']['CONCEDIDA'])  + "<BR>\n"
        resultado = resultado +  "PRODUTOS-TECNOLOGICOS:               "  + str(self.__tabela_de_qualificacao['PRODUCAO-TECNICA']['PRODUTO-TECNOLOGICO'])  + "<BR>\n"
        resultado = resultado +  "PROCESSOS-OU-TECNICAS:               "  + str(self.__tabela_de_qualificacao['PRODUCAO-TECNICA']['PROCESSOS-OU-TECNICAS'])  + "<BR>\n"
        resultado = resultado +  "TRABALHOS-TECNICOS:                  "  + str(self.__tabela_de_qualificacao['PRODUCAO-TECNICA']['TRABALHO-TECNICO'])  + "<BR>\n"

        resultado = resultado + "<h2>6.1 - PRODUÇÃO ARTÍSTICA-CULTURAL</h2><BR>\n"
        resultado = resultado +  "APRESENTACAO-DE-OBRA-ARTISTICA:      "  + str(self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['PRODUCAO-ARTISTICA-CULTURAL']['APRESENTACAO-DE-OBRA-ARTISTICA'])  + "<BR>\n"
        resultado = resultado +  "COMPOSICAO-MUSICAL:                  "  + str(self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['PRODUCAO-ARTISTICA-CULTURAL']['COMPOSICAO-MUSICAL'])  + "<BR>\n"
        resultado = resultado +  "MUSICA:                              "  + str(self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['PRODUCAO-ARTISTICA-CULTURAL']['MUSICA'])  + "<BR>\n"
        resultado = resultado +  "OBRA-DE-ARTES-VISUAIS:               "  + str(self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['PRODUCAO-ARTISTICA-CULTURAL']['OBRA-DE-ARTES-VISUAIS'])  + "<BR>\n"

        resultado = resultado + "<h2>6.2 - SUPERVISÕES, ORIENTAÇÕES E COORIENTAÇÕES EM ANDAMENTO E CONCLUÍDAS</h2><BR>\n"
        resultado = resultado +  "ORIENTACOES-PARA-POS-DOUTORADO:      "  + str(self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-CONCLUIDAS']['ORIENTACOES-CONCLUIDAS-PARA-POS-DOUTORADO'])  + "<BR>\n"
        resultado = resultado +  "ORIENTACOES-PARA-DOUTORADO:          "  + str(self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-CONCLUIDAS']['ORIENTACOES-CONCLUIDAS-PARA-DOUTORADO']['ORIENTADOR_PRINCIPAL'])  + "<BR>\n"
        resultado = resultado +  "ORIENTACOES-PARA-MESTRADO:           "  + str(self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-CONCLUIDAS']['ORIENTACOES-CONCLUIDAS-PARA-MESTRADO']['ORIENTADOR_PRINCIPAL'])  + "<BR>\n"
        resultado = resultado +  "CO-ORIENTACOES-PARA-DOUTORADO:       "  + str(self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-CONCLUIDAS']['ORIENTACOES-CONCLUIDAS-PARA-DOUTORADO']['CO_ORIENTADOR'])  + "<BR>\n"
        resultado = resultado +  "CO-ORIENTACOES-PARA-MESTRADO:        "  + str(self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-CONCLUIDAS']['ORIENTACOES-CONCLUIDAS-PARA-MESTRADO']['CO_ORIENTADOR'])  + "<BR>\n"

        resultado = resultado + "<h3>OUTRAS ORIENTAÇÕES CONCLUÍDAS</h3><BR>\n"
        resultado = resultado +  "ORIENTACOES-DE-ESPECIALIZACAO:       "  + str(self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-CONCLUIDAS']['OUTRAS-ORIENTACOES-CONCLUIDAS']['MONOGRAFIA_DE_CONCLUSAO_DE_CURSO_APERFEICOAMENTO_E_ESPECIALIZACAO'])  + "<BR>\n"
        resultado = resultado +  "ORIENTACOES-DE-TCC:                  "  + str(self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-CONCLUIDAS']['OUTRAS-ORIENTACOES-CONCLUIDAS']['TRABALHO_DE_CONCLUSAO_DE_CURSO_GRADUACAO'])  + "<BR>\n"
        resultado = resultado +  "ORIENTACOES-DE-INICIACAO-CIENTIFICA: "  + str(self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-CONCLUIDAS']['OUTRAS-ORIENTACOES-CONCLUIDAS']['INICIACAO_CIENTIFICA'])  + "<BR>\n"
        #resultado = resultado +  "ORIENTACOES-DE-OUTRA-NATUREZA:       "  + str(self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-CONCLUIDAS']['OUTRAS-ORIENTACOES-CONCLUIDAS']['ORIENTACAO-DE-OUTRA-NATUREZA'])  + "<BR>\n"

        resultado = resultado + "<h3>ORIENTAÇÕES EM ANDAMENTO</h3><BR>\n"
        resultado = resultado +  "ORIENTACOES-PARA-POS-DOUTORADO-EM-ANDAMENTO:      "  + str(self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-EM-ANDAMENTO']['ORIENTACOES-EM-ANDAMENTO-PARA-POS-DOUTORADO'])  + "<BR>\n"
        resultado = resultado +  "ORIENTACOES-PARA-DOUTORADO-EM-ANDAMENTO:          "  + str(self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-EM-ANDAMENTO']['ORIENTACOES-EM-ANDAMENTO-PARA-DOUTORADO']['ORIENTADOR_PRINCIPAL'])  + "<BR>\n"
        resultado = resultado +  "ORIENTACOES-PARA-MESTRADO-EM-ANDAMENTO:           "  + str(self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-EM-ANDAMENTO']['ORIENTACOES-EM-ANDAMENTO-PARA-MESTRADO']['ORIENTADOR_PRINCIPAL'])  + "<BR>\n"
        resultado = resultado +  "CO-ORIENTACOES-PARA-DOUTORADO-EM-ANDAMENTO:       "  + str(self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-EM-ANDAMENTO']['ORIENTACOES-EM-ANDAMENTO-PARA-DOUTORADO']['CO_ORIENTADOR'])  + "<BR>\n"
        resultado = resultado +  "CO-ORIENTACOES-PARA-MESTRADO-EM-ANDAMENTO:        "  + str(self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-EM-ANDAMENTO']['ORIENTACOES-EM-ANDAMENTO-PARA-MESTRADO']['CO_ORIENTADOR'])  + "<BR>\n"

        resultado = resultado + "<h3>OUTRAS ORIENTAÇÕES EM ANDAMENTO</h3><BR>\n"
        resultado = resultado +  "ORIENTACOES-DE-ESPECIALIZACAO-EM-ANDAMENTO:       "  + str(self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-EM-ANDAMENTO']['OUTRAS-ORIENTACOES-EM-ANDAMENTO']['MONOGRAFIA_DE_CONCLUSAO_DE_CURSO_APERFEICOAMENTO_E_ESPECIALIZACAO'])  + "<BR>\n"
        resultado = resultado +  "ORIENTACOES-DE-TCC-EM-ANDAMENTO:                  "  + str(self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-EM-ANDAMENTO']['OUTRAS-ORIENTACOES-EM-ANDAMENTO']['TRABALHO_DE_CONCLUSAO_DE_CURSO_GRADUACAO'])  + "<BR>\n"
        resultado = resultado +  "ORIENTACOES-DE-INICIACAO-CIENTIFICA-EM-ANDAMENTO: "  + str(self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-EM-ANDAMENTO']['OUTRAS-ORIENTACOES-EM-ANDAMENTO']['INICIACAO_CIENTIFICA'])  + "<BR>\n"
        #resultado = resultado +  "ORIENTACOES-DE-OUTRA-NATUREZA-EM-ANDAMENTO:       "  + str(self.__tabela_de_qualificacao['OUTRA-PRODUCAO']['ORIENTACOES-EM-ANDAMENTO']['OUTRAS-ORIENTACOES-EM-ANDAMENTO']['ORIENTACAO-DE-OUTRA-NATUREZA'])  + "<BR>\n"

        resultado = resultado + "<h2>PONTUAÇÃO TOTAL</h2><BR>\n"
        resultado = resultado +  "<h3>TOTAL:                               "  + str(self.__score)  + "</h3><BR>\n"
        resultado = resultado +  "<BR>\n"

        return (resultado)

def main():
    # Define program arguments
    parser = argparse.ArgumentParser(description="Computes scores from Lattes curricula.")
    parser.add_argument('area', metavar='AREA', type=str, nargs=1,
        help="specify Qualis Periodicos area")
    parser.add_argument('istream', metavar='FILE', type=argparse.FileType('r'), default=sys.stdin,
        help="XML file containing a Lattes curriculum")
    parser.add_argument('-v', '--verbose', action='count',
        help="explain what is being done")
    parser.add_argument('-d', '--debug', action='count',
        help="show debug messages")
    parser.add_argument('--version', action='version', version='%(prog)s 0.1')
    parser.add_argument('-p', '--qualis-periodicos', dest='ano_qualis_periodicos', default=[2017], metavar='YYYY', type=int, nargs=1,
        help="employ Qualis Periodicos from year YYYY")
    parser.add_argument('-s', '--since-year', dest='since', default=-1, metavar='YYYY', type=int, nargs=1,
        help="consider academic productivity since year YYYY")
    parser.add_argument('-u', '--until-year', dest='until', default=date.today().year, metavar='YYYY', type=int, nargs=1,
        help="consider academic productivity until year YYYY")

    # Process arguments
    args = parser.parse_args()
    xml_file = args.istream.name
    score = Score(xml_file, args.since[0], args.until[0], args.area[0], 
                  args.ano_qualis_periodicos[0], args.verbose, args.debug)

    if args.verbose == 1:
        print (score.sumario())
    else:
        print ("%.1f" % (score.get_score()))

# Main
if __name__ == "__main__":
    #sys.exit(main())
    main()
