from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from db.repo import DEFAULT_DB_PATH, get_database_url


def get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def ensure_data_dir(db_path: Path = DEFAULT_DB_PATH) -> Path:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def run_migrations(db_path: Path = DEFAULT_DB_PATH) -> Path:
    db_file = ensure_data_dir(db_path)
    project_root = get_project_root()

    alembic_cfg = Config(str(project_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(project_root / "db" / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", get_database_url(db_file))

    command.upgrade(alembic_cfg, "head")
    return db_file


def main() -> Path:
    return run_migrations()


if __name__ == "__main__":
    db_file = main()
    print(f"Initialized database at {db_file}")
