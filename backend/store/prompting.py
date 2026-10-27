"""Durable LLM configuration and preparation results, separate from image tasks."""
import json
import uuid
from ..domain import ConflictError, ValidationError

LEGACY_ID = 'legacy-prompt-api'


class PromptStore:
    def __init__(self, repository):
        self.repository = repository
        with repository.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS prompt_settings (
                    id INTEGER PRIMARY KEY CHECK(id=1), revision TEXT NOT NULL, config TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS llm_connections (
                    id TEXT PRIMARY KEY, revision TEXT NOT NULL, config TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS prompt_preparations (
                    id TEXT PRIMARY KEY, digest TEXT NOT NULL, document TEXT NOT NULL,
                    result TEXT, attempted INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            ''')
            # Move the singleton once; keep historical image/job revisions untouched.
            old = db.execute('SELECT revision,config FROM prompt_settings WHERE id=1').fetchone()
            if old:
                config = dict(json.loads(old['config']), id=LEGACY_ID, name='Prompt API', kind='openai')
                db.execute('INSERT OR IGNORE INTO llm_connections VALUES (?,?,?)',
                           (LEGACY_ID, old['revision'], json.dumps(config)))
                db.execute('DELETE FROM prompt_settings WHERE id=1')

    def connections(self):
        with self.repository.connection() as db:
            return [dict(json.loads(r['config']), revision=r['revision']) for r in
                    db.execute('SELECT * FROM llm_connections ORDER BY rowid')]

    def settings(self, identifier=LEGACY_ID):
        if not isinstance(identifier, str) or len(identifier) > 80:
            raise ValidationError('Invalid LLM API selection.')
        with self.repository.connection() as db:
            row = db.execute('SELECT revision,config FROM llm_connections WHERE id=?', (identifier,)).fetchone()
        return dict(json.loads(row['config']), revision=row['revision']) if row else {
            'base_url': '', 'model': '', 'api_key': '', 'revision': ''}

    def save_settings(self, config):
        return self.save_connection(dict(config, id=LEGACY_ID, name='Prompt API', kind='openai'))

    def save_connection(self, config):
        revision = uuid.uuid4().hex
        with self.repository.connection() as db:
            db.execute('INSERT INTO llm_connections VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET '
                       'revision=excluded.revision,config=excluded.config', (config['id'], revision, json.dumps(config)))
        return dict(config, revision=revision)

    def delete_connection(self, identifier):
        with self.repository.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            backends = db.execute('SELECT r.config FROM backends b JOIN backend_revisions r ON r.id=b.revision_id')
            for row in backends:
                config = json.loads(row['config'])
                if config.get('prompt_type') == 'natural_language' and config.get('llm_id', LEGACY_ID) == identifier:
                    raise ValidationError('This LLM API is used by an image API. Change its selection first.')
            db.execute('DELETE FROM llm_connections WHERE id=?', (identifier,))

    def save_image_backend(self, config):
        with self.repository.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            identifier = config.get('llm_id', LEGACY_ID)
            if config.get('prompt_type') == 'natural_language' and identifier != LEGACY_ID:
                if not db.execute('SELECT 1 FROM llm_connections WHERE id=?', (identifier,)).fetchone():
                    raise ValidationError('Select a saved LLM API for natural-language prompts.')
            pool_id = config.get('canvas_pool_id')
            if pool_id and not db.execute('SELECT 1 FROM canvas_pools WHERE id=?', (pool_id,)).fetchone():
                raise ValidationError('Select a saved canvas pool.')
            self.repository._save_backend(db, config)
        return config

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
