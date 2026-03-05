# MTG Card Scanner

Phase 1 adds a local SQLite database for card metadata, inventory, scan events, and sync outbox records.

## Setup

Create or activate a virtual environment, then install dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Initialize the local database

This project stores the SQLite database at `data/local.sqlite`.

```powershell
python -m db.init_db
```

The init script creates the `data/` directory if it does not already exist and applies Alembic migrations to the latest revision.

## Run migrations manually

Upgrade to the latest migration:

```powershell
alembic upgrade head
```

Show the current revision:

```powershell
alembic current
```

Create a new migration after model changes:

```powershell
alembic revision --autogenerate -m "describe change"
```

## Smoke test

Run the database smoke test to initialize the database, insert a dummy card and inventory row, then print the stored quantity:

```powershell
python scripts/smoke_test_db.py
```
