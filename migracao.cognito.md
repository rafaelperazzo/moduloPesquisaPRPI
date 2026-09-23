# Migração da autenticação para o AWS Cognito (gradual, silenciosa)

## Contexto
Hoje o app guarda as credenciais no MariaDB (hash Argon2id, `users.password`) e **o próprio app** manda senhas em texto puro por e-mail (via SQS) no cadastro, no "esqueci minha senha" e no reset feito pelo admin. O objetivo é passar a guarda das credenciais e os e-mails de senha para o Cognito (pool `app-yoko`, `us-east-2_xsTbiRLIy`, client `flask-backend-client`). A migração é gradual e **silenciosa**: cada usuário migra sozinho no primeiro login bem-sucedido, com a mesma senha, marcada como permanente.

Decisões do usuário:
- O Cognito vale **só em produção** (`PRODUCAO==1`). Em dev/testes continua o login legado no MariaDB da EC2, como hoje.
- Os papéis vêm da coluna `roles` e são migrados para `custom:roles` (e `permission` para `custom:permission`). Em produção, a sessão lê os papéis do Cognito.
- Política de senha com **no mínimo 12 caracteres**.
- **`MessageAction='SUPPRESS'` só é usado na migração.** Todas as outras operações de senha (cadastro de usuário novo, esqueci minha senha, reset pelo admin) usam o Cognito com **os e-mails enviados pelo próprio Cognito**. O app não gera nem envia senha por e-mail.

## 1. Levantamento de custo

| Item | Situação atual | Custo |
|---|---|---|
| Cognito, plano **Essentials** (o do pool) | Faixa gratuita de **10.000 MAU/mês por conta, sem prazo de validade**; acima disso US$ 0,015/MAU | ~400 usuários cadastrados, então o MAU real fica bem abaixo: **US$ 0,00/mês** |
| Chamadas Admin* (AdminInitiateAuth, AdminCreateUser…) | Incluídas no preço por MAU | US$ 0 |
| E-mails do Cognito via SES (`yokoapps.com.br`, conta DEVELOPER) | Convites de usuários novos e códigos de recuperação/reset; **a migração não envia nada** | SES a US$ 0,10 por 1.000 e-mails, ou seja, centavos por ano |
| SMS/MFA, Advanced Security, M2M, multi-região | Não usados (MFA OFF) | US$ 0 |
| Desenvolvimento | ~7 a 10 dias de trabalho | — |

Se um dia passar de 10k MAU: US$ 0,015/MAU no Essentials, ou US$ 0,0055 no **Lite**, que tem a mesma faixa gratuita e atende a tudo o que este plano usa. Mudar para o Lite é opcional e não altera o custo de hoje.
Fonte: https://aws.amazon.com/cognito/pricing/ (consultado em 23/09/2026).

## 2. Estado verificado na AWS (via CLI, somente leitura)
- Pool: senha com mín. 8 caracteres e 4 classes; senha temporária vale 7 dias; MFA OFF; e-mail pelo SES `NAO-RESPONDA@yokoapps.com.br`; mensagem de verificação em português; `InviteMessageTemplate` não definido (sairia o padrão em inglês); nenhum trigger Lambda; `AllowAdminCreateUserOnly=false`; `DeletionProtection=INACTIVE`.
- Atributos já criados: `email`, `email_verified`, `name`, `custom:roles` (String), `custom:permission` (Number), `custom:legacy_id` (Number).
- Client: sem secret; fluxos `ALLOW_ADMIN_USER_PASSWORD_AUTH`, `ALLOW_REFRESH_TOKEN_AUTH`, `ALLOW_USER_PASSWORD_AUTH`; `ReadAttributes`/`WriteAttributes` sem restrição; `PreventUserExistenceErrors` não definido.
- A role da EC2 (`CloudWatch`, instância `vps_pesquisa`) **já tem**: AdminInitiateAuth, AdminCreateUser, AdminSetUserPassword, AdminUpdateUserAttributes, AdminGetUser.
- A role **não tem**: AdminRespondToAuthChallenge, AdminResetUserPassword. ForgotPassword, ConfirmForgotPassword e ChangePassword são APIs públicas e não precisam de IAM.

