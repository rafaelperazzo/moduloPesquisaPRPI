# Arquivos do S3: criptografia com KMS, URLs assinadas e Lambdas

> **Status:** plano, sem nada implementado ainda (levantamento de 2026-09-23; decisões da seção 7 registradas em 2026-09-23). Item do TODO: "Utilizar função Lambda para lidar com o download, upload e criptografia dos arquivos do app que estão no S3".

## Contexto

Hoje o app faz todo o trabalho com os arquivos dos projetos e das indicações (PDFs):
- **No upload,** grava o arquivo sem criptografia no disco da EC2, criptografa com GPG usando uma senha fixa (`GPG_KEY`) e o envia ao S3 numa thread.
- **No download,** baixa o `.gpg`, grava a versão descriptografada no disco, entrega ao navegador e apaga o arquivo 3 segundos depois.

O objetivo é:
- tirar a criptografia e o trânsito dos arquivos do servidor de aplicação;
- usar a criptografia do próprio S3 com a **chave gerenciada pela AWS** (`aws/s3`, no KMS): rotação automática e auditoria, sem chave para administrar;
- entregar os downloads por URLs assinadas de curta duração;
- usar Lambda onde ela agrega: validar os uploads;
- migrar o acervo `.gpg` atual com um script único executado na EC2.

**Os bytes dos arquivos não passam pela Lambda.** A chamada direta a uma Lambda aceita no máximo 6 MB, e o upload do app aceita até 16 MB. Passar os arquivos pela Lambda também somaria latência sem ganho de segurança, porque quem decide "quem pode ver o arquivo" continua sendo o app.

## 1. Levantamento (estado atual)

### 1.1 Código (`app/pesquisa.py`)
| Onde | O que faz |
|---|---|
| l.288-301 | Cliente `s3`: em produção usa a role da EC2; em dev usa `AWS_S3_KEY_ID`/`AWS_S3_SECRET_KEY` |
| `id_generator` (l.839) | Sufixo aleatório dos nomes de arquivo (20 caracteres) com `random.choice`, que **não é um gerador criptográfico** |
| Upload de submissões (l.1655-1712) | Salva os 5 arquivos do projeto e chama `encripta_e_apaga` |
| `upload_s3` / `encripta_e_apaga` (l.4125-4150) | GPG simétrico AES256 via `python-gnupg` (`cripto.aes_gpg_encrypt_file`), apaga o original e sobe o `.gpg` numa thread. Uma falha no envio só vai para o log |
| `esperar` (l.4330) | Apaga os arquivos temporários 3 s depois do download |
| `/admin/verArquivo` (l.4346) | Documentos das indicações (`docs_indicacoes/`), só para admins |
| `/verArquivosProjeto/<filename>` (l.4370) | Arquivos dos projetos (`submissoes/`). **É pública, sem login:** os links vão por e-mail para os avaliadores (l.2012) e aparecem em `editalProjeto.html` e `alterarProjeto.html`. A única proteção é o nome do arquivo |
| `MAX_CONTENT_LENGTH` (l.360) | 16 MB |

**Nomes dos objetos no S3:** `pesquisa/<submissoes|docs_indicacoes>/<nome>.pdf.gpg`. A tabela guarda o nome sem o `.gpg`.

### 1.2 AWS (us-east-2)
- **Bucket `rajardekalambur`:**
  - compartilhado com o app **cppgi** (prefixos `cppgi/`, `cppgi_backup/`);
  - SSE-S3 (AES256) padrão com Bucket Key;
  - SSE-C bloqueado;
  - versionamento ligado;
  - bloqueio de acesso público total;
  - sem bucket policy.
- **Regra do bucket:** `NoncurrentVersionExpiration` = **1 dia**. Uma versão sobrescrita ou apagada some depois de 1 dia, então **o versionamento não serve como backup** nesta migração.
- **Volume:**
  - `pesquisa/submissoes/`: 6.637 objetos, 2,64 GB;
  - `pesquisa/docs_indicacoes/`: 12.254 objetos, 6,83 GB;
  - média de cerca de 500 KB por arquivo.
