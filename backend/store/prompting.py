"""Durable LLM configuration and preparation results, separate from image tasks."""
import json
import uuid
from ..domain import ConflictError


class PromptStore:
    def __init__(self, repository):
        self.repository = repository
        with repository.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS prompt_settings (
                    id INTEGER PRIMARY KEY CHECK(id=1), revision TEXT NOT NULL, config TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS prompt_preparations (
                    id TEXT PRIMARY KEY, digest TEXT NOT NULL, document TEXT NOT NULL,
                    result TEXT, attempted INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            ''')

    def settings(self):
        with self.repository.connection() as db:
            row = db.execute('SELECT revision,config FROM prompt_settings WHERE id=1').fetchone()
        return dict(json.loads(row['config']), revision=row['revision']) if row else {
            'base_url': '', 'model': '', 'api_key': '', 'revision': ''}

    def save_settings(self, config):
        revision = uuid.uuid4().hex
        with self.repository.connection() as db:
            db.execute('INSERT INTO prompt_settings VALUES (1,?,?) ON CONFLICT(id) DO UPDATE SET '
                       'revision=excluded.revision,config=excluded.config', (revision, json.dumps(config)))
        return dict(config, revision=revision)

    def get(self, identifier, digest=None):
        with self.repository.connection() as db:
            row = db.execute('SELECT * FROM prompt_preparations WHERE id=?', (identifier,)).fetchone()
        if row is None:
            return None
        if digest is not None and row['digest'] != digest:
            raise ConflictError('This request ID belongs to different prompt inputs.')
        return {'document': json.loads(row['document']), 'result': json.loads(row['result']) if row['result'] else None,
                'attempted': bool(row['attempted'])}

    def reserve(self, identifier, digest, document):
        with self.repository.connection() as db:
            db.execute('INSERT OR IGNORE INTO prompt_preparations(id,digest,document) VALUES (?,?,?)',
                       (identifier, digest, json.dumps(document, ensure_ascii=False)))
            # Bound disposable preview/preparation history; job snapshots own submitted history.
            db.execute("DELETE FROM prompt_preparations WHERE id NOT IN "
                       "(SELECT id FROM prompt_preparations ORDER BY created_at DESC,rowid DESC LIMIT 500)")
        return self.get(identifier, digest)

    def finish(self, identifier, result):
        with self.repository.connection() as db:
            db.execute('UPDATE prompt_preparations SET result=? WHERE id=?',
                       (json.dumps(result, ensure_ascii=False), identifier))

    def started(self, identifier):
        with self.repository.connection() as db:
            db.execute('UPDATE prompt_preparations SET attempted=1 WHERE id=?', (identifier,))

    def remove(self, identifiers):
        with self.repository.connection() as db:
            db.executemany('DELETE FROM prompt_preparations WHERE id=?', [(key,) for key in identifiers])
