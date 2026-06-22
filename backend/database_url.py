def normalize_database_url(database_url: str) -> str:
    """Return a SQLAlchemy-compatible database URL."""
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql://", 1)
    return database_url
