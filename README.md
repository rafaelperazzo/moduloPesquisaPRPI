# 🎓 Módulo de Pesquisa

![Header](./github-header-image.png)

[![Better Stack Badge](https://uptime.betterstack.com/status-badges/v1/monitor/1z0ga.svg)](https://yoko.betteruptime.com/pt)
![GitHub last commit (branch)](https://img.shields.io/github/last-commit/rafaelperazzo/moduloPesquisaPRPI/python3)
![GitHub Tag](https://img.shields.io/github/v/tag/rafaelperazzo/moduloPesquisaPRPI)
![GitHub Pipenv locked Python version (branch)](https://img.shields.io/github/pipenv/locked/python-version/rafaelperazzo/moduloPesquisaPRPI/python3?label=Python)
![GitHub Pipenv locked dependency version (branch)](https://img.shields.io/github/pipenv/locked/dependency-version/rafaelperazzo/moduloPesquisaPRPI/flask/python3)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/rafaelperazzo/moduloPesquisaPRPI/update.yml?label=Update)

![Debian](https://img.shields.io/badge/Debian-D70A53?style=for-the-badge&logo=debian&logoColor=white)
![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white)

Sistema web desenvolvido para auxiliar no gerenciamento e acompanhamento de projetos de pesquisa de instituição de ensino superior.



---

## Quem utiliza?

- **Universidade Federal do Cariri (UFCA)**

---

## Status do Sistema

[![Better Stack Badge](https://uptime.betterstack.com/status-badges/v1/monitor/1z0ga.svg)](https://yoko.betteruptime.com/pt)

---

## Dashboard de LOGS

[![Static Badge](https://img.shields.io/badge/Dashboard%20-%20LOGS%20-%20blue)](https://telemetry.betterstack.com/dashboards/5Y3xD2)
---

## 📌 Funcionalidades

- 📁 Cadastro e gerenciamento de projetos de pesquisa
- 🧮 Cálculo automático da pontuação Lattes
- 🧑‍⚖️ Avaliação Ad Hoc por avaliadores externos
- 🧾 Consulta e visualização de resultados dos projetos
- 👨‍🎓 Indicação e acompanhamento de discentes vinculados
- 📤 Envio de folhas de frequência mensal

---

## 🛠️ Tecnologias Utilizadas

- **Linguagem:** Python 3.13.5 (container)
- **Framework Web:** Flask  3.1.1
- **Banco de Dados:** (MariaDB 11.7.2)

---

## 🔒 Segurança

Uma página com o detalhamento completo dos recursos abaixo está disponível em `/seguranca` dentro do próprio sistema.

**Infraestrutura (Cloudflare - plano Free)**

- Criptografia TLS 1.3 (Universal SSL)
- Proteção contra DDoS
- Firewall de Aplicação Web (WAF) com regras gerenciadas
- Limitação de taxa (Rate Limiting) na borda da rede
- Bot Fight Mode
- Bloqueio geográfico e de VPNs/proxies anônimos
- Verificação de credenciais vazadas (Leaked Credential Check)
- Rede global Anycast/CDN, que oculta o IP de origem do servidor

**Aplicação**

- Todas as consultas SQL utilizam parâmetros vinculados (*bound parameters*) via o conector `mariadb`, eliminando os riscos de SQL Injection identificados em uma varredura completa da aplicação.
- Dados sensíveis da tabela de indicações (RG, telefone, celular, nascimento, endereço) são criptografados com AES-256, com o banco também protegido por criptografia em repouso — a chave dessa criptografia é armazenada no AWS Systems Manager (SSM) Parameter Store, fora do servidor de aplicação.
- Em produção, os segredos da aplicação (senhas de banco de dados, chaves de criptografia, tokens de serviços externos etc.) são carregados em tempo de execução a partir do AWS SSM Parameter Store, e não mais de um arquivo `.env` local.
- Senhas armazenadas com Argon2id, com política de senha forte (mínimo 12 caracteres, com maiúsculas, minúsculas, números e caracteres especiais).
- Bloqueio automático de acesso quando a senha do usuário é identificada como vazada no login.
- Limitação de tentativas (rate limiting) por rota em Flask-Limiter, com destaque para login e redefinição de senha.
- Proteção contra CSRF (Flask-WTF), cabeçalhos de segurança HTTP (Flask-Talisman) e reCAPTCHA em formulários sensíveis.
- Sessões armazenadas no servidor (Redis), com expiração automática.
- Registro e auditoria de acessos (usuário, IP, rota e localização).

---

## ⚙️ Instalação

Ainda em fase de desenvolvimento, o passo a passo abaixo ainda precisa de alguns ajustes.

### Pré-requisitos

- Linux (Ubuntu 22.04 ou superior)

### Passos

#### 1. Configuração do Github

- Adicione sua chave SSH ao GitHub

#### 2. Faça o login no GitHub CLI

```bash
gh auth login
```

#### 3. Instalação do Docker

```bash
# Add Docker's official GPG key:
sudo apt-get update
sudo apt-get install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository to Apt sources:
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "noble") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo groupadd docker
sudo usermod -aG docker $USER
newgrp docker
```

#### 4. Instalação das ferramentas de apoio (GitHub CLI e Hub)

```bash
# Instale os requisitos
sudo apt-get update && sudo apt-get -y upgrade
# Instale os pacotes necessários
sudo apt-get -y install gh hub
echo "eval $(hub alias -s)" >> ~/.bashrc
```

#### 5. Instalação do projeto

```bash
mkdir pesquisa
cd pesquisa
git remote add origin git@github.com:rafaelperazzo/moduloPesquisaPRPI.git
hub sync
git checkout python3
```

#### 6. Crie a chave AES para criptografar os dados do MariaDB

Esta chave (`MARIADB_REST_AES_KEY`) é usada apenas em desenvolvimento local (via `docker-compose.yml`); defina-a no seu `.env` antes de prosseguir. Em produção, o servidor de aplicação roda fora do Docker e as credenciais são obtidas do AWS SSM Parameter Store — veja a seção de Segurança.

```bash
#Criando as chaves AES
(echo -n "1;" ; openssl rand -hex 32 ) | sudo tee -a keyfile
(echo -n "2;" ; openssl rand -hex 32 ) | sudo tee -a keyfile
(echo -n "3;" ; openssl rand -hex 32 ) | sudo tee -a keyfile
(echo -n "4;" ; openssl rand -hex 32 ) | sudo tee -a keyfile
#Encriptando as chaves AES
set -a; source .env; set +a
sudo openssl enc -aes-256-cbc -md sha1 \
   -pass env:MARIADB_REST_AES_KEY \
   -in keyfile \
   -out aes_key.key.enc
   
#Ajustando permissões
sudo rm keyfile
sudo chmod 400 aes_key.key.enc
sudo chown $USER aes_key.key.enc
```

#### 7. Configure o projeto

```bash
cp atualizar_db.sh.sample atualizar_db.sh
./reiniciar.sh.run
```
