"""Testes do download dos arquivos do S3 (migracao.s3.md, fase 1) com o cliente boto3 mockado.

Não acessam a AWS nem o banco: s3 e executarSelect2 são substituídos via monkeypatch.
Rodar a partir de app/: pytest test_download_s3.py -v
"""
import os
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from flask.sessions import SecureCookieSessionInterface

import pesquisa as P

URL_ASSINADA = 'https://rajardekalambur.s3.dualstack.us-east-2.amazonaws.com/assinada'


def erro(codigo):
    return ClientError({'Error': {'Code': codigo, 'Message': codigo}}, 'HeadObject')


@pytest.fixture
def s3(monkeypatch):
    c = MagicMock()
    c.head_object.return_value = {'ServerSideEncryption': 'aws:kms'}
    c.generate_presigned_url.return_value = URL_ASSINADA
    monkeypatch.setattr(P.app, 'session_interface', SecureCookieSessionInterface())
    monkeypatch.setattr(P.app, 'secret_key', 'teste-download')
    monkeypatch.setitem(P.app.config, 'WTF_CSRF_ENABLED', False)
    monkeypatch.setattr(P.limiter, 'enabled', False)
    monkeypatch.setattr(P, 's3', c)
    monkeypatch.setattr(P, 'carregar_mensagens', lambda: [])  # banner do BASE_v3 lê o banco
    return c


@pytest.fixture
def dono(monkeypatch):
    """executarSelect2 do dono_do_arquivo: o siape 111 é dono de Projeto_1_111_abc.pdf."""
    consultas = []

    def falso(consulta, tipo=0, valores=()):
        consultas.append((consulta, list(valores)))
        siape, nome = valores
        return ([(1,)], 1) if (siape, nome) == ('111', 'Projeto_1_111_abc.pdf') else ([], 0)
    monkeypatch.setattr(P, 'executarSelect2', falso)
    return consultas


@pytest.fixture
def client(s3):
    return P.app.test_client()


def logado(client, username='111', roles=('user',)):
    with client.session_transaction() as s:
        s.update({'username': username, 'permissao': 1, 'roles': list(roles), 'edital': 0})


def token_avaliador(nome='Projeto_1_111_abc.pdf', prefixo='submissoes'):
    return P.assinador_arquivos.dumps({'p': prefixo, 'n': nome})


# --- url_download ------------------------------------------------------------

def test_caminho_novo_redireciona_para_url_assinada(s3):
    with P.app.test_request_context():
        resposta = P.url_download('submissoes', 'Projeto_1_111_abc.pdf', 'teste')
    assert resposta.status_code == 302
    assert resposta.location == URL_ASSINADA
    s3.head_object.assert_called_once_with(Bucket=P.AWS_S3_BUCKET, Key='pesquisa/submissoes/Projeto_1_111_abc.pdf')
    s3.generate_presigned_url.assert_called_once_with(
        'get_object',
        Params={'Bucket': P.AWS_S3_BUCKET, 'Key': 'pesquisa/submissoes/Projeto_1_111_abc.pdf',
                'ResponseContentDisposition': 'inline; filename="Projeto_1_111_abc.pdf"'},
        ExpiresIn=60,
    )
    s3.download_file.assert_not_called()


def test_nome_passa_pelo_secure_filename(s3):
    with P.app.test_request_context():
        P.url_download('docs_indicacoes', '../../cppgi/segredo.pdf', 'teste')
    s3.head_object.assert_called_once_with(Bucket=P.AWS_S3_BUCKET, Key='pesquisa/docs_indicacoes/cppgi_segredo.pdf')


def test_nome_vazio_nao_consulta_o_s3(s3):
    with P.app.test_request_context():
        assert P.url_download('submissoes', '', 'teste') == "Arquivo não encontrado!"
    s3.head_object.assert_not_called()


@pytest.mark.parametrize('codigo', ['404', '403'])
def test_caminho_antigo_quando_nao_migrado(s3, monkeypatch, codigo):
    """Arquivo ainda em .gpg (enviado antes da fase 2): baixa, descriptografa e entrega pelo app."""
    s3.head_object.side_effect = erro(codigo)
    nome = 'teste_download_s3_caminho_antigo.pdf'
    pasta = P.PREFIXOS_ARQUIVOS['submissoes'][0]
    os.makedirs(pasta, exist_ok=True)

    def descriptografar(chave, origem, destino):
        assert origem == pasta + nome + '.gpg'
        with open(destino, 'wb') as f:
            f.write(b'%PDF-1.4 conteudo')
    monkeypatch.setattr(P.cripto, 'aes_gpg_decrypt_file', descriptografar)
    apagar = []
    monkeypatch.setattr(P, 'esperar', apagar.append)
    try:
        with P.app.test_request_context():
            resposta = P.url_download('submissoes', nome, 'teste')
            resposta.direct_passthrough = False
            assert resposta.status_code == 200
            assert resposta.get_data() == b'%PDF-1.4 conteudo'
    finally:
        if os.path.exists(pasta + nome):
            os.remove(pasta + nome)
    s3.download_file.assert_called_once_with(P.AWS_S3_BUCKET, 'pesquisa/submissoes/' + nome + '.gpg', pasta + nome + '.gpg')
    s3.generate_presigned_url.assert_not_called()


