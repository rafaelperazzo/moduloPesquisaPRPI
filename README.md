# 🎓 Módulo de Pesquisa

Sistema web desenvolvido para auxiliar no gerenciamento e acompanhamento de projetos de pesquisa no âmbito acadêmico. Projetado para atender às necessidades de instituições de ensino e pesquisa.

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

- **Linguagem:** Python 3.13  
- **Framework Web:** Flask  
- **Banco de Dados:** (MariaDB 11.7.2)

---

## ⚙️ Instalação

### Pré-requisitos

- Python 3.13 instalado
- Gerenciador de pacotes `pip`
- Docker

### Passos (em construção...)

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
```

```bash
# Instale os requisitos
sudo apt-get update && sudo apt-get -y upgrade

# Instale os pacotes necessários
sudo apt-get -y install gh hub

# Instale o Infisical
curl -1sLf \
'https://artifacts-cli.infisical.com/setup.deb.sh' \
| sudo -E bash

sudo apt-get update && sudo apt-get install -y infisical

echo "eval $(hub alias -s)" >> ~/.bashrc

mkdir pesquisa
cd pesquisa
git remote add origin git@github.com:rafaelperazzo/moduloPesquisaPRPI.git
git sync

# Em construção...
```
