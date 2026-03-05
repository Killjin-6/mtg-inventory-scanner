from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


DEFAULT_DB_PATH = Path("data") / "local.sqlite"


def get_database_url(db_path: Path | str = DEFAULT_DB_PATH) -> str:
    path = Path(db_path).resolve()
    return f"sqlite:///{path.as_posix()}"


def create_engine_for_path(db_path: Path | str = DEFAULT_DB_PATH) -> Engine:
    return create_engine(get_database_url(db_path), future=True)


def get_engine() -> Engine:
    return create_engine_for_path(DEFAULT_DB_PATH)


SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False, class_=Session, future=True)
