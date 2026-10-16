"""Local appearance settings, stored alongside application data."""
from contextlib import contextmanager
import sqlite3

from ..domain import ValidationError


class GeneralSettings:
    def __init__(self, paths):
        self.path = paths.database
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS general_settings ("
                       "id INTEGER PRIMARY KEY CHECK(id=1), "
                       "theme TEXT NOT NULL CHECK(theme IN ('light','dark')))")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self):
        with self.connect() as db:
            row = db.execute("SELECT theme FROM general_settings WHERE id=1").fetchone()
        return {"theme": row[0] if row else "light"}

    def save(self, theme):
        if theme not in ("light", "dark"):
            raise ValidationError("主题须为 light 或 dark。")
        with self.connect() as db:
            db.execute("INSERT INTO general_settings VALUES(1,?) ON CONFLICT(id) "
                       "DO UPDATE SET theme=excluded.theme", (theme,))
        return {"theme": theme}
