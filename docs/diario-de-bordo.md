# Diário de bordo — Agente de IA para Consultas SQL

Este documento registra o processo de construção do projeto para o desafio da DIO: o que foi planejado, as decisões tomadas, os problemas encontrados e o que aprendi no caminho.

## 1. Contexto

O desafio propõe criar um agente de IA que converta perguntas em linguagem natural para consultas SQL, aplicando os conceitos vistos nas aulas e documentando a experiência.

Mais do que "fazer o modelo escrever SQL", o objetivo que estabeleci foi construir algo **confiável**: um agente que não estrague o banco, que saiba quando errou e que explique o resultado para quem não programa.

## 2. Requisitos que defini

**Funcionais**

- Receber perguntas em português e devolver SQL + resultado.
- Entender o banco sem que eu precisasse escrever o esquema à mão.
- Explicar o resultado em linguagem natural.
- Funcionar no terminal, de forma interativa e também em uma pergunta única.
- Oferecer uma interface web amigável para demonstração.
- Conectar a um banco remoto (MySQL), além do SQLite local.
- Permitir integração futura (saída em JSON).

**Não funcionais**

- Segurança: apenas leitura, sempre.
- Baixo custo de execução: possibilidade de usar Ollama local.
- Testável sem depender de rede ou de chave de API.
- Documentação clara o suficiente para outra pessoa rodar o projeto.

## 3. Etapas do desenvolvimento

### 3.1 Escolha do banco

Comecei com **SQLite** porque:

- não exige servidor nem configuração;
- o banco inteiro é um arquivo, fácil de versionar (quando faz sentido) e de recriar;
- permite demonstrar o projeto com um único comando.

Depois, ao reler o enunciado do desafio, percebi que ele pede explicitamente **configuração de banco de dados remoto**. Em vez de trocar o SQLite (e perder a reprodutibilidade), adicionei um segundo backend:

- `SQL_AGENT_BACKEND=sqlite` → comportamento original, zero configuração;
- `SQL_AGENT_BACKEND=mysql` → conexão com MySQL local ou gerenciado.

Os dois backends compartilham a mesma validação, o mesmo agente e a mesma massa de dados. Só mudam a conexão e o dialeto enviado no prompt.

Para tornar a demonstração realista, criei um banco de uma empresa fictícia com cinco tabelas (`clientes`, `vendedores`, `produtos`, `pedidos`, `itens_pedido`), chaves estrangeiras, índices e dados determinísticos. Deixei **cinco clientes sem pedidos** de propósito, para que perguntas com `NOT EXISTS` e `LEFT JOIN` tivessem significado.

### 3.2 Introspecção do esquema

Em vez de colar o `CREATE TABLE` no prompt manualmente, implementei a leitura automática:

- `sqlite_master` para o DDL de tabelas e views;
- `pragma_foreign_key_list` para os relacionamentos;
- montagem de um texto legível, com nomes reais de tabelas, colunas e tipos.

Assim o agente se adapta a qualquer banco SQLite sem alteração de código.

### 3.3 Prompt

O system prompt ficou com regras explícitas:

- responder **somente** com SQL, sem markdown;
- usar apenas `SELECT`/`WITH`;
- não inventar tabelas ou colunas;
- tratar datas como texto ISO;
- usar `LIMIT` para "top N";
- buscar textos com `LIKE` + `LOWER()`;
- não pedir esclarecimentos: assumir a interpretação mais natural.

Incluí também a data atual, porque perguntas como "este ano" e "último mês" dependem disso.

### 3.4 Segurança em camadas

Essa foi a parte que mais exigiu cuidado. O modelo pode gerar `DROP TABLE` por engano — ou ser induzido a isso por um texto malicioso vindo dos dados. A solução foi não confiar em uma única barreira:

1. **Validação textual** (`validate_sql`): apenas uma instrução, começando por `SELECT`/`WITH`, com uma lista de palavras proibidas. Antes de procurar palavras-chave, removo comentários e literais de texto para não gerar falso positivo (por exemplo, `SELECT 'update'` é inofensivo).
2. **Conexão `mode=ro`**: o SQLite abre o arquivo em modo somente leitura.
3. **`PRAGMA query_only` + authorizer**: a conexão só autoriza ações de leitura (`SELECT`, `READ`, `FUNCTION`, `RECURSIVE`).
4. **Limite de linhas**: `fetchmany(max_rows + 1)`, sem alterar a consulta original.