### Ajustes na AWS: primeiro passo da execução, feito por mim pela CLI (autorizado)
Pool `us-east-2_xsTbiRLIy`:
1. **Política de senha:** `MinimumLength=12`, mantendo as 4 classes. Fica igual ao `senha_segura_valida` do app.
2. **Segurança, crítico:** `AllowAdminCreateUserOnly=true`. Hoje está `false`, então qualquer pessoa com o client id (que é público) consegue se auto-cadastrar. Os convites continuam valendo 7 dias.
3. **Segurança:** `DeletionProtection=ACTIVE`.
4. E-mails do Cognito em português:
   - `InviteMessageTemplate`, para usuários novos. Assunto: "[PLATAFORMA YOKO] Cadastro de usuário". Corpo com `{username}`, `{####}` e o link `USUARIO_SITE`, avisando que é uma senha provisória que precisa ser trocada no primeiro acesso.
   - `VerificationMessageTemplate`, para o esqueci a senha e o reset pelo admin. Já está em PT; só vou acrescentar o link `<USUARIO_SITE>/redefinirSenha`.

Client `7gu9a6nifq9e5s04cudfm40b9f`:
5. **Segurança, crítico:** `WriteAttributes=[name, email]` (sem `custom:*`). Sem isso, um usuário com o próprio access token pode chamar `UpdateUserAttributes` e se dar `custom:roles=admin`. As APIs Admin* ignoram essa restrição.
6. **Segurança:** `ExplicitAuthFlows=[ALLOW_ADMIN_USER_PASSWORD_AUTH, ALLOW_REFRESH_TOKEN_AUTH]`, ou seja, sem `ALLOW_USER_PASSWORD_AUTH`, que é público e não é necessário.
7. **Segurança:** `PreventUserExistenceErrors=ENABLED`, para que o "esqueci a senha" não revele quais usuários existem.

IAM, role `CloudWatch`:
8. Política inline acrescentando `cognito-idp:AdminRespondToAuthChallenge` e `cognito-idp:AdminResetUserPassword`, restritas ao ARN do pool.

Como executar: `update-user-pool` e `update-user-pool-client` **redefinem com o valor padrão tudo o que não for enviado**. Por isso, antes de cada update eu salvo o `describe` atual no scratchpad (backup), monto o update a partir dele mudando só os campos acima e, no fim, rodo o `describe` de novo para comparar. As permissões são conferidas com `simulate-principal-policy`.

**Efeito da senha mínima de 12 na migração:** uma senha legada com menos de 12 caracteres (ou sem as 4 classes) é recusada no `admin_set_user_password`. Nesse caso entra o fallback da seção 5.2: o usuário loga pelo legado e é levado a `/novaSenha`, e a troca conclui a migração, sem e-mail. As senhas geradas pelo app têm 16 caracteres e 4 classes, então passam.

## 3. Banco de dados (MariaDB): **você executa manualmente**, fora deste plano
O código vai contar com estas colunas:
```sql
ALTER TABLE users
  ADD COLUMN migrado TINYINT(1) NOT NULL DEFAULT 0,
  ADD COLUMN cognito_sub VARCHAR(64) NULL;
```
A tabela `users` continua como espelho (nome, e-mail, roles, permission), usada por `listar_usuarios`, pelas buscas por e-mail e por dev. A coluna `password` fica intacta durante a transição (não é mais atualizada para quem migrou) e é limpa depois (seção 7).

## 4. Configuração (`app/pesquisa.py`, perto das outras variáveis AWS, ~l.286-310)
```python
COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID", "")
COGNITO_APP_CLIENT_ID = os.getenv("COGNITO_APP_CLIENT_ID", "")
USAR_COGNITO = PRODUCAO == 1
cognito = boto3.client('cognito-idp', region_name=AWS_REGION) if USAR_COGNITO else None
```
Os valores vêm do SSM pelo `load_ssm_parameters()` (l.63) que já existe. Não precisa mexer no `.env`, porque dev não usa Cognito.

## 5. Mudanças no código (todas em `app/pesquisa.py`)

### 5.0 Quem envia e-mail em cada operação

