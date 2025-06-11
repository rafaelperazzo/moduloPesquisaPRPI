# 🎓 Módulo de Pesquisa

[![Better Stack Badge](https://uptime.betterstack.com/status-badges/v1/monitor/1z0ga.svg)](https://yoko.betteruptime.com/pt)
![GitHub last commit](https://img.shields.io/github/last-commit/rafaelperazzo/moduloPesquisaPRPI)
![GitHub Tag](https://img.shields.io/github/v/tag/rafaelperazzo/moduloPesquisaPRPI)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![Flask](https://img.shields.io/badge/flask-%23000.svg?style=for-the-badge&logo=flask&logoColor=white)
![Debian](https://img.shields.io/badge/Debian-D70A53?style=for-the-badge&logo=debian&logoColor=white)
![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white)

Sistema web desenvolvido para auxiliar no gerenciamento e acompanhamento de projetos de pesquisa no âmbito acadêmico
da UFCA. Projetado para atender às necessidades da instituição supracitada.

---

## Status do Sistema

[![Better Stack Badge](https://uptime.betterstack.com/status-badges/v1/monitor/1z0ga.svg)](https://yoko.betteruptime.com/pt)

Página de status do sistema: [Yoko](https://yoko.betteruptime.com/pt)

---

## Dashboard de erros e acessos

[Dashboard](https://telemetry.betterstack.com/dashboards/5Y3xD2)

## 📌 Funcionalidades

- 📁 Cadastro e gerenciamento de projetos de pesquisa
- 🧮 Cálculo automático da pontuação Lattes
- 🧑‍⚖️ Avaliação Ad Hoc por avaliadores externos
- 🧾 Consulta e visualização de resultados dos projetos
- 👨‍🎓 Indicação e acompanhamento de discentes vinculados
- 📤 Envio de folhas de frequência mensal

---

## 🛠️ Tecnologias Utilizadas

- **Linguagem:** Python 3.13.4
- **Framework Web:** Flask  3.1.1
- **Banco de Dados:** (MariaDB 11.7.2)

---

## 🔐 Recursos de Segurança

Este projeto Flask foi desenvolvido com atenção às melhores práticas de segurança. Abaixo estão os principais recursos implementados:

- **Autenticação Segura**
  - Sistema de login com autenticação baseada em senhas fortes, geradas automaticamente sem intervenção do usuário.
  - Proteção contra força bruta com **Flask-Limiter** para limitar tentativas de login.

- **Autorização baseada em papéis (RBAC)**
  - Gerenciamento de permissões por nível de acesso (usuário, admin).
  - Rotas protegidas com decoradores de verificação de acesso.

- **Proteção contra CSRF**
  - Tokens CSRF automáticos com **Flask-WTF**, incluídos em todos os formulários.
  - Validação ativa para impedir requisições forjadas.

- **Validação e Sanitização de Entradas**
  - Validação de entradas do usuário.
  - Prevenção contra injeções de código malicioso (SQL Injection, XSS).

- **Criptografia de Senhas**
  - Armazenamento seguro com **Argon2** com pepper (HMAC).

- **Comunicação Segura**
  - Obrigatoriedade de uso de HTTPS/TLS em produção.
  - Configuração de cabeçalhos de segurança (HSTS, X-Frame-Options, etc.) com **Flask-Talisman**.