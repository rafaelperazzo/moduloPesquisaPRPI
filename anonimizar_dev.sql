-- Anonimiza a cópia LOCAL do banco de produção (LGPD: dados reais de discentes fora da produção).
-- Chamado pelo atualizar_db.sh depois de restaurar o backup, nos bancos `pesquisa` e `pesquisa_test`
-- do container de desenvolvimento. NUNCA rodar em produção.
--
-- O que faz:
--   * procura, em todas as tabelas (não views), as colunas com nomes de dados sensíveis (CPF, RG,
--     dados bancários, telefone, endereço, nascimento), inclusive com os prefixos estudante_/orientador_
--     e no_ (ex.: estudante_no_conta_corrente, orientador_cpf, da tabela legada cadastro_geral);
--   * CPF vira um pseudônimo de 11 dígitos: o mesmo CPF gera o mesmo pseudônimo em todas as tabelas
--     (joins e checagem de duplicidade continuam funcionando), com um sal aleatório descartado no fim;
--   * as demais colunas viram 'ANONIMIZADO' (texto), 2000-01-01 (data) ou 0 (número);
--   * e-mail dos discentes, IPs dos acessos e solicitações LGPD também são trocados;
--   * no fim, lista colunas com nomes suspeitos que NÃO foram tratadas, para revisão.

SET @sal = SHA2(CONCAT(RAND(), NOW(6), UUID()), 256);

