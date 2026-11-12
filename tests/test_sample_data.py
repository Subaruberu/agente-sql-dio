from __future__ import annotations

from sql_agent.sample_data import MYSQL_SCHEMA_STATEMENTS, build_sample_data


def test_massa_de_dados_tem_os_tamanhos_esperados() -> None:
    data = build_sample_data()

    assert len(data["clientes"]) == 40
    assert len(data["vendedores"]) == 6
    assert len(data["produtos"]) == 25
    assert len(data["pedidos"]) == 120
    assert len(data["itens_pedido"]) == 289


def test_massa_de_dados_e_deterministica() -> None:
    assert build_sample_data(seed=2026) == build_sample_data(seed=2026)
    assert build_sample_data(seed=2026) != build_sample_data(seed=7)


def test_relacionamentos_e_dominios_dos_dados() -> None:
    data = build_sample_data()

    clientes = {row[0] for row in data["clientes"]}
    produtos = {row[0] for row in data["produtos"]}
    pedidos = {row[0] for row in data["pedidos"]}
    pedidos_por_cliente = {row[1] for row in data["pedidos"]}

    assert all(row[1] in clientes for row in data["pedidos"])
    assert all(row[2] in pedidos and row[3] in produtos for row in data["itens_pedido"])
    assert all(row[4] in {"pago", "enviado", "entregue", "cancelado"} for row in data["pedidos"])
    assert all(row[5] in {"site", "loja", "telefone"} for row in data["pedidos"])
    # Cinco clientes ficam sem pedidos para exercitar LEFT JOIN/NOT EXISTS.
    assert len(clientes - pedidos_por_cliente) == 5
    # E-mails são únicos.
    assert len({row[2] for row in data["clientes"]}) == len(data["clientes"])


def test_schema_mysql_cobre_todas_as_tabelas() -> None:
    ddl = "\n".join(MYSQL_SCHEMA_STATEMENTS)

    for table in ("clientes", "vendedores", "produtos", "pedidos", "itens_pedido"):
        assert f"CREATE TABLE {table}" in ddl
    assert "FOREIGN KEY (cliente_id) REFERENCES clientes (id)" in ddl
    assert "ENGINE=InnoDB" in ddl
