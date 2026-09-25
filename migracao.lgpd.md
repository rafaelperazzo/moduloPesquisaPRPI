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
| Retenção de logs `retention=30`: no loguru, isso quer dizer 30 arquivos, não 30 dias | **`LOG_RETENCAO = "90 days"`** no servidor. **Desde 2026-09-25, guardados por 2 anos:** só no dia 1º de cada mês, sem limite de tamanho, o `app.json` é fechado, compactado e enviado a `s3://<bucket>/pesquisa/logs/` em SSE-KMS, e a regra de lifecycle `pesquisa-logs-2-anos` apaga os objetos depois de 730 dias. Uma cópia fica no servidor por 90 dias, e os envios que falharam são refeitos quando o app inicia |
| Sem política, sem canal do titular e sem registro de ciência | **Implementado** (seção 3) |
| Sentry com `send_default_pii=True`: IP, usuário e dados da requisição vão para os EUA | **Resolvido em 2026-09-24:** `send_default_pii=False`; `include_local_variables=False`, porque as variáveis dos stack traces guardam CPF, senha e dados bancários; `EventScrubber` com os nomes de campos em português e o `CF-Connecting-IP`; `before_send` e `before_breadcrumb` mascaram IP, e-mail e CPF no texto. Há 9 testes em `app/test_sentry.py`, com um evento real capturado localmente |
| CPF, dados bancários, nome e e-mail do discente sem criptografia por coluna | Recomendação (exige migrar os dados) |
| Backup de produção restaurado **em claro** na máquina de dev (`atualizar_db.sh`), com CPF e dados bancários reais | **`anonimizar_dev.sql`**, chamado pelo `atualizar_db.sh.sample` nos bancos `pesquisa` e `pesquisa_test`: CPF vira pseudônimo (o mesmo em todas as tabelas), dados bancários, RG, telefone, endereço e nascimento viram `ANONIMIZADO`, e-mail do discente e IPs são trocados, e as colunas suspeitas não tratadas são listadas para revisão. Um `trap` apaga o dump decifrado mesmo se o script falhar. Testado num MariaDB 11 descartável |
| Tabela `acessos` sem expurgo | **2 anos**, o prazo dos logs, pela tarefa mensal (seção 7) |
| Terceiros recebem o IP: Cloudflare, reCAPTCHA, CDNs (Tailwind, jsDelivr, cdnjs, googleapis, jQuery) e shields.io | Declarados na política. **reCAPTCHA trocado pelo Cloudflare Turnstile** (seção 6), e o Google saiu da lista de operadores. Recomendação que continua: hospedar os assets |
| reCAPTCHA **conferido só no navegador**, sem validação no servidor, e com a caixa fora do `<form>` em 5 páginas; o script do Google era carregado em **todas** as páginas | **Resolvido pelo Turnstile** (seção 6) |

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
- [x] **Prazos de guarda dos documentos das bolsas:** 6 anos após o fim da bolsa, por decisão do usuário em 2026-09-25. O expurgo está na seção 7. Recomendação que continua: formalizar com a CPAD/Arquivo da UFCA (Resolução CONARQ 40/2014).
- [x] **Tabela `acessos`** (IP e data dos logins): os registros com mais de 2 anos, o mesmo prazo dos logs, são apagados pela `expurgar_acessos` na tarefa mensal (seção 7). Código de 2026-09-25; falta a primeira execução em produção.
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

## 6. Cloudflare Turnstile (no lugar do reCAPTCHA), 2026-09-24

> **Em produção desde a v11.1.0 (`a7e54cc`).** O usuário conferiu em 2026-09-24, e está funcionando.

- **Chaves no SSM:** `/pesquisa/TURNSTILE_SITE_KEY` (String) e `/pesquisa/TURNSTILE_SECRET_KEY` (SecureString), criadas pelo usuário e conferidas. Sem elas, o app usa as chaves de teste da Cloudflare.
- **Servidor:** `turnstile_valido()` valida o `cf-turnstile-response` no `siteverify`, enviando o IP do `CF-Connecting-IP`, **só em produção**, como o MFA. Sem token ou com token recusado, o envio é recusado. Se a Cloudflare não responder, o envio é aceito e fica um aviso no log, para não travar o login. O decorator `@exigir_turnstile(<endpoint>)` volta ao formulário com uma mensagem.
- **Rotas protegidas:**
  - `/login`;
  - `/enviarMinhaSenha`;
  - `/projetosAluno`, que também ganhou o limitador que não tinha;
  - `/projetos_discente`;
  - `/score2`;
  - `/lgpd/consulta`;
  - `/lgpd/solicitacao`, que devolve o formulário preenchido.