| Operação (produção) | Chamada no Cognito | E-mail |
|---|---|---|
| **Migração** no login | `admin_create_user(MessageAction='SUPPRESS')` + `admin_set_user_password(Permanent=True)` | **nenhum** (único uso do SUPPRESS) |
| Cadastro de usuário novo (individual ou por edital) | `admin_create_user` **sem SUPPRESS** (`DesiredDeliveryMediums=['EMAIL']`) | **convite do Cognito** (senha provisória, troca obrigatória no 1º acesso) |
| Convite não usado ou expirado (reset pelo admin) | `admin_create_user(MessageAction='RESEND')` | convite do Cognito |
| Esqueci minha senha | `forgot_password` + `confirm_forgot_password` | código do Cognito |
| Reset pelo admin (usuário já confirmado) | `admin_reset_user_password` | código do Cognito |
| Troca de senha logado | `change_password` | nenhum (o usuário está logado) |

Os 4 envios feitos hoje pelo app via SQS, com a função `enviar_email_senha` (l.3038), são **removidos**, junto com a função:
- `enviarMinhaSenha` (l.3064-3065)
- `cadastrar_usuario` (l.4331-4332)
- `cadastrar_usuarios_projetos` (l.4365-4366)
- `alterar_usuario` (l.4422-4423)

Em dev nada muda na prática, porque o SQS já não envia nada com `PRODUCAO=0`.

Há dois casos em que alguém que ainda não migrou precisa entrar no Cognito para receber o e-mail: o esqueci a senha e o reset pelo admin. Nos dois, primeiro acontece a migração silenciosa (SUPPRESS) e depois a operação normal, que dispara o e-mail do Cognito.

### 5.1 Helpers novos (bloco "Cognito")
- `iniciar_sessao(username, permissao, roles)`: extraído do final de `verify_password` (l.976-983). Preenche `username`, `permissao`, `roles`, `edital`. Serve para os dois backends, e os 45 `login_required` não mudam.
- `verificar_senha_legado(username, password) -> linha|None`: o miolo atual de `verify_password` (consulta + `cripto.hash_argon2id_verify` + logs), sem mexer na sessão.
- `atributos_cognito(nome, email, roles, permission, id)`: monta `email`, `email_verified=true`, `name`, `custom:roles`, `custom:permission`, `custom:legacy_id`. O `email_verified=true` é necessário para o Cognito entregar os códigos de recuperação.
- `cognito_autenticar(username, senha)`: `admin_initiate_auth(AuthFlow='ADMIN_USER_PASSWORD_AUTH')` e depois `admin_get_user` para ler `custom:roles`/`custom:permission`. Os tokens não ficam guardados na sessão, que continua sendo a do Flask no Redis. A função devolve o resultado ou o desafio `NEW_PASSWORD_REQUIRED`.
- `cognito_migrar_usuario(linha, senha_ou_None)`: **só para a migração.** `admin_create_user(MessageAction='SUPPRESS', atributos)`, tratando `UsernameExistsException` como sucesso para ser idempotente. Depois `admin_set_user_password(Password=senha, Permanent=True)` e `UPDATE users SET migrado=1, cognito_sub=%s`. Com `senha=None` (antes de um esqueci/reset), define uma senha aleatória que nunca é mostrada nem enviada, porque o usuário vai definir a própria pelo código do Cognito logo em seguida.
- `cognito_convidar_usuario(siape, nome, email, roles, permission, id)`: `admin_create_user` **sem SUPPRESS**. O Cognito envia o convite. Grava `migrado=1` e `cognito_sub`.
- `cognito_sincronizar_atributos(username, ...)`: `admin_update_user_attributes`. Quando o e-mail muda, inclui `email_verified=true`: a troca é feita pelo admin, que é confiável, e assim os códigos futuros chegam ao e-mail novo.

### 5.2 Login: `autenticar(username, senha)` substitui a chamada em `login()` (l.3011)
- `username_valido` + busca da linha em `users` (id, username, permission, roles, password, migrado, nome, email).
- **Dev (`not USAR_COGNITO`):** fluxo legado atual.
- **Prod, `migrado=1`:** `cognito_autenticar`, com os erros tratados assim:
  - `NotAuthorizedException` / `UserNotFoundException`: "usuário ou senha inválidos"; o segundo caso também gera um log de erro por inconsistência.
  - `PasswordResetRequiredException` (resetado pelo admin): redireciona para `/redefinirSenha` com a mensagem "Use o código enviado para seu e-mail".
  - Desafio `NEW_PASSWORD_REQUIRED` (usuário novo entrando com a senha provisória do convite): guarda `session['cognito_desafio'] = {'username', 'session'}` e redireciona para `/definirSenha`.
