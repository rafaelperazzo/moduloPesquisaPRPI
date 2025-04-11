"""
Testes automatizados para o módulo scorerun.
"""
import os
from modules import scorerun
from pesquisa import salvarCV
import pytest

ID_LATTES = "3078288668202994"
XML_DIR = "xml/"

@pytest.fixture(autouse=True)
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
    salvarCV(ID_LATTES)
    xml_file = XML_DIR + ID_LATTES + ".xml"
    score = scorerun.Score(xml_file, 2020, 2025, "CIENCIA_DA_COMPUTACAO",
                  2017, 0,False)
    pontuacao = float(score.get_score())
    sumario = str(score.sumario())
    print(sumario)
    print(pontuacao)
    assert pontuacao >= 0
    assert "3078288668202994" in sumario
