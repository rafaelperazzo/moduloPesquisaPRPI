	2025-06-09 16:18:29 -0300	docs: Alguns links com o target = blank
	2025-06-09 16:16:03 -0300	docs: Incluída sessão de status do sistema no README
	2025-06-09 16:13:23 -0300	docs: GPL 3 no README
	2025-06-09 16:08:26 -0300	docs: Incluídos novos badges no readme separados por tipo
	2025-06-09 16:07:39 -0300	docs: Incluídos novos badges no readme
	2025-06-09 16:05:14 -0300	docs: Organizado badges do readme
	2025-06-09 15:58:35 -0300	fix: Incluídos badges do shield.io no README
	2025-06-09 15:55:21 -0300	docs: Incluídos badges do shield.io no README
	2025-06-09 14:50:05 -0300	docs: README atualizado em seus pre-requisitos
	2025-06-09 14:45:18 -0300	feat: Incluído recurso do betterstack no readme.md
	2025-06-09 14:25:37 -0300	fix: Removido titulo do projeto da declaração do avaliador.
	2025-06-09 10:43:05 -0300	docs: Atualizados comentários nos github actions e nos scripts de deploy e commit
	2025-06-09 10:38:09 -0300	fix: decorator login_required agora mostra mensagem em home em caso de erro de permissão. Corrigidos SQLi até antes de obterColuneUnica
	2025-06-08 17:12:40 -0300	fix: opções do sentry corrigidas para capturar o logging
	2025-06-08 16:27:33 -0300	fix: DSN do sentry incluído como um segredo do infisical
	2025-06-08 16:22:41 -0300	feat: Comecei a incluir o recurso de integração com o sentry
	2025-06-08 14:28:00 -0300	security: rota /cadastrarProjeto protegida e com consultas parametrizadas (não testado)
	2025-06-08 13:32:21 -0300	fix: permissões das rotas agora estão protegidas com o decorator login_required
	2025-06-08 12:35:45 -0300	feat: Página principal implementada
	2025-06-08 11:47:09 -0300	feat: Página principal implementada
	2025-06-08 10:19:53 -0300	style: modificado estilos dos logging de verify password
	2025-06-08 09:56:33 -0300	fix: decorator login_required solicita também um role de usuário
	2025-06-08 09:31:48 -0300	feat: Implementado decorator login_required
	2025-06-07 13:33:57 -0300	doc: Removidos TODOs resolvidos
	2025-06-07 13:29:15 -0300	fix: protegida rota /estatisticas e incluída variável de ambiente DEFAULT_EMAIL no docker-compose.yml
	2025-06-07 13:22:21 -0300	fix: protegidas rotas de inserção de avaliadores para projetos
	2025-06-07 13:17:11 -0300	fix: Corrigidos SQLi até a rota /inserirAvaliador (não testado)
	2025-06-06 15:45:44 -0300	fix: Rota /avaliar com consultas parametrizadas
	2025-06-06 15:18:12 -0300	fix: Removido render_template da rota /testes
	2025-06-06 15:14:59 -0300	fix: atualizar2 implementada e corrigida
	2025-06-06 10:48:22 -0300	fix: adicionada verificação da entrada do usuário até a rota /avaliacao
	2025-06-06 10:07:43 -0300	fix: verify_password evita sql injection
	2025-06-05 16:02:38 -0300	fix: gitignore inclui .vscode
	2025-06-05 15:46:53 -0300	docs: TODO atualizado para criptografia da tabela users
	2025-06-05 15:40:38 -0300	style: Ajustes na identação da função id_generator
	2025-06-05 15:39:04 -0300	docs: TODO atualizado para remover email NAO-RESPONDA
	2025-06-05 15:34:21 -0300	style: corrigida identação da rota minhaDeclaração
	2025-06-05 15:26:43 -0300	style: Inluído arquivo de TODO e iniciada a modificação das sugestões do lint para python3
	2025-06-05 15:04:30 -0300	fix: Email padrão da pesquisa agora é  recuperado dos segredos do infisical
	2025-06-05 10:54:53 -0300	fix: cron do actions frequencia agora funciona a cada 5 dias
	2025-06-05 10:30:54 -0300	fix: Script merge aogra faz o merge do master com o python3
	2025-06-05 10:21:23 -0300	fix: Nomes das actions corrigidas (avaliacao e frequencia - estavam como backup)
	2025-06-05 10:06:00 -0300	fix: Corrigido formulário de avaliação de projeto(abre o projeto em nova janela) e e-mail de solicitação de frequência (removida a senha)
	2025-06-02 10:43:00 -0300	fix: Solicitação de envio de frequência agora não envia senha por e-mail.
	2025-05-30 15:46:26 -0300	fix: Rota efetivarIndicação agora criptografa os campos telefone, endereço e RG, e enviar confirmação com thread.
	2025-05-30 15:23:46 -0300	fix: script para criptografar dados da tabela indicacoes
	2025-05-30 10:42:41 -0300	feat: Gerado vetor iv para criptografia dos dados dos indicados.
	2025-05-30 10:20:49 -0300	fix: cron.avaliacao.sh agora depende do infisical
	2025-05-30 10:16:44 -0300	chore: Rota argon2 protegida para admin
	2025-05-30 10:10:26 -0300	feat: Adicionado recurso para cadastrar todos os usuários ainda não cadastrados.
	2025-05-29 16:44:27 -0300	fix: Senha do login limitada a 64 caracteres para evitar ataques DoS
	2025-05-29 16:03:08 -0300	docs: Adicionado TODO para criação dos usuários ainda não cadastrados
	2025-05-29 16:01:09 -0300	docs: Adicionado log no ambiente de testes que confirma o envio do email
	2025-05-29 15:59:23 -0300	docs: Adicionada novo recurso para cadastro de usuário. Não testado ainda.
	2025-05-29 15:56:34 -0300	feat: Adicionada novo recurso para cadastro de usuário. Não testado ainda.
	2025-05-29 15:22:54 -0300	fix: Envio de nova senha como uma thread
	2025-05-29 14:53:18 -0300	fix: Corrigida verificação de senha para checar hash argon2id
	2025-05-29 11:02:31 -0300	fix: Iniciada transição para senhas em argon2
	2025-05-28 17:39:11 -0300	feat: iniciada funcionalidade para migração de senhas para argon2
	2025-05-28 15:27:20 -0300	fix: Liberadas avaliações de membros internos.
	2025-05-22 09:17:24 -0300	fix: update.yml comando docker estava errado -> o certo é docker-compose e não docker compose
	2025-05-22 09:06:47 -0300	fix: rota declaraçãoAvaliador estava com redirect errado.
	2025-05-04 10:17:35 -0300	docs: Incluída primeira versão do README completo
	2025-05-03 22:36:38 -0300	docs: Readme reiniciado...
	2025-05-03 13:21:16 -0300	chore: modificado horário da action backup para as 03:45 (UTC), 7:45 da manhã
	2025-05-03 13:15:45 -0300	fix: script backup.mysql está corrigido para RCLONE
	2025-05-03 09:36:28 -0300	fix: atualizar.db agora está criptografado
	2025-05-03 08:40:58 -0300	fix: gitignore agora ignora os .gpg
	2025-05-02 11:12:32 -0300	chore: atualizado atualizar_db para dodar o workflow do actions (backup.mysql.sh)
	2025-05-02 11:03:21 -0300	feat: backup do BD agendado para cada 6 horas
	2025-05-02 10:55:00 -0300	fix: action backup - corrigido trigger
	2025-05-02 10:52:56 -0300	fix: action backup - removido push
	2025-05-02 10:49:53 -0300	fix: action backup
	2025-05-02 10:41:18 -0300	feat: action Backup mysql
	2025-05-02 09:18:01 -0300	fix: reiniciar.sh.run limpa o bash_history apos execução
	2025-05-02 08:50:12 -0300	fix: actions - clear bash_history
	2025-05-02 08:47:02 -0300	chore: docker-compose modificado para criptografar mariadb
	2025-04-30 14:15:32 -0300	fix: Corrigida criptografia dos arquivos das submissões.
	2025-04-29 13:23:36 -0300	chore: removidos arquivos desnecessários da pasta documentos
	2025-04-29 10:56:37 -0300	fix: avaliação de projeto agora envia e-mail com o link da declaração.
	2025-04-29 09:05:48 -0300	fix: links dos projetos para os avaliadores estavam incorretos!
	2025-04-28 15:34:29 -0300	chore: WSDL do Cnpq incluido do repositorio
	2025-04-28 14:59:59 -0300	feat: Adicionada rota /version
	2025-04-28 14:44:30 -0300	chore: incluído arquivo exemplo para recuperar os segredos do infisical
	2025-04-25 15:06:44 -0300	feat: Adicionada versão na rota /admin
	2025-04-25 14:16:32 -0300	fix: editalProjeto com o plano 3
	2025-04-25 09:39:46 -0300	chore: Incluída consultas para criptografar colunas da tabela indicações, assim como como fazer o select
	2025-04-23 15:50:41 -0300	feat: Criptografa arquivos pessoais dos indicados no momento da indicação
	2025-04-23 15:10:52 -0300	chore: Incluída funcionalidade de criptografia dos documentos pessoais dos bolsistas ew docker-compose agora utiliza uma imagem personalizada
	2025-04-21 16:20:13 -0300	feat: Gitpython incluído nos requirements
	2025-04-21 15:02:54 -0300	fix: requirements.txt atualizado e corrigido
	2025-04-21 14:55:57 -0300	fix: docker compose do autoheal
	2025-04-21 11:42:40 -0300	fix: Numero siape conferido se é numérico
	2025-04-21 10:54:06 -0300	feat: docker compose com healthcheck
	2025-04-21 10:16:47 -0300	feat: Incluído healthcheck no compose
	2025-04-21 09:57:23 -0300	chore: apagando arquivos desnecessários
	2025-04-20 22:39:49 -0300	fix: qualis.sqlite3
	2025-04-20 22:24:13 -0300	fix: salvarCV - id
	2025-04-20 22:15:29 -0300	fix: pull do actions
	2025-04-20 22:12:03 -0300	fix: mensagem de log do /score
	2025-04-20 22:07:37 -0300	fix: Logging da thread de processarPontuaçãoLattes
	2025-04-20 19:00:15 -0300	chore: Github actions agora atualiza o sistema a cada nova tag
	2025-04-20 18:57:20 -0300	fix: Corrigido scorelattes para consultar periodicos em base sqlite no lugar do csv, para deixar o processamento mais rápido! (modules)
	2025-04-20 18:56:39 -0300	fix: Corrigido scorelattes para consultar periodicos em base sqlite no lugar do csv, para deixar o processamento mais rápido!
	2025-04-18 09:21:23 -0300	feat: Convertida tabela qualis para sqlite
	2025-04-17 10:45:24 -0300	fix: gitignore no gpg e pdf das submissoes
	2025-04-16 14:25:38 -0300	fix: corrigido login.required de indicacoes
	2025-04-16 14:21:13 -0300	fix: Proteção na rota /indicacoes e carregamento da chave aes
	2025-04-15 15:15:17 -0300	tests: Ajustados o setup dos testes submissão
	2025-04-15 13:12:34 -0300	fix: removida acentuação do qualis.csv
	2025-04-15 10:30:12 -0300	fix: carregamento do scorelattes
	2025-04-14 15:49:55 -0300	fix: adicionada pasta pdfs
	2025-04-14 14:10:00 -0300	fix: typo no Dockerfile
	2025-04-14 14:05:13 -0300	fix: Removendo aspas do grupo de pesquisa
	2025-04-11 11:48:54 -0300	fix: Incluido o scorelattes.html como rota
	2025-04-11 10:51:00 -0300	fix: Scorelattes testa se o arquivo do curriculo foi obtido com sucesso. Email é enviado independentemente.
	2025-04-11 10:11:33 -0300	fix: scorelattes.html virou rota
	2025-04-11 09:55:58 -0300	fix: scorelattes funcionando
	2025-04-10 20:20:20 -0300	fix: Dockerfile personalizado para permitir acessar a api do cnpq
	2025-04-10 13:56:46 -0300	fix: rule do docker-compose
	2025-04-10 11:33:48 -0300	fix: nome do router corrigido para pesquisa
	2025-04-10 11:16:57 -0300	docs: Atualizado README
	2025-04-10 11:13:33 -0300	fix: cron.frequencia atualizado
	2025-04-10 11:09:33 -0300	feat: Adicionado script de backup do mariadb
	2025-04-10 10:54:52 -0300	fix: Corrigido o atualizar_db.sh.sample
	2025-04-10 10:30:16 -0300	fix: cadastrarAvaliador: Impedido incluir os mesmos avaliadores para o mesmo projeto
	2025-04-09 19:16:00 -0300	fix: Modificado nome dos serviços no docker compose
	2025-04-09 19:10:20 -0300	fix: corrigido os testes para simular diferentes formas de incluir avaliadores
	2025-04-09 19:05:16 -0300	fix: cadastrarProjeto sem avaliadores, com string vazia
	2025-04-09 18:56:11 -0300	fix: a submissão agora aceita sem avaliadores
	2025-04-09 16:35:54 -0300	fix: Correção geral
	2025-04-09 15:01:44 -0300	fix: removida pasta home
	2025-04-09 15:00:12 -0300	fix: REORGANIZAÇÃO GERAL DO PROJETO
	2025-04-08 18:25:52 -0300	fix: docker-compose ajustado
	2025-04-08 17:24:53 -0300	fix: incluido docker-compose no gitignore
	2025-04-08 17:22:33 -0300	fix: Docker compose com servies alterados
	2025-04-08 17:15:27 -0300	feat: incluido arquivo do actions
	2025-04-08 17:06:47 -0300	fix: o prefixo agora é uma env var
	2025-04-08 16:32:37 -0300	fix: Corrigido o atualizar_db.sh
	2025-04-08 16:28:44 -0300	fix: incluída a env AES_KEY no .env
	2025-04-08 16:25:49 -0300	fix: removida obrigatoriedade de indicar avaliadores dos projetos
	2025-04-08 16:17:35 -0300	fix: Adicionada proteção de CSRF nos forms
	2025-04-08 15:57:05 -0300	fix: editalProjeto - removida linha de log
	2025-04-08 15:48:07 -0300	new: Migrando para Python 3
	2025-03-24 08:53:29 -0300	fix: /cadastrarProjeto - Corrigido INSERT
	2025-03-21 09:55:40 -0300	feat: inseridos novos campos no formulário de cadastrar projeto: justificativa PIBITI e arquivo_plano3
	2025-03-21 08:55:47 -0300	fix: versão do matplotlib corrigida
	2024-09-13 13:26:00 -0300	feat: Incluído o impedimento da indicação de um discente que já está em outro projeto.
	2024-09-13 10:58:05 -0300	fix: rota auditoria_indicacoes protegida
	2024-09-13 10:38:13 -0300	fix: ajustado a rota de auditoria_indicacoes
	2024-09-12 15:05:26 -0300	feat: inicio da implementação da rota /auditoria_indicacoes para identificar indicações em mais de um projeto em um mesmo ano
	2024-09-11 10:54:45 -0300	fix: incluida a data na api indicacao
	2024-09-11 09:29:07 -0300	fix: adicionado CORS na api indicacao
	2024-09-11 09:11:07 -0300	chore: incluída api para obtenção de dados de um indicado a partir do cpf
	2024-09-10 15:53:49 -0300	chore: api de cpf para dados do indicado
	2024-09-03 15:14:23 -0300	fix: ajustado prazo para envio das frequencias para 90 dias apos o termino
	2024-08-23 16:14:08 -0300	fix: Distribuição de bolsas com mensagem de concessão parcial
	2024-08-23 13:59:33 -0300	fix: rota resultados
	2024-07-01 09:25:17 -0300	chore: adicionado teste da rota /meusPareceres
	2024-07-01 09:09:47 -0300	fix: Consulta nos /meusPareceres estava com uma coluna ambigua: inovacao
	2024-06-12 09:17:18 -0300	fix: try-except nos meus pareceres
	2024-05-03 14:35:10 -0300	fix: rota meusPareceres com campo de inovação para projetos pibiti
	2024-05-03 14:07:48 -0300	fix: Removidos gráficos da rota editalProjeto
	2024-05-03 13:52:23 -0300	fix: Ajustado test da rota editalProjeto com timeout de 15s
	2024-05-03 13:35:46 -0300	fix: Removida a opção (não sei responder) do formulário de avaliação pibiti
	2024-05-03 13:16:13 -0300	fix: Calculo da Licença maternidade funcionando corretamente - 2 anos para cada licença nos últimos 5 anos.
	2024-05-03 10:52:46 -0300	feat: Considerar licença maternidade na pontuação do lattes
	2024-05-02 09:52:13 -0300	fix: Corrigido texto do formulário de avaliação de projetos
	2024-05-02 09:17:31 -0300	fix: removida mensagem de log para registrar a modalidade do projeto
	2024-04-30 16:01:15 -0300	feat: formulários de avaliação pibiti agora tem opção para o avaliador dizer se o projeto tem potencial de inovação
	2024-04-30 14:03:48 -0300	fix: /editalProjeto demanda foi apagada acidentalmente
	2024-04-30 13:34:05 -0300	fix: corrigido problema do editalProjeto que so mostrava projetos com algum avaliador atribuido
	2024-04-26 11:01:02 -0300	fix: unicode error em enviar_frequencia
	2024-04-25 12:57:51 -0300	fix: unicode error no lembrete de frequencia
	2024-04-22 14:37:16 -0300	fix: ajustado texto da declaração do orientador
	2024-04-16 15:33:33 -0300	fix: adicionado <br> no scorelattes
	2024-04-16 15:21:25 -0300	fix: incluido período no score lattes static
	2023-12-21 07:31:00 -0300	refactor: Colunas da API em UPPERcase
	2023-12-20 09:07:43 -0300	feat: Adicionados projetos anteriores a 2019 na API
	2023-12-08 13:56:29 -0300	test: Incluído teste de resposta da rota editalProjeto
	2023-12-08 08:55:25 -0300	test: Incluído arquivo inicial de testes
	2023-12-07 15:29:34 -0300	fix: corrigida consulta da rota get_bib
	2023-11-29 15:03:59 -0300	feat: Extração de dados de projetos de pesquisa a partir de uma lista de siapes
	2023-11-29 10:27:53 -0300	chore: Script de atualizar_db funcionando
	2023-11-28 15:38:58 -0300	chore: script de cicd atualizado
	2023-11-28 15:32:52 -0300	1.2.5 Merge branch 'develop'
	2023-11-28 15:32:16 -0300	chore: modificado scripts cicd e commit para ajustes ao projeto
	2023-11-28 15:10:59 -0300	1.2.4 Merge branch 'develop'
	2023-11-28 15:10:39 -0300	fix: corrigido where da cobrança de frequência para não incluir indicações com menos de 1 mês de atividades
	2023-11-09 16:09:06 -0300	chore: Adicionar scripts de cicd e commit
	2023-11-08 08:50:50 -0300	1.2.3 Merge branch 'develop'
	2023-11-08 08:50:28 -0300	Corrigidos problemas no lembrete de frequencia
	2023-10-06 16:15:41 -0300	1.2.2 Merge branch 'develop'
	2023-10-06 16:15:18 -0300	email de lembrete de frequência corrigido!
	2023-10-05 14:33:17 -0300	1.2.1 Merge branch 'develop'
	2023-10-05 14:33:03 -0300	listaNegra enviando emails corretamente
	2023-10-05 14:04:04 -0300	1.2.0 Merge branch 'develop'
	2023-10-05 14:03:48 -0300	ajustes
	2023-10-05 14:02:59 -0300	1.1.9 Merge branch 'develop'
	2023-10-05 14:02:37 -0300	corrigida rota listaNegra
	2023-10-05 14:00:44 -0300	atualizado o gitignore
	2023-10-05 13:33:01 -0300	1.1.8 Merge branch 'develop'
	2023-10-05 13:32:41 -0300	enviar email com thread na rota listaNegra
	2023-10-05 11:31:06 -0300	1.1.7 Merge branch 'develop'
	2023-10-05 11:28:44 -0300	ajustada rota listaNegra
	2023-10-03 16:08:39 -0300	1.1.6 Merge branch 'develop'
	2023-10-03 16:08:20 -0300	frequencias - lembretes
	2023-10-03 16:00:00 -0300	email de frequencia modificado
	2023-10-03 15:18:30 -0300	1.1.5 Merge branch 'develop'
	2023-10-03 15:18:11 -0300	atualizado o registro de acessos
	2023-10-03 15:13:13 -0300	modificado o registro de acessos
	2023-09-19 13:50:27 -0300	1.1.4 Merge branch 'develop'
	2023-09-19 13:50:05 -0300	assinaturas de clarice e claudener
	2023-08-15 11:34:10 -0300	1.1.3 Merge branch 'develop'
	2023-08-15 11:30:12 -0300	assinaturas atualizadas
	2023-04-28 14:59:24 -0300	1.1.2 Merge branch 'develop'
	2023-04-28 14:59:09 -0300	Validacao do CPF
	2023-04-20 09:10:20 -0300	1.1.1 Merge branch 'develop'
	2023-04-20 09:09:55 -0300	Corrigido scorerun para varias formacoes academicas
	2023-04-03 14:45:35 -0300	1.1.0 Merge branch 'develop'
	2023-04-03 14:45:17 -0300	corrigido pontuação de a3 e a4
	2023-04-03 14:20:58 -0300	1.0.9 Merge branch 'develop'
	2023-04-03 14:20:44 -0300	qualis 2017 - barema
	2023-04-03 14:00:14 -0300	1.0.8 Merge branch 'develop'
	2023-04-03 13:59:31 -0300	atualizado para qualis 2017
	2023-03-31 15:49:46 -0300	1.0.7 Merge branch 'develop'
	2023-03-31 15:49:26 -0300	incluido campo de inovação
	2023-03-14 14:30:14 -0300	1.0.6 Merge branch 'develop'
	2023-03-14 14:30:11 -0300	ajustada data na declaração
	2023-03-14 14:27:30 -0300	1.0.5 Merge branch 'develop'
	2023-03-14 14:27:05 -0300	ajustada data na declaração
	2022-11-29 14:42:15 -0300	1.0.4 Merge branch 'develop'
	2022-11-29 14:41:55 -0300	Ajustado inicio da indicacao
	2022-10-07 10:50:53 -0300	1.0.3 Merge branch 'develop'
	2022-10-07 10:50:33 -0300	incluída coluna fomento na lista de indicações
	2022-09-09 14:57:40 -0300	1.0.2 Merge branch 'develop'
	2022-09-09 14:57:25 -0300	Corrigido bug do /score
	2022-09-09 14:23:03 -0300	1.0.1 Merge branch 'develop'
	2022-09-09 14:22:41 -0300	try-except nos envios de e-mail
	2022-08-23 15:53:11 -0300	1.0.1 Merge branch 'develop'
	2022-08-23 15:52:43 -0300	Incluída modalidade AF em meusProjetos
	2022-08-04 10:48:53 -0300	1.0.0 Merge branch 'develop'
	2022-08-04 10:48:17 -0300	Possibilidade de envio da frequencia até 30 dias após o termino da bolsa
	2022-08-04 10:20:23 -0300	0.9.9 Merge branch 'develop'
	2022-08-04 10:20:03 -0300	Ajustes finais antes da versão
	2022-07-14 10:36:12 -0300	Incluído formulário de motivos de substituição
	2022-07-13 15:32:50 -0300	Justificativa de desligamento no README
	2022-07-13 15:31:11 -0300	Implementação do motivo do desligamento
	2022-07-08 16:24:22 -0300	Bootstrap em algumas páginas
	2022-07-07 15:42:30 -0300	Correção da declaração do orientador
	2022-06-24 10:47:05 -0300	Pronto para producao
	2022-06-23 15:17:54 -0300	E-mail com cobrança de frequencias ajustado
	2022-06-23 14:57:00 -0300	Cobrança de frequencia reativada
	2022-06-23 14:22:54 -0300	Remoção de imports desnecessários
	2022-06-23 10:22:12 -0300	Corrigidas algumas identações
	2022-06-23 10:09:51 -0300	Preparando para gerar qrcodes
	2022-06-23 09:54:08 -0300	Incluido arquivo license
	2022-06-23 09:35:06 -0300	Ajustada página pública do scorelattes
	2022-06-23 09:32:09 -0300	Calculo do scorelattes separado foi modificado
	2022-06-23 09:17:36 -0300	0.9.8 Merge branch 'develop'
	2022-06-23 09:17:12 -0300	Curriculo xml baixado automaticamente
	2022-06-22 11:18:28 -0300	0.9.7 Merge branch 'develop'
	2022-06-22 11:18:11 -0300	Corrigido Dockerfile
	2022-06-22 11:05:23 -0300	0.9.6 Merge branch 'develop'
	2022-06-22 11:05:06 -0300	Corrigido captcha
	2022-06-22 09:47:26 -0300	0.9.5 Merge branch 'develop'
	2022-06-22 09:47:12 -0300	Removidos pyc
	2022-06-22 09:38:03 -0300	0.9.3 Merge branch 'develop'
	2022-06-22 09:37:36 -0300	Ajustado envio de e-mail para avaliadores
	2022-06-20 16:29:51 -0300	Adicionado schema do banco de dados
	2022-06-20 16:26:28 -0300	Incluído sample do docker-compose
	2022-06-20 11:13:46 -0300	Merge branch 'develop' 0.9.2
	2022-06-20 11:13:33 -0300	Envio de e-mail para consultores OK
	2022-06-20 10:12:17 -0300	Incluída função para envio imediato ao avaliador
	2022-06-20 07:18:44 -0300	Incluido script merge
	2022-06-17 10:43:34 -0300	Primeiro commit - develop
	2022-06-17 10:40:25 -0300	Merge branch 'master' of github.com:rafaelperazzo/moduloPesquisaPRPI
	2022-06-17 10:40:00 -0300	Adicionado configparser
	2022-06-17 10:37:40 -0300	Certificado 2018 corrigido
	2022-06-17 10:30:25 -0300	Incluido configparser
	2022-06-15 15:29:18 -0300	correção do certificado 2018
	2022-06-15 08:37:59 -0300	Organizado gitignore
	2022-06-15 08:04:28 -0300	15/06/2022 - 08:04
	2022-06-15 08:03:50 -0300	15/06/2022
	2022-06-13 16:52:39 -0300	Certificados 2018 pronto
	2022-06-13 15:39:14 -0300	ajustado requirements
	2022-06-13 15:38:11 -0300	requirements.txt
	2022-06-13 15:33:53 -0300	Iniciando certificados antes de 2018
	2022-06-10 08:28:19 -0300	Adicionado certificado discente
	2022-04-27 14:34:51 -0300	Segundo commit...
	2022-04-27 14:33:53 -0300	Segundo commit...
	2022-04-27 14:26:49 -0300	Primeiro commit