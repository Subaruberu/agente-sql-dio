from __future__ import annotations

from pathlib import Path

import pytest

from sql_agent.config import load_settings

ENV_VARS = [
    "SQL_AGENT_BACKEND",
    "SQL_AGENT_DB",
    "MYSQL_HOST",
    "MYSQL_PORT",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "MYSQL_DATABASE",
    "MYSQL_SSL_CA",
    "DATABASE_URL",
    "LLM_MODEL",
    "LLM_API_KEY",
    "LLM_BASE_URL",
]


@pytest.fixture(autouse=True)
def _limpa_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_configuracao_padrao_usa_sqlite() -> None:
    settings = load_settings()

    assert settings.backend == "sqlite"
    assert settings.db_path == Path("data/empresa.db")
    assert settings.max_rows == 100
    assert settings.max_retries == 2
    assert settings.database_label.startswith("SQLite")


def test_database_url_monta_configuracao_mysql(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "mysql://us%40r:s%3Aenh%40@db.exemplo.com:3307/diobank",
    )

    settings = load_settings()

    assert settings.backend == "mysql"
    assert settings.mysql_host == "db.exemplo.com"
    assert settings.mysql_port == 3307
    assert settings.mysql_user == "us@r"
    assert settings.mysql_password == "s:enh@"
    assert settings.mysql_database == "diobank"
    assert settings.database_label == "MySQL (us@r@db.exemplo.com:3307/diobank)"


def test_variaveis_mysql_individuais(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQL_AGENT_BACKEND", "mysql")
    monkeypatch.setenv("MYSQL_HOST", "localhost")
    monkeypatch.setenv("MYSQL_PORT", "3306")
    monkeypatch.setenv("MYSQL_USER", "leitor")
    monkeypatch.setenv("MYSQL_PASSWORD", "segredo")
    monkeypatch.setenv("MYSQL_DATABASE", "diobank")
    monkeypatch.setenv("MYSQL_SSL_CA", r"C:\certs\ca.pem")

    settings = load_settings()

    assert settings.backend == "mysql"
    assert settings.mysql_database == "diobank"
    assert settings.mysql_ssl_ca == r"C:\certs\ca.pem"


def test_mysql_sem_ca_nao_exige_tls() -> None:
    assert load_settings().mysql_ssl_ca == ""


def test_override_de_backend_pela_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQL_AGENT_BACKEND", "sqlite")

    settings = load_settings(backend="mysql")

    assert settings.backend == "mysql"


def test_database_url_invalida(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@host/db")

    with pytest.raises(ValueError, match="mysql"):
        load_settings()


def test_backend_invalido(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQL_AGENT_BACKEND", "oracle")

    with pytest.raises(ValueError, match="sqlite"):
        load_settings()
