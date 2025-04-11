'''
TESTES AUTOMATIZADOS
'''
import os
import pytest
from pesquisa import app

EMAIL_TESTES = os.getenv("EMAIL_TESTES", "")
CPF_TESTES = os.getenv("CPF_TESTES", "00000000000")

@pytest.fixture
def client():
    """A test client for the app."""
    TEST_USER = os.getenv("TEST_USER", "")
    TEST_PASSWORD = os.getenv("TEST_PASSWORD", "")
    with app.test_client() as client:
        data = {
            "siape": TEST_USER,
            "senha": TEST_PASSWORD,
        }
        client.post("/login", data=data)
        yield client

def test_home(client):
    """Test the home route."""
    response = client.get('/')
    assert response.status_code == 200
    
def test_cadastrar_projeto(client):
    """Test the cadastrar_projeto route."""
    data={
            "tipo": "40",
            "nome": "nome",
            "categoria_projeto": "1",
            "siape": "1570709123",
            "email": EMAIL_TESTES,
            "ua": "CCT",
            "area_capes": "CIENCIA_DA_COMPUTACAO",
            "grande_area": "Engenharias",
            "grupo": "Grupo de pesquisa",
            "ods_projeto": "01",
            "inovacao": "1",
            "justificativa": "Justificativa",
            "cpf": CPF_TESTES,
            "titulo": "(1)O TITULO DO PROJETO PARA TESTES AUTOMATIZADOS",
            "validade": "3",
            "palavras_chave": "palavras chave",
            "descricao_resumida": "Descrição resumida",
            "numero_bolsas": "1",
            "transporte": "1",
            "inicio": "2023-10-01",
            "fim": "2024-10-01",
            "arquivo_projeto": open("/app/teste.pdf","rb"),
            "arquivo_plano1": open("/app/teste.pdf","rb"),
            "arquivo_plano2": open("/app/teste.pdf","rb"),
            "arquivo_plano3": open("/app/teste.pdf","rb"),
            "arquivo_comprovantes": open("/app/teste.pdf","rb"),
            "avaliador1_email": "TESTE@123.com"
    }
    response = client.post("/cadastrarProjeto", 
                           data=data,follow_redirects=True,content_type='multipart/form-data')
    assert response.status_code == 200
    assert b"FECHADA COM SEGU" in response.data
    response = client.get("/editalProjeto?edital=40")
    assert response.status_code == 200
    assert b"Propostas submetidas" in response.data
    assert b"O TITULO DO PROJETO PARA TESTES AUTOMATIZADOS" in response.data
    assert b"TESTE@123.com" in response.data

def test_cadastrar_projeto_sem_avaliadores(client):
    """Test the cadastrar_projeto route."""
    data={
            "tipo": "40",
            "nome": "nome",
            "categoria_projeto": "1",
            "siape": "1570709123",
            "email": EMAIL_TESTES,
            "ua": "CCT",
            "area_capes": "CIENCIA_DA_COMPUTACAO",
            "grande_area": "Engenharias",
            "grupo": "Grupo de pesquisa",
            "ods_projeto": "01",
            "inovacao": "1",
            "justificativa": "Justificativa",
            "cpf": CPF_TESTES,
            "titulo": "(2)O TITULO DO PROJETO PARA TESTES AUTOMATIZADOS",
            "validade": "3",
            "palavras_chave": "palavras chave",
            "descricao_resumida": "Descrição resumida",
            "numero_bolsas": "1",
            "transporte": "1",
            "inicio": "2023-10-01",
            "fim": "2024-10-01",
            "arquivo_projeto": open("/app/teste.pdf","rb"),
            "arquivo_plano1": open("/app/teste.pdf","rb"),
            "arquivo_plano2": open("/app/teste.pdf","rb"),
            "arquivo_plano3": open("/app/teste.pdf","rb"),
            "arquivo_comprovantes": open("/app/teste.pdf","rb"),
    }
    response = client.post("/cadastrarProjeto", 
                           data=data,follow_redirects=True,content_type='multipart/form-data')
    assert response.status_code == 200
    assert b"FECHADA COM SEGU" in response.data
    response = client.get("/editalProjeto?edital=40")
    assert response.status_code == 200
    assert b"Propostas submetidas" in response.data
    assert b"O TITULO DO PROJETO PARA TESTES AUTOMATIZADOS" in response.data

