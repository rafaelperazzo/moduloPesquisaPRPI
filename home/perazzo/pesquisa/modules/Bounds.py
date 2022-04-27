bounds = {
    'FORMACAO-ACADEMICA-TITULACAO' : {'POS-DOUTORADO': 10, 'LIVRE-DOCENCIA': 8, 'DOUTORADO': 7, 'MESTRADO': 3},
    'PROJETO-DE-PESQUISA' : {'PESQUISA': 8, 'DESENVOLVIMENTO': 8},
    'PRODUCAO-BIBLIOGRAFICA' : {
        'ARTIGOS-PUBLICADOS': {'A1': 'inf', 'A2': 'inf', 'B1': 'inf', 'B2': 'inf', 'B3': 'inf', 'B4': 'inf', 'B5': 'inf', 'C': 'inf', 'NAO-ENCONTRADO': 'inf'},
        'TRABALHOS-EM-EVENTOS': {
            'INTERNACIONAL': { 'COMPLETO': 'inf', 'RESUMO_EXPANDIDO': 'inf', 'RESUMO': 'inf' },
            'NACIONAL': { 'COMPLETO': 'inf', 'RESUMO_EXPANDIDO': 'inf', 'RESUMO': 'inf' },
            'REGIONAL': { 'COMPLETO': 'inf', 'RESUMO_EXPANDIDO': 'inf', 'RESUMO': 'inf' },
            'LOCAL': { 'COMPLETO': 'inf', 'RESUMO_EXPANDIDO': 'inf', 'RESUMO': 'inf' },
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
        'PATENTE': {'DEPOSITADA': 'inf', 'CONCEDIDA': 'inf'},
        'PRODUTO-TECNOLOGICO': 6,
        'PROCESSOS-OU-TECNICAS': 6,
        'TRABALHO-TECNICO': 1,
    },
    'OUTRA-PRODUCAO': {
        'PRODUCAO-ARTISTICA-CULTURAL': {
            'APRESENTACAO-DE-OBRA-ARTISTICA': 5,
            'COMPOSICAO-MUSICAL': 4,
            'OBRA-DE-ARTES-VISUAIS': 4,
            'MUSICA': 4,
            'ARTES-CENICAS': 4,
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
    },
}
