# Inventário de dados pessoais: Plataforma Yoko - Pesquisa

**Registro das operações de tratamento (LGPD, art. 37)**

| | |
|---|---|
| **Situação** | Rascunho da PRPI, para ser incluído pelo Encarregado no inventário de dados pessoais da UFCA |
| **Data** | 25/09/2026 |
| **Política relacionada** | [PRIVACY.md](../../PRIVACY.md), versão 1.0, vigente desde 24/09/2026 |

Este documento descreve **quais dados pessoais a plataforma trata, de quem, para quê, com quem são compartilhados, por quanto tempo são guardados e como são protegidos**. Ele não contém dados pessoais de ninguém, só as categorias.

---

## 1. Identificação do processo

| Campo | Descrição |
|---|---|
| **Processo** | Gestão dos editais de pesquisa e de iniciação científica, tecnológica e de ensino médio da UFCA: submissão, avaliação e classificação de projetos; indicação, acompanhamento e pagamento de bolsistas; declarações e certificados |
| **Sistema** | Plataforma Yoko - Pesquisa (aplicação web) |
| **Unidade responsável** | Pró-reitoria de Pesquisa, Pós-graduação e Inovação (PRPI) |
| **Início do tratamento** | Registros de bolsas desde 2014, das tabelas do sistema anterior |

## 2. Agentes de tratamento

| Papel | Quem |
|---|---|
| **Controlador** | Universidade Federal do Cariri (UFCA), por meio da PRPI |
| **Encarregado** | Encarregado pelo Tratamento de Dados Pessoais da UFCA. Os pedidos dos titulares chegam pela PRPI e são repassados a ele |
| **Operadores** | Amazon Web Services (AWS), Cloudflare e Sentry (seção 7) |

## 3. Titulares e dados tratados

| Titular | Dados | Origem |
|---|---|---|
| **Discente indicado(a)**, inclusive **adolescentes** do ensino médio (PIBIC-EM) | **Identificação:** nome, data de nascimento, estado civil, sexo, RG (órgão emissor e UF), CPF. **Acadêmicos:** curso, matrícula, ano de ingresso, link do currículo Lattes, escola e ano de conclusão do ensino médio, frequência mensal. **Financeiros:** banco, agência e conta. **Contato:** telefone, celular, e-mail, endereço. **Documentos:** cópia do RG/CPF, extrato bancário, histórico escolar, termo de compromisso e plano de trabalho | Formulário de indicação, preenchido pelo(a) orientador(a) |
| **Orientador(a) / usuário(a)** | SIAPE, nome, e-mail, CPF, unidade acadêmica, área, grupo de pesquisa, projetos e planos de trabalho, currículo Lattes e sua pontuação, conta de acesso (autenticação e segundo fator), registro da ciência da política | Cadastro na plataforma; currículo Lattes obtido do CNPq |
| **Avaliador(a) de projetos** | Nome, e-mail e parecer | Cadastro pela PRPI e formulário de avaliação |
| **Solicitante de direitos (LGPD)** | Nome, e-mail e descrição do pedido | Formulário de solicitação |
| **Qualquer visitante** | Endereço IP, página acessada, data e hora, localização aproximada (cidade, estado e país) deduzida do IP; cookie de sessão | Registros de segurança da aplicação |
| **Usuário que faz login** | Data e IP de cada login | Registro de acessos |

**Dados sensíveis (art. 5º, II):** a plataforma não coleta dados sensíveis, como origem racial, saúde, religião, opinião política ou biometria. O campo "sexo" é um dado pessoal comum.

**Dados de adolescentes (art. 14):** nas modalidades de ensino médio, os discentes podem ter menos de 18 anos. Os dados deles são tratados no seu melhor interesse, só para as finalidades do edital.

**Dados financeiros e de identidade:** CPF, RG e dados bancários dos discentes são os dados de maior risco. Por isso, são cifrados por coluna no banco (seção 9) e são o foco do relatório de impacto (art. 38).

## 4. Ciclo de vida

