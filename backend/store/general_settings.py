"""Local interface preferences, stored alongside application data."""
from contextlib import contextmanager
import sqlite3

from ..domain import ValidationError


class GeneralSettings:
    def __init__(self, paths):
        self.path = paths.database
        schema = ("CREATE TABLE IF NOT EXISTS general_settings ("
                  "id INTEGER PRIMARY KEY CHECK(id=1), "
                  "theme TEXT NOT NULL CHECK(theme IN ('system','light','dark')), "
                  "language TEXT NOT NULL, "
                  "image_transitions INTEGER NOT NULL DEFAULT 1 CHECK(image_transitions IN (0,1)))")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            columns = {row[1] for row in db.execute("PRAGMA table_info(general_settings)")}
            if columns and "language" not in columns:
                db.execute("ALTER TABLE general_settings RENAME TO general_settings_previous")
                db.execute(schema)
                db.execute("INSERT INTO general_settings (id, theme, language) SELECT id, theme, 'system' "
                           "FROM general_settings_previous")
                db.execute("DROP TABLE general_settings_previous")
            else:
                db.execute(schema)
            columns = {row[1] for row in db.execute("PRAGMA table_info(general_settings)")}
            if "image_transitions" not in columns:
                db.execute("ALTER TABLE general_settings ADD COLUMN image_transitions "
                           "INTEGER NOT NULL DEFAULT 1 CHECK(image_transitions IN (0,1))")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _read(db):
        row = db.execute("SELECT theme, language, image_transitions "
                         "FROM general_settings WHERE id=1").fetchone()
        return ({"theme": row[0], "language": row[1], "image_transitions": bool(row[2])} if row else
                {"theme": "system", "language": "system", "image_transitions": True})

    def get(self):
        with self.connect() as db:
            return self._read(db)

    def save(self, payload):
        if not any(key in payload for key in ("theme", "language", "image_transitions")):
            raise ValidationError("请选择通用设置。")
        if "theme" in payload and payload["theme"] not in ("system", "light", "dark"):
            raise ValidationError("主题须为 system、light 或 dark。")
        if "language" in payload and payload["language"] not in ("system", "zh-CN", "en"):
            raise ValidationError("语言须为 system、zh-CN 或 en。")
        if "image_transitions" in payload and not isinstance(payload["image_transitions"], bool):
            raise ValidationError("图片切换动效须为布尔值。")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            document = self._read(db)
            document.update({key: payload[key] for key in document if key in payload})
            db.execute("INSERT INTO general_settings (id, theme, language, image_transitions) "
                       "VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET theme=excluded.theme, "
                       "language=excluded.language, image_transitions=excluded.image_transitions",
                       (document["theme"], document["language"], document["image_transitions"]))
        return document
