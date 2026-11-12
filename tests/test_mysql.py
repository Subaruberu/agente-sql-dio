from __future__ import annotations

import pytest

from sql_agent.database import DatabaseConfigurationError, MySQLDatabase


def test_mysql_exige_configuracao_minima() -> None:
    with pytest.raises(DatabaseConfigurationError, match="MYSQL_HOST"):
        MySQLDatabase(host="", port=3306, user="root", password="", database="diobank")

    with pytest.raises(DatabaseConfigurationError, match="MYSQL_HOST"):
        MySQLDatabase(host="localhost", port=3306, user="root", password="", database="")
