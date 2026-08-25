from db_connection import DatabaseSettings, sqlalchemy_url


def test_sqlalchemy_url_uses_mysql_pymysql_and_utf8mb4() -> None:
    url = sqlalchemy_url(
        DatabaseSettings(host="db.example", port=3307, user="analyst", password="test-secret")
    )

    assert url.drivername == "mysql+pymysql"
    assert url.host == "db.example"
    assert url.port == 3307
    assert url.database == "insightops_mart"
    assert url.query == {"charset": "utf8mb4"}
    assert "test-secret" not in url.render_as_string(hide_password=True)
