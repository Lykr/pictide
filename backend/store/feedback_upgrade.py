"""One-time conversion of the deployed likes-only SQLite layout; run offline after backup."""
from contextlib import closing
from pathlib import Path
import sqlite3


def upgrade(database):
    database = Path(database)
    if not database.is_file():
        raise FileNotFoundError(database)
    with closing(sqlite3.connect(database)) as db, db:
        columns = {row[1] for row in db.execute('PRAGMA table_info(recommendation_events)')}
        if 'value' in columns:
            return False
        if 'liked' not in columns:
            raise ValueError('Expected the current likes-only recommendation tables')
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT seq FROM sqlite_sequence WHERE name='recommendation_events'").fetchone()
        sequence = row[0] if row else 0
        db.execute('''CREATE TABLE feedback_signed (
            artifact_id TEXT NOT NULL REFERENCES artifacts(id),
            actor_id TEXT NOT NULL, value INTEGER NOT NULL CHECK(value IN (-1,1)),
            updated_at TEXT NOT NULL, PRIMARY KEY(artifact_id,actor_id))''')
        db.execute('INSERT INTO feedback_signed SELECT * FROM feedback')
        db.execute('DROP TABLE feedback')
        db.execute('ALTER TABLE feedback_signed RENAME TO feedback')
        db.execute('''CREATE TABLE recommendation_events_signed (
            revision INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL, artifact_id TEXT NOT NULL,
            value INTEGER CHECK(value IN (-1,1)), candidate TEXT NOT NULL)''')
        db.execute('''INSERT INTO recommendation_events_signed
            SELECT revision,user_id,artifact_id,CASE WHEN liked=1 THEN 1 ELSE NULL END,candidate
            FROM recommendation_events''')
        db.execute('DROP TABLE recommendation_events')
        db.execute('ALTER TABLE recommendation_events_signed RENAME TO recommendation_events')
        db.execute('CREATE INDEX recommendation_events_image ON recommendation_events(user_id,artifact_id,revision DESC)')
        db.execute("UPDATE sqlite_sequence SET seq=max(seq,?) WHERE name='recommendation_events'", (sequence,))
        db.execute('''CREATE TABLE recommendation_evidence_signed (
            user_id TEXT NOT NULL, feature_version TEXT NOT NULL, artifact_id TEXT NOT NULL,
            revision INTEGER NOT NULL, value INTEGER CHECK(value IN (-1,1)), candidate TEXT NOT NULL,
            PRIMARY KEY(user_id,feature_version,artifact_id))''')
        db.execute('''INSERT INTO recommendation_evidence_signed
            SELECT user_id,feature_version,artifact_id,revision,CASE WHEN liked=1 THEN 1 ELSE NULL END,candidate
            FROM recommendation_evidence''')
        db.execute('DROP TABLE recommendation_evidence')
        db.execute('ALTER TABLE recommendation_evidence_signed RENAME TO recommendation_evidence')
    return True


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    args = parser.parse_args()
    print('Converted signed feedback tables' if upgrade(args.database) else 'Already converted')
