"""Prompts enviados ao LLM.

Manter os prompts isolados facilita ajustar o comportamento sem tocar na
orquestração do agente e deixa explícitas as regras de negócio.
"""

from __future__ import annotations

from datetime import date
from typing import Sequence

SQL_SYSTEM_TEMPLATE = """Você é um engenheiro de dados especialista em {dialect_name}.
Sua tarefa é converter a pergunta do usuário em UMA consulta {dialect_name} correta.

## Regras obrigatórias
1. Responda APENAS com a consulta SQL. Sem explicações, sem markdown, sem cercas de código.
2. Use apenas SELECT (ou WITH ... SELECT). Nunca escreva comandos que alterem dados ou estrutura.
3. Use somente tabelas e colunas presentes no esquema abaixo. Nunca invente nomes.
4. Escreva nomes de tabelas/colunas exatamente como no esquema.
5. Use aliases curtos e legíveis; ao agregar, dê nomes claros às colunas (ex.: total_pedidos).
6. Para "top N", "maiores", "mais recentes": use ORDER BY ... LIMIT N.
7. Buscas textuais: prefira LIKE com LOWER() para ignorar maiúsculas/minúsculas.
8. Valores monetários: arredonde resultados com ROUND(valor, 2) quando fizer sentido.
9. Se a pergunta for ambígua, adote a interpretação mais natural e não peça esclarecimentos.
10. Se a pergunta não puder ser respondida com o esquema, gere a consulta mais próxima possível.
11. Não use ponto e vírgula no final.

## Regras específicas do dialeto
{dialect_rules}

## Data de hoje
{today}

## Esquema do banco ({dialect_name})
{schema}
"""

DIALECTS = {
    "sqlite": {
        "name": "SQLite",
        "rules": (
            "- Datas estão armazenadas como texto ISO (YYYY-MM-DD). Use date('now'),\n"
            "  strftime('%Y', coluna) e comparações com strings no formato 'YYYY-MM-DD'.\n"
            "- Para extrair o mês: strftime('%m', coluna). Para o dia: strftime('%d', coluna).\n"
            "- Identificadores podem ser escritos sem aspas; use aspas duplas só se necessário."
        ),
    },
    "mysql": {
        "name": "MySQL",
        "rules": (
            "- Datas usam o tipo DATE. Use CURDATE(), YEAR(coluna), MONTH(coluna)\n"
            "  e DATE_FORMAT(coluna, '%Y-%m') para agrupar por mês.\n"
            "- Para intervalos, prefira coluna >= '2026-01-01' AND coluna < '2027-01-01'\n"
            "  (mais eficiente para o índice do que YEAR(coluna) = 2026).\n"
            "- Identificadores podem ser escritos sem aspas; use crase (`nome`) apenas\n"
            "  quando o nome tiver caracteres especiais.\n"
            "- Não use funções exclusivas do SQLite, como strftime ou julianday."
        ),
    },
}

EXPLAIN_SYSTEM = """Você é um analista de dados que conversa com pessoas de negócio.
Responda em português do Brasil, de forma direta e cordial, em no máximo 3 frases.
Use SOMENTE os dados fornecidos (pergunta, consulta e resultado). Não invente números.
Se o resultado estiver vazio, diga que a consulta não retornou registros.
Se os dados estiverem truncados, avise que a lista é parcial."""


def build_sql_system_prompt(
    schema: str, today: date | None = None, dialect: str = "sqlite"
) -> str:
    spec = DIALECTS.get(dialect.strip().lower(), DIALECTS["sqlite"])
    return SQL_SYSTEM_TEMPLATE.format(
        schema=schema.strip(),
        today=(today or date.today()).isoformat(),
        dialect_name=spec["name"],
        dialect_rules=spec["rules"],
    )


def build_sql_user_prompt(
    question: str,
    previous_sql: str | None = None,
    previous_error: str | None = None,
) -> str:
    parts = [f"Pergunta do usuário: {question.strip()}"]
    if previous_sql:
        parts.append(f"Consulta SQL da tentativa anterior:\n{previous_sql.strip()}")
    if previous_error:
        parts.append(f"Erro retornado pelo banco:\n{previous_error.strip()}")
    if previous_sql or previous_error:
        parts.append("Corrija o problema acima e responda apenas com o SQL corrigido.")
    return "\n\n".join(parts)


def format_rows_preview(
    columns: Sequence[str],
    rows: Sequence[Sequence[object]],
    max_rows: int = 10,
    max_cell: int = 80,
) -> str:
    """Formata uma prévia do resultado em texto simples para o prompt de explicação."""

    if not rows:
        return "(nenhuma linha)"

    def cell(value: object) -> str:
        text = "NULL" if value is None else str(value)
        text = text.replace("\n", " ").replace("|", "/")
        return text[:max_cell] + ("..." if len(text) > max_cell else "")

    lines = [" | ".join(columns), " | ".join("---" for _ in columns)]
    for row in rows[:max_rows]:
        lines.append(" | ".join(cell(value) for value in row))
    return "\n".join(lines)


def build_explain_prompt(
    question: str,
    sql: str,
    columns: Sequence[str],
    rows: Sequence[Sequence[object]],
    truncated: bool,
    max_rows: int = 10,
) -> str:
    preview = format_rows_preview(columns, rows, max_rows=max_rows)
    truncation_note = (
        "O resultado foi truncado; há mais linhas do que as exibidas."
        if truncated
        else "O resultado não foi truncado."
    )
    return (
        f"Pergunta: {question.strip()}\n\n"
        f"Consulta SQL executada:\n{sql.strip()}\n\n"
        f"Resultado ({len(rows)} linha(s) exibida(s), colunas: {', '.join(columns) or 'nenhuma'}):\n"
        f"{preview}\n\n"
        f"{truncation_note}\n\n"
        "Responda à pergunta do usuário com base nesse resultado."
    )
