from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:  # pragma: no cover
    from .config import Settings


class UnsafeQueryError(ValueError):
    """A consulta gerada não é uma leitura segura e não deve ser executada."""


class QueryExecutionError(RuntimeError):
    """O banco recusou ou não conseguiu executar a consulta."""


class DatabaseConfigurationError(RuntimeError):
    """Configuração de banco ausente ou inválida."""


class DatabaseConnectionError(RuntimeError):
    """Não foi possível abrir a conexão com o banco."""


# Palavras-chave que nunca podem aparecer em uma consulta de leitura.
# `replace` fica de fora de propósito: é também uma função de string válida.
FORBIDDEN_KEYWORDS = frozenset(
    {
        "alter",
        "analyze",
        "attach",
        "begin",
        "benchmark",
        "commit",
        "create",
        "delete",
        "detach",
        "drop",
        "dumpfile",
        "insert",
        "load_extension",
        "load_file",
        "outfile",
        "pragma",
        "reindex",
        "release",
        "rollback",
        "savepoint",
        "sleep",
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

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


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


class Database(Protocol):
    """Contrato comum entre os backends."""

    max_rows: int
    dialect: str

    def schema(self) -> str: ...

    def tables(self) -> list[str]: ...

    def run(self, sql: str, max_rows: int | None = None) -> QueryResult: ...

    def close(self) -> None: ...

    @property
    def label(self) -> str: ...


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

    # Comentários executáveis do MySQL (`/*! ... */`) escondem SQL de olhos
    # ingênuos e não têm uso legítimo em uma consulta gerada pelo agente.
    if "/*!" in cleaned:
        raise UnsafeQueryError("Comentários executáveis (/*! ... */) não são permitidos.")

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

    if re.search(r"\bfor\s+update\b", scan) or re.search(r"\block\s+in\s+share\s+mode\b", scan):
        raise UnsafeQueryError("Consultas que bloqueiam linhas (FOR UPDATE / LOCK) não são permitidas.")

    return cleaned


def _authorizer(
    action: int, arg1: str | None, arg2: str | None, dbname: str | None, trigger: str | None
) -> int:
    """Autoriza somente ações de leitura na conexão SQLite."""

    if action in _ALLOWED_ACTIONS:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


class SQLiteDatabase:
    """Conexão somente leitura a um arquivo SQLite."""

    dialect = "sqlite"

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

    @property
    def label(self) -> str:
        return f"SQLite ({self.path.name})"

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
        try:
            cursor = self._conn.execute(safe_sql)
            fetched = cursor.fetchmany(limit + 1)
            columns = [description[0] for description in (cursor.description or [])]
        except sqlite3.Error as exc:
            raise QueryExecutionError(str(exc)) from exc
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

    def __enter__(self) -> "SQLiteDatabase":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class MySQLDatabase:
    """Conexão somente leitura a um banco MySQL/MariaDB."""

    dialect = "mysql"

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        max_rows: int = 100,
        connect_timeout: int = 10,
        ssl_ca: str = "",
    ) -> None:
        if not host or not user or not database:
            raise DatabaseConfigurationError(
                "Configure MYSQL_HOST, MYSQL_USER e MYSQL_DATABASE "
                "(ou use DATABASE_URL) para conectar ao MySQL."
            )

        try:
            import pymysql
        except ImportError as exc:  # pragma: no cover - depende do ambiente
            raise DatabaseConfigurationError(
                "Pacote 'PyMySQL' não instalado. Rode: pip install -r requirements.txt"
            ) from exc

        self._pymysql = pymysql
        self.host = host
        self.port = port
        self.user = user
        self.database = database
        self.max_rows = max(1, max_rows)

        try:
            self._conn = pymysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                charset="utf8mb4",
                autocommit=True,
                connect_timeout=connect_timeout,
                read_timeout=60,
                write_timeout=60,
                **({"ssl": {"ca": ssl_ca}} if ssl_ca else {}),
            )
        except pymysql.MySQLError as exc:
            raise DatabaseConnectionError(
                f"Não foi possível conectar ao MySQL em {host}:{port}/{database}: {exc}"
            ) from exc

        self._configure_read_only_session()
        self._table_names = self._read_tables()
        self._schema_text = self._read_schema()

    @property
    def label(self) -> str:
        return f"MySQL ({self.user}@{self.host}:{self.port}/{self.database})"

    def _configure_read_only_session(self) -> None:
        """Torna a sessão somente leitura e limita o tempo das consultas."""

        with self._conn.cursor() as cursor:
            try:
                cursor.execute("SET SESSION TRANSACTION READ ONLY")
            except self._pymysql.MySQLError:
                pass
            try:
                cursor.execute("SET SESSION max_execution_time = 30000")  # milissegundos
            except self._pymysql.MySQLError:
                try:
                    cursor.execute("SET SESSION max_statement_time = 30")  # segundos (MariaDB)
                except self._pymysql.MySQLError:
                    pass

    # -- introspecção -----------------------------------------------------
    def _read_tables(self) -> list[str]:
        with self._conn.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = DATABASE() "
                "AND table_type IN ('BASE TABLE', 'VIEW') "
                "ORDER BY table_name"
            )
            return [str(row[0]) for row in cursor.fetchall()]

    def _read_schema(self) -> str:
        if not self._table_names:
            return "(o banco não possui tabelas)"

        blocks: list[str] = []
        with self._conn.cursor() as cursor:
            for table in self._table_names:
                cursor.execute(
                    "SELECT column_name, column_type, is_nullable, column_key, extra, column_comment "
                    "FROM information_schema.columns "
                    "WHERE table_schema = DATABASE() AND table_name = %s "
                    "ORDER BY ordinal_position",
                    (table,),
                )
                columns = cursor.fetchall()

                cursor.execute(
                    "SELECT column_name, referenced_table_name, referenced_column_name "
                    "FROM information_schema.key_column_usage "
                    "WHERE table_schema = DATABASE() AND table_name = %s "
                    "AND referenced_table_name IS NOT NULL "
                    "ORDER BY ordinal_position",
                    (table,),
                )
                foreign_keys = cursor.fetchall()

                lines = [f"-- TABLE: {table}", f"CREATE TABLE `{table}` ("]
                definitions = []
                for name, column_type, nullable, key, extra, comment in columns:
                    definition = f"  `{name}` {column_type}"
                    if nullable == "NO":
                        definition += " NOT NULL"
                    if "auto_increment" in (extra or "").lower():
                        definition += " AUTO_INCREMENT"
                    if key == "PRI":
                        definition += " PRIMARY KEY"
                    elif key == "UNI":
                        definition += " UNIQUE"
                    if comment:
                        definition += f"  -- {comment}"
                    definitions.append(definition)
                lines.append(",\n".join(definitions))
                lines.append(");")

                for column, referenced_table, referenced_column in foreign_keys:
                    lines.append(
                        f"-- FK: {table}.{column} -> {referenced_table}.{referenced_column}"
                    )
                blocks.append("\n".join(lines))

        return "\n\n".join(blocks)

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
        try:
            with self._conn.cursor() as cursor:
                cursor.execute(safe_sql)
                fetched = cursor.fetchmany(limit + 1)
                columns = [description[0] for description in (cursor.description or [])]
        except self._pymysql.MySQLError as exc:
            raise QueryExecutionError(str(exc)) from exc
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

    def __enter__(self) -> "MySQLDatabase":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def create_database(settings: "Settings") -> Database:
    """Cria o backend configurado (`sqlite` ou `mysql`)."""

    if settings.backend == "mysql":
        return MySQLDatabase(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            max_rows=settings.max_rows,
            ssl_ca=settings.mysql_ssl_ca,
        )
    return SQLiteDatabase(settings.db_path, max_rows=settings.max_rows)


def quote_identifier(name: str) -> str:
    """Escapa um identificador SQL com segurança (usado pelos scripts)."""

    if _IDENTIFIER.match(name):
        return name
    return "`" + name.replace("`", "``") + "`"
