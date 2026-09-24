# Adequação à LGPD

> **Status (2026-09-24):**
> - **código pronto e NÃO commitado**; 33 testes novos em `app/test_lgpd.py`, que passam junto com os 96 testes com mocks já existentes. Os testes de integração (banco real) falham da mesma forma com e sem estas mudanças;
> - **falta:** rodar o `lgpd.sql.sample` no banco `pesquisa`, fazer o deploy e a conferência em produção (seção 5);
> - itens fora do código: seção 4.
>
> Este documento é técnico e não é parecer jurídico. O texto da política deve ser revisado pelo Encarregado da UFCA e, se necessário, pela Procuradoria.

## 1. Decisões do usuário (2026-09-24)
- **Manter a hospedagem na us-east-2**, com as cláusulas-padrão contratuais da ANPD (Resolução CD/ANPD nº 19/2024) como salvaguarda.
- **Canal do titular:** o e-mail da PRPI (`DEFAULT_INSTITUCIONAL`), que repassa os pedidos ao Encarregado da UFCA.
- **Implementar:** a página `/lgpd`, os ajustes rápidos, "Meus dados", o formulário de solicitação, os avisos nos formulários e o **registro, após o login, de que o usuário tomou ciência dos termos**, com data e versão.
- **Verificação diretamente em produção.**

## 2. Levantamento

**Dados tratados:**

| Titular | Dados | Onde |
|---|---|---|
| Discente indicado | nome, nascimento, estado civil, sexo, RG/órgão/UF, **CPF**, curso, matrícula, Lattes, **banco/agência/conta**, telefone, celular, e-mail, endereço, escola, frequência; PDFs de RG/CPF, extrato, histórico, termo e plano | `indicacoes`, `frequencias`; S3 `pesquisa/docs_indicacoes/` |
| Orientador (usuário) | siape, nome, e-mail, CPF (Lattes), projetos, Lattes, IP dos acessos | `users`, `editalProjeto`, `acessos`; S3 `pesquisa/submissoes/`; Cognito |
| Avaliador externo | nome, e-mail, parecer | `avaliacoes` |
| Qualquer visitante | IP, rota, cidade/estado/país (GeoLite2), cookie de sessão | `app.json`/`app.log`, Sentry, Redis |

**Adolescentes:** a modalidade **PIBIC-EM** (ensino médio) pode envolver menores de 18 anos, e o art. 14 exige o tratamento no melhor interesse deles. A política informa isso.

**O que já atendia ao art. 46 (segurança):**
- Cloudflare (TLS e WAF) e MFA obrigatório;
- MariaDB criptografado em repouso;
- AES por coluna em RG, nascimento, telefone, celular e endereço;
- S3 em SSE-KMS com URL assinada de 60 s e bucket policy que exige KMS;
- `AmazonS3FullAccess` removida da role da EC2;
- limitador de acessos e bloqueio de senha vazada.

**Lacunas encontradas e o que foi feito com cada uma:**

| Lacuna | Situação |
|---|---|
| Google Analytics `UA-164056633-1` em `avaliacao.html`, `cadastrarProjeto.html` e `editalProjeto.html`. O UA parou em 2023, mas o script ainda mandava o IP ao Google | **Removido** |
| Retenção de logs `retention=30`: no loguru, isso quer dizer 30 arquivos, não 30 dias | **`LOG_RETENCAO = "90 days"`** |
| Sem política, sem canal do titular e sem registro de ciência | **Implementado** (seção 3) |
| Sentry com `send_default_pii=True`: IP, usuário e dados da requisição vão para os EUA | Declarado na política; **recomendação:** `send_default_pii=False` |
| CPF, dados bancários, nome e e-mail do discente sem criptografia por coluna | Recomendação (exige migrar os dados) |
| Tabela `acessos` sem expurgo | Depende do prazo de guarda (seção 4) |
| Terceiros recebem o IP: Cloudflare, reCAPTCHA, CDNs (Tailwind, jsDelivr, cdnjs, googleapis, jQuery) e shields.io | Declarados na política; recomendação: hospedar os assets e trocar o reCAPTCHA pelo Turnstile |

**Base legal:** a UFCA é a controladora, como órgão público (arts. 7º, II e III, 23 e 26). **O consentimento não é a base legal.** O aceite pedido é o **registro de ciência** dos Termos de Uso e da Política de Privacidade, e a página deixa isso claro. Assim, se o titular "revogar", o tratamento obrigatório para as bolsas não precisa parar.

**Transferência internacional (art. 33, II, "b"):** a política publica o país, as empresas, a finalidade e as salvaguardas. As cláusulas-padrão com a AWS são uma ação fora do código (seção 4).

## 3. Implementação

**Banco:** `lgpd.sql.sample` cria as tabelas `lgpd_aceites (username, versao, data, ip)`, com chave única em `(username, versao)`, e `lgpd_solicitacoes` (protocolo, dados do pedido, `prazo` = data + 15 dias, situação e resposta).

**`app/pesquisa.py`:**
- `LGPD_VERSAO` e `LGPD_VIGENCIA`. **Mudar a versão faz todos registrarem a ciência de novo no próximo login.**
- `iniciar_sessao()`, usada pelos dois backends de login, marca `session['aceite_pendente']` com `aceite_pendente()`. Um erro de banco conta como "sem pendência", então o login nunca trava. Isso cobre, por exemplo, o caso de as tabelas ainda não existirem.
- `exigir_aceite_lgpd()` (`before_request`) roda depois dos bloqueios de senha vazada e de MFA. Com a marca, o usuário só acessa `ROTAS_PERMITIDAS_ACEITE`: a política, o aceite, a solicitação, o logout e as telas de MFA e de senha.
- Rotas:

