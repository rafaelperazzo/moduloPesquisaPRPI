# Criptografia do CPF e dos dados bancários (levantamento)

> **Status (2026-09-24): código pronto e NÃO commitado; falta o deploy (seção 7).** Faz parte das recomendações da LGPD (`migracao.lgpd.md`, art. 46).
> - Testado de ponta a ponta num MariaDB 11 descartável (com `aes-256-cbc`, como em produção): o `cripto_cpf.sql.sample`, o script em todos os modos (inclusive rodando de novo) e as consultas reais geradas pelo `pesquisa.py`, capturadas e executadas no banco;
> - 28 testes em `app/test_cripto_cpf.py`, que passam junto com os demais testes com mocks (180 no total).

## 1. Situação atual

**Já cifrados** em `indicacoes`: `rg`, `nascimento`, `telefone`, `celular` e `endereco`.

**Esquema usado:**
- `AES_ENCRYPT` do próprio MariaDB, com a chave `AES_KEY`, que vem do SSM;
- um IV por linha, na coluna `iv`, gerado com `secrets.token_urlsafe(16)`;
- o resultado é gravado em base64;
- para ler, o SQL decifra com `CONVERT(AES_DECRYPT(FROM_BASE64(col), chave, iv, 'AES-256-CBC'), CHAR)` ([pesquisa.py:4770](app/pesquisa.py#L4770)).

**Problemas desse esquema, que a mudança deve evitar:**
1. **Janela em claro:** o `INSERT` grava os dados em claro e só depois um `UPDATE` cifra ([pesquisa.py:4702-4720](app/pesquisa.py#L4702-L4720)). Em produção, o `encrypt_binlog` e o `innodb_encrypt_log` estão ligados (conferido em 2026-09-24), então os logs em disco estão cifrados e o risco é baixo. Ainda assim, vale cifrar direto no `INSERT`.
2. **O modo de cifra depende do servidor:** o `AES_ENCRYPT(rg, chave, iv)` não informa o modo e usa o `block_encryption_mode` do servidor. Em dev, ele está no `docker-compose.yml` (`--block-encryption-mode=aes-256-cbc`). **Em produção, conferido em 2026-09-24: `aes-256-cbc`**, tanto global quanto de sessão. Assim, as colunas já cifradas estão no mesmo modo em que o código decifra. Mesmo assim, o código novo deve sempre informar o modo `'aes-256-cbc'`.
3. **A chave vai no texto da consulta** como parâmetro. Ela nunca é gravada no banco, mas aparece no `PROCESSLIST` e no log geral, se ele estiver ligado. Isso é aceitável, mas vale registrar.

**Colunas que faltam:**

| Tabela | Colunas | Observação |
|---|---|---|
| `indicacoes` | `cpf`, `nome_banco`, `agencia`, `conta` | Tabela principal (desde 2019) |
| `alunos` | `cpf` | Legada. Conferido: **não tem dados bancários**; o `cpf varchar(16)` precisa crescer; não tem `iv`; guarda o `email` do discente (fora do escopo) |
| `cadastro_geral` | `cpf`, `orientador_cpf`, `rg`, `telefone`, `celular`, `estudante_banco`, `estudante_no_agencia`, `estudante_no_conta_corrente` | Legada (antes de 2019), com cerca de 800 linhas. Conferido: todas as colunas são `text` e já existe `iv varchar(100) NOT NULL DEFAULT ''`. Contagem de 2026-09-24: 773 linhas, todas com `iv`; `rg`, `telefone` e `estudante_no_conta_corrente` **parecem já cifrados** (770 a 772 linhas em base64); o **`cpf` está em claro** em 718 linhas. Segunda conferência, também em 2026-09-24: `orientador_cpf` (773), `celular`, `estudante_banco` e `estudante_no_agencia` (770) **já estão cifrados** e **decifram com a `AES_KEY` atual** no modo `aes-256-cbc`. O `cpf` tem 718 linhas em claro, 54 vazias e 1 em outro formato, que o script registra sem mostrar o valor. **Escopo nesta tabela: só o `cpf`**, mais a conversão para InnoDB Também guarda `e-mail` e `orientador_email` (fora do escopo). **É `ENGINE=MyISAM`** (ver a seção 5.4) |

O CPF dos orientadores não é gravado: ele só é usado para buscar o Lattes.

## 2. Decisões de desenho (recomendadas)

1. **Reaproveitar o esquema atual** (AES-256-CBC do MariaDB, com a `AES_KEY` e o `iv` por linha), para ficar coerente com as colunas que já são cifradas. As telas continuam recebendo o valor já decifrado pelo SQL, então os templates não mudam. Unificar tudo numa criptografia feita pelo app (AES-GCM em Python, com a chave fora do SQL) é possível, mas seria outro projeto, abrangendo todas as colunas.
2. **Índice cego para buscar por CPF:** uma coluna nova `cpf_hash CHAR(64)` com `HMAC-SHA256(CPF_HMAC_KEY, cpf só com dígitos)`, e um índice nela.
   - Não pode ser um SHA-256 simples: existem só cerca de 10⁹ CPFs possíveis, e dá para testar todos em minutos.
   - A chave **nova** fica em `/pesquisa/CPF_HMAC_KEY` (SecureString), separada da `AES_KEY`.
   - Esse índice também permite achar indicações duplicadas pelo CPF. Hoje, a checagem de duplicidade é feita pelo **nome** ([pesquisa.py:5473](app/pesquisa.py#L5473)).
3. **Cifrar já no `INSERT`**, com `TO_BASE64(AES_ENCRYPT(%s, %s, %s, 'aes-256-cbc'))` nos `VALUES`. Aproveitar a mudança para levar as cinco colunas já cifradas para esse formato, e eliminar a janela em claro.
4. **Normalizar o CPF** para só dígitos antes de cifrar e de calcular o hash. Hoje há CPFs com e sem pontuação: a rota `/indicacao/<cpf>` monta `000.000.000-00` para comparar.
5. **Mascarar o CPF** onde ele não precisa aparecer completo, como a verificação pública de declaração (`verificar_declaracao.html`): mostrar `***.456.789-**`. Declarações e certificados, que são documentos oficiais, continuam com o CPF completo.
6. **Transição sem parar o sistema:** a leitura usa `IF(cpf_hash IS NULL, cpf, <decifra>)`, então as linhas ainda não migradas continuam aparecendo. Essa expressão sai depois da migração.

## 3. Banco

1. **Antes de tudo**, anotar os tipos atuais: `SHOW CREATE TABLE indicacoes; SHOW CREATE TABLE alunos; SHOW CREATE TABLE cadastro_geral;`.
2. `ALTER TABLE` só para **ampliar** as colunas e **acrescentar** outras. É compatível com o código atual, então pode rodar antes do deploy. O texto cifrado ocupa em base64 cerca de 24 caracteres para até 15 bytes e 44 caracteres para até 31 bytes:
   **`indicacoes`, conferido em produção em 2026-09-24 (cerca de 8 mil linhas):**
   - `cpf`, `agencia` e `conta` já são `varchar(500) NOT NULL` e não precisam mudar;
   - `nome_banco` é `varchar(100)` e precisa crescer, porque o texto cifrado passa de 150 caracteres;
   - não há `UNIQUE` em `cpf`;
   - `iv` é `varchar(30) NOT NULL`, e o script gera um novo quando tiver menos de 16 caracteres;
   - os valores `N/A` dos voluntários também são cifrados, para a leitura seguir uma regra só.
   ```sql
   ALTER TABLE indicacoes
     MODIFY nome_banco VARCHAR(500) NOT NULL,
     ADD cpf_hash CHAR(64) NULL AFTER cpf,
     ADD INDEX idx_cpf_hash (cpf_hash);
   -- alunos (conferido em 2026-09-24): sem dados bancários; cpf varchar(16) precisa crescer; sem coluna iv
   ALTER TABLE alunos
     MODIFY cpf VARCHAR(64) NULL,
     ADD cpf_hash CHAR(64) NULL AFTER cpf,
     ADD iv VARCHAR(30) NULL,
     ADD INDEX idx_cpf_hash (cpf_hash);
   -- cadastro_geral (conferido em 2026-09-24): colunas text, iv já existe; converter para InnoDB (seção 5.4)
   ALTER TABLE cadastro_geral
     ENGINE = InnoDB,
     ADD cpf_hash CHAR(64) NULL AFTER cpf,
     ADD INDEX idx_cpf_hash (cpf_hash);
   ALTER TABLE alunos         MODIFY cpf VARCHAR(64), ADD iv VARCHAR(32) NULL, ADD cpf_hash CHAR(64) NULL, ADD INDEX idx_cpf_hash (cpf_hash);
   ALTER TABLE cadastro_geral MODIFY cpf VARCHAR(64), ADD iv VARCHAR(32) NULL, ADD cpf_hash CHAR(64) NULL, ADD INDEX idx_cpf_hash (cpf_hash);
   ```
   Os tipos exatos dependem do passo 1. Se `cpf` for `BIGINT` nas tabelas legadas, a conversão para `VARCHAR` precisa de atenção aos zeros à esquerda.
3. **Script de migração** `app/scripts/cifrar_cpf_banco.py`, rodado na EC2. Ele segue o padrão do `migrar_gpg_kms.py`: `--simular`, `--limite` e `--verificar`, lê as chaves do SSM e **nunca imprime CPF**. O script precisa ser em Python porque o MariaDB não tem HMAC. Para cada linha com `cpf_hash IS NULL`, ele:
   - normaliza o CPF;
   - calcula o HMAC;
   - faz `UPDATE ... SET cpf = TO_BASE64(AES_ENCRYPT(cpf_normalizado, chave, iv, 'aes-256-cbc')), nome_banco = ..., agencia = ..., conta = ..., cpf_hash = %s WHERE id = %s AND cpf_hash IS NULL`.

   O script é idempotente e pode ser repetido. Nas tabelas legadas, ele gera o `iv` antes. Na verificação, confere que `COUNT(cpf_hash IS NULL) = 0` e que o CPF decifrado bate com o hash, numa amostra.
4. **Backup** logo antes de rodar o script. Um script de reversão (decifrar de volta), guardado junto, serve de plano B.

**Por quanto tempo o CPF em claro ainda existe:** os backups antigos em `pesquisa/backup/`, cifrados com GPG, continuam com o CPF em claro até expirarem. Os binlogs são cifrados (`encrypt_binlog=ON`) e expiram conforme a configuração do servidor. Isso está coberto pela política de retenção dos backups, que deve ser definida (`migracao.lgpd.md`, seção 4).

## 4. Adaptações no código (`app/pesquisa.py`)

**Funções novas:**
- `normalizar_cpf(cpf)`: só os dígitos, com 11 dígitos obrigatórios;
- `hash_cpf(cpf)`: HMAC-SHA256 com a `CPF_HMAC_KEY`;
- `mascarar_cpf(cpf)`: `***.456.789-**`;
- uma constante com o trecho SQL que decifra, para não repetir `CONVERT(AES_DECRYPT(FROM_BASE64(...)),...)` em cada consulta.

**Pontos que mudam:**

| # | Onde | Hoje | Mudança |
|---|---|---|---|
| 1 | `efetivarIndicacao` ([4702-4720](app/pesquisa.py#L4702-L4720)) | `INSERT` em claro + `UPDATE` que cifra 5 colunas | Cifrar as 9 colunas no próprio `INSERT`, gravar o `cpf_hash` e remover o `UPDATE` |
| 2 | `indicacoes` ([4757-4759](app/pesquisa.py#L4757-L4759), [4782](app/pesquisa.py#L4782)) | `nome_banco`, `agencia` e `conta` em claro, nos dois ramos (com e sem `tipo`) | Decifrar as 3 colunas (e acrescentar a `AES_KEY` aos parâmetros do 2º ramo) |
| 3 | `substituicoes` ([5284](app/pesquisa.py#L5284), [5290](app/pesquisa.py#L5290)) | Dados bancários em claro nas 2 consultas | Decifrar |
| 4 | `verificarDeclaracao` ([1805-1815](app/pesquisa.py#L1805-L1815)) | `indicacoes.cpf` exibido completo numa página **pública** | Decifrar e **mascarar** |
| 5 | `meuCertificado` ([3493](app/pesquisa.py#L3493)) e `minhaDeclaracaoDiscente2019` ([3563](app/pesquisa.py#L3563)) | `cpf` no documento | Decifrar (o documento oficial continua com o CPF completo) |
| 6 | `gerarProjetosPorAluno` ([951-965](app/pesquisa.py#L951-L965)), usada por `/projetosAluno` e `/projetos_discente` | `WHERE cpf = %s` em `cadastro_geral` e `indicacoes` | `WHERE cpf_hash = %s`, com `hash_cpf(entrada)`, e decifrar no `SELECT` |
| 7 | `/indicacao/<cpf>` ([5480-5510](app/pesquisa.py#L5480-L5510)) | `WHERE cpf=%s`, com o CPF formatado | `WHERE cpf_hash = %s` (ver também a seção 5) |
| 8 | Legadas: `gerarDeclaracao` ([904](app/pesquisa.py#L904)) e `gerarAutenticacao` ([989](app/pesquisa.py#L989)) em `alunos`; `minhaDeclaracaoDiscente` ([3376](app/pesquisa.py#L3376)) e `meuCertificado2018` ([3426](app/pesquisa.py#L3426)) em `cadastro_geral` | `cpf` em claro | Decifrar |
| 9 | Indicações duplicadas ([5460-5476](app/pesquisa.py#L5460-L5476)) | `GROUP BY indicacoes.nome` | Opcional: `GROUP BY cpf_hash`, que é mais preciso |
| 10 | `anonimizar_dev.sql` | Já cobre as colunas legadas (`orientador_cpf`, `estudante_no_*`, e-mails de `alunos` e `cadastro_geral`) e normaliza o CPF para só dígitos antes de pseudonimizar | Pseudonimizar também o `cpf_hash`, com o mesmo sal, para as buscas em dev continuarem funcionando entre as tabelas |
| 11 | Testes | — | `test_cripto_cpf.py`: normalização, HMAC, máscara, SQL do `INSERT` com o modo explícito e buscas pelo hash |

Não mudam: os templates, que recebem os valores já decifrados, exceto no item 4; e as rotas de desligamento e substituição (`UPDATE indicacoes SET motivo/situacao`), que não tocam nessas colunas.

## 5. Problemas de segurança encontrados no levantamento (independentes da criptografia)

1. **`/indicacao/<cpf>` é pública, sem limite e com `Access-Control-Allow-Origin: *`.** Qualquer site ou script consegue testar CPFs e receber o **nome e o e-mail** do discente, a modalidade e o projeto. É uma enumeração de dados pessoais. **Quem usa: outro app** (resposta do usuário em 2026-09-24), então a rota não pode ser removida. A correção é exigir uma credencial desse app e pôr um limitador. Se o outro app chama a rota **pelo navegador** (JavaScript), qualquer segredo colocado ali fica exposto: o backend desse app precisa fazer a chamada. **Prioridade alta**, e dá para fazer antes da criptografia.
2. **`/projetosAluno` e `/projetos_discente`** fazem busca pública por CPF e devolvem os projetos e o `token` das declarações, que mostram o CPF completo. O reCAPTCHA só é conferido no navegador (ver o Turnstile, em `migracao.lgpd.md`), e a `/projetosAluno` não tem limitador.
3. ~~Produção: confirmar `@@block_encryption_mode`~~ **Conferido em 2026-09-24: `aes-256-cbc`.** Não é preciso recifrar as colunas existentes.
4. **`cadastro_geral` é `ENGINE=MyISAM`.** A criptografia em repouso do MariaDB (`file_key_management`) **não se aplica a MyISAM**, só a InnoDB e Aria. Então, essa tabela, com CPF, RG, telefone e dados bancários de cerca de 800 discentes e o CPF de orientadores, fica **em claro no disco**. A correção é `ALTER TABLE cadastro_geral ENGINE=InnoDB`, rápida nesse tamanho. **Conferido em 2026-09-24:** é a **única** tabela MyISAM. Em produção, `innodb_encrypt_tables = FORCE`, `innodb_encrypt_log = ON`, `encrypt_binlog = ON`, `encrypt_tmp_disk_tables = ON` e `aria_encrypt_tables = OFF` (sem tabelas Aria). Com o `FORCE`, a tabela passa a ser cifrada em disco assim que for convertida para InnoDB.

## 6. Ordem de execução sugerida

1. Corrigir o `/indicacao/<cpf>` (seção 5.1), num deploy separado.
2. Criar `/pesquisa/CPF_HMAC_KEY` no SSM e conferir os tipos das colunas (`information_schema.COLUMNS`). O `block_encryption_mode` já foi conferido.
3. Rodar o `ALTER TABLE` (compatível com o código atual).
4. Deploy do código novo, com a leitura de transição `IF(cpf_hash IS NULL, ...)`.
5. Backup e depois `cifrar_cpf_banco.py --simular`, `--limite 10` e a execução completa, com `--verificar` no fim.
6. Conferir em produção: nova indicação, listagens do admin, substituições, declaração e certificado, verificação pública (mascarada) e a busca de projetos por CPF.
7. Depois de alguns dias, remover a leitura de transição.

**Esforço estimado:** cerca de 1 dia de desenvolvimento e testes, mais a janela de migração (minutos, porque são alguns milhares de linhas).

## 7. Implementação (2026-09-24) e roteiro de deploy

**Arquivos:**
- `cripto_cpf.sql.sample`: os `ALTER TABLE` da seção 3, incluindo `cadastro_geral` para InnoDB;
- `app/pesquisa.py`:
  - `CPF_HMAC_KEY`, `normalizar_cpf`, `hash_cpf`, `mascarar_cpf`, `sql_decifra`, `sql_busca_cpf`/`valores_busca_cpf` e `montar_insert_indicacao`;
  - os 11 pontos da seção 4;
- `app/scripts/cifrar_cpf_banco.py`: a migração dos dados existentes;
- `app/test_cripto_cpf.py`;
- `anonimizar_dev.sql`: `cpf_hash = NULL` em dev, para o app ler os pseudônimos como texto, e o pseudônimo do CPF gerado a partir do `cpf_hash`, para ser o mesmo entre as tabelas.

**Decisões tomadas na implementação:**
- **O CPF é cifrado como foi digitado**, com ou sem pontuação, para as declarações continuarem iguais. Só o hash usa os dígitos. Com isso, a busca por CPF passa a achar o discente **com ou sem pontuação**, o que antes falhava.
- **A leitura de transição `IF(cpf_hash IS NULL ...)` fica permanente.** Ela é barata e é o que faz o banco de dev anonimizado funcionar. Em produção, o `--verificar` garante que não sobram linhas com `cpf_hash` nulo.
- **Os valores vazios continuam vazios**, sem cifrar, e a leitura os devolve como estão, para não aparecer "None" nas telas. Os `N/A` dos voluntários são cifrados.
- **Linhas com `iv` curto** (menos de 16 caracteres) são **puladas e informadas pelo id**. Nelas, as outras colunas provavelmente nunca foram cifradas, e é preciso decidir caso a caso.
- A indicação nova grava as **9 colunas pessoais cifradas no próprio `INSERT`**, e o `UPDATE` que cifrava depois foi removido.
- **Tamanho das colunas:** o valor gravado é `TO_BASE64(AES_ENCRYPT(...))`. O AES-256-CBC completa até o próximo múltiplo de 16 bytes, e o `TO_BASE64` do MariaDB quebra a linha a cada 76 caracteres. Medido num MariaDB 11: 14 bytes viram 24, 100 viram 153 e 367 viram 498. Então, `varchar(500)` aceita valores de até 367 bytes, e `varchar(64)` (`alunos.cpf`) aceita até 47. Antes de alterar qualquer linha, o script confere o maior valor de cada coluna e **para** se algum não couber. Isso evita que um banco fora do modo estrito corte o texto cifrado sem aviso.

**Roteiro (nesta ordem):**
1. **Criar a chave do HMAC** (o valor não aparece na tela). **Ela nunca deve mudar depois da migração**, senão as buscas por CPF deixam de achar as linhas:
   ```bash
   aws ssm put-parameter --region us-east-2 --name /pesquisa/CPF_HMAC_KEY --type SecureString --value "$(openssl rand -hex 32)"
   ```
2. **Backup do banco**, com o `backup.mysql.sh` de sempre, e conferir se ele chegou ao S3.
3. **Rodar o `cripto_cpf.sql.sample`** no banco `pesquisa`, pelo phpMyAdmin, e conferir com as consultas do final do arquivo. **Tem que ser antes do deploy**, porque o `INSERT` novo usa o `cpf_hash`.
4. **Commit, tag e deploy.** A partir daqui, as indicações novas já saem cifradas, e as antigas continuam aparecendo pela leitura de transição.
5. **Migração, na EC2:**
   ```bash
   cd /opt/moduloPesquisaPRPI/app
   env/bin/python scripts/cifrar_cpf_banco.py --simular      # só contagens: pendentes, CPF vazio/fora do formato, iv inválido
   env/bin/python scripts/cifrar_cpf_banco.py --limite 10    # 10 linhas por tabela
   env/bin/python scripts/cifrar_cpf_banco.py --verificar    # a amostra deve dar problemas: 0
   env/bin/python scripts/cifrar_cpf_banco.py                # o restante (poucos minutos)
   env/bin/python scripts/cifrar_cpf_banco.py --verificar    # OK nas três tabelas
   ```
   Se o `--simular` mostrar linhas com **iv inválido**, anote os ids e me avise antes de seguir.
6. **Conferência nas telas:**
   - a lista de indicações do admin, com banco, agência e conta legíveis, nos dois formatos;
   - as substituições;
   - a declaração e o certificado de um discente de 2019 em diante e de um legado (`cadastro_geral`);
   - a verificação pública de declaração, com o CPF mascarado;
   - a consulta de projetos por CPF, com e sem pontuação;
   - uma indicação nova.
7. Conferir no phpMyAdmin que os dados estão cifrados, sem mostrar valores:
   ```sql
   SELECT COUNT(*) total, SUM(cpf_hash IS NULL) sem_hash, SUM(cpf REGEXP '^[0-9.\\-]{11,14}$') cpf_em_claro FROM indicacoes;
   ```

**Plano B (desfazer):** reverter o commit e o deploy e, se for preciso, decifrar de volta. O SQL abaixo não depende da chave do HMAC:
```sql
SET @k = '<AES_KEY>';
UPDATE indicacoes SET
  cpf = IF(cpf = '', cpf, CONVERT(AES_DECRYPT(FROM_BASE64(cpf), @k, iv, 'aes-256-cbc'), CHAR)),
  nome_banco = IF(nome_banco = '', nome_banco, CONVERT(AES_DECRYPT(FROM_BASE64(nome_banco), @k, iv, 'aes-256-cbc'), CHAR)),
  agencia = IF(agencia = '', agencia, CONVERT(AES_DECRYPT(FROM_BASE64(agencia), @k, iv, 'aes-256-cbc'), CHAR)),
  conta = IF(conta = '', conta, CONVERT(AES_DECRYPT(FROM_BASE64(conta), @k, iv, 'aes-256-cbc'), CHAR)),
  cpf_hash = NULL
WHERE cpf_hash IS NOT NULL;
UPDATE alunos SET cpf = IF(cpf IS NULL OR cpf = '', cpf, CONVERT(AES_DECRYPT(FROM_BASE64(cpf), @k, iv, 'aes-256-cbc'), CHAR)), cpf_hash = NULL WHERE cpf_hash IS NOT NULL;
UPDATE cadastro_geral SET cpf = IF(cpf IS NULL OR cpf = '', cpf, CONVERT(AES_DECRYPT(FROM_BASE64(cpf), @k, iv, 'aes-256-cbc'), CHAR)), cpf_hash = NULL WHERE cpf_hash IS NOT NULL;
SET @k = NULL;
```
Atenção: as indicações gravadas depois do deploy também têm as 5 colunas antigas (rg, nascimento, telefone, celular e endereco) cifradas no `INSERT`. Isso é compatível com o código antigo, que já as decifrava.
