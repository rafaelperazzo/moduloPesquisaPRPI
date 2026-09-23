"""Testes do upload direto do navegador (migracao.s3.md, fase 3) e da Lambda validar-upload.

S3 mockado: não acessam a AWS nem o banco. Rodar a partir de app/: pytest test_upload_direto.py -v
"""
import io
import os
import re
import sys
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from flask.sessions import SecureCookieSessionInterface

import pesquisa as P

os.environ.setdefault('AWS_DEFAULT_REGION', 'us-east-2')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambda', 'validar_upload'))
import lambda_function as L  # noqa: E402

TOKEN = 'A' * 32


def erro(codigo, operacao='HeadObject'):
    return ClientError({'Error': {'Code': codigo, 'Message': codigo}}, operacao)


@pytest.fixture
def s3(monkeypatch):
    c = MagicMock()
    c.generate_presigned_post.return_value = {'url': 'https://s3.exemplo/', 'fields': {'key': 'k', 'policy': 'p'}}
    monkeypatch.setattr(P.app, 'session_interface', SecureCookieSessionInterface())
    monkeypatch.setattr(P.app, 'secret_key', 'teste-upload-direto')
    monkeypatch.setitem(P.app.config, 'WTF_CSRF_ENABLED', False)
    monkeypatch.setattr(P.limiter, 'enabled', False)
    monkeypatch.setattr(P, 's3', c)
    monkeypatch.setattr(P, 'PRODUCAO', 1)
    monkeypatch.setattr(P, 'getEditaisAbertos', lambda: [(1, 'Edital', '31/12/2026')])
    monkeypatch.setattr(P, 'idSiape', lambda id, siape: (str(id), str(siape)) == ('10', '111'))
    monkeypatch.setattr(P.time, 'sleep', lambda s: None)
    monkeypatch.setattr(P, 'carregar_mensagens', lambda: [])  # banner do BASE_v3 lê o banco
    return c


@pytest.fixture
def client(s3):
    c = P.app.test_client()
    with c.session_transaction() as s:
        s.update({'username': '111', 'permissao': 1, 'roles': ['user'], 'edital': 0})
    return c


def pedir(client, **dados):
    corpo = {'tipo': 'submissoes', 'campo': 'arquivo_projeto', 'tamanho': 1000, 'content_type': 'application/pdf'}
    corpo.update(dados)
    return client.post('/arquivos/url_upload', json=corpo)


# --- /arquivos/url_upload ----------------------------------------------------

def test_url_upload_submissao(client, s3):
    resposta = pedir(client)
    assert resposta.status_code == 200
    nome = resposta.json['nome']
    assert re.fullmatch(r'projeto_111_[A-Za-z0-9]{32}\.pdf', nome)
    args, kwargs = s3.generate_presigned_post.call_args
    assert args == (P.AWS_S3_BUCKET, 'pesquisa/incoming/submissoes/' + nome)
    assert kwargs['Fields'] == {'Content-Type': 'application/pdf', 'x-amz-server-side-encryption': 'aws:kms'}
    assert {'x-amz-server-side-encryption': 'aws:kms'} in kwargs['Conditions']
    assert {'Content-Type': 'application/pdf'} in kwargs['Conditions']
    assert ['content-length-range', 1, P.app.config['MAX_CONTENT_LENGTH']] in kwargs['Conditions']
    assert kwargs['ExpiresIn'] == 300


def test_url_upload_indicacao_com_imagem(client, s3):
    resposta = pedir(client, tipo='docs_indicacoes', campo='extrato', idProjeto='10', content_type='image/jpeg')
    assert resposta.status_code == 200
    assert re.fullmatch(r'EXTRATO\.10\.[A-Za-z0-9]{32}\.pdf', resposta.json['nome'])


@pytest.mark.parametrize('dados,status', [
    ({'content_type': 'image/jpeg'}, 415),  # submissão só aceita PDF
    ({'content_type': 'application/x-msdownload'}, 415),
    ({'campo': 'arquivo_lattes'}, 400),  # campo fora da lista
    ({'tipo': 'cppgi'}, 400),
    ({'tamanho': 0}, 413),
    ({'tamanho': 16 * 1000 * 1000 + 1}, 413),
    ({'tamanho': '1000'}, 413),
    ({'tipo': 'docs_indicacoes', 'campo': 'termo', 'idProjeto': '11'}, 403),  # projeto de outro
    ({'tipo': 'docs_indicacoes', 'campo': 'termo', 'idProjeto': '10 OR 1=1'}, 403),
])
def test_url_upload_recusas(client, s3, dados, status):
    assert pedir(client, **dados).status_code == status
    s3.generate_presigned_post.assert_not_called()