- **Prod, `migrado=0`:** `verificar_senha_legado`. Se estiver correta, chama `cognito_migrar_usuario(linha, senha)` e depois `iniciar_sessao` com os dados da linha. **Nenhum e-mail é enviado.**
  - Se `admin_set_user_password` der `InvalidPasswordException` (senha antiga fora da política de 12+), o login continua pelo legado, `migrado` fica em 0 e a sessão recebe a marca `senha_vazada`. Isso reaproveita o `bloquear_acesso_com_senha_vazada` (l.422), que obriga a passar por `/novaSenha`, e a troca completa a migração.
  - Se o Cognito estiver fora do ar (`ClientError`/`BotoCoreError`), o login continua pelo legado sem migrar e grava um log de warning. A migração é tentada de novo no próximo login.
- `verify_password` (callback do `@auth`, usado em `/segredo` e `/get_bib`) passa a delegar para `autenticar`.
- A checagem de senha vazada (Cloudflare) e `registrar_acesso` continuam iguais.

### 5.3 Nova rota `/definirSenha` (primeiro acesso de usuário convidado)
Template novo `definirSenha.html`, baseado em `novaSenha.html` mas sem o campo "senha atual". Só abre se existir `session['cognito_desafio']`. Valida com `senha_segura_valida` (l.4885) e chama `admin_respond_to_auth_challenge(ChallengeName='NEW_PASSWORD_REQUIRED')`. Depois limpa o desafio da sessão e chama `admin_get_user` e `iniciar_sessao`. Se a sessão do desafio expirar (3 min no Cognito), volta para o login.

### 5.4 Esqueci minha senha: `enviarMinhaSenha` (l.3045) + nova rota `/redefinirSenha`
- **Prod:**
  1. Busca `username` e `migrado` pelo e-mail em `users`. Se o usuário existir e `migrado=0`, chama `cognito_migrar_usuario(linha, None)`, que é a migração e por isso é silenciosa.
  2. Chama `cognito.forgot_password(ClientId, Username)`, e **o Cognito envia o e-mail com o código**.
  3. A resposta é sempre **genérica** ("Se o e-mail estiver cadastrado, você receberá um código"), mesmo quando o e-mail não existe.
  4. Redireciona para `/redefinirSenha`.
- `/redefinirSenha` (template novo `redefinirSenha.html`): SIAPE + código + nova senha + confirmação, validadas com `senha_segura_valida`, e depois `confirm_forgot_password`. Erros tratados: `CodeMismatchException`, `ExpiredCodeException` (com um link para pedir outro código), `InvalidPasswordException`. Rate limit igual ao de `enviarMinhaSenha`.
- Usuário novo que ainda não usou o convite (`FORCE_CHANGE_PASSWORD`): o `forgot_password` não funciona nesse estado. Nesse caso chamo `admin_create_user(MessageAction='RESEND')`, e o Cognito reenvia o convite.
- **Dev:** mostra só a mensagem genérica. Não gera nem sobrescreve senha.
- Isto também corrige o bug atual: `enviarMinhaSenha` usa `str(linhas[0])` onde deveria ser `linhas[0][0]`, sobrescreve a senha antes de confirmar e revela quais e-mails estão cadastrados.

### 5.5 Troca de senha logado: `nova_senha` (l.4906)
- **Prod, `migrado=1`:** `admin_initiate_auth` com a senha atual (se falhar, "Senha atual incorreta"), e com o access token devolvido chama `change_password(PreviousPassword, ProposedPassword, AccessToken)`. É a operação própria do Cognito para isso, e o token não fica guardado.
- **Prod, `migrado=0`** (caso da política): confere pelo legado e chama `cognito_migrar_usuario(linha, nova)`.
- **Dev:** sem alteração.

