"""Carregamento de configuração via variáveis de ambiente (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Configuração do agente.

    Os valores vêm de variáveis de ambiente (veja `.env.example`) e podem ser
    sobrescritos pelos argumentos de linha de comando.
    """

    db_path: Path
    model: str
    api_key: str
    base_url: str | None
    temperature: float
    max_rows: int
    max_retries: int


def load_settings(
    *,
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

    return Settings(
        db_path=Path(db_path or os.getenv("SQL_AGENT_DB", "data/empresa.db")),
        model=model or os.getenv("LLM_MODEL", "gpt-4o-mini"),
        api_key=os.getenv("LLM_API_KEY", "").strip(),
        base_url=(base_url or os.getenv("LLM_BASE_URL") or "").strip() or None,
        temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
        max_rows=int(max_rows if max_rows is not None else os.getenv("SQL_AGENT_MAX_ROWS", "100")),
        max_retries=int(
            max_retries if max_retries is not None else os.getenv("SQL_AGENT_MAX_RETRIES", "2")
        ),
    )
