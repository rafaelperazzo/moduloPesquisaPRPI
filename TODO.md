# Yoko  - Pesquisa

Sistema de gerenciamento de projetos de pesquisa

## Todo

- [ ] Remover email NAO-RESPONDA e colocar no infisical
- [ ] Criptografar dados da tabela users (nome e email)
- [ ] Avaliar unificar `permissao` e `roles`

## Em progresso

- [ ] Migração da autenticação para o AWS Cognito (plano em `migracao.cognito.md`)
  - [x] Código: migração silenciosa no login, esqueci/redefinir senha, primeiro acesso (`/definirSenha`), troca de senha, CRUD admin e logs `migracao_*`
  - [x] Removido o envio de senhas por e-mail pelo app (`enviar_email_senha`)
  - [x] Ajustes no pool/client/IAM (aplicados e testados via CLI em 2026-09-23) (senha 12+, sem auto-cadastro, `WriteAttributes` sem `custom:*`, sem `ALLOW_USER_PASSWORD_AUTH`, `PreventUserExistenceErrors`, templates PT, `AdminRespondToAuthChallenge` + `AdminResetUserPassword`)
  - [ ] `ALTER TABLE users ADD migrado, cognito_sub` em `pesquisa_test` e `pesquisa` (manual, **antes do deploy**)
  - [ ] Testes manuais em produção (seção 8 do plano)
  - [ ] Após ~60 dias: tratar quem não migrou, limpar `users.password` dos migrados e remover o Argon2 do caminho de produção

- [ ] Remover lazy logs

## Finalizadas ✓

- [x] Adicionar logs em todas as rotas
- [x] Adicionar logs de erro
- [x] Remover consultas vulneráveis a SQL Injection