### 5.6 CRUD de usuários (admin)
- `cadastrar_novo_usuario` (l.4291), usado por `cadastrar_usuario` e `cadastrar_usuarios_projetos`:
  - `INSERT` em `users` com `password` preenchido com o hash de uma senha aleatória descartada (mantém o NOT NULL). A função **deixa de retornar a senha**.
  - Prod: `cognito_convidar_usuario(...)`, e **o Cognito envia o convite**. No primeiro login cai no desafio e vai para `/definirSenha`.
  - Dev: só o `INSERT`.
  - Flash para o admin: "Usuário cadastrado. O convite foi enviado por e-mail."
  - No cadastro em lote, se o `admin_create_user` falhar para alguém, o erro é registrado e o laço continua, como já acontece hoje.
- `alterar_usuario` (l.4391): depois do `UPDATE` local, em prod chama `cognito_sincronizar_atributos` (nome, e-mail, roles) se o usuário já migrou. Para quem não migrou nada é feito, porque os dados vão junto na migração a partir do espelho.
- Reset de senha pelo admin (checkbox `resetar_senha`), só em prod. Primeiro olha o status com `admin_get_user`:
  - `FORCE_CHANGE_PASSWORD` (convite não usado ou expirado): `admin_create_user(MessageAction='RESEND')`, e o Cognito reenvia o convite.
  - Usuário não migrado: `cognito_migrar_usuario(linha, None)` (silencioso) e depois `admin_reset_user_password`, e o Cognito envia o código.
  - Usuário migrado: `admin_reset_user_password`, e o Cognito envia o código. O próximo login cai em `PasswordResetRequiredException` e redireciona para `/redefinirSenha`.
  - Em dev, um flash avisa que o reset não está disponível.
- `listar_usuarios` / `listarUsuarios.html`: acrescentar a coluna "Migrado" para acompanhar o progresso.
- `/admin/argon2` (l.4273): continua valendo só para o legado.

### 5.7 Log de todas as operações de migração
Segue o padrão que já existe (`logger.contextualize(ip=..., username=..., rota=..., metodo=..., erro=..., classe_erro=...)`, como em `verify_password` l.961-970). O log vai para `app.json` e, no nível ERROR, também para o Sentry, que já está integrado via `LoguruIntegration`.

Helper novo `log_migracao(evento, username, nivel='info', origem=None, etapa=None, erro=None, **extra)`. Ele chama `logger.contextualize` com os campos padrão, mais `evento`, `origem` (`login` | `esqueci_senha` | `reset_admin` | `nova_senha`), `etapa` (`admin_create_user` | `admin_set_user_password` | `db_update`) e `cognito_sub`, e grava a mensagem. Ele é chamado **em todos os pontos de `cognito_migrar_usuario` e dos fluxos que a usam**:

| Evento | Nível | Quando |
|---|---|---|
| `migracao_iniciada` | INFO | Senha legada validada; começa a criação no Cognito |
| `migracao_usuario_ja_existia` | WARNING | `UsernameExistsException` no `admin_create_user` (retomada idempotente de uma migração interrompida) |
| `migracao_concluida` | INFO | `admin_set_user_password` ok e `migrado=1` gravado (com `cognito_sub` e `origem`) |
| `migracao_adiada_politica_senha` | WARNING | `InvalidPasswordException`: login pelo legado e troca obrigatória em `/novaSenha` |
| `migracao_concluida_nova_senha` | INFO | Migração completada pela troca de senha depois do adiamento |
| `migracao_falha_cognito` | ERROR | `ClientError`/`BotoCoreError` em qualquer etapa (com `etapa`, `erro`, `classe_erro`); login segue pelo legado |
| `migracao_falha_db` | ERROR | Usuário criado no Cognito mas falhou o `UPDATE users SET migrado=1` (inconsistência; a próxima tentativa se recupera pela idempotência) |
| `migracao_silenciosa_pre_recuperacao` | INFO | Migração com senha aleatória antes do esqueci a senha ou do reset pelo admin (`origem` indica qual) |
| `login_inconsistente_migrado_sem_cognito` | ERROR | `migrado=1` mas `UserNotFoundException` no Cognito |

