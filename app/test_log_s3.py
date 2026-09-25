"""Testes da rotação mensal do log e do envio ao S3 (retenção de 2 anos, declarada em /lgpd).

Rodar a partir de app/: pytest test_log_s3.py -v
"""
import gzip
import json
import os
import time
from datetime import datetime, timezone

import pytest
from botocore.exceptions import ClientError
from loguru import logger

import pesquisa as P


class S3Falso:
    def __init__(self, existentes=()):
        self.enviados = {}
        self.existentes = set(existentes)

    def put_object(self, Bucket, Key, Body, **extra):
        self.enviados[Key] = (Body.read(), extra)

    def head_object(self, Bucket, Key):
        if Key not in self.existentes:
            raise ClientError({'Error': {'Code': '404'}}, 'HeadObject')


@pytest.fixture
def s3(monkeypatch):
    falso = S3Falso()
    monkeypatch.setattr(P, 's3', falso)
    return falso


def esperar(condicao, segundos=3):
    limite = time.time() + segundos
    while not condicao() and time.time() < limite:
        time.sleep(0.02)
    return condicao()


def em(data):
    return logger.patch(lambda r: r.update(time=data))


def test_rotacao_no_dia_primeiro_compacta_e_envia(tmp_path, s3):
    caminho = tmp_path / "app.json"
    sink = logger.add(str(caminho), rotation=P.RotacaoMensalDoLog(), serialize=True,
                      compression=P.compactar_e_enviar_log, level="INFO")
    try:
        setembro = datetime(2026, 9, 30, 23, 59, tzinfo=timezone.utc)
        em(setembro).info("ultima de setembro")
        em(setembro).info("ainda setembro")
        assert list(tmp_path.glob("*.gz")) == []
        em(datetime(2026, 10, 1, 0, 0, 1, tzinfo=timezone.utc)).info("primeira de outubro")
    finally:
        logger.remove(sink)

    compactados = list(tmp_path.glob("app.*.json.gz"))
    assert len(compactados) == 1
    assert not list(tmp_path.glob("app.*.json"))  # o original some depois de compactado
    with gzip.open(compactados[0], 'rt') as f:
        mensagens = [json.loads(linha)['record']['message'] for linha in f]
    assert mensagens == ["ultima de setembro", "ainda setembro"]
    assert "primeira de outubro" in caminho.read_text()

    chave = P.LOG_PREFIXO_S3 + compactados[0].name
    assert esperar(lambda: chave in s3.enviados)
    conteudo, extra = s3.enviados[chave]
    assert conteudo == compactados[0].read_bytes()
    assert extra['ServerSideEncryption'] == 'aws:kms'
    assert chave.startswith('pesquisa/logs/app.')


def test_sem_troca_de_mes_nao_rotaciona():
    rotacao = P.RotacaoMensalDoLog()

    class Mensagem(str):
        record = {'time': datetime(2026, 9, 15)}

    with open(os.devnull, 'a+') as arquivo:
        assert rotacao(Mensagem("x"), arquivo) is False
        Mensagem.record = {'time': datetime(2026, 9, 30, 23, 59)}
        assert rotacao(Mensagem("x"), arquivo) is False


def test_app_reiniciado_depois_da_virada_rotaciona_o_mes_anterior(tmp_path):
    arquivo = tmp_path / "app.json"
    arquivo.write_text("log de setembro\n")
    setembro = datetime(2026, 9, 29, 12, 0).timestamp()
    os.utime(arquivo, (setembro, setembro))
    rotacao = P.RotacaoMensalDoLog()

    class Mensagem(str):
        record = {'time': datetime(2026, 10, 2, 8, 0)}

    with open(arquivo, 'a') as f:
        assert rotacao(Mensagem("x"), f) is True
        assert rotacao(Mensagem("x"), f) is False


def test_arquivo_grande_nao_rotaciona_no_meio_do_mes(tmp_path):
    rotacao = P.RotacaoMensalDoLog()

    class Mensagem(str):
        record = {'time': datetime.now()}

    with open(tmp_path / "app.json", 'a') as f:
        f.write("x" * (30 * 1024 * 1024))
        assert rotacao(Mensagem("x"), f) is False


def test_falha_no_envio_so_registra_erro(tmp_path, monkeypatch):
    class S3Fora:
        def put_object(self, **kw):
            raise ClientError({'Error': {'Code': 'AccessDenied'}}, 'PutObject')

    monkeypatch.setattr(P, 's3', S3Fora())
    gz = tmp_path / "app.2026-10-01_00-00-00_000000.json.gz"
    gz.write_bytes(b"x")
    assert P.enviar_log_s3(str(gz)) is False
    assert gz.exists()  # continua no servidor para o reenvio


def test_reenvia_so_os_pendentes(tmp_path, monkeypatch):
    for nome in ("app.2026-08-01_00-00-00_000000.json.gz", "app.2026-09-01_00-00-00_000000.json.gz"):
        (tmp_path / nome).write_bytes(nome.encode())
    (tmp_path / "app.json").write_text("atual")
    falso = S3Falso(existentes={P.LOG_PREFIXO_S3 + "app.2026-08-01_00-00-00_000000.json.gz"})
    monkeypatch.setattr(P, 's3', falso)
    monkeypatch.chdir(tmp_path)
    P.enviar_logs_pendentes()
    assert list(falso.enviados) == [P.LOG_PREFIXO_S3 + "app.2026-09-01_00-00-00_000000.json.gz"]


def test_politica_declara_2_anos():
    with open('templates/lgpd.html', encoding='utf-8') as f:
        html = f.read()
    assert '<td class="px-4 py-3 text-gray-700">2 anos.' in html
    assert 'logs e registros de acesso guardados por 2 anos' in html and 'Logs apagados após 90 dias' not in html
