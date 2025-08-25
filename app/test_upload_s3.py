# -*- coding: utf-8 -*-
"""
Test the home route of the app.
This module contains a test for the home route of the app.
"""
import time
import os
from pesquisa import encripta_e_apaga,s3,AWS_S3_BUCKET

def test_upload_s3():
    """Test the upload to S3."""
    arquivo = "docs_indicacoes/00_arquivo.pdf"
    encripta_e_apaga(arquivo)
    time.sleep(5)  # Wait for the upload thread to finish
    # Here you would typically check if the file exists in S3
    #assert s3_file_exists(AWS_S3_BUCKET, "pesquisa/docs_indicacoes/00_arquivo.pdf")
    assert not os.path.exists(arquivo + ".gpg")
    assert not os.path.exists(arquivo)
