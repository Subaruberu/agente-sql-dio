from __future__ import annotations

import pytest

from sql_agent.agent import SQLAgent, SQLGenerationError, extract_sql
from sql_agent.database import SQLiteDatabase
from tests.conftest import StubLLM


def test_agente_responde_pergunta_com_sql_e_explicacao(database: SQLiteDatabase) -> None:
    llm = StubLLM(
        "SELECT COUNT(*) AS total_clientes FROM clientes",
        "O banco tem 40 clientes cadastrados.",
    )
    agent = SQLAgent(database, llm)

    response = agent.ask("Quantos clientes existem?")

    assert response.sql == "SELECT COUNT(*) AS total_clientes FROM clientes"
    assert response.result.rows == [(40,)]
    assert response.explanation == "O banco tem 40 clientes cadastrados."
    assert response.attempts == 1
    assert len(llm.calls) == 2
    assert "CREATE TABLE clientes" in llm.calls[0]["system"]


def test_agente_corrige_sql_com_erro_de_execucao(database: SQLiteDatabase) -> None:
    llm = StubLLM(
        "SELECT * FROM tabela_inexistente",
        "SELECT COUNT(*) AS total FROM clientes",
        "Existem 40 clientes.",
    )
    agent = SQLAgent(database, llm, max_retries=2)

    response = agent.ask("Quantos clientes existem?")

    assert response.attempts == 2
    assert response.result.rows == [(40,)]
    # O erro foi enviado de volta ao modelo na segunda tentativa.
    assert "no such table" in llm.calls[1]["user"]


def test_agente_tenta_novamente_quando_modelo_responde_texto(database: SQLiteDatabase) -> None:
    llm = StubLLM(
        "Não é possível responder com o esquema atual.",
        "SELECT COUNT(*) AS total FROM produtos",
        "Há 25 produtos cadastrados.",
    )
    agent = SQLAgent(database, llm, max_retries=1)

    response = agent.ask("Quantos produtos existem?")

    assert response.attempts == 2
    assert response.result.rows == [(25,)]


def test_agente_extrai_sql_de_cerca_markdown(database: SQLiteDatabase) -> None:
    llm = StubLLM(
        "Claro! Aqui está:\n```sql\nSELECT COUNT(*) AS total FROM pedidos;\n```\n",
        "Foram registrados 120 pedidos.",
    )
    agent = SQLAgent(database, llm)

    response = agent.ask("Quantos pedidos foram registrados?")

    assert response.sql == "SELECT COUNT(*) AS total FROM pedidos"
    assert response.result.rows == [(120,)]


def test_agente_nunca_executa_consulta_destrutiva(database: SQLiteDatabase) -> None:
    llm = StubLLM("DROP TABLE clientes", "DELETE FROM clientes")
    agent = SQLAgent(database, llm, max_retries=1)

    with pytest.raises(SQLGenerationError):
        agent.ask("Apague os clientes", explain=False)

    total = database.run("SELECT COUNT(*) AS total FROM clientes")
    assert total.rows[0][0] == 40


def test_agente_pode_pular_explicacao(database: SQLiteDatabase) -> None:
    llm = StubLLM("SELECT COUNT(*) AS total FROM clientes")
    agent = SQLAgent(database, llm)

    response = agent.ask("Quantos clientes existem?", explain=False)

    assert response.explanation is None
    assert len(llm.calls) == 1


def test_falha_na_explicacao_nao_descarta_o_resultado(database: SQLiteDatabase) -> None:
    llm = StubLLM(
        "SELECT COUNT(*) AS total FROM clientes",
        RuntimeError("limite de requisições atingido"),
    )
    agent = SQLAgent(database, llm)

    response = agent.ask("Quantos clientes existem?")

    assert response.result.rows == [(40,)]
    assert response.explanation is None
    assert "limite de requisições" in response.warnings[0]


def test_explicacao_recebe_aviso_de_truncamento(database: SQLiteDatabase) -> None:
    llm = StubLLM("SELECT nome FROM clientes ORDER BY nome", "Mostrando os primeiros clientes.")
    agent = SQLAgent(database, llm)

    response = agent.ask("Liste os clientes", explain=True)

    assert response.result.truncated is True
    assert "truncado" in llm.calls[1]["user"]


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("SELECT 1", "SELECT 1"),
        ("```sql\nSELECT 1;\n```", "SELECT 1"),
        ("SQL: SELECT 1", "SELECT 1"),
        ("Segue a consulta:\nSELECT 1;\nEspero ter ajudado.", "SELECT 1"),
        (
            "SELECT replace(nome, ';', '-') FROM clientes; -- fim",
            "SELECT replace(nome, ';', '-') FROM clientes",
        ),
    ],
)
def test_extract_sql(texto: str, esperado: str) -> None:
    assert extract_sql(texto) == esperado
