import os

command = "python /home/perazzo/flask/projetos/pesquisa/modules/scorerun.py -v -p 2016 -s 2014 -u 2019 \"ADMINISTRACAO_PUBLICA_E_DE_EMPRESAS_CIENCIAS_CONTABEIS_E_TURISMO\" /home/perazzo/flask/projetos/pesquisa/static/files/2315016_yUXhR5M03UPLWR4TaAfe.xml"
s = os.popen(command).read()
print (s)
