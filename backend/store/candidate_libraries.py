"""Selectable read-only vocabulary files and the user's persisted selection."""
from contextlib import closing
import gzip
from pathlib import Path
import re
import sqlite3
from threading import RLock
import uuid

from ..candidate.errors import CandidateError
from .candidate import STATISTICS_SCHEMA

MAX_LIBRARY_BYTES = 2 * 1024 ** 3


class CandidateLibraries:
    def __init__(self, paths):
        self.directory = paths.libraries
        self.config = paths.candidate_database
        self.tmp = paths.tmp
        self.directory.mkdir(parents=True, exist_ok=True)
        self._summaries = {}
        self._lock = RLock()
        with closing(sqlite3.connect(self.config)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS library_selection("
                       "id INTEGER PRIMARY KEY CHECK(id=1), filename TEXT NOT NULL)")

    def _selection(self):
        with closing(sqlite3.connect(self.config)) as db:
            row = db.execute("SELECT filename FROM library_selection WHERE id=1").fetchone()
        return row[0] if row else ""

    def _save_selection(self, filename):
        with closing(sqlite3.connect(self.config)) as db, db:
            db.execute("INSERT INTO library_selection VALUES(1,?) ON CONFLICT(id) "
                       "DO UPDATE SET filename=excluded.filename", (filename,))

    def _path(self, filename):
        if not isinstance(filename, str) or not filename or Path(filename).name != filename:
            raise CandidateError("请选择词库目录中的文件。")
        path = self.directory / filename
        if (path.suffix.lower() != ".sqlite3" or filename.startswith(".")
                or not path.is_file() or path.resolve().parent != self.directory.resolve()):
            raise CandidateError("请选择词库目录中的 SQLite 词库。")
        return path

    @staticmethod
    def stamp(path):
        try:
            stat = path.stat()
            return (stat.st_size, stat.st_mtime_ns)
        except FileNotFoundError:
            return None

    def inspect(self, path, *, integrity=False):
        path = Path(path)
        key = self.stamp(path)
        cached = self._summaries.get(path)
        if cached and cached[0] == key and not integrity:
            return dict(cached[1])
        try:
            with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
                db.execute("PRAGMA trusted_schema=OFF")
                tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {"tags", "correlations", "dataset"} <= tables:
                    raise CandidateError("请选择包含标签、关系和来源统计的词库文件。")
                db.execute("SELECT id,name,post_count FROM tags LIMIT 1")
                db.execute("SELECT tag_a,tag_b,pmi,count FROM correlations LIMIT 1")
                source = db.execute("SELECT source,revision,post_count,status FROM dataset WHERE id=1").fetchone()
                tags = db.execute("SELECT count(*) FROM tags").fetchone()[0]
                relations = db.execute("SELECT count(*) FROM correlations").fetchone()[0]
                if not source or source[3] != "ready" or not tags or not isinstance(source[2], int) or source[2] <= 0:
                    raise CandidateError("词库需要有效的标签和已就绪的来源统计。")
                if integrity and db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise CandidateError("词库完整性检查失败。")
        except sqlite3.Error as error:
            raise CandidateError("词库文件格式或统计结构无效。") from error
        summary = dict(filename=path.name, tag_count=tags, relation_count=relations, bytes=key[0])
        self._summaries[path] = (key, summary)
        return dict(summary)

    def listing(self):
        libraries = []
        for path in sorted((item for item in self.directory.iterdir() if item.suffix.lower() == ".sqlite3"), key=lambda item: item.name.casefold()):
            if path.name.startswith("."):
                continue
            try:
                path = self._path(path.name)
                libraries.append(self.inspect(path))
            except (CandidateError, OSError):
                continue
        selected = self._selection()
        if selected not in {item["filename"] for item in libraries}:
            selected = ""
        return dict(selected=selected, libraries=libraries)

    def selected_path(self):
        listing = self.listing()
        if listing["selected"]:
            return self.directory / listing["selected"]
        if not self._selection() and listing["libraries"]:
            return self.select(listing["libraries"][0]["filename"])
        return self.empty_path()

    def empty_path(self):
        path = self.directory / ".empty.sqlite3"
        if not path.exists():
            with closing(sqlite3.connect(path)) as db:
                db.executescript(STATISTICS_SCHEMA)
        return path

    def select(self, filename):
        with self._lock:
            path = self._path(filename)
            self.inspect(path)
            self._save_selection(filename)
            return path

    def refresh_path(self, filename):
        return self.select(filename) if filename else self.empty_path()

    def add(self, source_path, filename):
        name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
        compressed = name.lower().endswith(".sqlite3.gz")
        if not (compressed or name.lower().endswith(".sqlite3")):
            raise CandidateError("请选择 .sqlite3 或 .sqlite3.gz 词库文件。")
        if compressed:
            name = name[:-3]
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).lstrip(". ")[:180]
        if not name.lower().endswith(".sqlite3"):
            name = "library.sqlite3"
        source_path = Path(source_path)
        unpacked = None
        temporary = self.directory / ("." + uuid.uuid4().hex + ".sqlite3")
        try:
            if compressed:
                unpacked = self.tmp / (uuid.uuid4().hex + ".sqlite3")
                size = 0
                with gzip.open(source_path, "rb") as source, unpacked.open("wb") as target:
                    while chunk := source.read(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_LIBRARY_BYTES:
                            raise CandidateError("词库解压后最大支持 2 GiB。")
                        target.write(chunk)
                source_path = unpacked
            if source_path.stat().st_size > MAX_LIBRARY_BYTES:
                raise CandidateError("词库最大支持 2 GiB。")
            self.inspect(source_path, integrity=True)
            with self._lock:
                with closing(sqlite3.connect(temporary, uri=True)) as db:
                    db.executescript(STATISTICS_SCHEMA)
                    db.execute("ATTACH DATABASE ? AS incoming", (source_path.resolve().as_uri() + "?mode=ro",))
                    with db:
                        db.execute("INSERT INTO tags SELECT id,name,post_count FROM incoming.tags")
                        db.execute("INSERT INTO correlations SELECT tag_a,tag_b,pmi,count FROM incoming.correlations")
                        db.execute("INSERT INTO dataset SELECT id,source,revision,post_count,status FROM incoming.dataset WHERE id=1")
                    db.execute("ANALYZE main")
                destination = self.directory / name
                index = 2
                while destination.exists():
                    destination = self.directory / f"{Path(name).stem}-{index}.sqlite3"
                    index += 1
                temporary.replace(destination)
                return self.inspect(destination)
        except (sqlite3.Error, OSError, EOFError) as error:
            raise CandidateError("词库导入失败，请检查文件格式与可用磁盘空间。") from error
        finally:
            self._summaries.pop(Path(source_path), None)
            if unpacked is not None:
                unpacked.unlink(missing_ok=True)
            temporary.unlink(missing_ok=True)
