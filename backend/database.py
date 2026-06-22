from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

import os

from .database_url import normalize_database_url

SQLALCHEMY_DATABASE_URL = normalize_database_url(os.environ.get("DATABASE_URL", "sqlite:///./atelier.db"))

connect_args = {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args=connect_args
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
