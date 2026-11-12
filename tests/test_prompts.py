from __future__ import annotations

from datetime import date

from sql_agent.prompts import build_sql_system_prompt

SCHEMA = "CREATE TABLE clientes (id INT, nome VARCHAR(120));"
HOJE = date(2026, 11, 12)


def test_prompt_de_sqlite_cita_recursos_do_sqlite() -> None:
    prompt = build_sql_system_prompt(SCHEMA, today=HOJE)

    assert "especialista em SQLite" in prompt
    assert "strftime" in prompt
    assert "2026-11-12" in prompt
    assert SCHEMA in prompt
    assert "CURDATE" not in prompt


def test_prompt_de_mysql_cita_recursos_do_mysql() -> None:
    prompt = build_sql_system_prompt(SCHEMA, today=HOJE, dialect="mysql")

    assert "especialista em MySQL" in prompt
    assert "CURDATE" in prompt
    assert "DATE_FORMAT" in prompt
    assert "Não use funções exclusivas do SQLite" in prompt
    assert "2026-11-12" in prompt


def test_dialeto_desconhecido_cai_no_padrao_sqlite() -> None:
    prompt = build_sql_system_prompt(SCHEMA, today=HOJE, dialect="oracle")

    assert "especialista em SQLite" in prompt