def test_cadastrar_projeto_sem_avaliadores_vazio(client):
    """Test the cadastrar_projeto route."""
    data={
            "tipo": "40",
            "nome": "nome",
            "categoria_projeto": "1",
            "siape": "1570709123",
            "email": EMAIL_TESTES,
            "ua": "CCT",
            "area_capes": "CIENCIA_DA_COMPUTACAO",
            "grande_area": "Engenharias",
            "grupo": "Grupo de pesquisa",
            "ods_projeto": "01",
            "inovacao": "1",
            "justificativa": "Justificativa",
            "cpf": CPF_TESTES,
            "titulo": "(3)O TITULO DO PROJETO PARA TESTES AUTOMATIZADOS",
            "validade": "3",
            "palavras_chave": "palavras chave",
            "descricao_resumida": "Descrição resumida",
            "numero_bolsas": "1",
            "transporte": "1",
            "inicio": "2023-10-01",
            "fim": "2024-10-01",
            "arquivo_projeto": open("/app/teste.pdf","rb"),
            "arquivo_plano1": open("/app/teste.pdf","rb"),
            "arquivo_plano2": open("/app/teste.pdf","rb"),
            "arquivo_plano3": open("/app/teste.pdf","rb"),
            "arquivo_comprovantes": open("/app/teste.pdf","rb"),
            "avaliador1_email": "",
            "avaliador2_email": "",
            "avaliador3_email": "",
    }
    response = client.post("/cadastrarProjeto", 
                           data=data,follow_redirects=True,content_type='multipart/form-data')
    assert response.status_code == 200
    assert b"FECHADA COM SEGU" in response.data
    response = client.get("/editalProjeto?edital=40")
    assert response.status_code == 200
    assert b"Propostas submetidas" in response.data
    assert b"O TITULO DO PROJETO PARA TESTES AUTOMATIZADOS" in response.data

def test_cadastrar_projeto_cpf_invalido(client):
    """Test the cadastrar_projeto route."""
    data={
            "tipo": "40",
            "nome": "nome",
            "categoria_projeto": "1",
            "siape": "1570709123",
            "email": EMAIL_TESTES,
            "ua": "CCT",
            "area_capes": "CIENCIA_DA_COMPUTACAO",
            "grande_area": "Engenharias",
            "grupo": "Grupo de pesquisa",
            "ods_projeto": "01",
            "inovacao": "1",
            "justificativa": "Justificativa",
            "cpf": "00000000000",
            "titulo": "(3)O TITULO DO PROJETO PARA TESTES AUTOMATIZADOS",
            "validade": "3",
            "palavras_chave": "palavras chave",
            "descricao_resumida": "Descrição resumida",
            "numero_bolsas": "1",
            "transporte": "1",
            "inicio": "2023-10-01",
            "fim": "2024-10-01",
            "arquivo_projeto": open("/app/teste.pdf","rb"),
            "arquivo_plano1": open("/app/teste.pdf","rb"),
            "arquivo_plano2": open("/app/teste.pdf","rb"),
            "arquivo_plano3": open("/app/teste.pdf","rb"),
            "arquivo_comprovantes": open("/app/teste.pdf","rb"),
            "avaliador1_email": "",
            "avaliador2_email": "",
            "avaliador3_email": "",
    }
    response = client.post("/cadastrarProjeto", 
                           data=data,follow_redirects=True,content_type='multipart/form-data')
    assert response.status_code == 200
    assert b"FECHADA COM SEGU" in response.data
    response = client.get("/editalProjeto?edital=40")
    assert response.status_code == 200
    assert b"Propostas submetidas" in response.data
    assert b"O TITULO DO PROJETO PARA TESTES AUTOMATIZADOS" in response.data

def test_edital_projeto(client):
    response = client.get("/editalProjeto?edital=40")
    assert response.status_code == 200
    assert b"Propostas submetidas" in response.data

def test_cadastrar_avaliador(client):
    data = {
        "txtProjeto": "1560",
        "txtEmail": "TESTE@INSERIDO.AVALIADOR",
    }
    response = client.post("/inserirAvaliador", data=data, follow_redirects=True)
    assert response.status_code == 200
    response = client.post("/inserirAvaliador", data=data, follow_redirects=True)
    assert response.status_code == 200
    assert b"cadastrado para este projeto" in response.data
    response = client.get("/editalProjeto?edital=40")
    assert response.status_code == 200
    assert b"INSERIDO.AVALIADOR" in response.data
    