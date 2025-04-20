"""
Testes automatizados para o módulo scorerun.
"""
import os
import pytest
import time
from modules import scorerun
from pesquisa import salvarCV

ID_LATTES = "0728801046272432"
XML_DIR = "xml/"

@pytest.fixture(autouse=True,scope="session")
def setup():
    """
    Configuração do ambiente de teste.
    """
    if not os.path.exists(XML_DIR):
        os.makedirs(XML_DIR)
    yield
    # Limpeza após os testes
    if os.path.exists(XML_DIR + ID_LATTES + ".xml"):
        os.remove(XML_DIR + ID_LATTES + ".xml")
    if os.path.exists(XML_DIR + ID_LATTES + "_ERRO.xml"):
        os.remove(XML_DIR + ID_LATTES + "_ERRO.xml")

def test_salvar_cv(setup):
    """
    Teste da função salvarCV.
    """
    salvarCV(ID_LATTES)
    assert os.path.exists(XML_DIR + ID_LATTES + ".xml") or os.path.exists(XML_DIR + ID_LATTES + "_ERRO.xml")

def test_scorelattes(setup):
    """
    Teste da função scorelattes.
    """
    inicio = time.time()
    salvarCV(ID_LATTES)
    print("Tempo de execução do salvarCV:", time.time() - inicio)
    xml_file = XML_DIR + ID_LATTES + ".xml"
    inicio = time.time()
    score = scorerun.Score(xml_file, 2020, 2025, "CIENCIAS_BIOLOGICAS_I",
                  2017, 0,False)
    print("Tempo de execução do scorerun:", time.time() - inicio)
    pontuacao = float(score.get_score())
    sumario = str(score.sumario())
    assert pontuacao >= 500
    assert "0728801046272432" in sumario