Pelo mesmo helper também ficam no log, em INFO, as operações de senha no Cognito que acontecem depois da migração, para ter trilha de auditoria: convite enviado/reenviado, código de recuperação pedido, senha redefinida, reset pelo admin (com o `username` do admin) e troca de senha.

**Nunca entram no log** senha, código de verificação, tokens nem o `Session` do desafio. O e-mail só aparece onde já é registrado hoje, no esqueci a senha.

### 5.8 Documentação
README/`docs/seguranca.html`/CHANGELOG/TODO.md: novo fluxo, variáveis `COGNITO_*`, SQL de migração, a tabela de e-mails da seção 5.0 e o fim do envio de senhas pelo app.

## 6. Ordem de execução
0. **Antes de tudo:** salvar este plano, completo, em `migracao.cognito.md` na raiz do repositório (`/home/perazzo/Projetos/docker/pesquisa/migracao.cognito.md`).
1. Ajustes na AWS (seção 2, itens 1 a 8), com backup do `describe` e conferência depois.
2. Código (seções 4 e 5).
3. Deploy (depois que você rodar o `ALTER TABLE`) e acompanhamento dos eventos `migracao_*` no `app.json`/Sentry e da coluna Migrado.

## 7. Depois da migração (~60 dias)
- Usuários que ainda não migraram: usar o reset do admin (migração silenciosa + código do Cognito) ou deixar que usem o "esqueci minha senha".
- `UPDATE users SET password='' WHERE migrado=1` e, por fim, remover o Argon2 do caminho de produção.

## 8. Verificação
Quem faz: **[eu]** = executo e reporto o resultado; **[você]** = roteiro manual.
- **[eu] Dev (`PRODUCAO=0`):** `pytest tests/test_login.py`. O login e a troca de senha continuam como hoje. `grep "Senha: \|enviar_email_senha"` não encontra nada.
- **[eu] Pool de produção, antes de ligar no app** (pela CLI, logo depois dos ajustes da seção 2). Vou pedir um e-mail de teste seu, e você me confirma o que chegou:
  - `admin-create-user --message-action SUPPRESS` + `admin-set-user-password --permanent` + `admin-initiate-auth`: **nenhum e-mail chega**.
  - `admin-create-user` sem SUPPRESS: chega o convite em PT.
  - `admin-reset-user-password`: chega o código em PT.
  - `sign-up` com o client id é recusado (item 2), `initiate-auth USER_PASSWORD_AUTH` é recusado (item 6) e uma senha de 11 caracteres dá `InvalidPasswordException` (item 1).

  Apagar os usuários de teste no fim.
- **[você] App em produção depois do deploy, com usuários de teste** (depende de navegador e de caixa de e-mail):
  1. Um usuário legado: o primeiro login migra (`migrado=1`, `CONFIRMED` no Cognito com `custom:roles` certo) sem nenhum e-mail, e o segundo login autentica pelo Cognito. No `app.json` aparecem `migracao_iniciada` e `migracao_concluida`, sem senha no log.
  2. Senha errada é recusada nos dois estados.
  3. O "esqueci a senha" faz o Cognito mandar o código, e `/redefinirSenha` troca a senha. Testar com um usuário migrado e com um não migrado.
  4. Cadastrar pelo admin faz o Cognito mandar o convite, e o login com a senha provisória leva a `/definirSenha`.
  5. O reset pelo admin faz o Cognito mandar o código (ou reenviar o convite, se ele ainda não foi usado).
  6. A troca de senha logado funciona pelo `change_password`.
  7. Alterar o e-mail/roles pelo admin reflete no `admin-get-user`.
- O rollback é reverter o deploy: quem ainda não migrou continua no legado, e quem migrou precisaria de reset.

## 9. Roteiro de testes do pool pela CLI
Estes comandos conferem **só o pool do Cognito**, com as mesmas chamadas que o app faz; eles não passam pelo app. Rode com credenciais de admin da AWS, porque a role `CloudWatch` da EC2 não tem `AdminDeleteUser`. Os usuários `9999901` e `9999903` não existem na tabela `users` e não interferem no app. **Rode sempre a limpeza (passo 6) no fim.**

Executado com sucesso em 23/09/2026: chegaram exatamente os 2 e-mails do passo 5, e nenhum da migração silenciosa.