def test_url_upload_admin_indica_em_qualquer_projeto(client, s3):
    with client.session_transaction() as s:
        s['roles'] = ['admin', 'user']
    assert pedir(client, tipo='docs_indicacoes', campo='termo', idProjeto='11').status_code == 200


def test_url_upload_sem_edital_aberto(client, s3, monkeypatch):
    monkeypatch.setattr(P, 'getEditaisAbertos', lambda: [])
    assert pedir(client).status_code == 403


def test_url_upload_desativado_em_dev(client, s3, monkeypatch):
    monkeypatch.setattr(P, 'PRODUCAO', 0)
    assert pedir(client).status_code == 404
    s3.generate_presigned_post.assert_not_called()


def test_url_upload_exige_login(s3):
    resposta = P.app.test_client().post('/arquivos/url_upload', json={})
    assert resposta.status_code == 200 and b'login' in resposta.data.lower()  # página de login
    s3.generate_presigned_post.assert_not_called()


# --- uploads_diretos (conferência no submit) ---------------------------------

def conferir(form, prefixo='submissoes', idProjeto=''):
    with P.app.test_request_context('/', method='POST', data=form):
        return P.uploads_diretos(prefixo, '111', idProjeto)


def test_uploads_diretos_aceita_nomes_do_usuario(s3):
    s3.head_object.return_value = {}
    diretos, erro_msg = conferir({'arquivo_projeto_s3': 'projeto_111_' + TOKEN + '.pdf',
                                  'arquivo_plano1_s3': 'plano1_111_' + TOKEN + '.pdf'})
    assert erro_msg is None
    assert diretos == {'arquivo_projeto': 'projeto_111_' + TOKEN + '.pdf', 'arquivo_plano1': 'plano1_111_' + TOKEN + '.pdf'}
    s3.head_object.assert_any_call(Bucket=P.AWS_S3_BUCKET, Key='pesquisa/submissoes/projeto_111_' + TOKEN + '.pdf')


@pytest.mark.parametrize('nome', [
    'projeto_222_' + TOKEN + '.pdf',  # arquivo de outro usuário
    'plano1_111_' + TOKEN + '.pdf',  # rótulo de outro campo
    'projeto_111_' + TOKEN[:20] + '.pdf',  # nome antigo (20 caracteres)
    'projeto_111_' + TOKEN + '.pdf/../x',
])
def test_uploads_diretos_recusa_nome_alheio(s3, nome):
    diretos, erro_msg = conferir({'arquivo_projeto_s3': nome})
    assert diretos == {} and 'inválido' in erro_msg
    s3.head_object.assert_not_called()


def test_uploads_diretos_indicacao_amarrada_ao_projeto(s3):
    s3.head_object.return_value = {}
    nome = 'TERMO.10.' + TOKEN + '.pdf'
    assert conferir({'termo_s3': nome}, 'docs_indicacoes', '10') == ({'termo': nome}, None)
    diretos, erro_msg = conferir({'termo_s3': nome}, 'docs_indicacoes', '11')
    assert diretos == {} and erro_msg


def test_uploads_diretos_recusado_pela_lambda(s3):
    s3.head_object.side_effect = erro('404')
    diretos, erro_msg = conferir({'arquivo_projeto_s3': 'projeto_111_' + TOKEN + '.pdf'})
    assert diretos == {} and 'precisa ser PDF' in erro_msg
    assert s3.head_object.call_count == P.UPLOAD_DIRETO_ESPERA


def test_uploads_diretos_espera_a_lambda(s3):
    s3.head_object.side_effect = [erro('404'), erro('404'), {}]
    diretos, erro_msg = conferir({'arquivo_projeto_s3': 'projeto_111_' + TOKEN + '.pdf'})
    assert erro_msg is None and diretos
    assert s3.head_object.call_count == 3


def test_sem_campos_s3_nada_a_conferir(s3):
    assert conferir({'titulo': 'x'}) == ({}, None)


# --- Lambda validar-upload ---------------------------------------------------

def evento(chave, bucket='rajardekalambur'):
    return {'detail-type': 'Object Created', 'source': 'aws.s3',
            'detail': {'bucket': {'name': bucket}, 'object': {'key': chave}}}