| Fase | Como acontece |
|---|---|
| **Coleta** | Formulários da plataforma: cadastro, submissão, indicação, avaliação e solicitação LGPD. Consulta do currículo Lattes ao CNPq. Registros automáticos de segurança e de acesso |
| **Armazenamento** | Banco de dados e arquivos em nuvem (AWS, EUA), com criptografia em repouso |
| **Uso** | Avaliação e classificação dos projetos, homologação pela PRPI, pagamento e prestação de contas das bolsas, emissão de declarações e certificados, e-mails do sistema |
| **Compartilhamento** | Seção 6 |
| **Eliminação** | Automática, pelos prazos da seção 8 |

## 5. Finalidades e bases legais

| Operação | Finalidade | Base legal (LGPD) |
|---|---|---|
| Projetos e avaliação | Submissão, avaliação, classificação e acompanhamento dos projetos dos editais | Execução de políticas públicas (art. 7º, III, e art. 23) |
| Indicação e bolsas | Indicação de discentes, pagamento e prestação de contas das bolsas, declarações e certificados | Obrigação legal ou regulatória e execução de políticas públicas (art. 7º, II e III) |
| Currículo Lattes | Obtenção e pontuação do currículo Lattes junto ao CNPq | Execução de políticas públicas e uso compartilhado entre órgãos públicos (art. 7º, III, e art. 26) |
| Avaliadores | Convites e pareceres | Execução de políticas públicas (art. 7º, III) |
| Segurança | Prevenção a fraudes e auditoria de acessos | Obrigação legal (art. 7º, II), em atenção ao dever de segurança (art. 46) |
| Direitos do titular | Atendimento aos pedidos do art. 18 | Obrigação legal (art. 7º, II, e arts. 18 e 19) |

O consentimento não é base legal de nenhuma operação. A ciência da política, registrada após o login, só documenta que o usuário foi informado.

Não há decisão tomada unicamente de forma automatizada (art. 20). A pontuação Lattes é um dos critérios, e a classificação final é homologada pela PRPI.

## 6. Compartilhamento

| Com quem | O quê | Por quê |
|---|---|---|
| **CNPq** | CPF do(a) orientador(a) | Obter o currículo Lattes |
| **Agências de fomento (CNPq, FUNCAP)** | Dados dos bolsistas exigidos pelo edital | Implementação e prestação de contas das bolsas, quando exigido |
| **Órgãos de controle** | Os dados exigidos | Quando exigido por lei |

Os dados não são vendidos nem usados para publicidade.

## 7. Operadores e transferência internacional (art. 33)

| Operador | País | Tratamento | Garantias |
|---|---|---|---|
| **Amazon Web Services** | EUA | Hospedagem do servidor, do banco de dados e dos arquivos; autenticação e segundo fator (e-mail e credenciais dos usuários); fila e envio de e-mails (endereços dos destinatários e conteúdo das mensagens); monitoramento dos logs no CloudWatch (IP, usuário, rota e localização aproximada); funções de criptografia e de validação de arquivos | AWS Data Processing Addendum; ISO/IEC 27001 e SOC 2; criptografia em trânsito e em repouso |
| **Cloudflare** | Rede global | Proteção do domínio: TLS, firewall, bloqueio de bots e verificação anti-robô dos formulários públicos. Todo o tráfego passa por ela, com o IP do visitante | Termos e DPA da Cloudflare, ainda a arquivar |
| **Sentry** | EUA | Registro de erros da aplicação. **Sem dados pessoais:** IP, usuário, cookies e variáveis locais não são enviados, e e-mail, CPF e IP são mascarados nas mensagens | DPA do Sentry, ainda a arquivar |
| **Bibliotecas públicas (CDNs)** | Diversos | Recebem o IP e os dados do navegador ao carregar a página | — |

**Pendente:** adotar as cláusulas-padrão contratuais da ANPD (art. 33, II, "b"; Resolução CD/ANPD nº 19/2024) com os operadores.

## 8. Retenção e eliminação (arts. 15 e 16)