- **Role da EC2 `CloudWatch`:**
  - tem `S3_ec2_PESQUISA_CPPGI`, limitada aos prefixos `pesquisa/`, `cppgi/` e `cppgi_backup/`;
  - **mas também tem `AmazonS3FullAccess`,** que dá acesso total a todos os buckets e anula a política anterior;
  - não tem permissões de KMS; e, com a chave `aws/s3`, **nem precisa** (seção 2).
- **Lambda `criptografia-aes`:** criptografa **textos** (AES-GCM, Argon2id com pepper), com a chave em `/cripto/AES_KEY` no SSM e acesso por URL da função com autenticação IAM. Não serve para arquivos. Continua útil para o item "Criptografar dados da tabela users".

### 1.3 Problemas
1. PDF sem criptografia no disco da EC2, no upload e no download. Se a thread falhar, sobra lixo com dados pessoais.
2. Uma única senha para todos os arquivos, sem rotação nem trilha de auditoria.
3. `/verArquivosProjeto` pública, com links permanentes e nomes gerados por `random`.
4. O arquivo inteiro passa pela memória e pelo disco da EC2, que tem limite de 450 MB no systemd.
5. Uma falha de upload para o S3 é silenciosa para o usuário.
6. `AmazonS3FullAccess` na role da EC2.

## 2. Arquitetura proposta

```
UPLOAD (fase 3)
  navegador --(1) pede URL de upload--> app (valida sessão/edital, define o nome)
  navegador --(2) PUT direto--> s3://.../pesquisa/incoming/<nome>   [SSE-KMS obrigatório]
  S3 --(3) evento--> Lambda validar-upload --> move para pesquisa/submissoes/<nome>
  navegador --(4) envia o formulário--> app (confere o objeto final e grava na tabela)

DOWNLOAD (fase 1)
  navegador --> app (/verArquivosProjeto, /admin/verArquivo: login; /arquivo/<token>: link do avaliador, 30 dias)
  app --> 302 para URL assinada do S3 (60 s)  -->  S3 descriptografa com o KMS e entrega
```

1. **SSE-KMS com a chave gerenciada pela AWS `aws/s3`** (decisão do usuário: nada de chave gerenciada pelo cliente):
   - já existe na conta e está ativa: `alias/aws/s3` = `arn:aws:kms:us-east-2:584868042744:key/36d0ea20-0a5b-4420-acfd-a5895f190e78`;
   - o S3 criptografa ao gravar e descriptografa ao entregar; a chave nunca sai do KMS;
   - **a AWS administra tudo:** a rotação é automática (anual), e ninguém consegue desativar, apagar nem alterar a key policy dessa chave;
   - **nenhuma permissão de KMS no IAM:** a key policy da AWS permite o uso a qualquer usuário ou role da conta, desde que o pedido venha do S3 (`kms:ViaService`). Então **quem tem `s3:GetObject` no objeto consegue lê-lo**, e o controle de acesso fica todo nas permissões de S3;
   - **auditoria:** cada `Decrypt` continua registrado no CloudTrail;
   - **limitação aceita:** a chave `aws/s3` não pode ser compartilhada com outras contas nem ter política própria, o que não faz falta aqui;
   - a bucket policy **só para `pesquisa/*`** recusa `PutObject` sem `aws:kms`, sem afetar o cppgi. A criptografia padrão do bucket (SSE-S3) **não muda**; os objetos do pesquisa pedem SSE-KMS explicitamente.
2. **Download por URL assinada** (`generate_presigned_url('get_object')`):
   - validade de 60 s, com `ResponseContentDisposition` para manter o nome do arquivo;
   - o app continua fazendo a autorização: sessão (admin ou dono do projeto) ou **link assinado do avaliador, válido por 30 dias**.