DROP PROCEDURE IF EXISTS anonimizar_dev;
DELIMITER //
CREATE PROCEDURE anonimizar_dev()
BEGIN
  DECLARE fim INT DEFAULT 0;
  DECLARE v_tabela, v_coluna, v_tipo VARCHAR(64);
  DECLARE v_tam BIGINT;
  DECLARE cur CURSOR FOR
    SELECT c.TABLE_NAME, c.COLUMN_NAME, c.DATA_TYPE, c.CHARACTER_MAXIMUM_LENGTH
    FROM information_schema.COLUMNS c
    JOIN information_schema.TABLES t
      ON t.TABLE_SCHEMA = c.TABLE_SCHEMA AND t.TABLE_NAME = c.TABLE_NAME AND t.TABLE_TYPE = 'BASE TABLE'
    WHERE c.TABLE_SCHEMA = DATABASE()
      AND LOWER(c.COLUMN_NAME) REGEXP '^(estudante_|orientador_)?(no_)?(cpf|cpf_corrigido|rg|orgao_emissor|nome_banco|banco|agencia|conta|conta_corrente|telefone|celular|endereco|nascimento|data_nascimento)$';
  DECLARE CONTINUE HANDLER FOR NOT FOUND SET fim = 1;

  CREATE OR REPLACE TEMPORARY TABLE anonimizacao_relatorio (tabela VARCHAR(64), coluna VARCHAR(64), linhas BIGINT);

  OPEN cur;
  laco: LOOP
    FETCH cur INTO v_tabela, v_coluna, v_tipo, v_tam;
    IF fim THEN LEAVE laco; END IF;
    SET @col = CONCAT('`', v_coluna, '`');
    -- só os dígitos: o mesmo CPF com ou sem pontuação vira o mesmo pseudônimo em todas as tabelas.
    -- Coluna `cpf` já cifrada (migracao.cripto_cpf.md): a origem é o cpf_hash, que é igual para o mesmo CPF
    -- em qualquer tabela (o texto cifrado muda com o iv de cada linha)
    SET @origem = CONCAT('REGEXP_REPLACE(', @col, ', ''[^0-9]'', '''')');
    IF LOWER(v_coluna) = 'cpf' AND EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE()
                                           AND TABLE_NAME = v_tabela AND COLUMN_NAME = 'cpf_hash') THEN
      SET @origem = CONCAT('COALESCE(cpf_hash, ', @origem, ')');
    END IF;
    SET @pseudonimo = CONCAT('CONV(LEFT(SHA2(CONCAT(@sal, ', @origem, '), 256), 12), 16, 10) MOD 100000000000');
    SET @valor = CASE
      WHEN v_tipo IN ('date', 'datetime', 'timestamp') THEN '''2000-01-01'''
      WHEN v_tipo IN ('int', 'bigint', 'smallint', 'mediumint', 'tinyint', 'decimal', 'float', 'double') THEN
        IF(LOWER(v_coluna) LIKE '%cpf%', @pseudonimo, '0')
      WHEN LOWER(v_coluna) LIKE '%cpf%' THEN CONCAT('LEFT(LPAD(', @pseudonimo, ', 11, ''0''), ', IFNULL(v_tam, 11), ')')
      ELSE CONCAT('LEFT(''ANONIMIZADO'', ', IFNULL(v_tam, 11), ')')
    END;
    SET @filtro = IF(v_tipo IN ('char', 'varchar', 'text', 'tinytext', 'mediumtext', 'longtext'),
                     CONCAT(@col, ' IS NOT NULL AND ', @col, ' <> '''''),
                     CONCAT(@col, ' IS NOT NULL'));
    SET @sql = CONCAT('UPDATE `', v_tabela, '` SET ', @col, ' = ', @valor, ' WHERE ', @filtro);
    PREPARE s FROM @sql;
    EXECUTE s;
    INSERT INTO anonimizacao_relatorio VALUES (v_tabela, v_coluna, ROW_COUNT());
    DEALLOCATE PREPARE s;
  END LOOP;
  CLOSE cur;

  -- cpf_hash (migracao.cripto_cpf.md): NULL faz o app ler as colunas acima como texto (caminho de transição),
  -- já que em dev elas viraram pseudônimos/ANONIMIZADO, e não texto cifrado
  SET fim = 0;
  BEGIN
    DECLARE v_t VARCHAR(64);
    DECLARE fim_hash INT DEFAULT 0;
    DECLARE cur_hash CURSOR FOR
      SELECT c.TABLE_NAME FROM information_schema.COLUMNS c
      JOIN information_schema.TABLES t
        ON t.TABLE_SCHEMA = c.TABLE_SCHEMA AND t.TABLE_NAME = c.TABLE_NAME AND t.TABLE_TYPE = 'BASE TABLE'
      WHERE c.TABLE_SCHEMA = DATABASE() AND c.COLUMN_NAME = 'cpf_hash';
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET fim_hash = 1;
    OPEN cur_hash;
    laco_hash: LOOP
      FETCH cur_hash INTO v_t;
      IF fim_hash THEN LEAVE laco_hash; END IF;
      SET @sql = CONCAT('UPDATE `', v_t, '` SET cpf_hash = NULL');
      PREPARE s FROM @sql;
      EXECUTE s;
      INSERT INTO anonimizacao_relatorio VALUES (v_t, 'cpf_hash (NULL)', ROW_COUNT());
      DEALLOCATE PREPARE s;
    END LOOP;
    CLOSE cur_hash;
  END;

  -- Colunas conhecidas que não entram no padrão acima (só se a tabela/coluna existir nesta cópia)
  IF EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'indicacoes' AND COLUMN_NAME = 'email') THEN
    UPDATE indicacoes SET email = CONCAT('discente', id, '@exemplo.invalid') WHERE email IS NOT NULL AND email <> '';
    INSERT INTO anonimizacao_relatorio VALUES ('indicacoes', 'email', ROW_COUNT());
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'alunos' AND COLUMN_NAME = 'email') THEN
    UPDATE alunos SET email = CONCAT('aluno', id, '@exemplo.invalid') WHERE email IS NOT NULL AND email <> '';
    INSERT INTO anonimizacao_relatorio VALUES ('alunos', 'email', ROW_COUNT());
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cadastro_geral' AND COLUMN_NAME = 'e-mail') THEN
    UPDATE cadastro_geral SET `e-mail` = CONCAT('discente', id, '@exemplo.invalid') WHERE `e-mail` IS NOT NULL AND `e-mail` <> '';
    INSERT INTO anonimizacao_relatorio VALUES ('cadastro_geral', 'e-mail', ROW_COUNT());
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'acessos' AND COLUMN_NAME = 'ip') THEN
    UPDATE acessos SET ip = '0.0.0.0';
    INSERT INTO anonimizacao_relatorio VALUES ('acessos', 'ip', ROW_COUNT());
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'lgpd_solicitacoes') THEN
    UPDATE lgpd_solicitacoes SET nome = 'ANONIMIZADO', email = CONCAT('titular', id, '@exemplo.invalid'),
      descricao = 'ANONIMIZADO', resposta = IF(resposta IS NULL, NULL, 'ANONIMIZADO');
    INSERT INTO anonimizacao_relatorio VALUES ('lgpd_solicitacoes', 'nome, email, descricao, resposta', ROW_COUNT());
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'lgpd_aceites') THEN
    UPDATE lgpd_aceites SET ip = '0.0.0.0';
    INSERT INTO anonimizacao_relatorio VALUES ('lgpd_aceites', 'ip', ROW_COUNT());
  END IF;

  SELECT tabela, coluna, linhas AS linhas_anonimizadas FROM anonimizacao_relatorio ORDER BY tabela, coluna;

  -- Revisão: nomes que parecem sensíveis e ficaram de fora (tratar aqui se forem dados pessoais)
  SELECT c.TABLE_NAME AS tabela, c.COLUMN_NAME AS coluna_para_revisar
  FROM information_schema.COLUMNS c
  JOIN information_schema.TABLES t
    ON t.TABLE_SCHEMA = c.TABLE_SCHEMA AND t.TABLE_NAME = c.TABLE_NAME AND t.TABLE_TYPE = 'BASE TABLE'
  WHERE c.TABLE_SCHEMA = DATABASE()
    AND LOWER(c.COLUMN_NAME) REGEXP 'cpf|banc|conta|agenc|fone|celul|endere|nasc|pix|^rg|_rg$'
    AND LOWER(c.COLUMN_NAME) NOT LIKE 'arquivo%'
    AND LOWER(c.COLUMN_NAME) <> 'cpf_hash'
    AND NOT LOWER(c.COLUMN_NAME) REGEXP '^(estudante_|orientador_)?(no_)?(cpf|cpf_corrigido|rg|orgao_emissor|nome_banco|banco|agencia|conta|conta_corrente|telefone|celular|endereco|nascimento|data_nascimento)$'
  ORDER BY 1, 2;
END //
DELIMITER ;

CALL anonimizar_dev();
DROP PROCEDURE anonimizar_dev;
SET @sal = NULL;
