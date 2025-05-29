# -*- coding: utf-8 -*-
"""
Test the home route of the app.
This module contains a test for the home route of the app.
"""
import os
import pytest
from pesquisa import app

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
    assert b'SUBMETER PROJETO' in response.data

def test_login():
    """Test the login route"""
    TEST_USER = os.getenv("TEST_USER", "")
    TEST_PASSWORD = os.getenv("TEST_PASSWORD", "")
    data = {
            "siape": TEST_USER,
            "senha": TEST_PASSWORD,
        }
    response = client.post("/login", data=data)
    assert response.status_code == 200