3. **Upload direto do navegador por URL assinada** (`generate_presigned_post`), com condições:
   - nome exato;
   - `content-length-range` de até 16 MB;
   - `Content-Type: application/pdf`;
   - `x-amz-server-side-encryption: aws:kms`, sem informar a chave: o S3 usa a `aws/s3`.
4. **Lambda `validar-upload`** (evento `ObjectCreated` em `pesquisa/incoming/`):
   - confere a assinatura de PDF (`%PDF-`) e o tamanho;
   - com o arquivo válido, faz `CopyObject` para o prefixo final com SSE-KMS e apaga o original em `incoming/`;
   - com o arquivo inválido, apaga e registra o motivo;
   - uma regra do bucket apaga o que sobrar em `incoming/` depois de 1 dia.
5. **Script de migração `app/scripts/migrar_gpg_kms.py`** (execução única, **na EC2**, que já tem o `gpg`, a `GPG_KEY` no SSM e a role):
   - descriptografa cada `.gpg` **em memória** e grava **com um nome novo, sem o `.gpg`**, em SSE-KMS;
   - **não sobrescreve nada:** os `.gpg` continuam como versão atual até a fase de limpeza, porque o bucket apaga versões antigas em 1 dia.
6. **Menor privilégio:** remover `AmazonS3FullAccess` da role da EC2. Cada peça fica só com o que precisa (seção 4).

## 3. Fases

### Fase 0: preparação na AWS (eu aplico pelo CLI, **com a sua confirmação**, como no Cognito)
Com a chave gerenciada pela AWS, a fase 0 fica bem menor: **não se cria chave e não se altera nenhuma permissão da role `CloudWatch`.**
1. Salvar um backup da configuração atual (encryption, lifecycle, policies da role).
2. **Conferir (só leitura)** que a chave `alias/aws/s3` está `Enabled` (ok em 2026-09-23) e fazer um teste com um objeto descartável: um `put-object` com `--server-side-encryption aws:kms` em `pesquisa/_migracao/teste.txt`, depois o `get-object` pela role da EC2 e o `delete-object`. Esse teste roda **na EC2**, e eu te passo os comandos.
3. **Role `CloudWatch`: nenhuma alteração.** As permissões de S3 atuais já bastam para ler e gravar com a `aws/s3`. Nenhuma política é criada, alterada, anexada ou removida.
4. **Acesso de dev aos arquivos de produção: feito por você, manualmente.**
   - **Situação levantada em 2026-09-23:** nenhum usuário IAM atual lê `pesquisa/`. `cloudcone`, `sci01` e `ses-pesquisa` têm o `s3:GetObject` negado (`implicitDeny`). Então hoje o dev já não abre os arquivos de produção.
   - **Com a `aws/s3`, basta o `s3:GetObject`:** não é preciso nenhuma permissão de KMS.
   - **Roteiro sugerido:**
     1. **Escolher o usuário:** o recomendado é criar um usuário dedicado, `pesquisa-dev`, sem acesso ao console. A alternativa é usar o do `AWS_S3_KEY_ID` atual do `.env`.
     2. **Anexar a política inline `PesquisaArquivosDevLeitura`:**
        ```json
        {
          "Version": "2012-10-17",
          "Statement": [
            {"Sid": "LerArquivosPesquisa", "Effect": "Allow", "Action": "s3:GetObject",
             "Resource": ["arn:aws:s3:::rajardekalambur/pesquisa/submissoes/*",
                          "arn:aws:s3:::rajardekalambur/pesquisa/docs_indicacoes/*"]}
          ]
        }
        ```
        Por CLI: `aws iam put-user-policy --user-name pesquisa-dev --policy-name PesquisaArquivosDevLeitura --policy-document file://politica-dev.json`.
     3. **Não dar** `PutObject`, `DeleteObject` nem `ListBucket`: o dev só lê, um arquivo por vez, pelo nome que está no banco de teste.
     4. **Chave de acesso:** gerar com `aws iam create-access-key --user-name pesquisa-dev`, colocar em `AWS_S3_KEY_ID` e `AWS_S3_SECRET_KEY` no `.env` de dev e desativar a chave antiga, se ela não for usada em outro lugar.
     5. **Conferência:** `aws iam simulate-principal-policy --policy-source-arn arn:aws:iam::584868042744:user/pesquisa-dev --action-names s3:GetObject s3:PutObject --resource-arns arn:aws:s3:::rajardekalambur/pesquisa/submissoes/x` deve dar `allowed` para `GetObject` e `implicitDeny` para `PutObject`.
