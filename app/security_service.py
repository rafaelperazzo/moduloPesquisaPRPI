import json
import boto3

# Inicializa o client da Lambda apontando para a região correta
lambda_client = boto3.client('lambda', region_name='us-east-2')
FUNCTION_NAME = 'criptografia-aes'

def _call_crypto_lambda(payload: dict):
    """Envia o payload para a função Lambda e extrai o resultado."""
    response = lambda_client.invoke(
        FunctionName=FUNCTION_NAME,
        InvocationType='RequestResponse',
        Payload=json.dumps(payload)
    )
    
    # Decodifica a resposta da Lambda
    response_payload = json.loads(response['Payload'].read().decode('utf-8'))
    
    # Se a Lambda retornou um body serializado
    body = json.loads(response_payload['body']) if isinstance(response_payload.get('body'), str) else response_payload.get('body', {})
    
    if response_payload.get('statusCode') != 200:
        erro = body.get('erro', 'Erro desconhecido na execução da Lambda')
        raise RuntimeError(f"Erro na função Lambda: {erro}")
        
    return body.get('resultado')

# --- Funções Prontas para o seu App ---

def criptografar_dado(texto_puro: str) -> str:
    """Criptografa dados sensíveis com AES-256-GCM."""
    return _call_crypto_lambda({
        "operacao": "criptografar",
        "texto": texto_puro
    })

def descriptografar_dado(texto_cifrado_base64: str) -> str:
    """Descriptografa o dado cifrado com AES-256-GCM."""
    return _call_crypto_lambda({
        "operacao": "descriptografar",
        "texto": texto_cifrado_base64
    })

def gerar_hash_sha3(texto: str) -> str:
    """Gera o hash SHA3-256 (ideal para checksums, tokens determinísticos e integridade)."""
    return _call_crypto_lambda({
        "operacao": "hash_sha3_256",
        "texto": texto
    })

def criar_hash_senha(senha_pura: str) -> str:
    """Gera hash seguro com Argon2id + Pepper (HMAC) para salvar no banco."""
    return _call_crypto_lambda({
        "operacao": "hash_argon2id",
        "texto": senha_pura
    })

def verificar_senha(senha_fornecida: str, hash_banco: str) -> bool:
    """Verifica se a senha fornecida no login confere com o hash salvo no banco."""
    return _call_crypto_lambda({
        "operacao": "verificar_argon2id",
        "texto": senha_fornecida,
        "hash": hash_banco
    })