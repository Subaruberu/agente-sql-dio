"""Carregamento de configuração via variáveis de ambiente (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse


@dataclass(frozen=True)
class Settings:
    """Configuração do agente.

    Os valores vêm de variáveis de ambiente (veja `.env.example`) e podem ser
    sobrescritos pelos argumentos de linha de comando.
    """

    backend: str
    db_path: Path
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_database: str
    mysql_ssl_ca: str
    model: str
    api_key: str
    base_url: str | None
    temperature: float
    max_rows: int
    max_retries: int

    @property
    def database_label(self) -> str:
        if self.backend == "mysql":
            return f"MySQL ({self.mysql_user}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database})"
        return f"SQLite ({self.db_path.name})"


def _parse_database_url(url: str) -> dict[str, object]:
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()

    if scheme not in {"mysql", "mysql+pymysql", "mariadb", "mariadb+pymysql"}:
        raise ValueError(
            "DATABASE_URL deve começar com mysql:// ou mysql+pymysql:// "
            f"(recebido: {scheme or 'vazio'})."
        )

    database = parsed.path.lstrip("/")
    if not parsed.hostname or not database:
        raise ValueError(
            "DATABASE_URL inválida. Formato esperado: "
            "mysql://usuario:senha@host:3306/banco"
        )

    return {
        "backend": "mysql",
        "host": parsed.hostname,
        "port": parsed.port or 3306,
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "database": unquote(database),
    }


def load_settings(
    *,
    backend: str | None = None,
    db_path: str | Path | None = None,
    model: str | None = None,
    base_url: str | None = None,
    max_rows: int | None = None,
    max_retries: int | None = None,
) -> Settings:
    """Monta a configuração a partir do ambiente, aplicando os overrides."""

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:  # pragma: no cover - dependência opcional em tempo de execução
        pass

    mysql = {
        "backend": os.getenv("SQL_AGENT_BACKEND", "sqlite").strip().lower(),
        "host": os.getenv("MYSQL_HOST", "localhost").strip(),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root").strip(),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "diobank").strip(),
        "ssl_ca": os.getenv("MYSQL_SSL_CA", "").strip(),
    }

    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        mysql.update(_parse_database_url(database_url))

    if backend:
        mysql["backend"] = backend.strip().lower()

    if mysql["backend"] not in {"sqlite", "mysql"}:
        raise ValueError("SQL_AGENT_BACKEND deve ser 'sqlite' ou 'mysql'.")

    return Settings(
        backend=str(mysql["backend"]),
        db_path=Path(db_path or os.getenv("SQL_AGENT_DB", "data/empresa.db")),
        mysql_host=str(mysql["host"]),
        mysql_port=int(mysql["port"]),
        mysql_user=str(mysql["user"]),
        mysql_password=str(mysql["password"]),
        mysql_database=str(mysql["database"]),
        mysql_ssl_ca=str(mysql["ssl_ca"]),
        model=model or os.getenv("LLM_MODEL", "gpt-4o-mini"),
        api_key=os.getenv("LLM_API_KEY", "").strip(),
        base_url=(base_url or os.getenv("LLM_BASE_URL") or "").strip() or None,
        temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
        max_rows=int(max_rows if max_rows is not None else os.getenv("SQL_AGENT_MAX_ROWS", "100")),
        max_retries=int(
            max_retries if max_retries is not None else os.getenv("SQL_AGENT_MAX_RETRIES", "2")
        ),
    )
