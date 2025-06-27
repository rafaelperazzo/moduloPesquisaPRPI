# 🎓 Módulo de Pesquisa

[![Better Stack Badge](https://uptime.betterstack.com/status-badges/v1/monitor/1z0ga.svg)](https://yoko.betteruptime.com/pt)
![GitHub last commit (branch)](https://img.shields.io/github/last-commit/rafaelperazzo/moduloPesquisaPRPI/python3)
![GitHub Tag](https://img.shields.io/github/v/tag/rafaelperazzo/moduloPesquisaPRPI)
![GitHub Pipenv locked Python version (branch)](https://img.shields.io/github/pipenv/locked/python-version/rafaelperazzo/moduloPesquisaPRPI/python3?label=Python)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/rafaelperazzo/moduloPesquisaPRPI/update.yml?label=Update)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/rafaelperazzo/moduloPesquisaPRPI/backup.yml?label=Backup)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/rafaelperazzo/moduloPesquisaPRPI/frequencia.yml?label=Frequ%C3%AAncia)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/rafaelperazzo/moduloPesquisaPRPI/avaliacao.yml?label=Avalia%C3%A7%C3%A3o)

![Flask](https://img.shields.io/badge/flask-%23000.svg?style=for-the-badge&logo=flask&logoColor=white)
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

- **Linguagem:** Python 3.13.4 (container)
- **Framework Web:** Flask  3.1.1
- **Banco de Dados:** (MariaDB 11.7.2)

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

#### 4. Instalação das ferramentas de apoio (GitHub CLI, Hub e Infisical)

```bash
# Instale os requisitos
sudo apt-get update && sudo apt-get -y upgrade
# Instale os pacotes necessários
sudo apt-get -y install gh hub
echo "eval $(hub alias -s)" >> ~/.bashrc
# Instale o Infisical
curl -1sLf \
'https://artifacts-cli.infisical.com/setup.deb.sh' \
| sudo -E bash
sudo apt-get update && sudo apt-get install -y infisical
```

#### 5. Configuração do Token do Infisical

```bash
echo "*********************************"
echo "Digite seu token do Infisical:"
echo "*********************************"
read INFISICAL_TOKEN
```

#### 6. Instalação do projeto

```bash
mkdir pesquisa
cd pesquisa
git remote add origin git@github.com:rafaelperazzo/moduloPesquisaPRPI.git
hub sync
git checkout python3
```

#### 7. Crie a chave AES para criptografar os dados do MariaDB

```bash
#Criando as chaves AES
(echo -n "1;" ; openssl rand -hex 32 ) | sudo tee -a keyfile
(echo -n "2;" ; openssl rand -hex 32 ) | sudo tee -a keyfile
(echo -n "3;" ; openssl rand -hex 32 ) | sudo tee -a keyfile
(echo -n "4;" ; openssl rand -hex 32 ) | sudo tee -a keyfile
#Encriptando as chaves AES
sudo openssl enc -aes-256-cbc -md sha1 \
   -pass $(infisical secrets get MARIADB_REST_AES_KEY --plain) \
   -in keyfile \
   -out aes_key.key.enc
   
#Ajustando permissões
sudo rm keyfile
sudo chmod 400 aes_key.key.enc
sudo chown $USER aes_key.key.enc
```

#### 8. Configure o projeto

```bash
cp atualizar_db.sh.sample atualizar_db.sh
./reiniciar.sh.run
```
