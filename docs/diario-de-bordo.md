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
- Permitir integração futura (saída em JSON).

**Não funcionais**

- Segurança: apenas leitura, sempre.
- Baixo custo de execução: possibilidade de usar Ollama local.
- Testável sem depender de rede ou de chave de API.
- Documentação clara o suficiente para outra pessoa rodar o projeto.

## 3. Etapas do desenvolvimento

### 3.1 Escolha do banco

Optei por **SQLite** porque:

- não exige servidor nem configuração;
- o banco inteiro é um arquivo, fácil de versionar (quando faz sentido) e de recriar;
- permite demonstrar o projeto com um único comando.

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
- tabela ASCII com truncamento de células longas.

A explicação é uma segunda chamada ao LLM, com o resultado em mãos e a instrução de usar **apenas** os dados fornecidos. Se essa chamada falhar, o SQL e a tabela continuam válidos — apenas um aviso é exibido.

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

## 5. Resultados

- **40 testes automatizados** cobrindo validação, banco, agente e CLI.
- Banco de exemplo reproduzível: 40 clientes, 25 produtos, 120 pedidos e 289 itens.
- Nenhuma consulta destrutiva é executada, mesmo quando o modelo insiste.
- Projeto roda com OpenAI, Groq, Gemini, OpenRouter ou Ollama, trocando apenas três variáveis de ambiente.

## 6. O que aprendi

1. **Engenharia de prompt é engenharia de contexto.** Regras curtas, específicas e com o esquema certo valem mais do que um prompt gigante e genérico.
2. **Segurança não se delega ao modelo.** A parte determinística (validar, abrir somente leitura, limitar linhas) é o que permite dormir tranquilo.
3. **Feedback melhora a resposta.** Devolver o erro do banco é mais eficaz do que pedir "tente novamente".
4. **Normalizar a saída é essencial.** Grande parte das falhas era de formatação, não de raciocínio.
5. **Testes com stub de LLM são rápidos e baratos.** O pipeline inteiro pode ser validado sem rede.
6. **Documentar é revisar.** Escrever este diário expôs decisões que eu não tinha verbalizado e pontos que ainda podem melhorar.

## 7. Próximos passos

- Suporte a PostgreSQL com dialeto configurável.
- Memória de conversa para perguntas de acompanhamento.
- Catálogo semântico com métricas de negócio.
- Avaliação automatizada com perguntas e SQLs de referência.
- Interface web para facilitar demonstrações.
- *Timeouts* e limites de custo por consulta.
