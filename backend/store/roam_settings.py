"""Explicit local roam preferences; no generation or scheduling side effects."""
from contextlib import contextmanager
import sqlite3
import threading
import uuid

from ..domain import ValidationError

def max_history_images(value):
    if type(value) is not int or not 0 <= value <= 100000:
        raise ValidationError("漫游历史图片数量上限须为 0–100000 之间的整数，0 表示关闭数量清理。")
    return value


def prefetch_count(value):
    if type(value) is not int or not 0 <= value <= 20:
        raise ValidationError("漫游预取数量须为 0–20 之间的整数，0 表示关闭。")
    return value


def playback_interval_seconds(value):
    if type(value) is not int or not 1 <= value <= 600:
        raise ValidationError("每张展示时间须为 1–600 秒之间的整数。")
    return value


def liked_tags_only_value(value):
    if type(value) is not bool:
        raise ValidationError("仅从喜欢图片中抽取标签须为布尔值。")
    return value


def selection(value, label):
    if not isinstance(value, str) or len(value) > 200:
        raise ValidationError(f"{label}须为文本，留空表示自动选择。")
    return value.strip()


class RoamSettings:
    def __init__(self, paths):
        self.paths = paths
        self.path = paths.database
        self.lock = threading.Lock()
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS roam_settings (id INTEGER PRIMARY KEY CHECK(id=1), "
                       "prefetch_count INTEGER NOT NULL, max_history_images INTEGER NOT NULL, "
                       "backend_id TEXT NOT NULL, preset_id TEXT NOT NULL, epoch TEXT NOT NULL, "
                       "liked_tags_only INTEGER NOT NULL DEFAULT 0 CHECK(liked_tags_only IN (0,1)))")
            db.execute("CREATE TABLE IF NOT EXISTS roam_playback_settings (id INTEGER PRIMARY KEY CHECK(id=1), "
                       "interval_seconds INTEGER NOT NULL CHECK(interval_seconds BETWEEN 1 AND 600))")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def defaults():
        return {"prefetch_count": 0, "max_history_images": 0, "backend_id": "", "preset_id": "", "epoch": "0" * 32, "playback_interval_seconds": 5, "liked_tags_only": False}

    @classmethod
    def _get(cls, db):
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT prefetch_count,max_history_images,backend_id,preset_id,epoch,liked_tags_only "
                         "FROM roam_settings WHERE id=1").fetchone()
        playback = db.execute("SELECT interval_seconds FROM roam_playback_settings WHERE id=1").fetchone()
        document = dict(row) if row else cls.defaults()
        document["liked_tags_only"] = bool(document["liked_tags_only"])
        document["playback_interval_seconds"] = playback[0] if playback else 5
        return document

    def get(self):
        with self.connect() as db:
            return self._get(db)

    @staticmethod
    def _save_settings(db, document):
        db.execute("INSERT INTO roam_settings "
                   "(id,prefetch_count,max_history_images,backend_id,preset_id,epoch,liked_tags_only) "
                   "VALUES(1,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                   "prefetch_count=excluded.prefetch_count,max_history_images=excluded.max_history_images,"
                   "backend_id=excluded.backend_id,preset_id=excluded.preset_id,epoch=excluded.epoch,"
                   "liked_tags_only=excluded.liked_tags_only",
                   tuple(document[key] for key in ("prefetch_count","max_history_images","backend_id", "preset_id", "epoch", "liked_tags_only")))

    def history_limit(self):
        return self.get()["max_history_images"]

    def save(self, count, backend_id="", preset_id="", max_history=0, playback_interval=None, liked_tags_only=None):
        document = {"prefetch_count": prefetch_count(count), "backend_id": selection(backend_id, "生图后端"),
                    "max_history_images": max_history_images(max_history),
                    "preset_id": selection(preset_id, "候选预设"), "epoch": uuid.uuid4().hex}
        if playback_interval is not None:
            playback_interval_seconds(playback_interval)
        if liked_tags_only is not None:
            liked_tags_only_value(liked_tags_only)
        with self.lock, self.connect() as db:
            document["liked_tags_only"] = self._get(db)["liked_tags_only"] if liked_tags_only is None else liked_tags_only
            self._save_settings(db, document)
            if playback_interval is not None:
                self._save_playback(db, playback_interval)
            document = self._get(db)
        return document

    @staticmethod
    def _save_playback(db, seconds):
        db.execute("INSERT INTO roam_playback_settings VALUES(1,?) ON CONFLICT(id) DO UPDATE SET "
                   "interval_seconds=excluded.interval_seconds", (seconds,))

    def save_options(self, liked_tags_only=None, playback_interval=None):
        if liked_tags_only is not None:
            liked_tags_only_value(liked_tags_only)
        if playback_interval is not None:
            playback_interval_seconds(playback_interval)
        with self.lock, self.connect() as db:
            document = self._get(db)
            if liked_tags_only is not None and liked_tags_only != document["liked_tags_only"]:
                document["liked_tags_only"] = liked_tags_only
                document["epoch"] = uuid.uuid4().hex
                self._save_settings(db, document)
            if playback_interval is not None:
                self._save_playback(db, playback_interval)
            return self._get(db)

    def save_playback_interval(self, seconds):
        return self.save_options(playback_interval=seconds)
