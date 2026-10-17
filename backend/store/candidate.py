"""SQLite persistence for the read-only PMI library and editable presets."""
import json
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import uuid


class SQLiteCandidateStore:
    def __init__(self, path):
        self.path = Path(path)
        self._tags = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tags(
                    id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, post_count INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS tags_frequency ON tags(post_count DESC,name);
                CREATE TABLE IF NOT EXISTS correlations(
                    tag_a INTEGER NOT NULL, tag_b INTEGER NOT NULL, pmi REAL NOT NULL, count INTEGER NOT NULL,
                    PRIMARY KEY(tag_a, tag_b)) WITHOUT ROWID;
                CREATE INDEX IF NOT EXISTS correlations_b ON correlations(tag_b,tag_a);
                CREATE TABLE IF NOT EXISTS dataset(
                    id INTEGER PRIMARY KEY CHECK(id=1), source TEXT, revision TEXT,
                    post_count INTEGER, status TEXT);
                CREATE TABLE IF NOT EXISTS presets(
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, document TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def list_tags(self, query, page, page_size):
        query = query.replace(" ", "_")
        where, args = (" WHERE instr(lower(name), lower(?)) > 0", [query]) if query else ("", [])
        with self.connect() as db:
            total = db.execute("SELECT count(*) FROM tags" + where, args).fetchone()[0]
            tags = [dict(row) for row in db.execute(
                "SELECT id,name,post_count FROM tags" + where + " ORDER BY post_count DESC,name LIMIT ? OFFSET ?",
                [*args, page_size, (page-1)*page_size])]
        return dict(tags=tags, total=total, page=page, page_size=page_size)

    def find_tag(self, text):
        with self.connect() as db:
            row = db.execute("SELECT id,name,post_count FROM tags WHERE name=?",
                             (text.replace(" ", "_"),)).fetchone()
        return dict(row) if row else None

    def find_tags(self, names):
        """Resolve a unique pool in batches, preserving library spelling."""
        names = sorted(set(name.strip().replace(" ", "_") for name in names))
        result = []
        with self.connect() as db:
            for offset in range(0, len(names), 800):
                batch = names[offset:offset+800]
                marks = ",".join("?" for _ in batch)
                result.extend(dict(row) for row in db.execute(
                    f"SELECT id,name,post_count FROM tags WHERE name IN ({marks})", batch))
        return result

    def pair_relations(self, anchor_id, other_ids):
        result = {}
        with self.connect() as db:
            for offset in range(0, len(other_ids), 400):
                ids = other_ids[offset:offset+400]
                marks = ",".join("?" for _ in ids)
                rows = db.execute(f"""
                    SELECT tag_b AS id,pmi,count FROM correlations WHERE tag_a=? AND tag_b IN ({marks})
                    UNION ALL
                    SELECT tag_a AS id,pmi,count FROM correlations WHERE tag_b=? AND tag_a IN ({marks})
                """, [anchor_id, *ids, anchor_id, *ids])
                result.update((row["id"], dict(pmi=row["pmi"], count=row["count"])) for row in rows)
        return result

    def generation_tags(self):
        """Read immutable tag metadata once for a generation batch."""
        with self.connect() as db:
            cursor = db.cursor()
            cursor.row_factory = None
            return tuple(cursor.execute("SELECT id,name,post_count FROM tags ORDER BY id"))

    def qualified_relations(self, anchor_id, pmi_threshold, minimum, candidate_ids=None):
        """Read indexed qualified neighbours, optionally restricted to remaining IDs."""
        if candidate_ids is not None:
            candidate_ids = sorted(set(candidate_ids) - {anchor_id})
            if not candidate_ids:
                return ()
        with self.connect() as db:
            cursor = db.cursor()
            cursor.row_factory = None
            if candidate_ids is None:
                return tuple(cursor.execute("""
                    SELECT tag_b,pmi FROM correlations
                    WHERE tag_a=? AND tag_b!=? AND pmi>=? AND count>=?
                    UNION ALL
                    SELECT tag_a,pmi FROM correlations
                    WHERE tag_b=? AND tag_a!=? AND pmi>=? AND count>=?
                """, (anchor_id, anchor_id, pmi_threshold, minimum,
                      anchor_id, anchor_id, pmi_threshold, minimum)))
            result = []
            for offset in range(0, len(candidate_ids), 400):
                batch = candidate_ids[offset:offset+400]
                marks = ",".join("?" for _ in batch)
                result.extend(cursor.execute(f"""
                    SELECT tag_b,pmi FROM correlations
                    WHERE tag_a=? AND tag_b IN ({marks}) AND pmi>=? AND count>=?
                    UNION ALL
                    SELECT tag_a,pmi FROM correlations
                    WHERE tag_b=? AND tag_a IN ({marks}) AND pmi>=? AND count>=?
                """, [anchor_id, *batch, pmi_threshold, minimum,
                      anchor_id, *batch, pmi_threshold, minimum]))
        return tuple(result)

    def expansion_candidates(self, existing, pmi_threshold, minimum, allowed_ids=None):
        """Intersect PMI-qualified indexed neighbours, weighted by geometric lift."""
        if allowed_ids is not None and not allowed_ids:
            return []
        if not existing:
            if self._tags is None:
                with self.connect() as db:
                    self._tags = [(dict(row), row["post_count"]) for row in db.execute(
                        "SELECT id,name,post_count FROM tags ORDER BY id")]
            return self._tags if allowed_ids is None else [
                item for item in self._tags if item[0]["id"] in allowed_ids]
        weights = None
        with self.connect() as db:
            for tag in sorted(existing, key=lambda item: item["post_count"]):
                if weights is None:
                    neighbours = db.execute("""
                        SELECT tag_b AS id,pmi FROM correlations WHERE tag_a=? AND pmi>=? AND count>=?
                        UNION ALL
                        SELECT tag_a AS id,pmi FROM correlations WHERE tag_b=? AND pmi>=? AND count>=?
                    """, (tag["id"], pmi_threshold, minimum, tag["id"], pmi_threshold, minimum))
                    weights = {row["id"]: row["pmi"] for row in neighbours
                               if allowed_ids is None or row["id"] in allowed_ids}
                else:
                    # Later anchors only need to check the surviving intersection.
                    # Keep anchor order and sums unchanged for seed reproducibility.
                    remaining = list(weights)
                    current = {}
                    for offset in range(0, len(remaining), 400):
                        batch = remaining[offset:offset+400]
                        marks = ",".join("?" for _ in batch)
                        neighbours = db.execute(f"""
                            SELECT tag_b AS id,pmi FROM correlations
                            WHERE tag_a=? AND tag_b IN ({marks}) AND pmi>=? AND count>=?
                            UNION ALL
                            SELECT tag_a AS id,pmi FROM correlations
                            WHERE tag_b=? AND tag_a IN ({marks}) AND pmi>=? AND count>=?
                        """, [tag["id"], *batch, pmi_threshold, minimum,
                              tag["id"], *batch, pmi_threshold, minimum])
                        current.update((row["id"], row["pmi"]) for row in neighbours)
                    weights = {key: value + current[key] for key, value in weights.items() if key in current}
                if not weights:
                    return []
            selected = {tag["id"] for tag in existing}
            keys = sorted(set(weights) - selected)
            if not keys:
                return []
            # A shared subtraction preserves probability ratios and avoids overflow.
            maximum = max(weights[key]/len(existing) for key in keys)
            result = []
            for offset in range(0, len(keys), 800):
                batch = keys[offset:offset+800]
                rows = db.execute("SELECT id,name,post_count FROM tags WHERE id IN ("
                                  + ",".join("?" for _ in batch) + ") ORDER BY id", batch)
                result.extend((dict(row), 2.0 ** (weights[row["id"]]/len(existing) - maximum)) for row in rows)
        return result

    def list_presets(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT id,name FROM presets ORDER BY rowid")]

    def load_preset(self, preset_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM presets WHERE id=?", (preset_id,)).fetchone()
        if row is None:
            raise KeyError(preset_id)
        return dict(id=row["id"], name=row["name"], document=json.loads(row["document"]))

    def save_preset(self, preset_id, name, document):
        preset_id = preset_id or uuid.uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO presets VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET "
                       "name=excluded.name,document=excluded.document",
                       (preset_id, name, json.dumps(document, ensure_ascii=False, allow_nan=False)))
        return self.load_preset(preset_id)

    def delete_preset(self, preset_id):
        with self.connect() as db:
            deleted = db.execute("DELETE FROM presets WHERE id=?", (preset_id,)).rowcount > 0
        return dict(deleted=deleted, id=preset_id)

    def dataset_status(self):
        with self.connect() as db:
            row = db.execute("SELECT * FROM dataset WHERE id=1").fetchone()
            count = db.execute("SELECT count(*) FROM tags").fetchone()[0]
        return {**(dict(row) if row else {"status": "empty", "source": "", "revision": "", "post_count": 0}),
                "tag_count": count}
