# Yoko  - Pesquisa

Sistema de gerenciamento de projetos de pesquisa

## Todo

- [ ] Remover email NAO-RESPONDA e colocar no infisical
- [ ] Criptografar dados da tabela users (nome e email)
- [ ] Avaliar unificar `permissao` e `roles`
- [ ] Utilizar função Lambda para lidar com o download, upload e criptografia dos arquivos do app que estão no S3 (plano em `migracao.s3.md`)

## Em progresso

- [ ] Migração da autenticação para o AWS Cognito (plano em `migracao.cognito.md`)
  - [x] Código: migração silenciosa no login, esqueci/redefinir senha, primeiro acesso (`/definirSenha`), troca de senha, CRUD admin e logs `migracao_*`
  - [x] Removido o envio de senhas por e-mail pelo app (`enviar_email_senha`)
  - [x] Ajustes no pool/client/IAM (aplicados e testados via CLI em 2026-09-23) (senha 12+, sem auto-cadastro, `WriteAttributes` sem `custom:*`, sem `ALLOW_USER_PASSWORD_AUTH`, `PreventUserExistenceErrors`, templates PT, `AdminRespondToAuthChallenge` + `AdminResetUserPassword`)
  - [x] `ALTER TABLE users ADD migrado, cognito_sub` em `pesquisa_test` e `pesquisa`
  - [ ] Testes manuais em produção (seção 8 do plano)
  - [ ] Após ~60 dias: tratar quem não migrou, limpar `users.password` dos migrados e remover o Argon2 do caminho de produção

- [x] MFA obrigatório via Cognito (TOTP/Google Authenticator ou código por e-mail), seção 11 de `migracao.cognito.md`
  - [x] Código: cadastro com QR code, desafio no login, recuperação por e-mail, troca de método, `/novaSenha` via access token, testes `app/test_mfa.py`
  - [x] AWS: `set-user-pool-mfa-config` (OPTIONAL + TOTP + e-mail), `AuthSessionValidity` 5 min, `AdminSetUserMFAPreference` na role `CloudWatch` (aplicado e conferido em 2026-09-23)
  - [x] Deploy e testes manuais em produção (seção 11.4) (v10.0.0, testado em 2026-09-23)

- [ ] Remover lazy logs

## Finalizadas ✓

- [x] Adicionar logs em todas as rotas
- [x] Adicionar logs de erro
- [x] Remover consultas vulneráveis a SQL Injection