5. **Ainda não** mexer na bucket policy nem no `AmazonS3FullAccess`. Isso fica para as fases 2 e 4.
6. **Novo parâmetro no SSM:** `/pesquisa/ARQUIVOS_LINK_KEY` (SecureString, 32 bytes aleatórios), a chave que assina os links dos avaliadores. **Não pode ser a `SECRET_KEY` do Flask**, que muda a cada reinício do serviço e invalidaria os links. Em dev, a mesma variável vai no `.env`, com outro valor.

### Fase 1: download por URL assinada e migração do acervo
**Código:**
- Nova função `url_download(prefixo, nome)`:
  - tenta `head_object` em `pesquisa/<prefixo>/<nome>`, o objeto já migrado;
  - se existir, gera a URL assinada de 60 s e retorna `redirect(url)`;
  - se não existir, usa o **fluxo antigo** (`.gpg` com GPG), só durante a transição.
- `/admin/verArquivo` e `/verArquivosProjeto` passam a usar `url_download`. O `send_from_directory` e a thread `esperar` ficam só no caminho de transição.
- **`/verArquivosProjeto/<filename>` passa a exigir login:** admin ou dono do projeto (o `siape` do projeto na `editalProjeto`). Ela é usada pelas páginas internas (`editalProjeto.html`, `alterarProjeto.html`).
- **Links dos avaliadores com validade de 30 dias:**
  - nova rota `/arquivo/<token>`, sem login;
  - o token é assinado com `itsdangerous.URLSafeTimedSerializer`, usando a `ARQUIVOS_LINK_KEY`, e carrega o prefixo e o nome do arquivo;
  - `max_age` de 30 dias; com o token vencido ou adulterado, aparece a página "Link expirado" com orientação.
  - A página `/avaliacao` (l.2005-2016), que hoje monta `url_for('verArquivosProjeto', ...)`, passa a montar `url_for('arquivo_assinado', token=...)`. Os 30 dias contam a partir de cada abertura da página. O link de avaliação do e-mail não muda.
- Os downloads em dev também usam a URL assinada, com as credenciais de dev configuradas por você (fase 0, item 4). Sem elas, o S3 recusa o download em dev, como já acontece hoje.
- Log de cada download: quem (ou "avaliador" com o hash do token), qual arquivo e se veio pelo caminho novo ou pelo antigo.