- **Sem captcha:** `/cadastrarProjeto` e o cadastro de usuário. As duas rotas já exigem login com MFA, e o formulário de projeto é longo, com anexos.
- **Templates:** o widget fica em `templates/_turnstile.html`, incluído **dentro** do `<form>` e carregado só nessas páginas. O `BASE_v3.html` deixou de carregar o script do Google em todas as páginas. `base.html` e `consulta.html` ainda citam o reCAPTCHA, mas nenhuma rota os renderiza.
- **Testes:** `app/test_turnstile.py`, com 23 testes.
- **Conferência em produção:**
  1. fazer login, conferindo se a caixa aparece dentro do formulário e se o login funciona;
  2. abrir "esqueci minha senha" e a consulta de projetos por CPF;
  3. no log, os eventos `[turnstile]` não devem mostrar recusas de usuários legítimos;
  4. **para desfazer:** reverter o commit (o reCAPTCHA antigo não validava nada no servidor).

## 7. Retenção dos dados dos estudantes (6 anos após o fim da bolsa), 2026-09-25

**Decisão do usuário:** 6 anos após o término da bolsa, sendo 5 de guarda e mais 1 para a prestação de contas. A regra vale para todos os documentos e dados pessoais dos estudantes. A `LGPD_VERSAO` não muda.

**Por que o prazo vem do banco, e não de uma regra de lifecycle do S3:** os objetos de `pesquisa/docs_indicacoes/` têm a data do reenvio e da migração para o KMS (2025–2026), e não a da indicação. O prazo conta a partir de `indicacoes.fim`, que as rotas de substituição e de cancelamento atualizam para `NOW()`.

| Tabela | Coluna do prazo | Anonimizado (`NULL` ou valor vazio, se a coluna for NOT NULL) | Mantido |
|---|---|---|---|
| `indicacoes` | `fim` | CPF, `cpf_hash`, RG, órgão emissor, UF, nascimento, estado civil, sexo, banco, agência, conta, telefone, celular, e-mail, endereço, matrícula, Lattes, escola, ano de conclusão e as 6 colunas `arquivo_*`. Os arquivos são apagados de `pesquisa/docs_indicacoes/`. O `arquivo_af` tem `N/A` em todas as linhas, um valor de preenchimento: a coluna é limpa, mas o `N/A` não gera exclusão no S3 | nome, projeto, modalidade, tipo de vaga, fomento, curso, período, situação e `data` |
| `alunos` (legada) | `fim`, em texto: "Julho de 2018" ou "31/07/2019" | e-mail | nome, **CPF e `cpf_hash`**, para a busca das declarações antigas, o projeto, o período, o curso, o fomento e o programa |
| `cadastro_geral` (legada) | `estudante_fim`; se estiver vazio, o `termino` | RG, telefone, celular, banco, agência, conta, `e-mail`, matrícula, `id_lattes` e `estudante_obs` do estudante | nome, **CPF e `cpf_hash`**, a situação e o fomento da bolsa, os dados do orientador (`orientador_*`) e os do projeto |

**Código:**
- `app/modules/retencao.py`, com a lista `TABELAS_RETENCAO`:
  - uma linha só é anonimizada depois que o S3 confirma a exclusão dos arquivos dela;
  - se a linha tiver um nome de arquivo recusado pelo `secure_filename`, ela é mantida e conta como falha, para revisão manual. Anonimizar essa linha apagaria a única referência ao arquivo, que ficaria esquecido no S3;
  - a coluna `expurgo` marca a linha e torna a execução idempotente;
  - o log leva só contagens e ids.
- **Tarefa mensal** `job_expurgo_retencao`: roda no dia 1º, às 21:00, com no máximo 500 linhas por tabela. Não roda de madrugada porque a EC2 desliga às 22:00.
- **Script** `app/scripts/expurgar_dados_estudantes.py`: faz a primeira execução, sem limite.
- **Admin:** na lista de indicações, os documentos eliminados aparecem como "—".
- **Datas:** são lidas em Python, e não com `CAST` no SQL, porque nas tabelas legadas elas são texto. O leitor aceita:
  - data ou data e hora;
  - `AAAA-MM-DD`;
  - `DD/MM/AAAA`;
  - "Mês de AAAA", que conta a partir do último dia do mês.
