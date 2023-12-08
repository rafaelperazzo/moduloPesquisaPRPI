'''
Teste básico do app
'''

import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
import pytest

load_dotenv(override=True)

URL = os.getenv("URL")
USUARIO=os.getenv("USUARIO")
SENHA=os.getenv("SENHA")
SIAPES=os.getenv("SIAPES")
USUARIO_SIAPE=os.getenv("USUARIO_SIAPE")
SENHA_SIAPE=os.getenv("SENHA_SIAPE")

@pytest.fixture
def app():
    '''
    Cria um app para testes
    '''
    s = requests.Session()
    login_data =  {'siape': USUARIO_SIAPE, 'senha': SENHA_SIAPE}
    s.post(URL + 'login', login_data, timeout=5)
    return s

def test_app_main():
    '''
    Testa se a página principal está respondendo
    '''
    status = requests.get(URL, timeout=5).status_code
    assert status == 200

def test_app_get_bib():
    '''
    Testa se a página de busca de bib está respondendo
    '''
    status = requests.get(URL, auth=HTTPBasicAuth(USUARIO, SENHA), timeout=5).status_code
    assert status == 200

def test_app_get_bib_json():
    '''
    Testa se o JSON da página de busca de bib está respondendo
    '''
    r = requests.get(URL + 'get_bib/' + SIAPES, auth=HTTPBasicAuth(USUARIO, SENHA), timeout=5)
    r.json()

def test_get_bib_json_content():
    '''
    Testa se o conteúdo JSON da página de busca de bib está respondendo
    '''
    r = requests.get(URL + 'get_bib/' + SIAPES, auth=HTTPBasicAuth(USUARIO, SENHA), timeout=5)
    for linha in r.json():
        assert len(linha['nome']) >0
        assert 'nome' in linha

def test_login(app):
    '''
    Testa se o login está funcionando
    '''
    r = app.get(URL + 'meusProjetos', timeout=5)
    assert r.status_code == 200