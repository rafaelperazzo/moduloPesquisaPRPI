<!--
  Espelho de app/templates/lgpd.html (página /lgpd da plataforma). A versão que vale é a da plataforma.
  Ao mudar a política, atualizar os dois arquivos juntos, e também LGPD_VERSAO/LGPD_VIGENCIA em app/pesquisa.py
  quando a mudança for relevante. Valores copiados de app/pesquisa.py: LGPD_PRAZO_RESPOSTA (15 dias),
  URL_DOWNLOAD_VALIDADE (60 s), ARQUIVOS_LINK_VALIDADE (30 dias) e DEFAULT_INSTITUCIONAL.
-->

# Privacidade e LGPD

Termos de Uso e Política de Privacidade da **Plataforma Yoko - Pesquisa**. O documento traz as informações exigidas pela Lei Geral de Proteção de Dados Pessoais (Lei nº 13.709/2018, LGPD) e o quadro de atendimento aos requisitos da lei.

**Versão 1.0, vigente desde 24/09/2026.**

> Este arquivo reproduz a política publicada na página **Privacidade e LGPD** (`/pesquisa/lgpd`) da plataforma. Se houver diferença entre os dois, vale a versão da plataforma.

| | |
|---|---|
| **Controlador** | Universidade Federal do Cariri (UFCA), por meio da Pró-reitoria de Pesquisa, Pós-graduação e Inovação (PRPI). |
| **Canal do titular** | [pesquisa.prpi@ufca.edu.br](mailto:pesquisa.prpi@ufca.edu.br) ou o formulário de solicitação da plataforma (`/pesquisa/lgpd/solicitacao`). Os pedidos são repassados ao Encarregado pelo Tratamento de Dados Pessoais da UFCA. |
| **Hospedagem** | Amazon Web Services (AWS), região us-east-2 (Ohio, Estados Unidos). Veja a seção [5. Transferência internacional](#5-transferência-internacional). |

## 1. Termos de uso

A plataforma é de uso institucional, para a gestão dos editais de pesquisa e iniciação científica da UFCA. Ao usá-la, você se compromete a:

- manter em sigilo sua senha e seu segundo fator de autenticação (MFA), que são pessoais e intransferíveis;
- informar dados verdadeiros e mantê-los atualizados;
- usar os dados pessoais de terceiros a que tiver acesso (por exemplo, de discentes indicados ou de projetos em avaliação) apenas para a finalidade do edital, sem copiá-los ou repassá-los;
- ao indicar um discente, avisá-lo de que os dados dele serão tratados pela UFCA conforme esta política;
- comunicar à PRPI qualquer suspeita de uso indevido da sua conta ou de incidente com dados pessoais.

O descumprimento pode levar ao bloqueio do acesso, sem prejuízo das medidas administrativas cabíveis.

## 2. Quais dados pessoais são tratados

| Titular | Dados |
|---|---|
| **Discente indicado(a)** | Nome, data de nascimento, estado civil, sexo, RG (órgão emissor e UF), CPF, curso, matrícula, ano de ingresso, currículo Lattes, dados bancários (banco, agência e conta), telefone, celular, e-mail, endereço, escola e ano de conclusão do ensino médio, frequência mensal. Documentos enviados: RG/CPF, extrato bancário, histórico escolar, termo de compromisso e plano de trabalho. |
| **Orientador(a) / usuário(a)** | SIAPE, nome, e-mail, CPF (para obter o currículo Lattes junto ao CNPq), unidade acadêmica, área, grupo de pesquisa, projetos e planos de trabalho submetidos, currículo Lattes e sua pontuação, registros de acesso (data e IP) e da ciência destes termos. |
| **Avaliador(a) de projetos** | Nome, e-mail e o parecer emitido. |
| **Qualquer visitante** | Endereço IP, página acessada, data e hora, e a localização aproximada (cidade, estado e país) deduzida do IP, nos registros de segurança; cookie de sessão. |

## 3. Finalidades e bases legais

| Finalidade | Base legal (LGPD) |
|---|---|
| Submissão, avaliação, classificação e acompanhamento dos projetos dos editais | Execução de políticas públicas (art. 7º, III, e art. 23) |
| Indicação de discentes, pagamento e prestação de contas das bolsas, declarações e certificados | Cumprimento de obrigação legal ou regulatória e execução de políticas públicas (art. 7º, II e III) |
| Obtenção e pontuação do currículo Lattes junto ao CNPq | Execução de políticas públicas e uso compartilhado entre órgãos públicos (art. 7º, III, e art. 26) |
| Envio de convites e pareceres aos avaliadores | Execução de políticas públicas (art. 7º, III) |
| Segurança, prevenção a fraudes e auditoria de acessos | Cumprimento de obrigação legal (art. 7º, II), em atenção ao dever de segurança (art. 46) |

**O consentimento não é a base legal do tratamento.** A ciência destes termos, registrada após o login, apenas documenta que você foi informado(a). O tratamento necessário aos editais e às bolsas continua mesmo sem ela.

**Adolescentes:** nas modalidades de ensino médio (como o PIBIC-EM), os dados de discentes menores de 18 anos são tratados no seu melhor interesse (art. 14), só para as finalidades acima.

Não há decisões tomadas unicamente de forma automatizada. A pontuação Lattes é um dos critérios, e a classificação final segue o edital e é homologada pela PRPI.

## 4. Compartilhamento e operadores

Os dados não são vendidos nem usados para publicidade. Eles são compartilhados apenas com:

| Operador | Uso |
|---|---|
| **Amazon Web Services (EUA)** | Hospedagem do servidor, do banco de dados e dos arquivos; autenticação (Cognito); envio de e-mails (SQS/SES); funções de criptografia e de validação de arquivos. |
| **Cloudflare (rede global)** | Proteção do domínio: TLS, firewall de aplicação, bloqueio de bots e de ataques, e a verificação anti-robô (Turnstile) dos formulários públicos. Todo o tráfego passa por ela. |
| **CNPq (Brasil)** | Consulta do currículo Lattes a partir do CPF do(a) orientador(a). |
| **Sentry (EUA)** | Registro de erros da aplicação: a página e a descrição técnica do erro, sem IP, usuário, cookies nem dados pessoais, que são removidos ou mascarados antes do envio. |
| **Bibliotecas públicas (CDNs)** | Arquivos de estilo e de script (Tailwind, jsDelivr, cdnjs, Google APIs, jQuery, shields.io). Recebem apenas o IP e os dados do navegador ao carregar a página. |

Também pode haver compartilhamento com as agências de fomento das bolsas (CNPq e FUNCAP) e com os órgãos de controle, quando exigido pelas regras do edital ou por lei.

## 5. Transferência internacional

**5.1.** Os dados pessoais tratados pela Plataforma Yoko - Pesquisa são armazenados em servidores de computação em nuvem da **Amazon Web Services (AWS)**, localizados nos **Estados Unidos da América** (região us-east-2, Ohio). O uso é exclusivamente para a hospedagem, o processamento e a segurança da infraestrutura tecnológica do sistema. A Cloudflare (proteção do domínio) e o Sentry (registro de erros) também podem tratar dados fora do Brasil, nas finalidades descritas na seção 4.

**5.2.** Essa transferência internacional se fundamenta no **art. 33 da LGPD** (Lei nº 13.709/2018) e na regulamentação da Autoridade Nacional de Proteção de Dados (Resolução CD/ANPD nº 19/2024). Ela é amparada pelo **Adendo de Tratamento de Dados da AWS** (*AWS Data Processing Addendum*), que integra o contrato de serviço. A adoção das cláusulas-padrão contratuais aprovadas pela ANPD (art. 33, II, "b"), que devem ser usadas sem alteração, está em andamento (veja o quadro da seção 10).

**5.3.** A AWS mantém certificações internacionais de segurança da informação, como a ISO/IEC 27001 e os relatórios SOC 2. Na plataforma, os dados são protegidos por:

- criptografia em trânsito (TLS) em toda a comunicação entre o navegador e o servidor;
- criptografia em repouso do disco do servidor e dos arquivos enviados, com chaves gerenciadas pelo AWS KMS, e do banco de dados;
- criptografia própria dos campos pessoais mais sensíveis: CPF, RG, dados bancários, data de nascimento, telefone e endereço;
- acesso aos arquivos apenas por links temporários, gerados depois da verificação de permissão;
- permissões mínimas para o servidor e para as funções da AWS, e autenticação em duas etapas (MFA) para os usuários.

**5.4.** Ao registrar ciência destes termos, o usuário declara estar ciente do armazenamento dos dados em infraestrutura situada no exterior, nos limites e para as finalidades estritamente necessárias ao funcionamento da plataforma. Essa ciência não é consentimento e não é a base legal da transferência (seção 3).

## 6. Segurança

As medidas técnicas estão descritas na página **Segurança do sistema** (`/pesquisa/seguranca`) da plataforma. Em caso de incidente que possa causar risco ou dano relevante, a UFCA comunicará a ANPD e os titulares afetados, conforme o art. 48 da LGPD.

## 7. Por quanto tempo os dados são guardados

| Dado | Prazo |
|---|---|
| **Documentos e dados pessoais dos estudantes** | 6 anos após o término da bolsa (5 anos de guarda e 1 ano para a prestação de contas). Depois disso, os documentos enviados na indicação são eliminados e os dados pessoais são anonimizados. Ficam apenas o nome, o projeto e o período da bolsa, para as declarações e o histórico institucional. Nos registros do sistema anterior (bolsas encerradas até 2020), o CPF também é mantido, para a emissão das declarações. |
| **Projetos** | Pelo prazo exigido para a prestação de contas e para a guarda de documentos públicos. |
| **Registros de segurança (logs e registros de acesso)** | 2 anos. Os registros de acesso (data e IP de cada login) são apagados automaticamente depois de 2 anos. No dia 1º de cada mês, o registro do mês anterior é fechado, compactado e guardado com criptografia (AWS KMS) no armazenamento da AWS, com acesso restrito à equipe responsável pela plataforma. Depois de 2 anos, ele é apagado automaticamente. A cópia no servidor da aplicação é apagada depois de 90 dias. |
| **Links de acesso aos arquivos** | 60 segundos. Os links enviados aos avaliadores valem 30 dias e abrem apenas o projeto ou o plano de trabalho. |
| **Sessão** | Encerrada no logout ou depois de 1 hora de inatividade. |

## 8. Cookies

A plataforma usa apenas o cookie de sessão, estritamente necessário para manter o login, sem rastreamento nem publicidade. A verificação anti-robô (Cloudflare Turnstile) dos formulários públicos não usa cookies de rastreamento.

## 9. Seus direitos

Pelo art. 18 da LGPD, você pode pedir:
- confirmação de que seus dados são tratados;
- acesso aos dados;
- correção de dados incompletos, inexatos ou desatualizados;
- anonimização, bloqueio ou eliminação de dados desnecessários ou excessivos;
- portabilidade;
- informação sobre com quem os dados são compartilhados.

Dados necessários ao cumprimento de obrigação legal ou à prestação de contas das bolsas podem ser mantidos pelo prazo legal (art. 16).

A resposta é dada em até **15 dias**, enviada ao e-mail informado no pedido e disponível na consulta pelo protocolo. Para proteger seus dados, a PRPI pode pedir a confirmação da sua identidade antes de responder.

Na plataforma:
- **Meus dados** (`/pesquisa/meusDados`), para usuários, com download em JSON;
- **Fazer uma solicitação** (`/pesquisa/lgpd/solicitacao`);
- **Consultar solicitação** (`/pesquisa/lgpd/consulta`).

Você também pode apresentar reclamação à Autoridade Nacional de Proteção de Dados (ANPD).

## 10. Atendimento aos requisitos da LGPD

Situação atual de cada requisito na plataforma.

| Artigo | Requisito | Situação | Como é atendido |
|---|---|---|---|
| Art. 6º | Princípios (finalidade, necessidade, transparência) | ✅ Implementado | Coleta limitada ao que os editais exigem; esta política publica as finalidades; ferramenta de estatísticas do Google Analytics removida. |
| Art. 9º | Acesso facilitado às informações | ✅ Implementado | Política publicada na plataforma, com link no rodapé e avisos nos formulários de indicação, de submissão e de cadastro. |
| Art. 14 | Dados de adolescentes | ✅ Implementado | Tratamento no melhor interesse, restrito às finalidades do edital de ensino médio. |
| Arts. 15 e 16 | Término do tratamento e eliminação | ✅ Implementado | Documentos dos estudantes eliminados e dados pessoais anonimizados automaticamente 6 anos após o término da bolsa; logs e registros de acesso guardados por 2 anos e apagados automaticamente depois disso. |
| Arts. 18 e 19 | Direitos do titular e prazo de resposta | ✅ Implementado | "Meus dados" com download em JSON (portabilidade), formulário de solicitação com protocolo, consulta pelo protocolo, resposta por e-mail e controle do prazo de 15 dias. |
| Art. 33 | Transferência internacional | 🟡 Em andamento | Transferência informada nesta política e amparada pelo AWS Data Processing Addendum; adoção das cláusulas-padrão da ANPD com os operadores em andamento. |
| Art. 37 | Registro das operações de tratamento | 🟡 Em andamento | Inventário das operações de tratamento desta plataforma elaborado pela PRPI; inclusão no inventário de dados pessoais da UFCA a cargo do Encarregado. O rascunho está em [docs/lgpd/inventario.md](docs/lgpd/inventario.md). |
| Art. 38 | Relatório de impacto (RIPD) | 🟡 Em andamento | Em elaboração, pelos dados financeiros e de identidade dos discentes. |
| Art. 41 | Encarregado | 🟡 Em andamento | Pedidos recebidos pela PRPI e repassados ao Encarregado da UFCA. |
| Art. 46 | Segurança da informação | ✅ Implementado | TLS, WAF, MFA obrigatório, criptografia em repouso (disco do servidor e arquivos com AWS KMS, e banco de dados), criptografia própria de CPF, RG, dados bancários e contato, links temporários, permissões mínimas, verificação anti-robô (Turnstile) e limite de tentativas. |
| Art. 48 | Comunicação de incidentes | 🟡 Em andamento | Plano de resposta com comunicação à ANPD e aos titulares em elaboração. |

## 11. Alterações desta política

Quando houver mudança relevante, a versão será atualizada, e a ciência será pedida novamente no próximo login.

Versão atual: **1.0**, vigente desde 24/09/2026.