**Script de migração `app/scripts/migrar_gpg_kms.py` (roda na EC2). Pronto em 2026-09-23 e testado localmente com um S3 simulado e o `gpg` real:**
- **Pode rodar antes do código da fase 1:** ele só **acrescenta** as versões novas, sem `.gpg`, e não altera nem apaga os `.gpg`. Enquanto a fase 1 não for implantada, o app continua lendo os `.gpg`, e as versões novas ficam prontas para quando ela for.
- **Arquivo `.gpg` trocado depois da migração** (por exemplo, pela troca de um arquivo do projeto): o script compara o ETag do `.gpg` com o gravado na metadata da versão nova e **migra de novo** esse arquivo na rodada seguinte.
- **Acervo em 2026-09-23:** 6.634 `.pdf.gpg` em `submissoes/` e 12.251 em `docs_indicacoes/`, todos PDF. O maior tem cerca de 66 MB (é anterior ao limite atual de 16 MB). As pastas também têm um `.sh` e um `Readme`, que o script ignora.
- Usa a role da EC2, com as permissões de S3 atuais (a `aws/s3` não exige permissão de KMS), e lê do SSM a `GPG_KEY` (`/pesquisa/GPG_KEY`) e o nome do bucket (`/pesquisa/AWS_S3_BUCKET`). Não precisa de credenciais nem de permissões novas.
- **Para cada `pesquisa/<prefixo>/*.gpg`:**
  1. baixa o arquivo para a memória (média de 500 KB, máximo de 16 MB);
  2. descriptografa com `python-gnupg` a partir dos bytes (`gpg.decrypt`), **sem gravar nada sem criptografia no disco**;
  3. confere que o resultado começa com `%PDF`;
  4. faz `put_object` com o nome sem `.gpg`, `ServerSideEncryption='aws:kms'` (sem `SSEKMSKeyId`, então vale a `aws/s3`) e a metadata `migrado-de=<nome>.gpg`;
  5. relê com `head_object` para conferir a criptografia e o tamanho.
- **Idempotente:** pula quem já tem a versão sem `.gpg`, então pode ser interrompido e rodado de novo.
- **Opções:**
  - `--prefixo submissoes|docs_indicacoes`;
  - `--limite N` (lote de teste);
  - `--simular` (só lista o que faria, sem gravar);
  - `--workers N` (padrão 4 threads);
  - `--verificar` (só compara as contagens `.gpg` e sem `.gpg` e lista o que falta).
- **Saída:**
  - progresso na tela a cada 100 arquivos;
  - relatório CSV com `chave_gpg, status, tamanho_bytes, erro`, salvo em `~/migracao_s3/` (ou na pasta de `--saida`) e enviado para `pesquisa/_migracao/`;
  - código de saída 1 se houver falha;
  - **Ctrl+C** termina os arquivos em andamento, salva o relatório e para; basta repetir o comando para continuar.
  - **Nenhum conteúdo de arquivo nem a senha aparecem no log.**
- **Tempo estimado:** cerca de 1 a 2 horas para os 18,9 mil arquivos (9,5 GB) com 4 threads. **O site continua no ar**, porque o código da fase 1 lê os dois formatos.

**Execução na máquina local (preferida, decidida em 2026-09-23):** a EC2 tem só 927 MB de RAM (cerca de 250 MB livres) e não tem swap, o que não basta para arquivos de até 66 MB. Por isso, a migração roda na máquina do usuário com `app/scripts/migrar_s3_local.sh`. Esse script:
- cria a venv `~/venv-migracao` com `boto3`, `python-gnupg` e `botocore[crt]`;
- mostra a identidade AWS e pede confirmação se for a conta root;
- roda o lote de teste (10 de cada pasta) e a verificação, e pede confirmação;
- migra `submissoes` e `docs_indicacoes` em sequência, impedindo a suspensão do computador (`systemd-inhibit`);
- faz a verificação final e grava o log em `~/migracao_s3/`.

Opções: `--sem-teste` (retomar depois de uma interrupção) e `--workers N`. O custo é de cerca de US$ 0,85 de transferência (download de 9,5 GB).

**Como executar na EC2 (alternativa; exige swap temporário e `--workers 1`):**
1. Fazer o commit e o deploy do script. O `git pull` do deploy o leva para `/opt/moduloPesquisaPRPI/app/scripts/`. **Não é preciso esperar o código da fase 1.**
   Antes de rodar, conferir a memória livre com `free -m`. Com menos de cerca de 1,5 GB livre, use `--workers 2`, porque há arquivos de até 66 MB.
2. Abrir uma sessão que sobreviva à queda do SSH:
   ```bash
   sudo -u pesquisa -H tmux new -s migracao   # sem tmux: use nohup, no passo 4
   cd /opt/moduloPesquisaPRPI/app
   ```
   O `-H` faz o `HOME` ser `/home/pesquisa`, necessário para o `gpg` achar o `~/.gnupg`.