```bash
P=us-east-2_xsTbiRLIy; C=7gu9a6nifq9e5s04cudfm40b9f; R=us-east-2
U=9999901; SENHA='Teste#Cognito2026x'; EMAIL=rafaelperazzo@gmail.com

# 1. Migração silenciosa (NÃO deve chegar e-mail)
aws cognito-idp admin-create-user --region $R --user-pool-id $P --username $U --message-action SUPPRESS \
  --user-attributes Name=email,Value=$EMAIL Name=email_verified,Value=true Name=name,Value="Teste Cognito" \
  Name=custom:roles,Value=user Name=custom:permission,Value=1 Name=custom:legacy_id,Value=0
aws cognito-idp admin-set-user-password --region $R --user-pool-id $P --username $U --password "$SENHA" --permanent
aws cognito-idp admin-get-user --region $R --user-pool-id $P --username $U --query UserStatus   # esperado: CONFIRMED

# 2. Login (mesmo fluxo do app); guarda o token
TOKEN=$(aws cognito-idp admin-initiate-auth --region $R --user-pool-id $P --client-id $C \
  --auth-flow ADMIN_USER_PASSWORD_AUTH --auth-parameters USERNAME=$U,PASSWORD="$SENHA" \
  --query AuthenticationResult.AccessToken --output text)

# 3. Verificações de segurança (todas devem dar erro)
aws cognito-idp update-user-attributes --region $R --access-token "$TOKEN" \
  --user-attributes Name=custom:roles,Value=admin                          # NotAuthorizedException (unauthorized attribute)
aws cognito-idp admin-set-user-password --region $R --user-pool-id $P --username $U \
  --password 'Abc#1234567' --permanent                                     # InvalidPasswordException (11 caracteres)
aws cognito-idp sign-up --region $R --client-id $C --username 9999902 --password "$SENHA"   # SignUp is not permitted
aws cognito-idp initiate-auth --region $R --client-id $C --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters USERNAME=$U,PASSWORD="$SENHA"                           # USER_PASSWORD_AUTH flow not enabled

# 4. Troca de senha logado (change_password, como em /novaSenha)
aws cognito-idp change-password --region $R --access-token "$TOKEN" \
  --previous-password "$SENHA" --proposed-password 'Teste#Cognito2026y'

# 5. Os únicos que ENVIAM e-mail (devem chegar exatamente 2)
aws cognito-idp admin-reset-user-password --region $R --user-pool-id $P --username $U   # e-mail com código
aws cognito-idp admin-create-user --region $R --user-pool-id $P --username 9999903 --desired-delivery-mediums EMAIL \
  --user-attributes Name=email,Value=$EMAIL Name=email_verified,Value=true Name=name,Value="Teste Convite" \
  Name=custom:roles,Value=user Name=custom:permission,Value=1 Name=custom:legacy_id,Value=0   # convite

# 5b. Opcional: esqueci minha senha (mais um e-mail com código; rode antes da limpeza)
# aws cognito-idp forgot-password --region $R --client-id $C --username $U
# aws cognito-idp confirm-forgot-password --region $R --client-id $C --username $U \
#   --confirmation-code CODIGO --password 'Teste#Cognito2026z'

# 6. Limpeza
aws cognito-idp admin-delete-user --region $R --user-pool-id $P --username 9999901
aws cognito-idp admin-delete-user --region $R --user-pool-id $P --username 9999903
```

## 10. Templates de e-mail do Cognito
Os e-mails do Cognito usam HTML com CSS inline, no visual do `lembrete_frequencia.html`. A versão versionada fica em:
- `docs/cognito/convite.html`: `AdminCreateUserConfig.InviteMessageTemplate.EmailMessage` (precisa conter `{username}` e `{####}`)
- `docs/cognito/codigo.html`: `VerificationMessageTemplate.EmailMessage` e `EmailVerificationMessage`, com o mesmo conteúdo nos dois (precisa conter `{####}`); é usado no esqueci a senha e no reset pelo admin

Limite de 20.000 caracteres por mensagem. Para alterar, edite o arquivo e aplique com `update-user-pool`, partindo do `describe-user-pool` atual (campos omitidos voltam ao padrão). Aplicado e testado em 23/09/2026.
