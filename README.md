# Agente de IA para Consultas SQL

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![MySQL](https://img.shields.io/badge/MySQL-8%2B-4479A1?logo=mysql&logoColor=white)](https://www.mysql.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.50%2B-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Testes](https://img.shields.io/badge/testes-62%20passando-2ea44f)](#testes)
[![Licença](https://img.shields.io/badge/licen%C3%A7a-MIT-blue)](LICENSE)

Agente que recebe perguntas em **linguagem natural**, gera **SQL** com um LLM, valida a consulta, executa em um banco **somente leitura** e devolve o resultado com uma explicação em português.

Funciona no **terminal** e em uma interface web (**Streamlit**), com **SQLite** (zero configuração) ou **MySQL** (banco local ou remoto).

Projeto desenvolvido como entrega do desafio **"Desenvolvimento de um agente de IA capaz de converter perguntas em linguagem natural em consultas SQL"** da [DIO](https://www.dio.me/).

---

## Sumário

- [Demonstração](#demonstração)
- [O que é um agente?](#o-que-é-um-agente)
- [O que é o DioBank?](#o-que-é-o-diobank)
- [O que o projeto faz](#o-que-o-projeto-faz)
- [Arquitetura](#arquitetura)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Obtendo a chave de API](#obtendo-a-chave-de-api)
- [Configurando o ambiente](#configurando-o-ambiente)
- [Construindo o `.env` — Parte 1: LLM](#construindo-o-env--parte-1-llm)
- [Construindo o `.env` — Parte 2: banco de dados](#construindo-o-env--parte-2-banco-de-dados)
- [Configuração de banco remoto (MySQL)](#configuração-de-banco-remoto-mysql)
- [Criando a massa de dados](#criando-a-massa-de-dados)
- [Usando o agente no terminal](#usando-o-agente-no-terminal)
- [Usando a interface Streamlit](#usando-a-interface-streamlit)
- [Deploy no Streamlit Cloud](#deploy-no-streamlit-cloud)
- [Segurança](#segurança)
- [Testes](#testes)
- [Decisões técnicas](#decisões-técnicas)
- [Limitações](#limitações)
- [Aprendizados](#aprendizados)
- [Checklist de entrega do desafio](#checklist-de-entrega-do-desafio)
- [Próximos passos](#próximos-passos)
- [Licença](#licença)

---

## Demonstração

**Interface web (SQLite)**

![Interface Streamlit do agente respondendo a uma pergunta sobre os 5 clientes que mais gastaram em 2026](images/streamlit.png)

**Interface web (MySQL, com usuário somente leitura)**

![A mesma pergunta executada no backend MySQL, com o SQL usando faixas de data](images/streamlit-mysql.png)

> As duas capturas são do app real: mesma pergunta, mesmos números, dialetos diferentes. No SQLite o filtro usa `strftime`; no MySQL, `p.data_pedido >= '2026-01-01' AND p.data_pedido < '2027-01-01'`. Para gerar as imagens sem expor uma chave, a geração de SQL foi atendida por um servidor local compatível com a API da OpenAI; a execução e os números vêm do banco de exemplo.

No terminal, a mesma pergunta produz:

```text
$ python -m sql_agent -q "Quais foram os 5 clientes que mais gastaram em 2026?"

SQL gerado (tentativa 1):
  SELECT c.nome,
         ROUND(SUM(i.quantidade * i.preco_unitario), 2) AS total_gasto
  FROM clientes c
  JOIN pedidos p ON p.cliente_id = c.id
  JOIN itens_pedido i ON i.pedido_id = p.id
  WHERE p.status <> 'cancelado'
    AND strftime('%Y', p.data_pedido) = '2026'
  GROUP BY c.id, c.nome
  ORDER BY total_gasto DESC
  LIMIT 5

Resultado: 5 linha(s) em 1.5 ms
+-----------------+-------------+
| nome            | total_gasto |
+-----------------+-------------+
| Diego Almeida   | 45775.45    |
| Isabela Dias    | 43512.35    |
| Mariana Ribeiro | 32710.28    |
| Rafael Honda    | 25864.69    |
| Rafael Klein    | 19588.9     |
+-----------------+-------------+

Resposta: Os cinco clientes que mais gastaram em 2026 foram Diego Almeida,
Isabela Dias, Mariana Ribeiro, Rafael Honda e Rafael Klein, somando cerca de
R$ 167 mil em pedidos não cancelados.
```

> Os números acima vêm do banco de exemplo (dados determinísticos). A explicação é gerada pelo modelo a partir da tabela de resultados; no MySQL, o prompt troca as funções de data do SQLite pelas equivalentes (`YEAR`, `CURDATE`, `DATE_FORMAT`).

## O que é um agente?

Um **chatbot** responde com texto. Um **agente** usa o modelo como motor de decisão dentro de um ciclo com ferramentas: ele **observa** o ambiente, **decide** uma ação, **executa** e usa o resultado para continuar.

Neste projeto, o agente é composto por:

| Papel | Neste projeto |
| --- | --- |
| **Modelo (cérebro)** | LLM acessado via API compatível com OpenAI |
| **Ferramenta (ação)** | Executar uma consulta SQL em um banco somente leitura |
| **Contexto** | Esquema real do banco + data de hoje + pergunta do usuário |
| **Ciclo (loop)** | Gerar SQL → validar → executar → se falhar, devolver o erro ao modelo e tentar de novo |
| **Resposta** | SQL executado + tabela de resultados + explicação em português |

O agente **não** tem permissão de alterar dados: a única ação possível é ler. Isso torna o comportamento previsível e seguro o suficiente para ser usado por alguém de negócio.

## O que é o DioBank?

**DioBank** é o banco fictício usado como fio condutor nos desafios da [DIO](https://www.dio.me/). Neste projeto ele dá nome ao cenário de negócio: uma base relacional de uma operação comercial fictícia, com **clientes**, **vendedores**, **produtos**, **pedidos** e **itens de pedido**.

O esquema é propositalmente genérico — o mesmo agente funciona em qualquer banco relacional, bastando apontar a conexão para outra base. O que muda entre SQLite e MySQL é apenas o dialeto usado no prompt e na execução.

## O que o projeto faz

- Converte perguntas em português para **SQL** no dialeto do banco configurado (SQLite ou MySQL).
- Lê o **esquema do banco automaticamente** (tabelas, colunas, tipos, chaves estrangeiras) e o envia no prompt — o modelo não precisa "adivinhar" a estrutura.
- **Valida** a consulta e garante que apenas leituras (`SELECT` / `WITH ... SELECT`) sejam executadas.
- **Corrige sozinho**: se a consulta falhar, o erro real do banco volta para o modelo, que tem até 2 novas chances.
- Limita o número de linhas retornadas e sinaliza quando o resultado foi truncado.
- Gera uma **explicação em linguagem natural** com base apenas no resultado obtido.
- Funciona com **OpenAI, Groq, Gemini, OpenRouter ou Ollama local**, pois usa a API compatível com OpenAI.
- Oferece **CLI** (interativo, pergunta única, JSON, inspeção de esquema) e **interface web** com histórico, exemplos de perguntas e tabela de resultados.

## Arquitetura

```mermaid
flowchart LR
    U([Usuário]) -->|pergunta| UI[CLI ou Streamlit]
    UI --> AG[SQLAgent]
    AG -->|esquema real + pergunta| LLM[LLM]
    LLM -->|SQL| AG
    AG --> VAL{SELECT seguro?}
    VAL -- não --> AG
    VAL -- sim --> DB[(Banco somente leitura<br/>SQLite ou MySQL)]
    DB -->|linhas| AG
    AG -->|resultado| LLM
    LLM -->|explicação| AG
    AG -->|SQL + tabela + resposta| UI
    UI --> U
```

O fluxo é um **loop com autocorreção**: o SQL gerado é validado e executado; se houver erro, a mensagem do banco é enviada de volta ao modelo antes da próxima tentativa.

## Estrutura do repositório

```text
.
├── sql_agent/
│   ├── __init__.py          # exporta a API pública do pacote
│   ├── __main__.py          # permite `python -m sql_agent`
│   ├── agent.py             # orquestração, extração de SQL e retentativas
│   ├── cli.py               # interface de linha de comando e tabelas ASCII
│   ├── config.py            # configuração via .env / variáveis de ambiente
│   ├── database.py          # SQLite/MySQL somente leitura + introspecção + validação
│   ├── llm.py               # cliente para APIs compatíveis com OpenAI
│   ├── prompts.py           # prompts de geração de SQL (por dialeto) e explicação
│   └── sample_data.py       # massa de dados e esquemas SQLite/MySQL
├── app.py                   # interface web (Streamlit)
├── scripts/
│   ├── create_sample_db.py  # cria data/empresa.db
│   └── seed_mysql.py        # cria banco, tabelas e massa de dados no MySQL
├── tests/
│   ├── conftest.py          # fixtures e LLM falso (stub)
│   ├── test_agent.py        # pipeline, retentativas, extração de SQL
│   ├── test_cli.py          # saída em texto/JSON e --show-schema
│   ├── test_config.py       # .env, backend e DATABASE_URL
│   ├── test_database.py     # esquema, validação e proteção contra escrita
│   ├── test_mysql.py        # validação da configuração do MySQL
│   ├── test_prompts.py      # prompts por dialeto (SQLite/MySQL)
│   └── test_sample_data.py  # volumes, determinismo e relacionamentos
├── docs/
│   └── diario-de-bordo.md   # registro do processo de desenvolvimento
├── images/
│   ├── streamlit.png        # captura da interface web (SQLite)
│   └── streamlit-mysql.png  # captura da interface web (MySQL)
├── .streamlit/
│   └── config.toml          # tema e configuração do Streamlit
├── data/                    # banco SQLite gerado (fora do controle de versão)
├── .env.example             # modelo de configuração (Partes 1 e 2)
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

## Obtendo a chave de API

O agente não usa um provedor "oficial": qualquer serviço compatível com a API de *chat completions* da OpenAI funciona. Escolha **um** dos caminhos abaixo e guarde a chave para a Parte 1 do `.env`.

<details>
<summary><strong>OpenAI</strong> (pago, melhor qualidade)</summary>

1. Acesse <https://platform.openai.com/signup> e crie a conta.
2. Em **Billing**, adicione créditos (a API é cobrada por token; não existe plano gratuito permanente).
3. Em **API keys**, clique em **Create new secret key**.
4. Copie a chave (`sk-...`) — ela aparece **uma única vez**.
5. Defina `LLM_MODEL=gpt-4o-mini` e deixe `LLM_BASE_URL` vazio.

> Uma pergunta típica gasta poucos milhares de tokens. Ainda assim, configure um limite de gasto na conta.
</details>

<details>
<summary><strong>Groq</strong> (plano gratuito generoso, respostas rápidas)</summary>

1. Acesse <https://console.groq.com/> e faça login.
2. Em **API Keys**, crie uma chave (`gsk_...`).
3. Defina:
   ```env
   LLM_MODEL=llama-3.3-70b-versatile
   LLM_BASE_URL=https://api.groq.com/openai/v1
   ```
</details>

<details>
<summary><strong>Google Gemini</strong> (plano gratuito limitado)</summary>

1. Acesse <https://aistudio.google.com/app/apikey>.
2. Clique em **Create API key** e copie a chave.
3. Defina:
   ```env
   LLM_MODEL=gemini-2.0-flash
   LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
   ```
</details>

<details>
<summary><strong>OpenRouter</strong> (vários modelos, inclusive gratuitos)</summary>

1. Acesse <https://openrouter.ai/keys> e crie a chave.
2. Escolha um modelo em <https://openrouter.ai/models>.
3. Defina:
   ```env
   LLM_MODEL=meta-llama/llama-3.3-70b-instruct
   LLM_BASE_URL=https://openrouter.ai/api/v1
   ```
</details>

<details>
<summary><strong>Ollama</strong> (local, sem chave e sem custo por token)</summary>

1. Instale em <https://ollama.com/download>.
2. Baixe um modelo de código:
   ```powershell
   ollama pull qwen2.5-coder:7b
   ```
3. Defina:
   ```env
   LLM_MODEL=qwen2.5-coder:7b
   LLM_API_KEY=ollama
   LLM_BASE_URL=http://localhost:11434/v1
   ```
</details>

> **Nunca** versione o `.env`: ele já está no `.gitignore`. Se uma chave vazar, revogue no painel do provedor.

## Configurando o ambiente

### Pré-requisitos

- Python **3.10+**
- Uma chave de API de LLM **ou** Ollama local
- (Opcional) MySQL 8 local via Docker **ou** um MySQL gerenciado na nuvem

### Passo a passo

```powershell
# 1. Clone o repositório e entre na pasta
git clone https://github.com/Subaruberu/agente-sql-dio.git
cd agente-sql-dio

# 2. Crie e ative um ambiente virtual (Windows/PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Linux/macOS:
# python -m venv .venv
# source .venv/bin/activate

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Crie o arquivo de configuração a partir do modelo
Copy-Item .env.example .env      # Linux/macOS: cp .env.example .env

# 5. Edite o .env (Partes 1 e 2, abaixo)

# 6. Crie o banco SQLite de demonstração
python scripts/create_sample_db.py

# 7. Converse com o agente
python -m sql_agent
```

> No Windows, se os acentos aparecerem estranhos no terminal, execute `chcp 65001` antes de rodar o agente.

## Construindo o `.env` — Parte 1: LLM

O arquivo `.env` é dividido em duas partes. A **Parte 1** configura o provedor do modelo:

```env
# =============================================================================
# PARTE 1 — Provedor de LLM (API compatível com OpenAI)
# =============================================================================
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sua-chave-aqui
LLM_BASE_URL=
LLM_TEMPERATURE=0
```

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `LLM_MODEL` | `gpt-4o-mini` | Nome do modelo no provedor |
| `LLM_API_KEY` | — | Chave de API (Ollama aceita qualquer valor) |
| `LLM_BASE_URL` | — | URL base do provedor (vazio para OpenAI) |
| `LLM_TEMPERATURE` | `0` | Temperatura da geração (0 = mais determinístico) |

Referências rápidas por provedor:

| Provedor | `LLM_MODEL` | `LLM_BASE_URL` |
| --- | --- | --- |
| OpenAI | `gpt-4o-mini` | *(vazio)* |
| Groq | `llama-3.3-70b-versatile` | `https://api.groq.com/openai/v1` |
| Gemini | `gemini-2.0-flash` | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| OpenRouter | `meta-llama/llama-3.3-70b-instruct` | `https://openrouter.ai/api/v1` |
| Ollama | `qwen2.5-coder:7b` | `http://localhost:11434/v1` |

> `LLM_TEMPERATURE=0` reduz a variação entre execuções — bom para SQL, onde precisão importa mais que criatividade.

## Construindo o `.env` — Parte 2: banco de dados

A **Parte 2** escolhe o backend e configura a conexão:

```env
# =============================================================================
# PARTE 2 — Banco de dados
# =============================================================================
# "sqlite" (local, zero configuração) ou "mysql" (local/remoto)
SQL_AGENT_BACKEND=sqlite

# --- SQLite ------------------------------------------------------------------
SQL_AGENT_DB=data/empresa.db

# --- MySQL -------------------------------------------------------------------
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_DATABASE=diobank
MYSQL_SSL_CA=

# Alternativa: uma única URL. Tem prioridade sobre as variáveis MYSQL_* acima.
# DATABASE_URL=mysql://usuario:senha@host:3306/diobank

# --- Limites de execução -----------------------------------------------------
SQL_AGENT_MAX_ROWS=100
SQL_AGENT_MAX_RETRIES=2
```

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `SQL_AGENT_BACKEND` | `sqlite` | Backend usado pelo agente: `sqlite` ou `mysql` |
| `SQL_AGENT_DB` | `data/empresa.db` | Caminho do arquivo SQLite |
| `MYSQL_HOST` | `localhost` | Host do servidor MySQL |
| `MYSQL_PORT` | `3306` | Porta do MySQL |
| `MYSQL_USER` | `root` | Usuário do banco |
| `MYSQL_PASSWORD` | *(vazio)* | Senha do usuário |
| `MYSQL_DATABASE` | `diobank` | Nome do banco |
| `MYSQL_SSL_CA` | *(vazio)* | Caminho do certificado CA, quando o servidor exige TLS |
| `DATABASE_URL` | — | URL completa (`mysql://user:pass@host:3306/db`), tem prioridade sobre as variáveis `MYSQL_*` |
| `SQL_AGENT_MAX_ROWS` | `100` | Máximo de linhas devolvidas por consulta |
| `SQL_AGENT_MAX_RETRIES` | `2` | Tentativas extras de correção do SQL |

> Senhas com `@`, `:` ou `/` precisam ser codificadas na `DATABASE_URL` (`@` → `%40`, `:` → `%3A`). Nas variáveis separadas, use a senha como está.

## Configuração de banco remoto (MySQL)

O projeto vem com SQLite para rodar sem servidor, mas o desafio pede um **banco remoto**. O backend MySQL está implementado e pode ser usado localmente (Docker) ou em um provedor gerenciado.

### Opção A — MySQL local com Docker

```powershell
docker run --name mysql-diobank `
  -e MYSQL_ROOT_PASSWORD=root `
  -e MYSQL_DATABASE=diobank `
  -p 3306:3306 -d mysql:8.4
```

No `.env`:

```env
SQL_AGENT_BACKEND=mysql
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=root
MYSQL_DATABASE=diobank
```

### Opção B — MySQL gerenciado na nuvem

Funciona com **Azure Database for MySQL**, **Amazon RDS/Aurora MySQL**, **Aiven**, **Railway**, **PlanetScale** ou qualquer provedor MySQL/MariaDB. Passos gerais:

1. Crie a instância e um banco chamado `diobank` (ou use outro nome).
2. Libere o firewall para o seu IP (ou para o IP do Streamlit Cloud).
3. Se o provedor exigir TLS, baixe o certificado CA e aponte `MYSQL_SSL_CA` para ele.
4. Preencha as variáveis `MYSQL_*` (ou `DATABASE_URL`) no `.env`.
5. Rode a massa de dados (próxima seção) com um usuário que tenha permissão de DDL/DML.
6. **Crie um usuário somente leitura** para o agente usar:

```sql
-- Execute como administrador, no banco diobank
CREATE USER 'agente_ro'@'%' IDENTIFIED BY 'uma-senha-forte';
GRANT SELECT ON diobank.* TO 'agente_ro'@'%';
FLUSH PRIVILEGES;

-- Confira:
SHOW GRANTS FOR 'agente_ro'@'%';
```

Depois troque o `.env` para o usuário de leitura:

```env
SQL_AGENT_BACKEND=mysql
MYSQL_HOST=seu-servidor.mysql.database.azure.com
MYSQL_PORT=3306
MYSQL_USER=agente_ro
MYSQL_PASSWORD=uma-senha-forte
MYSQL_DATABASE=diobank
MYSQL_SSL_CA=C:\certs\DigiCertGlobalRootCA.crt.pem
```

> **Por que dois usuários?** Criar tabelas e inserir dados exige permissões de escrita. O agente em si só precisa de `SELECT`. Separar as credenciais garante que nem um bug nem uma injeção de prompt consigam alterar a base.

### Testando a conexão

```powershell
# Deve imprimir o esquema do banco MySQL
python -m sql_agent --backend mysql --show-schema
```

Se conectar, todas as perguntas passam a usar o MySQL — inclusive pela interface Streamlit.

### Problemas comuns

| Erro | Causa provável | Solução |
| --- | --- | --- |
| `1045 Access denied` | Usuário/senha incorretos ou host não liberado | Confira as credenciais e o firewall; `'usuario'@'%'` libera qualquer host |
| `2003 Can't connect` / *handshake timeout* | Porta bloqueada, servidor desligado, firewall da rede **ou** falta do pacote `cryptography` | Teste a porta (`Test-NetConnection host -Port 3306`), libere o IP e rode `pip install -r requirements.txt` |
| `1049 Unknown database` | O banco ainda não existe | Rode `python scripts/seed_mysql.py` com um usuário que possa criar bancos |
| `cryptography is required` | Falta a dependência do driver | `pip install -r requirements.txt` |
| Acentos virando `?` | Conexão sem `utf8mb4` | O projeto já usa `utf8mb4`; verifique o charset do banco/tabelas |

## Criando a massa de dados

A massa é gerada por código, de forma **determinística** (semente `2026`), e é a mesma para SQLite e MySQL:

| Tabela | Registros | Conteúdo |
| --- | ---: | --- |
| `clientes` | 40 | nome, e-mail, cidade/UF, segmento, data de cadastro |
| `vendedores` | 6 | nome, e-mail, região |
| `produtos` | 25 | nome, categoria, preço, estoque |
| `pedidos` | 120 | cliente, vendedor, data, status, canal |
| `itens_pedido` | 289 | pedido, produto, quantidade, preço unitário |

Os pedidos cobrem **janeiro/2025 a novembro/2026** e **cinco clientes não possuem pedidos** — o que permite testar agregações, filtros por data, `JOIN`, `NOT EXISTS` e `LEFT JOIN`. Categorias: `Eletrônicos`, `Móveis`, `Livros`, `Esportes` e `Casa`.

### SQLite

```powershell
python scripts/create_sample_db.py
```

```text
Banco criado em: C:\...\data\empresa.db
  clientes         40 registro(s)
  itens_pedido    289 registro(s)
  pedidos         120 registro(s)
  produtos         25 registro(s)
  vendedores        6 registro(s)
```

### MySQL

Com `SQL_AGENT_BACKEND=mysql` e as credenciais no `.env`:

```powershell
python scripts/seed_mysql.py          # cria as tabelas (aborta se já existirem)
python scripts/seed_mysql.py --force  # apaga as tabelas do projeto e recria
```

O script:

- cria o banco `MYSQL_DATABASE` se ele não existir;
- cria as tabelas com `InnoDB`, `utf8mb4` e chaves estrangeiras;
- insere os registros em uma transação (rollback em caso de erro);
- imprime a contagem por tabela.

> `--force` **apaga** as tabelas `clientes`, `vendedores`, `produtos`, `pedidos` e `itens_pedido` do banco configurado. Confira o `MYSQL_DATABASE` antes de rodar.

## Usando o agente no terminal

### Modo interativo

```powershell
python -m sql_agent
```

```text
Agente SQL - perguntas em linguagem natural viram consultas SQL
Banco: SQLite (empresa.db)
Digite /ajuda para ver os comandos ou /sair para encerrar.

pergunta> _
```

| Comando | Ação |
| --- | --- |
| `/ajuda` | Mostra a ajuda |
| `/schema` | Exibe o esquema do banco |
| `/sair` | Encerra o programa |

### Pergunta única

```powershell
python -m sql_agent -q "Qual o faturamento por categoria em 2026?"
```

### Saída em JSON (integração com outros sistemas)

```powershell
python -m sql_agent -q "Quantos pedidos foram entregues?" --json --no-explain
```

```json
{
  "pergunta": "Quantos pedidos foram entregues?",
  "sql": "SELECT COUNT(*) AS total FROM pedidos WHERE status = 'entregue'",
  "explicacao": null,
  "tentativas": 1,
  "colunas": ["total"],
  "linhas": [{ "total": 52 }],
  "total_linhas": 1,
  "truncado": false,
  "tempo_ms": 0.21,
  "avisos": []
}
```

### Outras opções

```powershell
python -m sql_agent --show-schema                 # imprime o esquema e sai
python -m sql_agent --backend mysql               # força o backend MySQL
python -m sql_agent -q "..." --max-rows 20        # limita o resultado
python -m sql_agent -q "..." --max-retries 0      # desativa autocorreção
python -m sql_agent -q "..." --model gpt-4o-mini  # sobrescreve o modelo
python -m sql_agent --help
```

### Exemplos de perguntas

- Quais foram os 5 clientes que mais gastaram em 2026?
- Qual o faturamento por categoria, considerando apenas pedidos não cancelados?
- Qual vendedor teve o maior número de pedidos entregues no último ano?
- Quais clientes nunca fizeram pedidos?
- Qual o ticket médio dos pedidos feitos pelo site?
- Quais produtos estão com estoque abaixo de 20 unidades?
- Qual a evolução mensal do faturamento em 2026?
- Qual cidade concentra mais clientes do segmento Tecnologia?

## Usando a interface Streamlit

```powershell
streamlit run app.py
```

O app abre em <http://localhost:8501> e oferece:

- **Chat** em português com histórico da conversa;
- **SQL gerado** em bloco destacado e **tabela** com o resultado;
- **Explicação** em linguagem natural (pode ser desligada na barra lateral);
- **Perguntas de exemplo** prontas para demonstração;
- **Esquema do banco** em um painel expansível;
- Indicadores de tempo, número de tentativas e truncamento.

A interface usa o mesmo backend configurado no `.env` — SQLite ou MySQL. A conexão é aberta a cada pergunta e fechada em seguida, porque o Streamlit pode executar o script em threads diferentes (conexões de banco não são thread-safe).

## Deploy no Streamlit Cloud

1. Suba o repositório para o GitHub (público).
2. Acesse <https://share.streamlit.io/> e clique em **New app**.
3. Selecione o repositório, a branch e o arquivo principal: **`app.py`**.
4. Em **Advanced settings → Secrets**, cole a configuração no formato TOML:

```toml
LLM_MODEL = "gpt-4o-mini"
LLM_API_KEY = "sk-..."
LLM_BASE_URL = ""

SQL_AGENT_BACKEND = "mysql"
MYSQL_HOST = "seu-servidor.mysql.database.azure.com"
MYSQL_PORT = 3306
MYSQL_USER = "agente_ro"
MYSQL_PASSWORD = "uma-senha-forte"
MYSQL_DATABASE = "diobank"
MYSQL_SSL_CA = "certs/DigiCertGlobalRootCA.crt.pem"  # certificado público versionado no repo (opcional)
```

O `app.py` copia automaticamente os valores de `st.secrets` para as variáveis de ambiente, sem sobrescrever o `.env` local.

> **Atenção:** o arquivo `data/empresa.db` está no `.gitignore`. No Streamlit Cloud, use **MySQL remoto** (recomendado) ou remova a regra e versione o banco de demonstração. Nunca versione o `.env`.

## Segurança

Um LLM pode gerar comandos destrutivos por engano — ou ser induzido a isso por *prompt injection* em dados. O projeto aplica defesa em camadas:

| Camada | Proteção |
| --- | --- |
| **Validação textual** | Aceita apenas uma instrução iniciada por `SELECT`/`WITH`; rejeita `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `PRAGMA`, `ATTACH`, `LOAD_FILE`, `SLEEP`, `FOR UPDATE`, `LOCK IN SHARE MODE` etc., ignorando o conteúdo de literais e comentários |
| **Comentários executáveis** | Rejeita `/*! ... */` (MySQL), que poderiam esconder comandos dentro de um comentário |
| **SQLite somente leitura** | URI `?mode=ro` + `PRAGMA query_only` + *authorizer* que só permite `SELECT`, `READ`, `FUNCTION` e `RECURSIVE` |
| **MySQL somente leitura** | Sessão com `SET SESSION TRANSACTION READ ONLY` e `max_execution_time` (30 s) |
| **Usuário de banco** | A documentação recomenda um usuário com apenas `SELECT` para o agente |
| **Limite de linhas** | `fetchmany(max_rows + 1)` evita carregar tabelas inteiras na memória e sinaliza truncamento |

Nenhuma camada substitui **permissões de banco bem configuradas**. Em produção, use um usuário de leitura dedicado e configure limites de custo/tempo no provedor de LLM.

## Testes

```powershell
pip install -r requirements-dev.txt
python -m pytest -q
```

```text
62 passed
```

Os testes usam um **LLM falso** (*stub*), portanto rodam **sem rede e sem custo de API**. A cobertura inclui:

- introspecção de esquema e listagem de tabelas;
- validação de SQL seguro (incluindo palavras perigosas dentro de strings, `FOR UPDATE` e comentários executáveis do MySQL);
- recusa de escrita pela conexão somente leitura;
- limite e truncamento de resultados;
- caminho feliz do agente (SQL + explicação);
- autocorreção após erro do banco e após resposta em texto puro;
- extração de SQL em blocos markdown e com texto ao redor;
- garantia de que consultas destrutivas **nunca** são executadas;
- falha na explicação sem perder o resultado;
- CLI em modo texto, JSON e `--show-schema`;
- configuração por `.env`, `DATABASE_URL` e validação do backend;
- prompts específicos por dialeto (SQLite e MySQL);
- volumes, determinismo e integridade referencial da massa de dados.

## Decisões técnicas

- **SQLite como padrão + MySQL como backend real**: o SQLite deixa o projeto reproduzível com um comando; o MySQL cobre o requisito de banco remoto sem duplicar a lógica do agente.
- **Prompt por dialeto**: as funções de data mudam entre bancos (`strftime` × `YEAR`/`DATE_FORMAT`). O prompt recebe o dialeto do backend, evitando SQL inválido.
- **API compatível com OpenAI**: um único cliente atende OpenAI, Groq, Gemini, OpenRouter e Ollama, reduzindo acoplamento e permitindo usar modelos locais.
- **Esquema no prompt em vez de *fine-tuning***: é simples, auditável e se adapta a qualquer banco sem treinar nada.
- **Validação fora do LLM**: segurança não pode depender do humor do modelo; a checagem é determinística e testável.
- **Autocorreção com o erro real do banco**: mensagens como `no such column` são o melhor *feedback* possível para o modelo.
- **`LLMClient` como protocolo**: o agente depende de uma interface mínima, o que permite testar todo o pipeline com um stub.
- **Limite via `fetchmany`**: não injeta `LIMIT` na consulta do usuário, preservando a semântica de `ORDER BY`, `LIMIT`/`OFFSET` e subconsultas.
- **Conexão por pergunta no Streamlit**: evita compartilhar conexões entre threads e elimina o risco de "SQLite objects created in a thread can only be used in that same thread".

## Limitações

- O esquema é lido na abertura da conexão; mudanças estruturais durante a sessão exigem reiniciar o agente (ou rodar novamente no Streamlit).
- A qualidade depende do modelo escolhido — modelos pequenos erram mais nomes de colunas.
- Não há memória entre perguntas: cada pergunta é independente.
- O limite de linhas protege a memória, mas não impede consultas caras; em bases grandes, configure *timeouts* no banco (o backend MySQL já define 30 s por consulta).
- A explicação pode falhar (ex.: limite de requisições) sem invalidar o resultado; o aviso aparece no terminal ou na interface.
- O backend MySQL foi validado contra um servidor MySQL real (criação da massa, introspecção, execução de SELECT, bloqueio de escrita e interface Streamlit). Recursos específicos de provedores (SSL mútuo, réplica de leitura, *connection string* proprietária) podem exigir ajustes na conexão.

## Aprendizados

- **O esquema é parte do prompt.** Quanto mais explícitos nomes, tipos e relacionamentos, menor a taxa de alucinação.
- **Validar é diferente de confiar.** O modelo propõe; o código dispõe. Camadas determinísticas são o que tornam o uso seguro.
- **Erro do banco é contexto útil.** Devolver a mensagem real ao modelo resolveu a maioria das falhas de sintaxe/coluna na segunda tentativa.
- **Extração robusta importa.** Modelos adoram responder com cercas de markdown e explicações; normalizar a saída antes de validar evitou retentativas desnecessárias.
- **Testar sem API é possível** ao depender de uma interface (`LLMClient`) em vez do SDK concreto.
- **Documentar faz parte do projeto.** Registrar decisões e dificuldades transforma o código em algo que outra pessoa consegue manter.

O processo completo está em [`docs/diario-de-bordo.md`](docs/diario-de-bordo.md).

## Checklist de entrega do desafio

- [x] Repositório público com o código do agente
- [x] Seção de **demonstração e apresentação** (captura do Streamlit + saída real do terminal)
- [x] Explicação do que é um **agente de IA**
- [x] Contexto do **DioBank**
- [x] Como **obter a chave de API** (OpenAI, Groq, Gemini, OpenRouter e Ollama)
- [x] **Configuração do ambiente** (venv, dependências, `.env`)
- [x] **Configuração de banco de dados remoto** (MySQL local e gerenciado, usuário somente leitura)
- [x] **Criação da massa de dados** (SQLite e MySQL)
- [x] **Construindo o `.env`** — Parte 1 (LLM) e Parte 2 (banco)
- [x] **Agente de terminal** (interativo, pergunta única e JSON)
- [x] **Streamlit agent** com histórico e exemplos
- [x] README detalhado + diário de bordo
- [x] Capturas de tela na pasta `images/`
- [x] Testes automatizados (`62 passed`)

## Próximos passos

- [ ] Memória de conversa para perguntas de acompanhamento ("e em 2025?").
- [ ] Catálogo semântico (descrições de colunas e métricas de negócio) no prompt.
- [ ] Avaliação automatizada com um conjunto de perguntas e SQLs esperados.
- [ ] Gráficos automáticos quando o resultado for temporal.
- [ ] Exportação do resultado em CSV na interface.
- [ ] Suporte a PostgreSQL e SQL Server.
- [ ] *Guardrails* de custo por sessão.

## Licença

Distribuído sob a licença MIT. Veja [LICENSE](LICENSE).

---

Feito com dedicação para o desafio da DIO.