@pytest.fixture
def ls3(monkeypatch):
    c = MagicMock()
    c.head_object.return_value = {'ContentLength': 1000, 'ETag': '"etag1"'}
    c.get_object.return_value = {'Body': io.BytesIO(b'%PDF-1.7')}
    monkeypatch.setattr(L, 's3', c)
    return c


def test_lambda_aceita_pdf(ls3):
    r = L.lambda_handler(evento('pesquisa/incoming/submissoes/projeto_111_' + TOKEN + '.pdf'), None)
    assert r['resultado'] == 'aceito'
    ls3.copy_object.assert_called_once_with(
        Bucket='rajardekalambur', Key='pesquisa/submissoes/projeto_111_' + TOKEN + '.pdf',
        CopySource={'Bucket': 'rajardekalambur', 'Key': 'pesquisa/incoming/submissoes/projeto_111_' + TOKEN + '.pdf'},
        CopySourceIfMatch='"etag1"', ServerSideEncryption='aws:kms', MetadataDirective='REPLACE',
        ContentType='application/pdf', Metadata={'enviado-por': 'navegador'})
    ls3.get_object.assert_called_once_with(Bucket='rajardekalambur', Key=r['chave'], Range='bytes=0-7', IfMatch='"etag1"')
    ls3.delete_object.assert_called_once_with(Bucket='rajardekalambur', Key=r['chave'])


def test_lambda_aceita_jpeg_nas_indicacoes(ls3):
    ls3.get_object.return_value = {'Body': io.BytesIO(b'\xff\xd8\xff\xe0abcd')}
    r = L.lambda_handler(evento('pesquisa/incoming/docs_indicacoes/EXTRATO.10.' + TOKEN + '.pdf'), None)
    assert r['resultado'] == 'aceito' and r['tipo'] == 'image/jpeg'
    assert ls3.copy_object.call_args.kwargs['Key'] == 'pesquisa/docs_indicacoes/EXTRATO.10.' + TOKEN + '.pdf'


@pytest.mark.parametrize('conteudo,prefixo', [
    (b'\xff\xd8\xff\xe0abcd', 'submissoes'),  # imagem não é aceita em submissões
    (b'MZ\x90\x00exe!', 'docs_indicacoes'),  # .exe renomeado para .pdf
    (b'<html>xx', 'submissoes'),
])
def test_lambda_recusa_tipo(ls3, conteudo, prefixo):
    ls3.get_object.return_value = {'Body': io.BytesIO(conteudo)}
    chave = 'pesquisa/incoming/' + prefixo + '/x_' + TOKEN + '.pdf'
    r = L.lambda_handler(evento(chave), None)
    assert r['resultado'] == 'recusado' and r['motivo'] == 'tipo'
    ls3.copy_object.assert_not_called()
    ls3.delete_object.assert_called_once_with(Bucket='rajardekalambur', Key=chave)


@pytest.mark.parametrize('tamanho', [0, 16 * 1000 * 1000 + 1])
def test_lambda_recusa_tamanho(ls3, tamanho):
    ls3.head_object.return_value = {'ContentLength': tamanho, 'ETag': '"e"'}
    r = L.lambda_handler(evento('pesquisa/incoming/submissoes/x_' + TOKEN + '.pdf'), None)
    assert r['motivo'] == 'tamanho'
    ls3.copy_object.assert_not_called()


@pytest.mark.parametrize('chave', [
    'pesquisa/incoming/cppgi/x.pdf',
    'pesquisa/incoming/submissoes/sub/x.pdf',
    'pesquisa/incoming/submissoes/x.exe',
    'pesquisa/incoming/x.pdf',
])
def test_lambda_recusa_chave_invalida(ls3, chave):
    r = L.lambda_handler(evento(chave), None)
    assert r['resultado'] == 'recusado' and r['motivo'] == 'chave inválida'
    ls3.copy_object.assert_not_called()
    ls3.delete_object.assert_called_once()


def test_lambda_ignora_fora_de_incoming(ls3):
    r = L.lambda_handler(evento('pesquisa/submissoes/x.pdf'), None)
    assert r['resultado'] == 'ignorado'
    ls3.delete_object.assert_not_called()
    ls3.copy_object.assert_not_called()


def test_lambda_evento_repetido(ls3):
    ls3.head_object.side_effect = erro('404')
    r = L.lambda_handler(evento('pesquisa/incoming/submissoes/x_' + TOKEN + '.pdf'), None)
    assert r['resultado'] == 'ignorado'
    ls3.copy_object.assert_not_called()
