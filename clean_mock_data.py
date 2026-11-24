"""Deprecated destructive cleaner. Preserve failures and MOCK evidence in place.

Use data_audit.py in the consolidated repository to filter and review evidence.
"""
from contextlib import closing
from pathlib import Path
import sqlite3

DB_PATH = Path(__file__).resolve().parent / "data" / "pilot.sqlite3"


def purge_mock_data(db_path=DB_PATH):
    raise RuntimeError("Destructive purge disabled: failed real requests are evidence. Use the read-only data audit workbench; no records were changed.")


def inventory(db_path=DB_PATH):
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        return db.execute("SELECT source,status,count(*) FROM trials GROUP BY source,status").fetchall()


if __name__ == "__main__":
    print("Read-only inventory. No deletion is performed.")
    for row in inventory():
        print(row)
