"""Explicit local roam preferences and atomic prefetch invalidation."""
from contextlib import contextmanager
import math
import sqlite3
import threading
import uuid

from ..domain import ValidationError
from .sqlite import Repository

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
        raise ValidationError("自动播放间隔须为 1–600 秒之间的整数。")
    return value


def liked_tags_only_value(value):
    if type(value) is not bool:
        raise ValidationError("喜欢偏好范围须为布尔值。")
    return value


def prompt_mode_value(value):
    if value not in ("random", "along", "stay"):
        raise ValidationError("漫游方式须为 random、along 或 stay。")
    return value


QUICK_DEFAULTS = {"quick_mode": False, "quick_steps_factor": 0.5, "quick_playback_factor": 0.5}


def quick_settings(payload):
    values = {key: payload[key] for key in QUICK_DEFAULTS if key in payload}
    if "quick_mode" in values and type(values["quick_mode"]) is not bool:
        raise ValidationError("快速模式须为布尔值。")
    for key in ("quick_steps_factor", "quick_playback_factor"):
        if key in values and (type(values[key]) not in (int, float) or not math.isfinite(values[key]) or not 0.01 <= values[key] <= 1):
            raise ValidationError("快速模式系数须为 0.01–1 之间的有限数值。")
    return values


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
                       "liked_tags_only INTEGER NOT NULL DEFAULT 0 CHECK(liked_tags_only IN (0,1)), "
                       "prompt_mode TEXT NOT NULL DEFAULT 'random' CHECK(prompt_mode IN ('random','along','stay')))")
            db.execute("CREATE TABLE IF NOT EXISTS roam_playback_settings (id INTEGER PRIMARY KEY CHECK(id=1), "
                       "interval_seconds INTEGER NOT NULL CHECK(interval_seconds BETWEEN 1 AND 600))")

            db.execute("CREATE TABLE IF NOT EXISTS roam_quick_settings (id INTEGER PRIMARY KEY CHECK(id=1), "
                       "quick_mode INTEGER NOT NULL CHECK(quick_mode IN (0,1)), "
                       "quick_steps_factor REAL NOT NULL CHECK(quick_steps_factor BETWEEN 0.01 AND 1), "
                       "quick_playback_factor REAL NOT NULL CHECK(quick_playback_factor BETWEEN 0.01 AND 1))")

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
        return {"prefetch_count": 0, "max_history_images": 0, "backend_id": "", "preset_id": "", "epoch": "0" * 32, "playback_interval_seconds": 5, "liked_tags_only": False, "prompt_mode": "random", **QUICK_DEFAULTS}

    @classmethod
    def _get(cls, db):
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT prefetch_count,max_history_images,backend_id,preset_id,epoch,liked_tags_only,prompt_mode "
                         "FROM roam_settings WHERE id=1").fetchone()
        playback = db.execute("SELECT interval_seconds FROM roam_playback_settings WHERE id=1").fetchone()
        document = dict(row) if row else cls.defaults()
        document["liked_tags_only"] = bool(document["liked_tags_only"])
        document["playback_interval_seconds"] = playback[0] if playback else 5
        quick = db.execute("SELECT quick_mode,quick_steps_factor,quick_playback_factor FROM roam_quick_settings WHERE id=1").fetchone()
        document.update(dict(quick) if quick else QUICK_DEFAULTS)
        document["quick_mode"] = bool(document["quick_mode"])
        return document

    def get(self):
        with self.connect() as db:
            return self._get(db)

    @staticmethod
    def _save_settings(db, document):
        db.execute("INSERT INTO roam_settings "
                   "(id,prefetch_count,max_history_images,backend_id,preset_id,epoch,liked_tags_only,prompt_mode) "
                   "VALUES(1,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                   "prefetch_count=excluded.prefetch_count,max_history_images=excluded.max_history_images,"
                   "backend_id=excluded.backend_id,preset_id=excluded.preset_id,epoch=excluded.epoch,"
                   "liked_tags_only=excluded.liked_tags_only,prompt_mode=excluded.prompt_mode",
                   tuple(document[key] for key in ("prefetch_count","max_history_images","backend_id", "preset_id", "epoch", "liked_tags_only", "prompt_mode")))

    def history_limit(self):
        return self.get()["max_history_images"]

    def save(self, count, backend_id="", preset_id="", max_history=0, playback_interval=None, liked_tags_only=None, prompt_mode=None, quick=None):
        document = {"prefetch_count": prefetch_count(count), "backend_id": selection(backend_id, "生图后端"),
                    "max_history_images": max_history_images(max_history),
                    "preset_id": selection(preset_id, "候选预设")}
        quick = quick_settings(quick or {})
        if playback_interval is not None:
            playback_interval_seconds(playback_interval)
        if liked_tags_only is not None:
            liked_tags_only_value(liked_tags_only)
        if prompt_mode is not None:
            prompt_mode_value(prompt_mode)
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = self._get(db)
            document["liked_tags_only"] = previous["liked_tags_only"] if liked_tags_only is None else liked_tags_only
            document["prompt_mode"] = previous["prompt_mode"] if prompt_mode is None else prompt_mode
            normal_changed = any(document[key] != previous[key] for key in document)
            # A full form that changes only quick options must retain its prefetch epoch.
            document["epoch"] = previous["epoch"] if quick and not normal_changed else uuid.uuid4().hex
            if any(document[key] != previous[key] for key in ("liked_tags_only", "prompt_mode", "backend_id", "preset_id")):
                Repository.discard_roam_prefetch(db)
            self._save_settings(db, document)
            if playback_interval is not None:
                self._save_playback(db, playback_interval)
            self._save_quick(db, previous | quick)
            document = self._get(db)
        return document

    @staticmethod
    def _save_playback(db, seconds):
        db.execute("INSERT INTO roam_playback_settings VALUES(1,?) ON CONFLICT(id) DO UPDATE SET "
                   "interval_seconds=excluded.interval_seconds", (seconds,))

    @staticmethod
    def _save_quick(db, document):
        db.execute("INSERT INTO roam_quick_settings VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                   "quick_mode=excluded.quick_mode,quick_steps_factor=excluded.quick_steps_factor,"
                   "quick_playback_factor=excluded.quick_playback_factor",
                   tuple(document[key] for key in QUICK_DEFAULTS))

    def save_options(self, liked_tags_only=None, playback_interval=None, prompt_mode=None, quick=None):
        quick = quick_settings(quick or {})
        if liked_tags_only is not None:
            liked_tags_only_value(liked_tags_only)
        if playback_interval is not None:
            playback_interval_seconds(playback_interval)
        if prompt_mode is not None:
            prompt_mode_value(prompt_mode)
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            document = self._get(db)
            changed = ((liked_tags_only is not None and liked_tags_only != document["liked_tags_only"])
                       or (prompt_mode is not None and prompt_mode != document["prompt_mode"]))
            if changed:
                if liked_tags_only is not None:
                    document["liked_tags_only"] = liked_tags_only
                if prompt_mode is not None:
                    document["prompt_mode"] = prompt_mode
                document["epoch"] = uuid.uuid4().hex
                Repository.discard_roam_prefetch(db)
                self._save_settings(db, document)
            if playback_interval is not None:
                self._save_playback(db, playback_interval)
            self._save_quick(db, document | quick)
            return self._get(db)

    def save_playback_interval(self, seconds):
        return self.save_options(playback_interval=seconds)
