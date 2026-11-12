"""Orquestração do agente: pergunta -> SQL -> validação -> execução -> resposta."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .database import Database, QueryExecutionError, QueryResult, UnsafeQueryError
from .llm import LLMClient
from .prompts import (
    EXPLAIN_SYSTEM,
    build_explain_prompt,
    build_sql_system_prompt,
    build_sql_user_prompt,
)


class SQLAgentError(RuntimeError):
    """Erro ao produzir uma resposta para a pergunta do usuário."""


class SQLGenerationError(SQLAgentError):
    """O LLM não produziu uma consulta válida dentro do número de tentativas."""


@dataclass
class AgentResponse:
    """Resposta completa do agente para uma pergunta."""

    question: str
    sql: str
    result: QueryResult
    explanation: str | None
    attempts: int
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pergunta": self.question,
            "sql": self.sql,
            "explicacao": self.explanation,
            "tentativas": self.attempts,
            "colunas": self.result.columns,
            "linhas": self.result.as_dicts(),
            "total_linhas": self.result.row_count,
            "truncado": self.result.truncated,
            "tempo_ms": self.result.elapsed_ms,
            "avisos": self.warnings,
        }


def _first_semicolon(text: str) -> int:
    """Índice do primeiro `;` fora de literais/comentários (-1 se não houver)."""

    index = 0
    quote: str | None = None
    while index < len(text):
        char = text[index]

        if quote is not None:
            if char == quote:
                if index + 1 < len(text) and text[index + 1] == quote:
                    index += 2
                    continue
                quote = None
            index += 1
            continue

        if char in ("'", '"', "`"):
            quote = char
            index += 1
        elif char == "-" and text.startswith("--", index):
            newline = text.find("\n", index)
            index = len(text) if newline == -1 else newline + 1
        elif char == "/" and text.startswith("/*", index):
            end = text.find("*/", index + 2)
            index = len(text) if end == -1 else end + 2
        elif char == ";":
            return index
        else:
            index += 1

    return -1


def extract_sql(text: str) -> str:
    """Extrai a consulta SQL da resposta do modelo.

    Aceita respostas com cercas de código, prefixos como "SQL:" e texto ao
    redor da consulta.
    """

    if not text or not text.strip():
        return ""

    fence = re.search(r"```(?:sql)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    candidate = fence.group(1) if fence else text
    candidate = candidate.strip()
    candidate = re.sub(r"^(?:sql|consulta)\s*:\s*", "", candidate, flags=re.IGNORECASE)

    keyword = re.search(r"\b(?:select|with)\b", candidate, flags=re.IGNORECASE)
    if keyword and keyword.start() > 0:
        candidate = candidate[keyword.start() :]

    end = _first_semicolon(candidate)
    if end != -1:
        candidate = candidate[:end]

    return candidate.strip().rstrip(";").strip()


class SQLAgent:
    """Agente que traduz perguntas em SQL e executa a consulta com segurança."""

    def __init__(self, database: Database, llm: LLMClient, max_retries: int = 2) -> None:
        self.database = database
        self.llm = llm
        self.max_retries = max(0, max_retries)

    def ask(self, question: str, *, explain: bool = True) -> AgentResponse:
        """Responde à pergunta, tentando corrigir automaticamente SQLs inválidos."""

        if not question or not question.strip():
            raise ValueError("A pergunta não pode estar vazia.")

        question = question.strip()
        system_prompt = build_sql_system_prompt(
            self.database.schema(), dialect=self.database.dialect
        )

        total_attempts = self.max_retries + 1
        previous_sql: str | None = None
        previous_error: str | None = None
        warnings: list[str] = []

        for attempt in range(1, total_attempts + 1):
            user_prompt = build_sql_user_prompt(question, previous_sql, previous_error)
            raw_answer = self.llm.complete(system_prompt, user_prompt)
            sql = extract_sql(raw_answer)

            try:
                result = self.database.run(sql)
            except (UnsafeQueryError, QueryExecutionError) as exc:
                previous_sql = sql or raw_answer.strip()
                previous_error = str(exc)
                continue

            explanation: str | None = None
            if explain:
                try:
                    explanation = self.llm.complete(
                        EXPLAIN_SYSTEM,
                        build_explain_prompt(
                            question=question,
                            sql=sql,
                            columns=result.columns,
                            rows=result.rows,
                            truncated=result.truncated,
                        ),
                    )
                except Exception as exc:  # noqa: BLE001 - a resposta SQL já é útil
                    warnings.append(f"Não foi possível gerar a explicação: {exc}")

            return AgentResponse(
                question=question,
                sql=sql,
                result=result,
                explanation=explanation,
                attempts=attempt,
                warnings=warnings,
            )

        raise SQLGenerationError(
            "Não foi possível gerar uma consulta válida após "
            f"{total_attempts} tentativa(s). Último erro: {previous_error}. "
            f"Última consulta: {previous_sql}"
        )