3. **Simulação e lote de teste:**
   ```bash
   env/bin/python scripts/migrar_gpg_kms.py --prefixo submissoes --limite 10 --simular
   env/bin/python scripts/migrar_gpg_kms.py --prefixo submissoes --limite 10
   ```
   Depois, abrir pelo app 2 ou 3 desses projetos. Os logs devem mostrar o caminho novo.
4. **Migração completa:**
   ```bash
   env/bin/python scripts/migrar_gpg_kms.py --prefixo submissoes
   env/bin/python scripts/migrar_gpg_kms.py --prefixo docs_indicacoes
   ```
   Para sair do tmux sem parar o script: `Ctrl+B` e depois `D`. Para voltar: `sudo -u pesquisa -H tmux attach -t migracao`. Com nohup: `nohup env/bin/python scripts/migrar_gpg_kms.py --prefixo submissoes > migracao_submissoes.log 2>&1 &`.
5. **Conferência:** `env/bin/python scripts/migrar_gpg_kms.py --verificar` deve mostrar 0 pendente e 0 falha nos dois prefixos. Me mande o resumo ou o CSV de falhas.
6. **Depois dos deploys das fases 1 e 2,** rodar de novo os passos 4 e 5. Isso pega os arquivos enviados ou trocados desde a última rodada, que ainda saíram em `.gpg`. Só esses serão processados.

**Critério de saída:**
- 100% dos objetos migrados (contagem com e sem `.gpg` igual por prefixo);
- os logs mostram só downloads pelo caminho novo por alguns dias.

### Fase 2: upload do app direto em SSE-KMS (ainda pelo formulário atual)
- `encripta_e_apaga` passa a ser `enviar_arquivo_s3(arquivo_do_form, prefixo, nome)`:
  - `put_object`/`upload_fileobj` **direto do stream do formulário**, com `ServerSideEncryption='aws:kms'`, sem `SSEKMSKeyId` (usa a `aws/s3`);
  - sem gravar em disco, sem GPG e sem thread;
  - se falhar, o erro aparece para o usuário e a linha da tabela não é atualizada.
- Os nomes passam a ser gerados com `secrets.token_urlsafe` em vez de `random`.
- **Bucket policy** (só para `pesquisa/submissoes/*` e `pesquisa/docs_indicacoes/*`): nega `s3:PutObject` quando `s3:x-amz-server-side-encryption` é diferente de `aws:kms`, ou quando `s3:x-amz-server-side-encryption-aws-kms-key-id` é diferente da `aws/s3` (`arn:aws:kms:us-east-2:584868042744:key/36d0ea20-0a5b-4420-acfd-a5895f190e78`). Assim, ninguém grava ali com outra chave.
- **Dev (`PRODUCAO=0`):** continua **sem enviar ao S3**, como hoje (o arquivo é descartado). A leitura dos arquivos de produção funciona pela URL assinada, com o `kms:Decrypt` dado ao usuário de dev na fase 0.

### Fase 3: upload direto do navegador e Lambda `validar-upload`
- Rota nova, `POST /arquivos/url_upload`:
  - exige login;
  - valida o edital, o tipo do arquivo e se o projeto pertence ao usuário;
  - devolve um `presigned_post` para `pesquisa/incoming/<nome>` (validade de 5 min, com as condições da seção 2).
- **JavaScript dos formulários de submissão e de indicação:**
  - envia cada arquivo ao S3 antes do submit e mostra o progresso;
  - preenche os campos ocultos com os nomes;
  - o submit leva só os nomes.
- **Rota do formulário:** confere com `head_object` que cada nome existe no prefixo final, porque a Lambda move o arquivo em cerca de 1 s. Se ainda não existir, tenta de novo por alguns segundos antes de falhar.
- **Lambda `validar-upload`:**
  - runtime Python, 256 MB, timeout de 30 s;
  - trigger S3 `ObjectCreated:*` com prefixo `pesquisa/incoming/`;
  - lê só os primeiros bytes (`Range: bytes=0-4`).
