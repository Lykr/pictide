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
                       "backend_id TEXT NOT NULL, preset_id TEXT NOT NULL, epoch TEXT NOT NULL)")
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
        return {"prefetch_count": 0, "max_history_images": 0, "backend_id": "", "preset_id": "", "epoch": "0" * 32, "playback_interval_seconds": 5}

    def get(self):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT prefetch_count,max_history_images,backend_id,preset_id,epoch FROM roam_settings WHERE id=1").fetchone()
            playback = db.execute("SELECT interval_seconds FROM roam_playback_settings WHERE id=1").fetchone()
        return dict(row or self.defaults(), playback_interval_seconds=playback[0] if playback else 5)

    def history_limit(self):
        return self.get()["max_history_images"]

    def save(self, count, backend_id="", preset_id="", max_history=0, playback_interval=None):
        document = {"prefetch_count": prefetch_count(count), "backend_id": selection(backend_id, "生图后端"),
                    "max_history_images": max_history_images(max_history),
                    "preset_id": selection(preset_id, "候选预设"), "epoch": uuid.uuid4().hex}
        if playback_interval is not None:
            playback_interval_seconds(playback_interval)
        with self.lock, self.connect() as db:
            db.execute("INSERT INTO roam_settings VALUES(1,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                       "prefetch_count=excluded.prefetch_count,max_history_images=excluded.max_history_images,"
                       "backend_id=excluded.backend_id,preset_id=excluded.preset_id,epoch=excluded.epoch",
                       tuple(document[key] for key in ("prefetch_count","max_history_images","backend_id","preset_id","epoch")))
            if playback_interval is not None:
                self._save_playback(db, playback_interval)
            playback = db.execute("SELECT interval_seconds FROM roam_playback_settings WHERE id=1").fetchone()
            document["playback_interval_seconds"] = playback[0] if playback else 5
        return document

    @staticmethod
    def _save_playback(db, seconds):
        db.execute("INSERT INTO roam_playback_settings VALUES(1,?) ON CONFLICT(id) DO UPDATE SET "
                   "interval_seconds=excluded.interval_seconds", (seconds,))

    def save_playback_interval(self, seconds):
        seconds = playback_interval_seconds(seconds)
        with self.lock:
            with self.connect() as db:
                self._save_playback(db, seconds)
            return self.get()
