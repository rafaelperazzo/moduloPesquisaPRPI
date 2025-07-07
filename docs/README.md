# 🎓 Módulo de Pesquisa

[![Better Stack Badge](https://uptime.betterstack.com/status-badges/v1/monitor/1z0ga.svg)](https://yoko.betteruptime.com/pt)
![GitHub last commit (branch)](https://img.shields.io/github/last-commit/rafaelperazzo/moduloPesquisaPRPI/python3)
![GitHub Tag](https://img.shields.io/github/v/tag/rafaelperazzo/moduloPesquisaPRPI)
![GitHub Pipenv locked Python version (branch)](https://img.shields.io/github/pipenv/locked/python-version/rafaelperazzo/moduloPesquisaPRPI/python3?label=Python)
![GitHub Pipenv locked dependency version (branch)](https://img.shields.io/github/pipenv/locked/dependency-version/rafaelperazzo/moduloPesquisaPRPI/flask/python3)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/rafaelperazzo/moduloPesquisaPRPI/update.yml?label=Update)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/rafaelperazzo/moduloPesquisaPRPI/backup.yml?label=Backup)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/rafaelperazzo/moduloPesquisaPRPI/frequencia.yml?label=Frequ%C3%AAncia)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/rafaelperazzo/moduloPesquisaPRPI/avaliacao.yml?label=Avalia%C3%A7%C3%A3o)

![Debian](https://img.shields.io/badge/Debian-D70A53?style=for-the-badge&logo=debian&logoColor=white)
![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white)

Sistema web desenvolvido para auxiliar no gerenciamento e acompanhamento de projetos de pesquisa de instituição de ensino superior.

---

## Quem utiliza?

- **Universidade Federal do Cariri (UFCA)**

---

## Status do Sistema

- **UFCA**

[![Better Stack Badge](https://uptime.betterstack.com/status-badges/v1/monitor/1z0ga.svg)](https://yoko.betteruptime.com/pt)

---

## Dashboard de LOGS

- **UFCA**

[![Static Badge](https://img.shields.io/badge/Dashboard%20-%20LOGS%20-%20blue)](https://telemetry.betterstack.com/dashboards/5Y3xD2)

[![Static Badge](https://img.shields.io/badge/Dashboard%20-%20INFRA%20-%20blue)](https://telemetry.betterstack.com/dashboards/13w7Sq)

## 📌 Funcionalidades

- 📁 Cadastro e gerenciamento de projetos de pesquisa
- 🧮 Cálculo automático da pontuação Lattes
- 🧑‍⚖️ Avaliação Ad Hoc por avaliadores externos
- 🧾 Consulta e visualização de resultados dos projetos
- 👨‍🎓 Indicação e acompanhamento de discentes vinculados
- 📤 Envio de folhas de frequência mensal
- 🧾 Baixa automaticamento o Lattes a partir do IDLattes

---

## 🛠️ Tecnologias Utilizadas

- **Linguagem:** Python 3.13.5 (container)
- **Framework Web:** Flask  3.1.1
- **Banco de Dados:** (MariaDB 11.7.2)
- **Docker:** Utilizado para containerização do sistema

---

## 🔐 Recursos de Segurança

Este projeto Flask foi desenvolvido com atenção às melhores práticas de segurança. Abaixo estão os principais recursos implementados:

- **Autenticação Segura**
  - Sistema de login com autenticação baseada em senhas fortes, geradas automaticamente sem intervenção do usuário.
  - Proteção contra força bruta com **Flask-Limiter** para limitar tentativas de login.
  - Captcha reCAPTCHA v2 para proteger formulários de login e registro contra bots.

- **Autorização baseada em papéis (RBAC)**
  - Gerenciamento de permissões por nível de acesso (usuário, admin).
  - Rotas protegidas com decoradores de verificação de acesso.

- **Proteção contra CSRF**
  - Tokens CSRF automáticos com **Flask-WTF**, incluídos em todos os formulários.
  - Validação ativa para impedir requisições forjadas.

- **Validação e Sanitização de Entradas**
  - Validação de entradas do usuário.
  - Prevenção contra injeções de código malicioso (SQL Injection, XSS).

- **Criptografia**
  - Armazenamento seguro de senhas utilizando **Argon2** com pepper (HMAC)
  - Criptografia de arquivos com **AES-256 e GPG**
  - Criptografia do Banco de Dados com **AES-256-CBC** para proteger dados em repouso

- **Comunicação Segura**
  - Obrigatoriedade de uso de HTTPS/TLS em produção.
  - Configuração de cabeçalhos de segurança (HSTS, X-Frame-Options, etc.) com **Flask-Talisman**.

- **Auditoria e Monitoramento**
  - Registro de logs de acesso e erros com **Loguru** estruturado, **BetterStack** e **Sentry** .
  - Monitoramento de erros, desempenho e disponibilidade com **BetterStack** e **Sentry**.
  