- **Regra do bucket:** apaga `pesquisa/incoming/` depois de 1 dia. Ao editar a regra, preservar a regra existente de versões antigas.
- **CORS do bucket:** só `POST` a partir de `https://aws.yokoapps.com.br`.
- **Cloudflare:** o upload vai direto ao S3, então o WAF e o limite de tamanho da borda não se aplicam. As condições da URL assinada e a Lambda de validação fazem esse papel.
- **Dev (`PRODUCAO=0`):** a rota `/arquivos/url_upload` não gera URL de upload. O JavaScript detecta isso e o formulário volta ao envio tradicional, que em dev descarta o arquivo, como hoje. **O dev nunca grava no bucket de produção.**

### Fase 4: limpeza e menor privilégio
1. **Período de segurança de 90 dias sem apagar os `.gpg`.** Não haverá cópia de backup: os `.gpg` simplesmente continuam onde estão, no mesmo bucket, por 90 dias depois de a migração ser concluída e conferida. Para que servem:
   - **Proteção contra um defeito não percebido na migração:** um arquivo que passou na conferência (`%PDF` e tamanho) mas veio incompleto ou corrompido só seria notado quando alguém o abrisse. Com o `.gpg` original disponível, basta migrá-lo de novo.
   - **Caminho alternativo independente do S3/KMS:** a `aws/s3` não pode ser apagada nem desativada, então o risco de "perder a chave" praticamente desaparece. Os `.gpg`, que só dependem da `GPG_KEY`, continuam sendo uma cópia independente durante a transição.
   - **Rollback sem risco:** o código da fase 1 ainda sabe ler `.gpg`, então dá para voltar ao fluxo antigo só com um deploy.
   - **Por que é preciso planejar isso:** a regra do bucket apaga versões antigas em 1 dia. Depois que um `.gpg` é apagado, ele some de vez, sem recuperação pelo versionamento.
   - **Custo:** cerca de 9,5 GB, ou cerca de US$ 0,22 por mês, só durante esses 90 dias.
2. Depois dos 90 dias, apagar os `.gpg` (`scripts/migrar_gpg_kms.py --apagar-gpg`, que só apaga os que têm a versão SSE-KMS conferida).
3. Remover do código:
   - o caminho de transição;
   - `esperar` e `upload_s3`;
   - o `gnupg`, se nada mais o usar.
4. Remover a `GPG_KEY` do SSM e do código **depois** de apagar os `.gpg`.
5. Remover `AmazonS3FullAccess` da role `CloudWatch` (seção 4). **Com a chave `aws/s3`, isso fica mais importante:** o KMS não é mais uma barreira separada, então quem tem `s3:GetObject` lê os arquivos. **Antes, confirmar o que o cppgi e os backups usam**, porque a política limitada atual já cobre `cppgi/` e `cppgi_backup/`.
6. Remover o script `scripts/migrar_gpg_kms.py` do repositório.

## 4. Permissões (resumo)
| Principal | S3 | KMS |
|---|---|---|
| EC2 `CloudWatch` (app) | Fases 0 a 3: as políticas atuais, sem alteração. Fase 4: `GetObject`/`PutObject`/`DeleteObject` em `pesquisa/*`, `ListBucket` com prefixo `pesquisa/`, **sem** `AmazonS3FullAccess` | Nenhuma: a `aws/s3` autoriza pelo S3 |
| Lambda `validar-upload` | `GetObject`/`DeleteObject` em `pesquisa/incoming/*`, `PutObject` em `pesquisa/submissoes/*` e `pesquisa/docs_indicacoes/*` | Nenhuma |
| Script de migração (na EC2) | Usa a role `CloudWatch`, sem nenhuma permissão nova | Nenhuma |
| Usuário IAM de dev (manual, fase 0, item 4) | **Só `GetObject`** em `pesquisa/submissoes/*` e `pesquisa/docs_indicacoes/*` | Nenhuma |

