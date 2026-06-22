from backend.database_url import normalize_database_url


def test_normalize_database_url_accepts_postgres_alias():
    assert (
        normalize_database_url("postgres://mmg:secret@db:5432/mmg")
        == "postgresql://mmg:secret@db:5432/mmg"
    )


def test_normalize_database_url_keeps_supported_urls():
    assert normalize_database_url("postgresql://mmg:secret@db:5432/mmg") == "postgresql://mmg:secret@db:5432/mmg"
    assert normalize_database_url("sqlite:///./atelier.db") == "sqlite:///./atelier.db"
