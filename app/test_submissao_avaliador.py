'''
TESTES AUTOMATIZADOS
'''
import os
import random
import time
import pytest
from pesquisa import app,executarSelect,atualizar,SUBMISSOES_DIR

EMAIL_TESTES = os.getenv("EMAIL_TESTES", "")
CPF_TESTES = os.getenv("CPF_TESTES", "00000000000")
TIPO = "40"

def generate_random_sentence(word_count):
    """Generate a random sentence with the given number of words."""
    words = ['apple', 'banana', 'cherry', 'date', 'elderberry', 'fig', 'grape', 'honeydew']
    return ' '.join(random.choice(words) for i in range(word_count)) + '.'

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

@pytest.fixture
def setup():
    """Setup and teardown for the test environment."""
    # Setup code here
    yield
    # Teardown code here
    consulta = """
    SELECT max(id) FROM editalProjeto
    """
    resultado = executarSelect(consulta)[0]
    for linha in resultado:
        idProjeto = linha[0]
    consulta = f"""
    SELECT arquivo_projeto, arquivo_plano1, arquivo_plano2, arquivo_plano3, 
    arquivo_comprovantes FROM editalProjeto 
    WHERE id = {idProjeto}"""
    resultado = executarSelect(consulta)[0]
    apagar = f"""
    DELETE FROM editalProjeto WHERE id = {idProjeto}
    """
    atualizar(apagar)
    for linha in resultado:
        if os.path.exists(SUBMISSOES_DIR + linha[0]):
            os.remove(SUBMISSOES_DIR + linha[0])
        if os.path.exists(SUBMISSOES_DIR + linha[1]):
            os.remove(SUBMISSOES_DIR + linha[1])
        if os.path.exists(SUBMISSOES_DIR + linha[2]):
            os.remove(SUBMISSOES_DIR + linha[2])
        if os.path.exists(SUBMISSOES_DIR + linha[3]):
            os.remove(SUBMISSOES_DIR + linha[3])
        if os.path.exists(linha[4]):
            os.remove(SUBMISSOES_DIR + linha[4])
    
def test_home(client):
    """Test the home route."""
    response = client.get('/')
    assert response.status_code == 200
    
def test_cadastrar_projeto(client,setup):
    """Test the cadastrar_projeto route."""
    titulo = generate_random_sentence(4)
    data={
            "tipo": TIPO,
            "nome": "nome",
            "categoria_projeto": "1",
            "siape": "1470709123",
            "email": EMAIL_TESTES,
            "ua": "CCT",
            "area_capes": "CIENCIA_DA_COMPUTACAO",
            "grande_area": "Engenharias",
            "grupo": generate_random_sentence(2),
            "ods_projeto": "01",
            "inovacao": "1",
            "justificativa": "Justificativa",
            "cpf": CPF_TESTES,
            "titulo": titulo,
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
    response = client.get("/editalProjeto?edital=" + TIPO)
    assert response.status_code == 200
    assert b"Propostas submetidas" in response.data
    assert titulo.encode() in response.data
    assert b"TESTE@123.com" in response.data
    time.sleep(4)

def test_cadastrar_projeto_sem_avaliadores(client,setup):
    """Test the cadastrar_projeto route."""
    titulo = generate_random_sentence(4)
    data={
            "tipo": TIPO,
            "nome": "nome",
            "categoria_projeto": "1",
            "siape": "1470709123",
            "email": EMAIL_TESTES,
            "ua": "CCT",
            "area_capes": "CIENCIA_DA_COMPUTACAO",
            "grande_area": "Engenharias",
            "grupo": generate_random_sentence(4),
            "ods_projeto": "01",
            "inovacao": "1",
            "justificativa": "Justificativa",
            "cpf": CPF_TESTES,
            "titulo": titulo,
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
    response = client.get("/editalProjeto?edital=" + TIPO)
    assert response.status_code == 200
    assert b"Propostas submetidas" in response.data
    assert titulo.encode() in response.data
    time.sleep(4)

def test_cadastrar_projeto_sem_avaliadores_vazio(client,setup):
    """Test the cadastrar_projeto route."""
    titulo = generate_random_sentence(4)
    data={
            "tipo": TIPO,
            "nome": "nome",
            "categoria_projeto": "1",
            "siape": "1470709123",
            "email": EMAIL_TESTES,
            "ua": "CCT",
            "area_capes": "CIENCIA_DA_COMPUTACAO",
            "grande_area": "Engenharias",
            "grupo": generate_random_sentence(2),
            "ods_projeto": "01",
            "inovacao": "1",
            "justificativa": "Justificativa",
            "cpf": CPF_TESTES,
            "titulo": titulo,
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
    response = client.get("/editalProjeto?edital=" + TIPO)
    assert response.status_code == 200
    assert b"Propostas submetidas" in response.data
    assert titulo.encode() in response.data
    time.sleep(4)

def test_cadastrar_projeto_cpf_invalido(client,setup):
    """Test the cadastrar_projeto route."""
    titulo = generate_random_sentence(4)
    data={
            "tipo": TIPO,
            "nome": "nome",
            "categoria_projeto": "1",
            "siape": "1470709123",
            "email": EMAIL_TESTES,
            "ua": "CCT",
            "area_capes": "CIENCIA_DA_COMPUTACAO",
            "grande_area": "Engenharias",
            "grupo": generate_random_sentence(2),
            "ods_projeto": "01",
            "inovacao": "1",
            "justificativa": "Justificativa",
            "cpf": "00000000000",
            "titulo": titulo,
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
    response = client.get("/editalProjeto?edital=" + TIPO)
    assert response.status_code == 200
    assert b"Propostas submetidas" in response.data
    assert titulo.encode() in response.data
    time.sleep(4)

def test_edital_projeto(client):
    """Testar página com lista de projetos"""
    response = client.get("/editalProjeto?edital=" + TIPO)
    assert response.status_code == 200
    assert b"Propostas submetidas" in response.data

def test_cadastrar_avaliador(client):
    """Testar cadastro de avaliador para projeto"""
    data = {
        "txtProjeto": "1560",
        "txtEmail": "TESTE@INSERIDO.AVALIADOR",
    }
    response = client.post("/inserirAvaliador", data=data, follow_redirects=True)
    assert response.status_code == 200
    response = client.post("/inserirAvaliador", data=data, follow_redirects=True)
    assert response.status_code == 200
    assert b"cadastrado para este projeto" in response.data
    response = client.get("/editalProjeto?edital=" + TIPO)
    assert response.status_code == 200
    assert b"INSERIDO.AVALIADOR" in response.data
    