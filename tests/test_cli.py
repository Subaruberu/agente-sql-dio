from __future__ import annotations

import json
from pathlib import Path

import pytest

from sql_agent import cli
from sql_agent.cli import main, render_table
from tests.conftest import StubLLM


def _fake_llm_factory(*responses: str):
    def factory(**kwargs: object) -> StubLLM:
        return StubLLM(*responses)

    return factory


def test_show_schema_funciona_sem_configurar_llm(
    db_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    exit_code = main(["--db", str(db_path), "--show-schema"])

    assert exit_code == 0
    assert "CREATE TABLE clientes" in capsys.readouterr().out


def test_json_exige_pergunta(
    db_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(["--db", str(db_path), "--json"])

    assert exit_code == 2
    assert "--json exige --question" in capsys.readouterr().err


def test_modo_json_imprime_resultado_estruturado(
    db_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli,
        "OpenAICompatibleLLM",
        _fake_llm_factory("SELECT COUNT(*) AS total_clientes FROM clientes"),
    )

    exit_code = main(
        ["--db", str(db_path), "-q", "Quantos clientes existem?", "--json", "--no-explain"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["pergunta"] == "Quantos clientes existem?"
    assert payload["sql"] == "SELECT COUNT(*) AS total_clientes FROM clientes"
    assert payload["linhas"] == [{"total_clientes": 40}]
    assert payload["tentativas"] == 1


def test_modo_texto_mostra_tabela_e_resposta(
    db_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli,
        "OpenAICompatibleLLM",
        _fake_llm_factory(
            "SELECT nome FROM clientes ORDER BY nome LIMIT 2",
            "Os dois primeiros clientes estão listados acima.",
        ),
    )

    exit_code = main(["--db", str(db_path), "-q", "Liste dois clientes", "--max-rows", "5"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "SQL gerado" in output
    assert "| nome" in output
    assert "Resposta: Os dois primeiros clientes" in output


def test_render_table_trunca_celulas_longas() -> None:
    table = render_table(["nome"], [("um nome muito comprido demais",)], max_width=10)

    assert "| nome" in table
    assert "um nome..." in table
    assert len(table.splitlines()[0]) == len(table.splitlines()[-1])
