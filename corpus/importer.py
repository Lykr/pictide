"""Offline Danbooru general tags + ratings -> filtered SQLite PMI vocabulary.

Only metadata is read. Intermediate counts and import progress live in a
separate SQLite file, never in the application's finished vocabulary.
Defaults retain general tags occurring >=100 times, observed ratings, and pairs
with >=10 co-occurrences. Thresholds and excluded tags are configurable.
"""
from __future__ import annotations

import argparse
import json
from array import array
from collections import Counter
from pathlib import Path
import sqlite3
import time

SOURCE = "Shio-Koube/Danbooru-2026-parquet-metadata"
MIN_POST_COUNT = 100
MIN_PAIR_COUNT = 10
RATINGS = {"g": "general", "s": "sensitive", "q": "questionable", "e": "explicit"}
SCHEMA = """
CREATE TABLE tags (
 id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, post_count INTEGER NOT NULL
);
CREATE TABLE correlations (
 tag_a INTEGER NOT NULL, tag_b INTEGER NOT NULL, pmi REAL NOT NULL,
 count INTEGER NOT NULL, PRIMARY KEY(tag_a,tag_b)
) WITHOUT ROWID;
CREATE TABLE dataset (
 id INTEGER PRIMARY KEY CHECK(id=1), source TEXT, revision TEXT,
 post_count INTEGER, status TEXT,
 min_cooccurrence INTEGER NOT NULL CHECK(min_cooccurrence >= 1)
);
"""
STATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS source (source TEXT, revision TEXT);
CREATE TABLE IF NOT EXISTS processing (
 id INTEGER PRIMARY KEY CHECK(id=1), min_tag_occurrences INTEGER NOT NULL,
 excluded_tags TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inputs (path TEXT PRIMARY KEY, bytes INTEGER);
CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS frequencies (name TEXT PRIMARY KEY, count INTEGER) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS groups (
 path TEXT, group_no INTEGER, phase INTEGER, next_block INTEGER DEFAULT 0,
 complete INTEGER DEFAULT 0, PRIMARY KEY(path,group_no,phase)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS pair_posts (id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS pair_counts (
 tag_a INTEGER, tag_b INTEGER, count INTEGER, PRIMARY KEY(tag_a,tag_b)
) WITHOUT ROWID;
"""


def _post_tags(text, rating):
    if rating not in RATINGS:
        raise ValueError(f"Unknown or missing Danbooru rating: {rating!r}")
    return set((text or "").split()) | {RATINGS[rating]}


def _summary(db):
    result = dict(zip(("source", "revision", "post_count", "status", "min_cooccurrence"),
                      db.execute("SELECT source,revision,post_count,status,min_cooccurrence FROM dataset WHERE id=1").fetchone()))
    result["tag_count"] = db.execute("SELECT count(*) FROM tags").fetchone()[0]
    result["pair_count"] = db.execute("SELECT count(*) FROM correlations").fetchone()[0]
    return result


def import_parquet(paths, destination, *, source=SOURCE, revision="local",
                   state_path=None, block_size=256, batch_size=16384,
                   exclude_tags=(), min_tag_occurrences=MIN_POST_COUNT,
                   min_cooccurrences=MIN_PAIR_COUNT, progress=print):
    """Two passes: count general tags + ratings, then retained tag pairs.

    General tags meet min_tag_occurrences; every observed rating is retained
    unless explicitly excluded. Excluding a tag keeps its source posts in N.
    Unknown or missing ratings fail the import rather than silently dropping posts.
    Only globally accumulated pairs meeting min_cooccurrences enter the DB.

    Post IDs are deduplicated across sorted input paths, keeping the first record.
    Every unique post contributes to N, including posts with no retained tags.
    Row groups / pair blocks resume from the separate state database.
    """
    import numpy as np
    import pyarrow.parquet as pq
    from scipy.sparse import csr_matrix

    paths = sorted({Path(path).resolve() for path in paths})
    options = processing_options(dict(exclude_tags=exclude_tags,
        min_tag_occurrences=min_tag_occurrences, min_cooccurrences=min_cooccurrences))
    excluded_tags = options["exclude_tags"]
    if not paths or any(type(value) is not int or value < 1 for value in (block_size, batch_size)):
        raise ValueError("Supply Parquet files and positive integer block/batch sizes")
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ValueError("Use a new destination database; intermediate state can be resumed")
    state_path = Path(state_path or destination.with_name(destination.stem + "-state.sqlite3")).resolve()
    if state_path == destination or state_path in paths:
        raise ValueError("Intermediate, input and application databases must be separate")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(state_path)
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if tables and "processing" not in tables:
        db.close()
        raise ValueError("State has no recorded processing parameters; use a new --state path")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA cache_size=-131072")
    db.executescript(STATE_SCHEMA)
    try:
        identity = db.execute("SELECT source,revision FROM source").fetchone()
        if identity and identity != (source, revision):
            raise ValueError("Intermediate database belongs to another dataset version")
        processing = (min_tag_occurrences, json.dumps(excluded_tags, ensure_ascii=False))
        recorded_options = db.execute("SELECT min_tag_occurrences,excluded_tags FROM processing WHERE id=1").fetchone()
        if recorded_options and recorded_options != processing:
            raise ValueError("Tag filters differ from intermediate state; use a new --state path")
        if not recorded_options:
            db.execute("INSERT INTO processing VALUES(1,?,?)", processing)
        if not identity:
            db.execute("INSERT INTO source VALUES(?,?)", (source, revision))
        inputs = [(str(path), path.stat().st_size) for path in paths]
        recorded = db.execute("SELECT path,bytes FROM inputs ORDER BY path").fetchall()
        if recorded and recorded != sorted(inputs):
            raise ValueError("Use the same input files when resuming an import")
        db.executemany("INSERT OR IGNORE INTO inputs VALUES(?,?)", inputs)
        db.commit()
        units = [(path, group) for path in paths for group in range(pq.ParquetFile(path).num_row_groups)]

        seen = {row[0] for row in db.execute("SELECT id FROM posts")}
        for path, group in units:
            key = (str(path), group, 1)
            if db.execute("SELECT complete FROM groups WHERE path=? AND group_no=? AND phase=?", key).fetchone():
                continue
            frequencies = Counter()
            new_posts = []
            for batch in pq.ParquetFile(path).iter_batches(batch_size=batch_size, columns=["id", "tag_string_general", "rating"], row_groups=[group]):
                data = batch.to_pydict()
                for post_id, text, rating in zip(data["id"], data["tag_string_general"], data["rating"]):
                    if post_id is None:
                        raise ValueError(f"Post without id in {path.name}")
                    if post_id in seen:
                        continue
                    seen.add(post_id)
                    new_posts.append(post_id)
                    frequencies.update(_post_tags(text, rating))
            with db:
                db.executemany("INSERT INTO posts VALUES(?)", ((ident,) for ident in new_posts))
                db.executemany("INSERT INTO frequencies VALUES(?,?) ON CONFLICT(name) DO UPDATE SET count=count+excluded.count", frequencies.items())
                db.execute("INSERT INTO groups VALUES(?,?,?,0,1)", key)
            progress(f"Frequency pass: {path.name}/group={group}, {len(new_posts):,} new posts")
        del seen
        tags = list(db.execute(
            "SELECT name,count FROM frequencies WHERE count>=? OR name IN (?,?,?,?) ORDER BY name",
            (min_tag_occurrences, *RATINGS.values())))
        excluded_names = set(excluded_tags)
        tags = [(name, count) for name, count in tags if name not in excluded_names]
        tag_ids = {name: index for index, (name, _) in enumerate(tags)}
        n_tags = len(tags)
        n_posts = db.execute("SELECT count(*) FROM posts").fetchone()[0]
        if not n_posts or not n_tags:
            raise ValueError("No posts or retained tags; adjust filters and use a new state path")
        progress(f"Retained {n_tags:,} tags (general frequency >= {min_tag_occurrences}, {len(excluded_tags)} excluded names); N={n_posts:,}")

        seen = {row[0] for row in db.execute("SELECT id FROM pair_posts")}
        for path, group in units:
            key = (str(path), group, 2)
            state = db.execute("SELECT next_block,complete FROM groups WHERE path=? AND group_no=? AND phase=?", key).fetchone()
            if state and state[1]:
                continue
            started = time.monotonic()
            pointers = array("i", [0]); indices = array("i"); new_posts = []
            for batch in pq.ParquetFile(path).iter_batches(batch_size=batch_size, columns=["id", "tag_string_general", "rating"], row_groups=[group]):
                data = batch.to_pydict()
                for post_id, text, rating in zip(data["id"], data["tag_string_general"], data["rating"]):
                    if post_id in seen:
                        continue
                    seen.add(post_id)
                    new_posts.append(post_id)
                    indices.extend(sorted({tag_ids[name] for name in _post_tags(text, rating) if name in tag_ids}))
                    pointers.append(len(indices))
            matrix = csr_matrix((np.ones(len(indices), dtype=np.int64), np.frombuffer(indices, dtype=np.int32), np.frombuffer(pointers, dtype=np.int32)), shape=(len(new_posts), n_tags))
            columns_matrix = matrix.tocsc()
            next_block = state[0] if state else 0
            for first in range(next_block, n_tags, block_size):
                last = min(first + block_size, n_tags)
                result = (columns_matrix[:, first:last].T.tocsr() @ matrix).tocoo()
                keep = result.row + first < result.col
                rows, cols, values = result.row[keep] + first + 1, result.col[keep] + 1, result.data[keep]
                with db:
                    db.executemany("INSERT INTO pair_counts VALUES(?,?,?) ON CONFLICT(tag_a,tag_b) DO UPDATE SET count=count+excluded.count", ((int(a), int(b), int(count)) for a, b, count in zip(rows, cols, values)))
                    db.execute("INSERT INTO groups VALUES(?,?,?,?,0) ON CONFLICT(path,group_no,phase) DO UPDATE SET next_block=excluded.next_block", (*key, last))
                progress(f"{path.name}/group={group}: pair block {last:,}/{n_tags:,}")
            with db:
                db.executemany("INSERT INTO pair_posts VALUES(?)", ((ident,) for ident in new_posts))
                db.execute("INSERT INTO groups VALUES(?,?,?,0,1) ON CONFLICT(path,group_no,phase) DO UPDATE SET complete=1", key)
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            progress(f"Completed pair group: {time.monotonic()-started:.1f}s")
            del matrix, columns_matrix, pointers, indices
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        db.close()

    output = sqlite3.connect(destination)
    try:
        output.executescript(SCHEMA)
        output.executemany("INSERT INTO tags VALUES(?,?,?)", ((index + 1, name, count) for index, (name, count) in enumerate(tags)))
        output.execute("INSERT INTO dataset VALUES(1,?,?,?,'importing',?)", (source, revision, n_posts, min_cooccurrences))
        output.commit()
        output.execute("ATTACH DATABASE ? AS intermediate", (str(state_path),))
        with output:
            output.execute("""INSERT INTO correlations
                SELECT p.tag_a,p.tag_b,
                       log2((1.0*p.count*?)/(a.post_count*1.0*b.post_count)),p.count
                FROM intermediate.pair_counts p
                JOIN tags a ON a.id=p.tag_a JOIN tags b ON b.id=p.tag_b
                WHERE p.count>=?""", (n_posts, min_cooccurrences))
        output.execute("CREATE INDEX correlations_b ON correlations(tag_b,tag_a)")
        output.execute("CREATE INDEX tags_frequency ON tags(post_count DESC,name)")
        output.execute("ANALYZE main")
        with output:
            output.execute("UPDATE dataset SET status='ready' WHERE id=1")
        return {**_summary(output), "min_tag_occurrences": min_tag_occurrences,
                "exclude_tags": excluded_tags}
    except BaseException:
        output.close()
        destination.unlink()
        raise
    finally:
        output.close()


def processing_options(document):
    """Resolve the small, shared JSON / Python processing contract."""
    defaults = dict(exclude_tags=[], min_tag_occurrences=MIN_POST_COUNT, min_cooccurrences=MIN_PAIR_COUNT)
    if not isinstance(document, dict) or set(document) - defaults.keys():
        raise ValueError("Config must be an object with exclude_tags, min_tag_occurrences and/or min_cooccurrences")
    options = {**defaults, **document}
    for key in ("min_tag_occurrences", "min_cooccurrences"):
        if type(options[key]) is not int or not 1 <= options[key] <= 2**53 - 1:
            raise ValueError(f"{key} must be an integer between 1 and {2**53 - 1}")
    names = options["exclude_tags"]
    if not isinstance(names, (list, tuple)) or any(not isinstance(name, str) or not name.strip() for name in names):
        raise ValueError("exclude_tags must be a list of nonempty tag names")
    options["exclude_tags"] = sorted({name.strip() for name in names})
    return options


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path, help="Directory containing downloaded Parquet shards")
    parser.add_argument("database", type=Path, help="New finished candidate database, outside the running app")
    parser.add_argument("--source", default=SOURCE)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--state", type=Path, help="Intermediate SQLite path; defaults to <database-stem>-state.sqlite3")
    parser.add_argument("--block-size", type=int, default=256)
    parser.add_argument("--batch-size", type=int, default=16384)
    parser.add_argument("--config", type=Path, help="JSON processing profile; explicit CLI values take precedence")
    parser.add_argument("--exclude-tags", nargs="+", action="extend", help="Exact raw tag names to remove; posts stay in the dataset")
    parser.add_argument("--min-tag-occurrences", type=int, help=f"Minimum general-tag post count (default {MIN_POST_COUNT})")
    parser.add_argument("--min-cooccurrences", type=int, help=f"Minimum global pair count (default {MIN_PAIR_COUNT})")
    parser.add_argument("--report", type=Path, help="Write processing options, input paths and result statistics to a new JSON file")
    args = parser.parse_args(argv)
    try:
        document = json.loads(args.config.read_text(encoding="utf-8-sig")) if args.config else {}
        options = processing_options(document)
        options = processing_options({**options, **{key: getattr(args, key) for key in options if getattr(args, key) is not None}})
        paths = sorted(args.raw.rglob("*.parquet"))
        if args.report and args.report.exists():
            raise ValueError("Use a new report file")
        state = args.state or args.database.with_name(args.database.stem + "-state.sqlite3")
        if args.report and args.report.resolve() in {args.database.resolve(), state.resolve(), *(path.resolve() for path in paths)}:
            raise ValueError("Report, input, state and output paths must be separate")
        started = time.monotonic()
        result = import_parquet(paths, args.database, source=args.source, revision=args.revision,
            state_path=args.state, block_size=args.block_size, batch_size=args.batch_size,
            **options, progress=lambda message: print(message, flush=True))
        report = {**result, "database": str(args.database.resolve()), "bytes": args.database.stat().st_size,
                  "state": str(state.resolve()), "inputs": [str(path.resolve()) for path in paths],
                  "elapsed_seconds": round(time.monotonic() - started, 3)}
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            with args.report.open("x", encoding="utf-8") as stream:
                json.dump(report, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