| Rota | Acesso | O que faz |
|---|---|---|
| `GET /lgpd` | público | Termos de uso, política de privacidade e quadro de requisitos (arts. 6º, 9º, 14, 18/19, 33, 37, 38, 41, 46, 48, 15/16) |
| `GET/POST /lgpd/aceite` | logado | Registro de ciência (`INSERT IGNORE`, com versão, data e IP) |
| `GET /meusDados` | `user` | Cadastro, projetos, a quantidade de discentes indicados (sem os dados deles), aceites e os 50 acessos mais recentes |
| `GET /meusDados.json` | `user` | Os mesmos dados para download (portabilidade) |
| `GET/POST /lgpd/solicitacao` | público, 3/dia | Grava o pedido com protocolo e envia e-mail à PRPI (com a descrição) e ao titular (com o protocolo, o prazo e o link da consulta). **Nunca devolve dados pessoais** |
| `GET/POST /lgpd/consulta` | público, 20/dia | Com o **protocolo e o e-mail do pedido**, mostra a situação, o prazo e a resposta. Protocolo fora do formato (12 caracteres A-Z/0-9) nem chega ao banco |
| `GET /admin/lgpd/solicitacoes` | `admin` | Lista por situação, com o prazo em destaque |
| `POST /admin/lgpd/solicitacoes/<id>/responder` | `admin` | Grava a resposta (só se a solicitação ainda estiver aberta) e **a envia automaticamente por e-mail ao titular**, com o link da consulta. Se o e-mail falhar, o admin vê um aviso para enviar manualmente |

**Regra da resposta:** o texto registrado no painel vai para o e-mail do titular e fica visível na consulta, por isso **não pode conter dados pessoais**; o painel mostra esse aviso junto ao campo. Dados pessoais, quando pedidos, seguem só depois de a PRPI confirmar a identidade do titular.

- `consultar_dicts()`: um SELECT que devolve dicionários. A tabela `acessos` não tem esquema no repositório, então "Meus dados" lê todas as colunas dela e ordena pela primeira coluna de data.

**Templates:**
- novos: `lgpd.html`, `lgpd_aceite.html`, `meus_dados.html`, `lgpd_solicitacao.html`, `lgpd_consulta.html`, `lgpd_solicitacoes.html`, `email_lgpd_solicitacao.html` e `email_lgpd_resposta.html`;
- link "Privacidade e LGPD" nos rodapés (`BASE_v3.html`, `base.html` e `index.html`) e um card na página inicial (`root.html`), com "Meus dados" para quem estiver logado;
- card "Solicitações LGPD" no painel do admin;
- aviso informativo (sem checkbox) em `indicacao.html`, `cadastrarProjeto.html` e `cadastrar_usuario.html`.

## 4. Fora do código (ações do usuário e da UFCA)
- [ ] **AWS Artifact:** conferir se há um adendo com as cláusulas-padrão da ANPD e aceitá-lo. Guardar também os DPAs da Cloudflare, do Google (reCAPTCHA) e do Sentry.
- [ ] **Encarregado da UFCA:** revisar o texto da `/lgpd`, informar o nome e o contato oficial dele (hoje o canal é a PRPI) e registrar o tratamento no inventário de dados (art. 37).
- [ ] **RIPD** (art. 38), por causa dos dados financeiros e de identidade dos discentes, inclusive de adolescentes.
- [ ] **Prazos de guarda** dos documentos das bolsas, definidos com a PRPI e o arquivo da UFCA; depois, o expurgo dos arquivos, das indicações e da tabela `acessos`.
- [ ] **Plano de resposta a incidentes:** comunicar a ANPD e os titulares em 3 dias úteis (Resolução CD/ANPD nº 15/2024).
- [ ] Quando cada item for concluído, mudar o cartão dele na `/lgpd` de "Em andamento" para "Implementado". A lista `requisitos` fica no topo do quadro, em `lgpd.html`.

**Recomendações técnicas futuras:**
- criptografar por coluna o CPF, os dados bancários, o nome e o e-mail;
- `send_default_pii=False` no Sentry;
- servir pelo próprio app os arquivos de CDN e os badges do shields.io;
- trocar o reCAPTCHA pelo Cloudflare Turnstile.

## 5. Deploy e conferência (em produção)
1. **Antes do deploy:** rodar o `lgpd.sql.sample` no banco `pesquisa`.
2. Commit, tag e deploy.
3. Abrir `/pesquisa/lgpd` sem login e conferir as seções e o quadro de requisitos.
4. Fazer login: depois do MFA, deve aparecer a tela de ciência. Sem registrar, qualquer outra rota volta para ela; `/lgpd` e o logout continuam acessíveis.
5. Registrar e conferir no banco: `SELECT * FROM lgpd_aceites ORDER BY id DESC LIMIT 5`. Sair e entrar de novo: a tela não deve voltar.
6. Abrir `/meusDados` e baixar o JSON: não pode haver senha nem dados de discentes.
7. Enviar **uma** solicitação de teste (os e-mails saem de verdade): conferir se chegaram à PRPI e ao titular, com o link da consulta. Consultar pelo protocolo e e-mail ("Em análise"). Responder pelo painel admin e conferir se a resposta chegou por e-mail e aparece na consulta como "Respondida".
8. Confirmar que não há mais `googletagmanager` no código-fonte de `cadastrarProjeto` e da avaliação.
9. Acompanhar os eventos `[lgpd]` no log nas primeiras horas.

**Para desfazer:** reverter o commit e fazer o deploy. As tabelas podem ficar no banco.