def test_erro_inesperado_do_s3(s3):
    s3.head_object.side_effect = erro('500')
    with P.app.test_request_context():
        assert P.url_download('submissoes', 'Projeto_1_111_abc.pdf', 'teste') == "Arquivo não encontrado!"
    s3.generate_presigned_url.assert_not_called()


# --- /verArquivosProjeto -----------------------------------------------------

def test_ver_arquivos_projeto_exige_login(client, s3):
    resposta = client.get('/verArquivosProjeto/Projeto_1_111_abc.pdf')
    assert resposta.status_code == 200  # página de login
    s3.head_object.assert_not_called()


def test_ver_arquivos_projeto_dono(client, s3, dono):
    logado(client, '111')
    resposta = client.get('/verArquivosProjeto/Projeto_1_111_abc.pdf')
    assert resposta.status_code == 302 and resposta.location == URL_ASSINADA
    consulta, valores = dono[0]
    assert valores == ['111', 'Projeto_1_111_abc.pdf']
    assert 'arquivo_comprovantes' in consulta and 'siape=%s' in consulta


def test_ver_arquivos_projeto_outro_usuario_recusado(client, s3, dono):
    logado(client, '222')
    resposta = client.get('/verArquivosProjeto/Projeto_1_111_abc.pdf')
    assert resposta.status_code == 302 and resposta.location != URL_ASSINADA
    s3.head_object.assert_not_called()


def test_ver_arquivos_projeto_admin(client, s3, dono):
    logado(client, '999', roles=('admin', 'user'))
    resposta = client.get('/verArquivosProjeto/Projeto_1_111_abc.pdf')
    assert resposta.status_code == 302 and resposta.location == URL_ASSINADA
    assert dono == []  # admin não consulta o dono


# --- /admin/verArquivo -------------------------------------------------------

def test_admin_ver_arquivo_usa_docs_indicacoes(client, s3):
    logado(client, '999', roles=('admin',))
    resposta = client.get('/admin/verArquivo?file=RG_10_abc.pdf')
    assert resposta.status_code == 302 and resposta.location == URL_ASSINADA
    s3.head_object.assert_called_once_with(Bucket=P.AWS_S3_BUCKET, Key='pesquisa/docs_indicacoes/RG_10_abc.pdf')


def test_admin_ver_arquivo_recusa_usuario_comum(client, s3):
    logado(client, '111')
    client.get('/admin/verArquivo?file=RG_10_abc.pdf')
    s3.head_object.assert_not_called()


# --- /arquivo/<token> (avaliadores) ------------------------------------------

def test_link_avaliador_valido_sem_login(client, s3):
    resposta = client.get('/arquivo/' + token_avaliador())
    assert resposta.status_code == 302 and resposta.location == URL_ASSINADA
    s3.head_object.assert_called_once_with(Bucket=P.AWS_S3_BUCKET, Key='pesquisa/submissoes/Projeto_1_111_abc.pdf')


def test_link_avaliador_gerado_pela_pagina(client, s3):
    with P.app.test_request_context():
        link = P.link_arquivo_avaliador('Projeto_1_111_abc.pdf')
    assert link.startswith('/arquivo/')
    assert client.get(link).location == URL_ASSINADA


def test_link_avaliador_adulterado(client, s3):
    token = token_avaliador()
    resposta = client.get('/arquivo/' + token[:-2] + ('AA' if token[-2:] != 'AA' else 'BB'))
    assert resposta.status_code == 403
    assert 'Link expirado' in resposta.get_data(as_text=True)
    s3.head_object.assert_not_called()


def test_link_avaliador_de_outra_chave(client, s3):
    from itsdangerous import URLSafeTimedSerializer
    token = URLSafeTimedSerializer('outra-chave', salt='arquivo-avaliador').dumps(
        {'p': 'submissoes', 'n': 'Projeto_1_111_abc.pdf'})
    assert client.get('/arquivo/' + token).status_code == 403
    s3.head_object.assert_not_called()


def test_link_avaliador_expirado(client, s3, monkeypatch):
    token = token_avaliador()
    monkeypatch.setattr(P, 'ARQUIVOS_LINK_VALIDADE', -1)
    resposta = client.get('/arquivo/' + token)
    assert resposta.status_code == 410
    assert 'Link expirado' in resposta.get_data(as_text=True)
    s3.head_object.assert_not_called()


@pytest.mark.parametrize('dados', [{'p': 'cppgi', 'n': 'x.pdf'}, {'n': 'x.pdf'}, 'texto'])
def test_link_avaliador_com_conteudo_invalido(client, s3, dados):
    assert client.get('/arquivo/' + P.assinador_arquivos.dumps(dados)).status_code == 403
    s3.head_object.assert_not_called()
