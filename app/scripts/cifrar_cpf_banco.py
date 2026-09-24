#!/usr/bin/env python3
"""
Cifra o CPF e os dados bancários já gravados (migracao.cripto_cpf.md):

  * indicacoes:     cpf, nome_banco, agencia, conta
  * alunos:         cpf (gera o iv, que a tabela não tinha)
  * cadastro_geral: cpf (as demais colunas pessoais já estavam cifradas)

Mesmo esquema das colunas já cifradas pelo app: AES-256-CBC do MariaDB, com a AES_KEY e o
iv da linha, em base64. Cada linha também recebe o cpf_hash (HMAC-SHA256 do CPF só com
dígitos, com a CPF_HMAC_KEY), usado nas buscas; cpf_hash preenchido marca a linha como
cifrada. A cifra é feita dentro do próprio UPDATE (os valores não passam em claro pelo
script); só o CPF é lido, para calcular o hash.

Idempotente: só processa linhas com cpf_hash IS NULL, e pode ser interrompido e executado
de novo. Nunca imprime CPF, dados bancários nem as chaves: só contagens e ids.

Pré-requisitos: o cripto_cpf.sql.sample já aplicado (colunas cpf_hash, iv em alunos,
cadastro_geral em InnoDB), a /pesquisa/CPF_HMAC_KEY no SSM e um backup recente do banco.

Execução na EC2 (roteiro completo em migracao.cripto_cpf.md):
    cd /opt/moduloPesquisaPRPI/app
    env/bin/python scripts/cifrar_cpf_banco.py --simular
    env/bin/python scripts/cifrar_cpf_banco.py --limite 10
    env/bin/python scripts/cifrar_cpf_banco.py --verificar
    env/bin/python scripts/cifrar_cpf_banco.py
    env/bin/python scripts/cifrar_cpf_banco.py --verificar
"""
import argparse
import hashlib
import hmac
import os
import re
import secrets
import sys

import mariadb

REGIAO = "us-east-2"
TABELAS = {
    # tabela: (colunas a cifrar, gera iv novo?)
    "indicacoes": (("cpf", "nome_banco", "agencia", "conta"), False),
    "alunos": (("cpf",), True),
    "cadastro_geral": (("cpf",), False),
}
MODO = "'aes-256-cbc'"


def carregar_ssm():
    """Mesmo carregamento do app: tudo sob /pesquisa vai para o os.environ."""
    import boto3
    ssm = boto3.client("ssm", region_name=REGIAO)
    for pagina in ssm.get_paginator("get_parameters_by_path").paginate(Path="/pesquisa", Recursive=True, WithDecryption=True):
        for p in pagina.get("Parameters", []):
            os.environ[p["Name"].rstrip("/").split("/")[-1]] = p["Value"]


def conectar(local):
    args = dict(host=os.environ.get("MYSQL_HOST", "localhost"), user=os.environ.get("MYSQL_USER", "pesquisa"),
                passwd=os.environ["MYSQL_PASSWORD"], db=os.environ.get("MYSQL_DATABASE", "pesquisa"))
    if not local:
        args["ssl"] = "required"
    conn = mariadb.connect(**args)
    conn.autocommit = False
    return conn


def normalizar_cpf(cpf):
    return re.sub(r"\D", "", str(cpf or ""))


def hash_cpf(chave, cpf):
    """Igual ao hash_cpf do app (pesquisa.py)."""
    return hmac.new(chave.encode(), normalizar_cpf(cpf).encode(), hashlib.sha256).hexdigest()


def colunas_da_tabela(cur, tabela):
    cur.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s", (tabela,))
    return {linha[0] for linha in cur.fetchall()}


def conferir_estrutura(cur):
    """Confere o cripto_cpf.sql.sample: cpf_hash nas 3 tabelas, iv em alunos, cadastro_geral em InnoDB."""
    faltas = []
    for tabela in TABELAS:
        colunas = colunas_da_tabela(cur, tabela)
        if "cpf_hash" not in colunas:
            faltas.append(f"{tabela}.cpf_hash")
        if "iv" not in colunas:
            faltas.append(f"{tabela}.iv")
    cur.execute("SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cadastro_geral'")
    motor = cur.fetchone()
    if motor and motor[0] != "InnoDB":
        faltas.append(f"cadastro_geral em InnoDB (hoje: {motor[0]})")
    return faltas


