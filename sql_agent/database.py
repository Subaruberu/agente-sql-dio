"""Acesso somente leitura ao banco SQLite, com introspecção de esquema.

A segurança é feita em três camadas:

1. Validação textual: apenas `SELECT`/`WITH ... SELECT` de uma única instrução.
2. Conexão aberta com `mode=ro` (o arquivo é aberto em modo somente leitura).
3. `PRAGMA query_only = ON` + authorizer que nega qualquer operação que não
   seja leitura, função ou CTE recursiva.
"""

from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class UnsafeQueryError(ValueError):
    """A consulta gerada não é uma leitura segura e não deve ser executada."""


# Palavras-chave que nunca podem aparecer em uma consulta de leitura.
# `replace` fica de fora de propósito: é também uma função de string válida.
FORBIDDEN_KEYWORDS = frozenset(
    {
        "alter",
        "analyze",
        "attach",
        "begin",
        "commit",
        "create",
        "delete",
        "detach",
        "drop",
        "insert",
        "load_extension",
        "pragma",
        "reindex",
        "release",
        "rollback",
        "savepoint",
        "truncate",
        "update",
        "vacuum",
    }
)

_ALLOWED_ACTIONS = frozenset(
    {
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_FUNCTION,
        sqlite3.SQLITE_RECURSIVE,
    }
)


@dataclass
class QueryResult:
    """Resultado de uma consulta executada."""

    columns: list[str]
    rows: list[tuple[Any, ...]]
    elapsed_ms: float
    truncated: bool = False

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def as_dicts(self) -> list[dict[str, Any]]:
        return [dict(zip(self.columns, row)) for row in self.rows]


def _strip_literals_and_comments(sql: str) -> str:
    """Remove comentários e literais para inspecionar apenas o "código" SQL."""

    result: list[str] = []
    index = 0
    length = len(sql)

    while index < length:
        char = sql[index]

        if char == "-" and sql.startswith("--", index):
            newline = sql.find("\n", index)
            if newline == -1:
                break
            index = newline + 1
            result.append(" ")
        elif char == "/" and sql.startswith("/*", index):
            end = sql.find("*/", index + 2)
            if end == -1:
                break
            index = end + 2
            result.append(" ")
        elif char in ("'", '"', "`"):
            quote = char
            index += 1
            while index < length:
                if sql[index] == quote:
                    # Aspas duplicadas representam um escape dentro do literal.
                    if index + 1 < length and sql[index + 1] == quote:
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            result.append(" '' ")
        else:
            result.append(char)
            index += 1

    return "".join(result)


def validate_sql(sql: str) -> str:
    """Valida e normaliza uma consulta, garantindo que seja apenas leitura.

    Retorna a consulta sem o ponto e vírgula final. Levanta `UnsafeQueryError`
    quando a consulta não é um SELECT único e seguro.
    """

    if not isinstance(sql, str):
        raise UnsafeQueryError("A consulta SQL deve ser um texto.")

    cleaned = sql.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip().rstrip(";").strip()

    if not cleaned:
        raise UnsafeQueryError("A consulta SQL está vazia.")

    scan = _strip_literals_and_comments(cleaned).lower()

    if ";" in scan:
        raise UnsafeQueryError("Apenas uma instrução SQL por vez é permitida.")

    first_token = re.match(r"\s*([a-z_]+)", scan)
    if not first_token or first_token.group(1) not in {"select", "with"}:
        raise UnsafeQueryError(
            "Apenas consultas de leitura (SELECT ou WITH ... SELECT) são permitidas."
        )

    tokens = set(re.findall(r"\b[a-z_]+\b", scan))
    forbidden = tokens & FORBIDDEN_KEYWORDS
    if forbidden:
        listed = ", ".join(sorted(forbidden))
        raise UnsafeQueryError(f"A consulta contém operações não permitidas: {listed}.")

    return cleaned


def _authorizer(action: int, arg1: str | None, arg2: str | None, dbname: str | None, trigger: str | None) -> int:
    """Autoriza somente ações de leitura na conexão SQLite."""

    if action in _ALLOWED_ACTIONS:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


class Database:
    """Conexão somente leitura a um arquivo SQLite."""

    def __init__(self, path: str | Path, max_rows: int = 100) -> None:
        self.path = Path(path).expanduser().resolve()
        if not self.path.is_file():
            raise FileNotFoundError(f"Banco de dados não encontrado: {self.path}")

        self.max_rows = max(1, max_rows)
        uri = f"{self.path.as_uri()}?mode=ro"
        self._conn = sqlite3.connect(uri, uri=True)
        self._conn.row_factory = sqlite3.Row
        # Precisa ser executado antes de instalar o authorizer, que nega PRAGMA.
        self._conn.execute("PRAGMA query_only = ON")

        # A introspecção usa PRAGMAs e, por isso, roda antes do authorizer.
        # O esquema é lido uma única vez: o arquivo é aberto em modo somente
        # leitura, então não muda durante a sessão.
        self._schema_text = self._read_schema()
        self._table_names = self._read_tables()

        self._conn.set_authorizer(_authorizer)

    # -- introspecção -----------------------------------------------------
    def _read_schema(self) -> str:
        objects = self._conn.execute(
            "SELECT name, type, sql FROM sqlite_master "
            "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' "
            "ORDER BY type DESC, name"
        ).fetchall()

        if not objects:
            return "(o banco não possui tabelas)"

        blocks: list[str] = []
        for obj in objects:
            lines = [
                f"-- {str(obj['type']).upper()}: {obj['name']}",
                f"{(obj['sql'] or '').strip()};",
            ]
            foreign_keys = self._conn.execute(
                'SELECT "from", "table", "to" FROM pragma_foreign_key_list(?)',
                (obj["name"],),
            ).fetchall()
            for fk in foreign_keys:
                lines.append(f"-- FK: {obj['name']}.{fk['from']} -> {fk['table']}.{fk['to']}")
            blocks.append("\n".join(lines))

        return "\n\n".join(blocks)

    def _read_tables(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
        return [str(row["name"]) for row in rows]

    def schema(self) -> str:
        """Devolve o esquema do banco em formato textual (DDL + chaves estrangeiras)."""

        return self._schema_text

    def tables(self) -> list[str]:
        """Lista os nomes das tabelas e views do banco."""

        return list(self._table_names)

    # -- execução ---------------------------------------------------------
    def run(self, sql: str, max_rows: int | None = None) -> QueryResult:
        """Valida e executa uma consulta de leitura, limitando as linhas retornadas."""

        safe_sql = validate_sql(sql)
        limit = max(1, max_rows if max_rows is not None else self.max_rows)

        started = time.perf_counter()
        cursor = self._conn.execute(safe_sql)
        fetched = cursor.fetchmany(limit + 1)
        columns = [description[0] for description in (cursor.description or [])]
        elapsed_ms = (time.perf_counter() - started) * 1000

        truncated = len(fetched) > limit
        rows = [tuple(row) for row in fetched[:limit]]

        return QueryResult(
            columns=columns,
            rows=rows,
            elapsed_ms=round(elapsed_ms, 2),
            truncated=truncated,
        )

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
