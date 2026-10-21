"""Read-only task guard usable before starting a CLI update or opening stores."""
from pathlib import Path
from contextlib import closing
import sqlite3


def unfinished_jobs(database):
    database = Path(database)
    if not database.exists():
        return False
    with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)) as connection:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='jobs'").fetchone():
            return False
        return bool(connection.execute("SELECT 1 FROM jobs WHERE status IN ('queued','submitting','running') "
                                       "OR (status='unknown' AND backend_pending=1) LIMIT 1").fetchone())