def tamanho_cifrado(tamanho_bytes):
    """Tamanho gravado de TO_BASE64(AES_ENCRYPT(...)): o AES-256-CBC completa até o próximo múltiplo de
    16 bytes (sempre acrescenta) e o TO_BASE64 do MariaDB quebra a linha a cada 76 caracteres.
    Conferido num MariaDB 11: 14 -> 24, 100 -> 153, 367 -> 498, 368 -> 518."""
    blocos = (tamanho_bytes // 16 + 1) * 16
    base64 = 4 * -(-blocos // 3)
    return base64 + (base64 - 1) // 76


def conferir_tamanhos(cur):
    """Se o banco não estiver em modo estrito, um valor cifrado maior que a coluna seria cortado sem aviso
    (e não decifraria mais). Confere o maior valor ainda não cifrado de cada coluna antes de alterar."""
    problemas = []
    for tabela, (colunas, _) in TABELAS.items():
        for coluna in colunas:
            cur.execute("SELECT CHARACTER_MAXIMUM_LENGTH FROM information_schema.COLUMNS "
                        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s", (tabela, coluna))
            limite = cur.fetchone()[0]
            cur.execute(f"SELECT COALESCE(MAX(LENGTH(`{coluna}`)), 0) FROM `{tabela}` WHERE cpf_hash IS NULL")
            maior = cur.fetchone()[0]
            if maior and tamanho_cifrado(maior) > limite:
                problemas.append(f"{tabela}.{coluna}: o maior valor ({maior} bytes) cifrado ocupa "
                                 f"{tamanho_cifrado(maior)} e a coluna aceita {limite}")
    return problemas


def montar_update(tabela, colunas, iv_novo):
    """UPDATE de uma linha. Valores vazios ficam como estão. Parâmetros: [iv], (chave, iv) por coluna, hash, id."""
    iv_sql = "%s" if iv_novo else "iv"
    partes = ["iv = %s"] if iv_novo else []
    for coluna in colunas:
        partes.append(f"`{coluna}` = IF(`{coluna}` IS NULL OR `{coluna}` = '', `{coluna}`, "
                      f"TO_BASE64(AES_ENCRYPT(`{coluna}`, %s, {iv_sql}, {MODO})))")
    partes.append("cpf_hash = %s")
    return f"UPDATE `{tabela}` SET {', '.join(partes)} WHERE id = %s AND cpf_hash IS NULL"


def parametros_update(colunas, iv_novo, iv, chave_aes, hash_valor, id_linha):
    params = [iv] if iv_novo else []
    for _ in colunas:
        params.extend([chave_aes, iv] if iv_novo else [chave_aes])
    return params + [hash_valor, id_linha]


def iv_valido(iv):
    return iv is not None and len(str(iv)) >= 16


def resumo_pendencias(cur, tabela, iv_novo):
    cur.execute(f"SELECT id, cpf, iv FROM `{tabela}` WHERE cpf_hash IS NULL ORDER BY id")
    pendentes = cur.fetchall()
    fora_formato = [i for i, cpf, _ in pendentes if normalizar_cpf(cpf) and len(normalizar_cpf(cpf)) != 11]
    vazios = sum(1 for _, cpf, _ in pendentes if not normalizar_cpf(cpf))
    iv_ruim = [] if iv_novo else [i for i, _, iv in pendentes if not iv_valido(iv)]
    return pendentes, fora_formato, vazios, iv_ruim


def cifrar_tabela(conn, tabela, chave_aes, chave_hmac, limite, simular):
    colunas, iv_novo = TABELAS[tabela]
    cur = conn.cursor()
    pendentes, fora_formato, vazios, iv_ruim = resumo_pendencias(cur, tabela, iv_novo)
    print(f"[{tabela}] pendentes: {len(pendentes)} | CPF vazio: {vazios} | CPF fora do formato: {len(fora_formato)}"
          f"{' (ids: ' + ', '.join(map(str, fora_formato[:20])) + ')' if fora_formato else ''}"
          f" | iv inválido (pulados): {len(iv_ruim)}{' (ids: ' + ', '.join(map(str, iv_ruim[:20])) + ')' if iv_ruim else ''}",
          flush=True)
    if simular:
        return 0
    consulta = montar_update(tabela, colunas, iv_novo)
    feitas = falhas = 0
    for id_linha, cpf, iv in pendentes:
        if limite and feitas >= limite:
            break
        if not iv_novo and not iv_valido(iv):
            continue
        if iv_novo:
            iv = secrets.token_urlsafe(16)
        # Um commit por linha: uma falha não desfaz as anteriores (são só alguns milhares de linhas)
        try:
            cur.execute(consulta, parametros_update(colunas, iv_novo, iv, chave_aes, hash_cpf(chave_hmac, cpf), id_linha))
            conn.commit()
            feitas += cur.rowcount
        except mariadb.Error as e:
            conn.rollback()
            falhas += 1
            print(f"[{tabela}] FALHA id={id_linha}: {type(e).__name__}", flush=True)
    print(f"[{tabela}] cifradas: {feitas} | falhas: {falhas}", flush=True)
    return falhas


def verificar_tabela(conn, tabela, chave_aes, chave_hmac, amostra):
    """Sem pendências e, numa amostra, o CPF decifrado bate com o cpf_hash e os dados bancários decifram."""
    colunas, _ = TABELAS[tabela]
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM `{tabela}` WHERE cpf_hash IS NULL")
    pendentes = cur.fetchone()[0]
    decifras = ", ".join(
        f"IF(`{c}` IS NULL OR `{c}` = '', '', CONVERT(AES_DECRYPT(FROM_BASE64(`{c}`), %s, iv, {MODO}), CHAR))" for c in colunas)
    cur.execute(f"SELECT id, cpf_hash, {decifras} FROM `{tabela}` WHERE cpf_hash IS NOT NULL ORDER BY RAND() LIMIT %s",
                tuple([chave_aes] * len(colunas)) + (amostra,))
    problemas = []
    linhas = cur.fetchall()
    for id_linha, hash_gravado, *valores in linhas:
        if any(v is None for v in valores):
            problemas.append(id_linha)  # alguma coluna não decifrou
        elif not hmac.compare_digest(hash_cpf(chave_hmac, valores[0]), hash_gravado):
            problemas.append(id_linha)  # CPF decifrado não bate com o hash
    ok = pendentes == 0 and not problemas
    print(f"[{tabela}] pendentes: {pendentes} | amostra: {len(linhas)} | problemas: {len(problemas)}"
          f"{' (ids: ' + ', '.join(map(str, problemas[:20])) + ')' if problemas else ''} -> {'OK' if ok else 'ATENÇÃO'}",
          flush=True)
    return ok


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tabela", choices=list(TABELAS), help="só esta tabela (padrão: as três)")
    parser.add_argument("--limite", type=int, default=0, help="no máximo N linhas por tabela")
    parser.add_argument("--simular", action="store_true", help="só mostra as contagens, sem alterar nada")
    parser.add_argument("--verificar", action="store_true", help="confere pendências e uma amostra decifrada")
    parser.add_argument("--amostra", type=int, default=200, help="tamanho da amostra do --verificar")
    parser.add_argument("--local", action="store_true",
                        help="testes: banco local sem SSL e sem SSM (MYSQL_*, AES_KEY e CPF_HMAC_KEY do ambiente)")
    args = parser.parse_args()

    if not args.local:
        carregar_ssm()
    chave_aes, chave_hmac = os.environ.get("AES_KEY", ""), os.environ.get("CPF_HMAC_KEY", "")
    if not chave_aes or not chave_hmac:
        sys.exit("AES_KEY e CPF_HMAC_KEY são obrigatórias (SSM /pesquisa/...).")

    conn = conectar(args.local)
    cur = conn.cursor()
    cur.execute("SELECT DATABASE(), @@block_encryption_mode")
    banco, modo = cur.fetchone()
    print(f"Banco: {banco} | block_encryption_mode do servidor: {modo} (o script usa aes-256-cbc explícito)", flush=True)
    faltas = conferir_estrutura(cur)
    if faltas:
        sys.exit("Estrutura incompleta, rode o cripto_cpf.sql.sample antes: " + "; ".join(faltas))
    grandes = conferir_tamanhos(cur)
    if grandes:
        sys.exit("Coluna pequena para o valor cifrado (nada foi alterado): " + "; ".join(grandes))

    tabelas = [args.tabela] if args.tabela else list(TABELAS)
    if args.verificar:
        ok = all([verificar_tabela(conn, t, chave_aes, chave_hmac, args.amostra) for t in tabelas])
        sys.exit(0 if ok else 1)
    falhas = sum(cifrar_tabela(conn, t, chave_aes, chave_hmac, args.limite, args.simular) for t in tabelas)
    conn.close()
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
