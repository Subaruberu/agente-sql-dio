from __future__ import annotations

import sqlite3

import pytest

from sql_agent.database import (
    QueryExecutionError,
    SQLiteDatabase,
    UnsafeQueryError,
    quote_identifier,
    validate_sql,
)


def test_schema_descreve_tabelas_e_relacionamentos(database: SQLiteDatabase) -> None:
    schema = database.schema()

    assert "CREATE TABLE clientes" in schema
    assert "CREATE TABLE itens_pedido" in schema
    assert "FK: pedidos.cliente_id -> clientes.id" in schema


def test_tables_lista_todas_as_tabelas(database: SQLiteDatabase) -> None:
    assert database.tables() == [
        "clientes",
        "itens_pedido",
        "pedidos",
        "produtos",
        "vendedores",
    ]


def test_backend_informa_o_dialeto_para_o_prompt(database: SQLiteDatabase) -> None:
    assert database.dialect == "sqlite"


def test_executa_select_e_devolve_colunas_e_linhas(database: SQLiteDatabase) -> None:
    result = database.run("SELECT nome, cidade FROM clientes ORDER BY nome LIMIT 3")

    assert result.columns == ["nome", "cidade"]
    assert result.row_count == 3
    assert not result.truncated
    assert result.elapsed_ms >= 0


def test_limita_quantidade_de_linhas_e_sinaliza_truncamento(database: SQLiteDatabase) -> None:
    result = database.run("SELECT id FROM clientes", max_rows=5)

    assert result.row_count == 5
    assert result.truncated is True


def test_consulta_com_erro_propaga_query_execution_error(database: SQLiteDatabase) -> None:
    with pytest.raises(QueryExecutionError):
        database.run("SELECT * FROM tabela_que_nao_existe")


@pytest.mark.parametrize(
    ("sql", "esperado"),
    [
        ("SELECT 1", "SELECT 1"),
        ("  select * from clientes;  ", "select * from clientes"),
        ("WITH x AS (SELECT 1) SELECT * FROM x", "WITH x AS (SELECT 1) SELECT * FROM x"),
        # a palavra perigosa dentro de um literal de texto é inofensiva
        ("SELECT 'update' AS palavra", "SELECT 'update' AS palavra"),
        ("SELECT replace(nome, 'a', 'b') FROM clientes", "SELECT replace(nome, 'a', 'b') FROM clientes"),
    ],
)
def test_validate_sql_aceita_leituras_seguras(sql: str, esperado: str) -> None:
    assert validate_sql(sql) == esperado


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "   ",
        "DELETE FROM clientes",
        "UPDATE clientes SET nome = 'x'",
        "DROP TABLE clientes",
        "INSERT INTO clientes (nome) VALUES ('x')",
        "PRAGMA table_info(clientes)",
        "SELECT load_extension('extensao')",
        "SELECT load_file('/etc/passwd')",
        "SELECT SLEEP(10)",
        "SELECT * FROM pedidos FOR UPDATE",
        "SELECT * FROM pedidos LOCK IN SHARE MODE",
        "SELECT 1 /*!; DROP TABLE clientes */",
        "SELECT 1; DROP TABLE clientes",
        "SELECT 1; SELECT 2",
        "Não sei responder essa pergunta.",
    ],
)
def test_validate_sql_rejeita_consultas_inseguras(sql: str) -> None:
    with pytest.raises(UnsafeQueryError):
        validate_sql(sql)


def test_banco_recusa_escrita_mesmo_fora_da_validacao(database: SQLiteDatabase) -> None:
    with pytest.raises(sqlite3.Error):
        database._conn.execute("DELETE FROM clientes")

    # Nada foi apagado.
    total = database.run("SELECT COUNT(*) AS total FROM clientes")
    assert total.rows[0][0] == 40


def test_quote_identifier_escapa_nomes_nao_simples() -> None:
    assert quote_identifier("clientes") == "clientes"
    assert quote_identifier("nome estranho") == "`nome estranho`"
    assert quote_identifier("com`aspas") == "`com``aspas`"
