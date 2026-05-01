import os
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()


class Base(DeclarativeBase):
    pass


def _database_url() -> str:
    user = quote_plus(os.getenv("user", ""))
    password = quote_plus(os.getenv("password", ""))
    host = os.getenv("host", "")
    port = os.getenv("port", "5432")
    dbname = os.getenv("dbname", "")

    if not all([user, password, host, port, dbname]):
        raise RuntimeError(
            "Database configuration is incomplete. Expected user, password, host, port, and dbname in the environment."
        )

    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"


_engine: Engine | None = None
_session_factory: sessionmaker | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            _database_url(), pool_pre_ping=True, connect_args={"connect_timeout": 8}
        )
    return _engine


def SessionLocal():
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), autoflush=False, expire_on_commit=False
        )
    return _session_factory()