As URLs assinadas usam as credenciais da role da EC2, então valem só enquanto essas credenciais valerem. Com 60 s de validade, isso não é problema.

## 5. Custos estimados
- **KMS:** a chave `aws/s3` não tem custo mensal; só as requisições, cerca de US$ 0,03 por 10 mil (a Bucket Key, já ligada, reduz as chamadas).
- **Lambda `validar-upload`:** centavos por mês. A migração roda na EC2, sem custo de Lambda; a transferência entre a EC2 e o S3 na mesma região não é cobrada.
- **S3:**
  - durante a transição e os 90 dias de segurança, o acervo fica em dobro (mais cerca de 9,5 GB, ou US$ 0,22 por mês);
  - depois de apagar os `.gpg`, o custo volta ao de hoje.

## 6. Verificação
- **Fase 1:**
  - o script de migração num lote de 10 arquivos (`--limite 10`), com a contagem conferida por `--verificar`;
  - abrir arquivos migrados pelo app, de admin e pelo link do avaliador;
  - `/verArquivosProjeto` sem login é recusada; o dono do projeto e o admin conseguem abrir;
  - um link de avaliador com o token adulterado é recusado, e um com data de mais de 30 dias (teste com `max_age` reduzido) mostra "Link expirado";
  - em dev, abrir um arquivo de produção funciona;
  - uma URL assinada vencida (mais de 60 s) retorna 403;
  - um arquivo ainda não migrado abre pelo caminho antigo;
  - o CloudTrail mostra o `Decrypt`.
- **Fase 2:**
  - enviar uma submissão de teste e conferir que o objeto sai com `ServerSideEncryption=aws:kms` e `SSEKMSKeyId` igual à `aws/s3` (`arn:aws:kms:us-east-2:584868042744:key/36d0ea20-0a5b-4420-acfd-a5895f190e78`);
  - um `put-object` sem KMS, ou com outra chave KMS, em `pesquisa/submissoes/` é negado pela bucket policy;
  - um `put-object` em `cppgi/` continua funcionando.
- **Fase 3:**
  - um PDF válido chega ao prefixo final;
  - um `.exe` renomeado para `.pdf` é apagado pela Lambda;
  - um arquivo acima de 16 MB é recusado pelo S3;
  - a URL de upload vencida é recusada;
  - o formulário com um nome inexistente é recusado.
- **Fase 4:**
  - o `simulate-principal-policy` mostra o S3 negado fora de `pesquisa/`, `cppgi/` e `cppgi_backup/`;
  - o cppgi e os backups continuam funcionando.
- **Em todas as fases:** os testes com mocks (boto3) para as rotas alteradas, no padrão de `app/test_mfa.py`.

## 7. Decisões

**Tomadas em 2026-09-23:**
1. **Migração:** script único na EC2 (`app/scripts/migrar_gpg_kms.py`), com o roteiro de execução na fase 1.
2. **Links dos avaliadores:** **só os links dos PDFs** passam a ter **validade de 30 dias** (token assinado; rota `/arquivo/<token>`). Eles são gerados cada vez que o avaliador abre a página de avaliação. O link de avaliação do e-mail continua como está, limitado pelo prazo do edital.
3. **Dev:** abre os arquivos de produção, mas nunca grava no bucket. O acesso IAM é configurado **por você, manualmente**, com o roteiro da fase 0, item 4.
4. **Fase 3** (upload direto do navegador com a Lambda `validar-upload`): **será feita**.
5. **`.gpg` antigos:** ficam no mesmo bucket, no próprio lugar, por 90 dias depois da migração, sem cópia de backup (motivos na fase 4).
6. **Chave:** **gerenciada pela AWS** (`aws/s3`), e não gerenciada pelo cliente. Sem chave nova e sem permissões de KMS no IAM.

**Ainda em aberto:**
- Nenhuma.
