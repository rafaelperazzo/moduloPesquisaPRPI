import pytest
from pesquisa import app


@pytest.fixture
def client():
    """A test client for the app."""
    with app.test_client() as client:
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
            "email": "rafaelperazzo@gmail.com",
            "ua": "CCT",
            "area_capes": "CIENCIA_DA_COMPUTACAO",
            "grande_area": "Engenharias",
            "grupo": "Grupo de pesquisa",
            "ods_projeto": "01",
            "inovacao": "1",
            "justificativa": "Justificativa",
            "cpf": "02675287440",
            "titulo": "Título do projeto",
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
            "avaliador1_email": "teste@123.com",
            "avaliador2_email": "teste@456.com",
            "avaliador3_email": "teste@789.com",
    }
    response = client.post("/cadastrarProjeto", 
                           data=data,follow_redirects=True,content_type='multipart/form-data')
    print(response.data)
    assert response.status_code == 200

def test_edital_projeto(client):
    #data = {
    #    "siape": "",
    #    "senha": "",
    #}
    #client.post("/login", data=data)
    response = client.get("/editalProjeto?edital=40")
    assert response.status_code == 200
    assert b"Esqueci" in response.data
    assert b"ERRO!" not in response.data