| Dado | Prazo | Como é eliminado |
|---|---|---|
| **Documentos e dados pessoais dos discentes** | 6 anos após o término da bolsa (5 anos de guarda e 1 ano para a prestação de contas) | **Automático, uma vez por mês:** os documentos são apagados e os dados pessoais anonimizados. Ficam nome, projeto e período, para as declarações. Nos registros do sistema anterior (bolsas encerradas até 2020), o CPF também fica, para a busca das declarações |
| **Registros de segurança (logs)** | 1 ano no CloudWatch; 2 anos no arquivo do S3 | Enviados ao Amazon CloudWatch (grupo `logs_pesquisa`, retenção de 365 dias, criptografia em repouso padrão do serviço). Também arquivados por mês, compactados e cifrados (AWS KMS), e apagados automaticamente depois de 2 anos. A cópia no servidor é apagada depois de 90 dias |
| **Registros de acesso (data e IP de cada login)** | 2 anos | Automático, uma vez por mês |
| **Sessão** | Até o logout ou 1 hora de inatividade | Automático |
| **Links de acesso aos arquivos** | 60 segundos; os links dos avaliadores valem 30 dias | Expiram sozinhos |

**Primeira eliminação, em 25/09/2026:**
- 1.633 registros de bolsistas anonimizados, somando as indicações atuais e as tabelas do sistema anterior (um mesmo bolsista pode aparecer em mais de uma tabela);
- 656 documentos apagados;
- 29.653 registros de acesso com mais de 2 anos apagados.

**Prazos ainda não definidos:**
- **projetos:** a política diz "pelo prazo exigido para a prestação de contas e para a guarda de documentos públicos";
- **contas de orientadores e usuários;**
- **avaliadores e pareceres;**
- **solicitações LGPD;**
- **registro da ciência da política.**

Esses prazos devem seguir a Tabela de Temporalidade da UFCA. Também é recomendado que a CPAD/Arquivo da UFCA formalize o prazo de 6 anos dos documentos dos discentes (Resolução CONARQ 40/2014).

## 9. Medidas de segurança (art. 46)

- **Criptografia em trânsito:** TLS em toda a comunicação.
- **Criptografia em repouso:** disco do servidor, arquivos (com chaves gerenciadas pelo AWS KMS) e banco de dados.
- **Criptografia por coluna** dos campos mais sensíveis: CPF (com busca por hash), RG, dados bancários, nascimento, telefone, celular e endereço.
- **Arquivos** acessíveis apenas por links temporários, gerados depois da verificação de permissão.
- **Autenticação em duas etapas (MFA) obrigatória** para os usuários; proteção adicional na borda para os administradores.
- **Permissões mínimas** para o servidor e para as funções em nuvem.
- **Proteção contra abuso:** firewall de aplicação, bloqueio de bots, verificação anti-robô e limite de tentativas.
- **Segredos** (senhas e chaves) fora do servidor de aplicação, em cofre gerenciado.
- **Ambiente de desenvolvimento:** as cópias do banco são anonimizadas antes do uso. A anonimização das cópias já existentes está em andamento.
- **Registro de erros** sem dados pessoais.

## 10. Direitos dos titulares (arts. 18 e 19)

- **Canal:** e-mail da PRPI ou formulário de solicitação da plataforma, com protocolo.
- **Prazo de resposta:** 15 dias, com consulta pelo protocolo.
- **"Meus dados":** os usuários veem e baixam os próprios dados em JSON (portabilidade).

## 11. Pendências de adequação

| Artigo | Pendência | Responsável |
|---|---|---|
| Art. 33 | Cláusulas-padrão da ANPD com os operadores; arquivar os DPAs da Cloudflare e do Sentry | PRPI |
| Art. 37 | Incluir este processo no inventário institucional | Encarregado da UFCA |
| Art. 38 | Relatório de impacto (RIPD), pelos dados financeiros e de identidade, inclusive de adolescentes | Encarregado, com a PRPI |
| Art. 41 | Publicar na política o nome e o contato do Encarregado | Encarregado |
| Art. 48 | Plano de resposta a incidentes (comunicação à ANPD e aos titulares em 3 dias úteis; Resolução CD/ANPD nº 15/2024) | PRPI e UFCA |
| Arts. 15 e 16 | Prazos de guarda que faltam (seção 8) | PRPI, com a CPAD |
