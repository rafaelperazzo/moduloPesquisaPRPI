# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Sistema web Flask para gerenciamento de projetos de pesquisa da Universidade Federal do Cariri (UFCA). Permite cadastro de projetos, cálculo automático de pontuação Lattes, avaliação ad hoc por avaliadores externos, indicação e acompanhamento de discentes, e envio de folhas de frequência mensal.

## Commands

**Run (development):**
```bash
python3 pesquisa.py
```

**Run (production via Docker):**
```bash
docker-compose up -d
```

**Run tests:**
```bash
pytest
# Single test file:
pytest tests/test_login.py -v
```

**Install dependencies:**
```bash
pip install -r requirements.txt
```

## Architecture

### Single-file monolith
The entire Flask application lives in `pesquisa.py` (~4000+ lines), containing all route handlers, database functions, and helper utilities. There is one supporting module: `modules/scorerun.py`, which handles Lattes curriculum scoring logic and Qualis journal database lookups.

### Request flow
1. All routes are defined in `pesquisa.py` with a `URL_PREFIX` (default `/pesquisa`)
2. Sessions are backed by Redis; authentication is session-based
3. CSRF protection via Flask-WTF is enforced in production (`PRODUCAO=1`) and disabled in dev (`PRODUCAO=0`)
4. Rate limiting via Flask-Limiter uses Redis as the storage backend
5. File uploads go to AWS S3 (production) or local `submissoes/` directory (dev)

### Key external integrations
- **CNPq SOAP API** (`./cnpq` WSDL): retrieves Lattes IDs from CPF and downloads compressed Lattes curriculum (ZIP → XML)
- **Lattes scoring service**: external HTTP endpoint at `sci01-ter-jne.ufca.edu.br` called via `modules/scorerun.py`
- **Gmail SMTP** (port 587, TLS): all outbound emails; suppressed in dev (`PRODUCAO=0`)
- **AWS S3**: file storage for project submissions and indication documents
- **Redis**: session storage and rate-limiting backend

### Database
MariaDB 11 with AES-256 encryption at rest. Raw SQL queries via the `mariadb` connector (no ORM). The `aes_key.key.enc` file must be present for the database container to start.

**Main tables:** `editalProjeto` (registered projects), `editais` (calls/announcements), `alunos` (scholarship holders), `indicacoes` (student nominations), `avaliacoes` (evaluations), `autenticacao` (document auth codes), `mensagens` (system-wide notices), `resumoGeralClassificacao` (ranking summaries).

### Background jobs
APScheduler (`Flask-APScheduler`) handles recurring tasks: frequency checks, evaluation deadline processing, and email dispatch.

## Environment Variables

Copy `.env.sample` to `.env` before running. Key variables:

| Variable | Purpose |
|---|---|
| `PRODUCAO` | `0` = dev (CSRF off, email suppressed), `1` = production |
| `URL_PREFIX` | URL path prefix, default `/pesquisa` |
| `MYSQL_HOST` / `MYSQL_DATABASE` / `MYSQL_PASSWORD` | MariaDB connection |
| `MYSQL_TEST_DATABASE` | Separate DB used by pytest |
| `REDIS_HOST` | Redis host for sessions and rate limiting |
| `GMAIL_PASSWORD` | Gmail app password for SMTP |
| `AWS_S3_KEY_ID` / `AWS_S3_SECRET_KEY` / `AWS_S3_BUCKET` | S3 file storage |
| `SESSION_SECRET_KEY` | Flask session secret |
| `TEST_USER` / `TEST_PASSWORD` / `EMAIL_TESTES` / `CPF_TESTES` | Test credentials |

## Tests

Test files live in `tests/` and require a running MariaDB instance pointed at `MYSQL_TEST_DATABASE`. Relevant test files:
- `test_login.py` — authentication flows
- `test_editalProjeto.py` — project registration
- `test_submissao_avaliador.py` — evaluator submission
- `test_scorelattes.py` — Lattes scoring
- `test_upload_s3.py` — S3 integration

## Known Technical Debt

- Some raw SQL queries are not yet parameterized (SQL injection risk — tracked in TODO.md)
- Users table fields (`nome`, `email`) not yet encrypted at rest
- Several lazy log entries scheduled for removal
