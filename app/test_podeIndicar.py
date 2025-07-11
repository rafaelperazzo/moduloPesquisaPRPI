# -*- coding: utf-8 -*-
"""
Test the home route of the app.
This module contains a test for the home route of the app.
"""
import os
import pytest
from pesquisa import podeIndicarVoluntarios,app

@pytest.fixture
def client_admin():
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

def test_indicacao_bolsista(client_admin):
    """Test the indicacao route."""
    response = client_admin.get('/indicacao?id=1944&b=1')
    assert response.status_code == 200
    assert "Indicação de bolsista".encode() in response.data
    
def test_indicacao_voluntario(client_admin):
    """Test the indicacao route."""
    response = client_admin.get('/indicacao?id=1944&b=0')
    assert response.status_code == 200
    assert "Indicação de voluntário".encode() in response.data

def test_pode_indicar_voluntarios():
    """
    Test the podeIndicarVoluntarios function.
    """
    
    result = podeIndicarVoluntarios("1944")

    # Assert that the result is True
    assert result is True