"""Testes do upload para o S3 em SSE-KMS (migracao.s3.md, fase 2) com o cliente boto3 mockado.

Também cobre a proteção do script de migração contra sobrescrever arquivos enviados pelo app.
Não acessam a AWS nem o banco. Rodar a partir de app/: pytest test_upload_s3.py -v
"""
import io
import string
import sys
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from werkzeug.datastructures import FileStorage

import pesquisa as P

sys.path.insert(0, 'scripts')
import migrar_gpg_kms as M  # noqa: E402

PDF = b'%PDF-1.7 conteudo do projeto'


@pytest.fixture
def s3(monkeypatch):
    c = MagicMock()
    monkeypatch.setattr(P, 's3', c)
    monkeypatch.setattr(P, 'PRODUCAO', 1)
    return c


def arquivo(conteudo=PDF, nome='original.pdf'):
    return FileStorage(stream=io.BytesIO(conteudo), filename=nome)


# --- enviar_arquivo_s3 -------------------------------------------------------

def test_envia_pdf_em_sse_kms(s3):
    assert P.enviar_arquivo_s3(arquivo(), 'submissoes', 'projeto_001_111_abc.pdf') is True
    args = s3.put_object.call_args.kwargs
    assert args['Bucket'] == P.AWS_S3_BUCKET
    assert args['Key'] == 'pesquisa/submissoes/projeto_001_111_abc.pdf'
    assert args['ServerSideEncryption'] == 'aws:kms'
    assert 'SSEKMSKeyId' not in args  # chave gerenciada pela AWS (aws/s3)
    assert args['ContentType'] == 'application/pdf'
    assert args['Metadata'] == {'enviado-por': 'app'}
    assert args['Body'].read() == PDF  # stream rebobinado depois de detectar o tipo


@pytest.mark.parametrize('conteudo,tipo', [
    (b'\xff\xd8\xff\xe0foto', 'image/jpeg'),
    (b'\x89PNG\r\n\x1a\nimagem', 'image/png'),
    (b'', 'application/octet-stream'),
    (b'MZ executavel', 'application/octet-stream'),
])
def test_content_type_pelo_conteudo(s3, conteudo, tipo):
    P.enviar_arquivo_s3(arquivo(conteudo), 'docs_indicacoes', 'EXTRATO.10.abc.pdf')
    assert s3.put_object.call_args.kwargs['Key'] == 'pesquisa/docs_indicacoes/EXTRATO.10.abc.pdf'
    assert s3.put_object.call_args.kwargs['ContentType'] == tipo


def test_falha_do_s3_retorna_false(s3):
    s3.put_object.side_effect = ClientError({'Error': {'Code': 'AccessDenied', 'Message': 'x'}}, 'PutObject')
    assert P.enviar_arquivo_s3(arquivo(), 'submissoes', 'projeto_001_111_abc.pdf') is False


@pytest.mark.parametrize('nome', ['', '../cppgi/x.pdf', 'TERMO.1/../x.pdf', 'a b.pdf'])
def test_nome_inseguro_recusado(s3, nome):
    assert P.enviar_arquivo_s3(arquivo(), 'docs_indicacoes', nome) is False
    s3.put_object.assert_not_called()


def test_dev_nao_envia_ao_s3(s3, monkeypatch):
    monkeypatch.setattr(P, 'PRODUCAO', 0)
    assert P.enviar_arquivo_s3(arquivo(), 'submissoes', 'projeto_001_111_abc.pdf') is True
    s3.put_object.assert_not_called()


# --- uploads em memória e nomes ----------------------------------------------

def test_upload_grande_fica_em_memoria():
    """O Werkzeug gravaria em /tmp os uploads acima de 500 KB; o app os mantém em memória."""
    conteudo = b'%PDF' + b'x' * (2 * 1024 * 1024)
    with P.app.test_request_context('/', method='POST', content_type='multipart/form-data',
                                    data={'f': (io.BytesIO(conteudo), 'grande.pdf')}):
        stream = P.request.files['f'].stream
        assert isinstance(stream, io.BytesIO)
        assert stream.getvalue() == conteudo


def test_id_generator_usa_secrets(monkeypatch):
    usados = []
    monkeypatch.setattr(P.secrets, 'choice', lambda chars: usados.append(chars) or 'Z')
    assert P.id_generator() == 'Z' * 20
    assert len(usados) == 20
    monkeypatch.undo()
    codigo = P.id_generator(40)
    assert len(codigo) == 40 and set(codigo) <= set(string.ascii_letters + string.digits)


# --- script de migração: nunca sobrescreve o que o app enviou ----------------

def objetos(*chaves):
    return {k: {'etag': 'etag-' + k[-5:], 'tamanho': 1} for k in chaves}


def test_situacao_arquivo_enviado_pelo_app_e_substituido():
    c = MagicMock()
    c.head_object.return_value = {'ServerSideEncryption': 'aws:kms', 'Metadata': {'enviado-por': 'app'}}
    lista = objetos('pesquisa/submissoes/a.pdf.gpg', 'pesquisa/submissoes/a.pdf')
    assert M.situacao(c, 'b', 'pesquisa/submissoes/a.pdf.gpg', 'e1', lista) == 'substituido'


def test_situacao_migrado_e_desatualizado():
    c = MagicMock()
    lista = objetos('pesquisa/submissoes/a.pdf.gpg', 'pesquisa/submissoes/a.pdf')
    c.head_object.return_value = {'ServerSideEncryption': 'aws:kms',
                                  'Metadata': {M.META_ORIGEM: 'a.pdf.gpg', M.META_ETAG: 'e1'}}
    assert M.situacao(c, 'b', 'pesquisa/submissoes/a.pdf.gpg', 'e1', lista) == 'migrado'
    assert M.situacao(c, 'b', 'pesquisa/submissoes/a.pdf.gpg', 'e2', lista) == 'desatualizado'
    assert M.situacao(c, 'b', 'pesquisa/submissoes/b.pdf.gpg', 'e1', lista) == 'pendente'


class GpgFalso:
    def decrypt(self, dados, passphrase):
        r = MagicMock()
        r.ok, r.data = True, PDF
        return r


@pytest.mark.parametrize('etag_destino,condicao', [(None, {'IfNoneMatch': '*'}), ('etag-x', {'IfMatch': 'etag-x'})])
def test_migrar_um_grava_condicionalmente(monkeypatch, etag_destino, condicao):
    monkeypatch.setattr(M, 'gpg_da_thread', lambda: GpgFalso())
    c = MagicMock()
    c.get_object.return_value = {'Body': io.BytesIO(b'cifrado')}
    c.head_object.return_value = {'ServerSideEncryption': 'aws:kms', 'ContentLength': len(PDF)}
    status, *_ = M.migrar_um(c, 'b', 'senha', 'pesquisa/submissoes/a.pdf.gpg', 'e1', False, etag_destino)
    assert status == 'migrado'
    args = c.put_object.call_args.kwargs
    for chave, valor in condicao.items():
        assert args[chave] == valor
    assert ({'IfMatch', 'IfNoneMatch'} - set(condicao)).isdisjoint(args)
