from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sql_agent.database import Database  # noqa: E402
from sql_agent.sample_data import create_sample_database  # noqa: E402


class StubLLM:
    """LLM falso: devolve respostas pré-programadas e registra as chamadas."""

    def __init__(self, *responses: str | Exception) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append({"system": system, "user": user})
        if not self.responses:
            raise AssertionError("O agente pediu mais respostas do que o esperado.")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return create_sample_database(tmp_path / "teste.db")


@pytest.fixture()
def database(db_path: Path) -> Database:
    db = Database(db_path, max_rows=10)
    try:
        yield db
    finally:
        db.close()