### 3.5 Autocorreção

A primeira versão do agente simplesmente falhava quando o SQL dava erro. Percebi que a mensagem do banco é um excelente *feedback*: `no such column: c.nome_cliente` diz exatamente o que corrigir.

Implementei um laço: pergunta + SQL anterior + erro → nova tentativa (padrão: 2 tentativas extras). O resultado melhorou bastante em casos de nomes de colunas e sintaxe.

### 3.6 Extração e normalização do SQL

Modelos frequentemente respondem com cercas de markdown, prefixos como `SQL:` ou uma frase antes da consulta. Criei `extract_sql()` para:

- pegar o conteúdo de blocos ```` ```sql ````;
- remover prefixos;
- descartar texto antes da primeira palavra-chave;
- cortar no primeiro `;` **fora** de strings e comentários.

Isso reduziu retentativas que aconteciam apenas por causa de formatação.

### 3.7 CLI e resposta

A interface de linha de comando oferece:

- modo interativo com `/ajuda`, `/schema` e `/sair`;
- pergunta única (`-q`);
- saída em JSON (`--json`);
- `--show-schema` para inspecionar o banco sem precisar configurar o LLM;
- `--backend sqlite|mysql` para alternar o banco;
- tabela ASCII com truncamento de células longas.

A explicação é uma segunda chamada ao LLM, com o resultado em mãos e a instrução de usar **apenas** os dados fornecidos. Se essa chamada falhar, o SQL e a tabela continuam válidos — apenas um aviso é exibido.

### 3.8 Backend MySQL

Implementei `MySQLDatabase` com o mesmo contrato de `SQLiteDatabase` (`schema`, `tables`, `run`, `close`, `label`, `dialect`):

- conexão via **PyMySQL**, com `utf8mb4` e timeouts de leitura/escrita;
- sessão somente leitura (`SET SESSION TRANSACTION READ ONLY`) e limite de execução (`max_execution_time`, com fallback para `max_statement_time` do MariaDB);
- introspecção por `information_schema` (colunas, tipos, chaves e comentários), montando um DDL textual para o prompt;
- suporte opcional a TLS via `MYSQL_SSL_CA`, necessário em vários provedores gerenciados;
- erros traduzidos para exceções do projeto (`DatabaseConnectionError`, `DatabaseConfigurationError`, `QueryExecutionError`).

A configuração aceita variáveis separadas (`MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`, `MYSQL_SSL_CA`) ou uma `DATABASE_URL` completa, que tem prioridade.

### 3.9 Dialeto no prompt

O primeiro prompt era específico de SQLite (`strftime`, `date('now')`). Ao apontar para MySQL, esse texto induziria o modelo ao erro. Refatorei os prompts para receberem o dialeto do backend:

- SQLite: `strftime('%Y', coluna)`, comparações com texto ISO;
- MySQL: `YEAR(coluna)`, `CURDATE()`, `DATE_FORMAT(coluna, '%Y-%m')` e faixas de data que aproveitam índice.

A escolha é automática: cada backend expõe `dialect`, e o `SQLAgent` usa esse valor ao montar o system prompt.

### 3.10 Massa de dados compartilhada

Extraí a geração dos dados para `build_sample_data()` e os esquemas para `SQLITE_SCHEMA` e `MYSQL_SCHEMA_STATEMENTS`. O script `scripts/seed_mysql.py`:

- cria o banco se ele não existir;
- cria as cinco tabelas em InnoDB/utf8mb4;
- insere tudo em uma transação;
- exige `--force` para apagar tabelas existentes, protegendo dados por acidente.

Assim, uma pergunta feita no SQLite e a mesma pergunta feita no MySQL retornam os mesmos números — o que é ótimo para comparar dialetos e testar a lógica.

### 3.11 Interface Streamlit

Criei `app.py` com:

- chat em português e histórico da conversa;
- SQL em bloco de código, tabela de resultados e explicação;
- perguntas de exemplo, painel com o esquema e indicadores de tempo/tentativas;
- leitura de `st.secrets` para funcionar no Streamlit Cloud sem alterar o `.env`;
- conexão aberta por pergunta e fechada em seguida.

Essa última decisão nasceu de um bug real: a primeira versão guardava a conexão em `@st.cache_resource` e o Streamlit executou o script em outra thread, disparando `SQLite objects created in a thread can only be used in that same thread`. Como conexões SQLite e PyMySQL não são thread-safe, passei a abrir e fechar a conexão dentro da própria execução do script.

## 4. Dificuldades e soluções

| Dificuldade | Como resolvi |
| --- | --- |
| O *authorizer* bloqueava a introspecção (`not authorized` ao ler `pragma_foreign_key_list`) | Passei a ler o esquema **antes** de instalar o authorizer e cacheei o resultado, já que a conexão é somente leitura e o esquema não muda na sessão |
| O modelo respondia com markdown e texto ao redor | Implementei `extract_sql()` com suporte a cercas, prefixos e corte seguro no `;` |
| Falso positivo ao bloquear `update` dentro de uma string | A validação remove literais e comentários antes de procurar palavras-chave |
| Consultas com erro derrubavam a resposta | Laço de autocorreção com o erro real do banco |
| Testar o pipeline sem gastar tokens | Criei a interface `LLMClient` e um stub nos testes |
| `--show-schema` exigia chave de API | Separei a abertura do banco da construção do cliente LLM |
| Explicação falhando descartava um resultado já pronto | A falha vira um aviso; o SQL e a tabela são preservados |
| O MySQL local aceitava TCP na 3306, mas o *handshake* expirava | A causa era a falta do pacote `cryptography` (exigido pelo `caching_sha2_password`). Instalei a dependência e validei o backend contra um servidor MySQL real, usando uma instância temporária na porta 3307 |
| `SQLite objects created in a thread can only be used in that same thread` no Streamlit | Removi o cache de conexão e passo a abrir/fechar o banco em cada execução do script |
| Comentários executáveis do MySQL (`/*! ... */`) escondiam SQL da validação | A validação textual agora rejeita `/*!` explicitamente |
| Prompt de SQLite gerando SQL inválido no MySQL | Prompts separados por dialeto, escolhidos automaticamente pelo backend |
| Capturar a tela do app em execução | Usei o Edge em modo *headless* com o Chrome DevTools Protocol para preencher o chat e fotografar a página real |

## 5. Resultados

- **62 testes automatizados** cobrindo validação, banco, agente, configuração, prompts e CLI.
- Dois backends funcionais: **SQLite** (padrão, zero configuração) e **MySQL** (local ou remoto).
- Backend MySQL validado de ponta a ponta contra um servidor real: criação do banco, carga dos dados, introspecção, execução, bloqueio de escrita e Streamlit.
- Banco de exemplo reproduzível: 40 clientes, 25 produtos, 120 pedidos e 289 itens — com os mesmos resultados nos dois bancos.
- Nenhuma consulta destrutiva é executada, mesmo quando o modelo insiste.
- Duas interfaces: **terminal** e **Streamlit**, com o mesmo agente e a mesma configuração.
- Projeto roda com OpenAI, Groq, Gemini, OpenRouter ou Ollama, trocando apenas três variáveis de ambiente.

## 6. O que aprendi

1. **Engenharia de prompt é engenharia de contexto.** Regras curtas, específicas e com o esquema certo valem mais do que um prompt gigante e genérico.
2. **Segurança não se delega ao modelo.** A parte determinística (validar, abrir somente leitura, limitar linhas) é o que permite dormir tranquilo.
3. **Feedback melhora a resposta.** Devolver o erro do banco é mais eficaz do que pedir "tente novamente".
4. **Normalizar a saída é essencial.** Grande parte das falhas era de formatação, não de raciocínio.
5. **Testes com stub de LLM são rápidos e baratos.** O pipeline inteiro pode ser validado sem rede.
6. **Dialeto não é detalhe.** `strftime` e `YEAR` parecem intercambiáveis até o banco recusar a consulta; o prompt precisa saber onde está rodando.
7. **Threads mudam tudo em aplicações web.** Um objeto que funciona no terminal pode falhar dentro do Streamlit; conexões devem viver o mínimo possível.
8. **Documentar é revisar.** Escrever este diário expôs decisões que eu não tinha verbalizado e pontos que ainda podem melhorar.

## 7. Próximos passos

- Suporte a PostgreSQL e SQL Server.
- Memória de conversa para perguntas de acompanhamento.
- Catálogo semântico com métricas de negócio.
- Avaliação automatizada com perguntas e SQLs de referência.
- Gráficos automáticos e exportação em CSV na interface.
- *Timeouts* e limites de custo por sessão.
