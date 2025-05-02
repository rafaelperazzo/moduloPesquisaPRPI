'''
TESTES AUTOMATIZADOS
'''
import os
import pytest
from pesquisa import app

TIPO = "37"

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

def test_cadastrar_avaliador(client):
    """Testar cadastro de avaliador para projeto"""
    data = {
        "txtProjeto": "1665",
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
    