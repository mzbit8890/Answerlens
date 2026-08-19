import os
from pathlib import Path

import psycopg

from config import load_local_environment


def migrate() -> None:
    load_local_environment()

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required to run migrations")

    sql = (
        Path(__file__).parent
        / "migrations"
        / "001_create_audits.sql"
    ).read_text(encoding="utf-8")

    with psycopg.connect(database_url) as connection:
        connection.execute(sql)


if __name__ == "__main__":
    migrate()