- **Testes:** 27 em `app/test_retencao.py`. O código também foi validado num MariaDB 11 descartável, em modo estrito, com as datas em texto.
- **Primeiro `--simular` em produção (2026-09-25):**
  - `indicacoes`: 175 linhas e 822 arquivos, com fim entre 2019-09 e 2020-09;
  - `alunos`: 3 linhas, e 682 ficaram sem data válida, o que levou ao leitor de datas em texto;
  - `cadastro_geral`: 763 linhas, e 10 ficaram sem data, das quais 9 têm `termino`.

  As colunas não classificadas foram revistas com o usuário.

  Na segunda simulação, `indicacoes` mostrou 656 arquivos em vez de 822. A diferença eram 165 valores `N/A` e um `N/D`, na linha 5319. Isso levou a separar, no `--simular`, os valores de preenchimento ignorados e as linhas com nome de arquivo recusado.

**Primeira execução, na EC2 (irreversível):**
1. aplicar o `retencao.sql.sample`, que cria a coluna `expurgo` nas 3 tabelas;
2. fazer o backup do banco;
3. `env/bin/python scripts/expurgar_dados_estudantes.py --simular` e conferir:
   - as linhas vencidas e os arquivos;
   - o `fim` mais antigo;
   - as linhas **sem data válida**, que não são tratadas e precisam ser revistas manualmente;
   - as **colunas não classificadas**, que precisam ser revisadas: se forem dados pessoais do estudante, entram em `anonimizar`;
4. `--limite 5`, e conferir essas linhas no admin e a marca de exclusão no S3 (`aws s3api list-object-versions --prefix pesquisa/docs_indicacoes/<arquivo>`);
5. rodar o script sem `--limite`.

**Recuperação:**
- um arquivo apagado por engano pode ser recuperado por 1 dia, removendo a marca de exclusão. Depois disso, a regra `S3 Lifecycle Rule` apaga a versão antiga;
- o banco só pode ser recuperado pelo backup;
- os backups guardam 21 cópias e sincronizam com `--delete`, então o dado anonimizado some dos backups em cerca de 3 semanas.

**Execução em produção (2026-09-25):** `--limite 5` e depois a execução completa.
- **`indicacoes`:** 175 linhas anonimizadas e 656 arquivos apagados. O S3 conferido mostra 656 marcas de exclusão com data de hoje, e o `head-object` de um arquivo devolve 404.
- **`alunos`:** 685 linhas.
- **`cadastro_geral`:** 772 linhas pelo script. A linha 345 não tinha nenhuma data, e as vizinhas (335 a 355) são de 2018. Ela foi anonimizada manualmente, com as mesmas colunas do script. Com isso, as 773 linhas estão tratadas.
- **Falhas:** nenhuma.
- **Daqui em diante:** a tarefa mensal do dia 1º, às 21:00, trata as bolsas que completarem 6 anos.

**Tabela `acessos` (IP e data dos logins), 2026-09-25:**
- **Prazo:** os registros com mais de 2 anos são apagados, o mesmo prazo dos logs. A exclusão é feita em lotes de 5.000 pela `expurgar_acessos`, na mesma tarefa mensal.
- **Coluna de data:** a tabela não tem esquema no repositório, então a coluna de data é descoberta pelo `information_schema`. O `--simular` mostra qual coluna foi usada.
- **Script:** `--tabela acessos` trata só essa tabela, e o `--limite` não se aplica a ela.
- **Validação:** feita num MariaDB 11 descartável. De 1.200 registros, sobraram 729, com o mais antigo de exatamente 2 anos, e a segunda execução não apagou nada.
- **Bug na primeira execução em produção:** o `--simular` mostrou a coluna `hora`, 29.653 registros e o mais antigo de 2019-06-27, mas a execução informou "0 apagados". Causa: no conector `mariadb`, o `COMMIT` zera o `cursor.rowcount`, e o código lia esse número depois do `commit`. Isso foi confirmado com o conector real: 3 antes do `commit` e 0 depois. O código apagou o primeiro lote, provavelmente de 5.000 registros, e parou. A validação anterior usou o `pymysql`, que não tem esse comportamento. Correção: o `rowcount` passa a ser lido antes do `commit`, e o teste falso imita o conector.
- **Primeira execução em produção:**
  1. backup do banco;
  2. `env/bin/python scripts/expurgar_dados_estudantes.py --tabela acessos --simular`;
  3. `env/bin/python scripts/expurgar_dados_estudantes.py --tabela acessos`.
