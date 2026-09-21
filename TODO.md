# Yoko  - Pesquisa

Sistema de gerenciamento de projetos de pesquisa

## Todo

- [ ] Remover email NAO-RESPONDA e colocar no infisical
- [ ] Criptografar dados da tabela users (nome e email)
- [ ] Migrar gerenciamento de usuários para o AWS Cognito, com **migração usuário a usuário no primeiro login** (sem carga em lote e sem e-mail de senha temporária) — ~10-16 dias, ~US$ 0/mês com ~400 usuários (confirmar preços)
  - [ ] Provisionar user pool de dev e de prod (username = SIAPE, grupos `admin`/`user`, política de senha 12+ com 4 classes, e-mail via SES, app client sem secret com `ADMIN_USER_PASSWORD_AUTH` e `PreventUserExistenceErrors`)
  - [ ] Permissões IAM `cognito-idp:Admin*` + `ListUsers` na role do app; variáveis `COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID`, `COGNITO_REGION` no `.env` e no SSM
  - [ ] `login()`: se o usuário já existe no Cognito, `admin_initiate_auth`; se não, validar a senha no hash Argon2 legado e, se correta, criar a conta (`admin_create_user` com `MessageAction='SUPPRESS'`), definir a mesma senha (`admin_set_user_password`, `Permanent=True`), adicionar ao grupo e autenticar — o usuário não percebe a migração
  - [ ] Fallback: se a senha antiga não cumprir a política do Cognito, exigir nova senha (fluxo `nova_senha`) em vez de falhar
  - [ ] Preencher `session['username'/'roles'/'permissao'/'edital']` a partir dos grupos, mantendo as mesmas chaves (os 45 decorators não mudam)
  - [ ] Manter a tabela `users` local como espelho (nome, e-mail, roles, `cognito_sub`, flag `migrado`) para `listar_usuarios` e para saber quem já migrou; remover só a senha após a migração
  - [ ] Adaptar CRUD admin: cadastrar (criar direto no Cognito, com convite por e-mail), alterar, resetar (`admin_reset_user_password`), listar pelo espelho local
  - [ ] Fluxo esqueci/nova senha com `forgot_password`/`confirm_forgot_password`; mensagem genérica (evita enumeração de e-mails; o `enviarMinhaSenha` atual sobrescreve a senha antes de confirmar)
  - [ ] Traduzir os e-mails do Cognito para português (convite e código de recuperação) e configurar o pool para enviar via SES: identidade já existente é o **domínio** `yokoapps.com.br` em us-east-2 (verificada, DKIM ok, fora do sandbox, compatível com pool em us-east-2); usar `EmailSendingAccount=DEVELOPER`, `SourceArn` da identidade e `From` = `nao-responda@yokoapps.com.br` (FROM de domínio só pode ser definido por CLI/API, não pelo console); quem configurar precisa de `iam:CreateServiceLinkedRole`
  - [ ] Flag `AUTH_BACKEND=cognito|legado` para rollback e piloto em dev/staging antes de produção
  - [ ] Depois de um período (ex.: 60 dias): convidar por e-mail os usuários inativos que ainda não migraram; só então remover `verify_password`, `@auth.*`, Argon2 e a coluna `password`
  - [ ] Criar testes de autenticação (não existe `tests/` hoje), incluindo migração no primeiro login e fallback de senha fraca
  - [ ] Avaliar unificar `permissao` e `roles`

## Em progresso

- [ ] Remover lazy logs

## Finalizadas ✓

- [x] Adicionar logs em todas as rotas
- [x] Adicionar logs de erro
- [x] Remover consultas vulneráveis a SQL Injection
