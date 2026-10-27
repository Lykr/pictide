"""Reusable named pixel-size pools; image APIs keep references, jobs keep sizes."""
import json
import re
import uuid

from ..domain import NotFoundError, ValidationError


def validate_pool(identifier, payload):
    if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', identifier):
        raise ValidationError('Invalid canvas pool identifier.')
    name, sizes = payload.get('name'), payload.get('sizes')
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise ValidationError('Enter a canvas pool name (up to 100 characters).')
    if not isinstance(sizes, list) or not 1 <= len(sizes) <= 64:
        raise ValidationError('A canvas pool needs 1 to 64 pixel sizes.')
    result = []
    for size in sizes:
        if not isinstance(size, dict) or set(size) != {'width', 'height'} or any(
                type(size[key]) is not int or not 1 <= size[key] <= 16384 for key in ('width', 'height')):
            raise ValidationError('Width and height must be integers from 1 to 16384 pixels.')
        if size in result:
            raise ValidationError('Remove duplicate pixel sizes from the canvas pool.')
        result.append(dict(size))
    return {'id': identifier, 'name': name.strip(), 'sizes': result}


class CanvasPoolStore:
    def __init__(self, repository):
        self.repository = repository
        with repository.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS canvas_pools ('
                       'id TEXT PRIMARY KEY, revision TEXT NOT NULL, config TEXT NOT NULL)')

    def listing(self):
        with self.repository.connection() as db:
            return [dict(json.loads(row['config']), revision=row['revision']) for row in
                    db.execute('SELECT * FROM canvas_pools ORDER BY rowid')]

    def read(self, identifier):
        with self.repository.connection() as db:
            row = db.execute('SELECT * FROM canvas_pools WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise NotFoundError('Canvas pool no longer exists.')
        return dict(json.loads(row['config']), revision=row['revision'])

    def save(self, identifier, payload):
        config = validate_pool(identifier, payload)
        with self.repository.connection() as db:
            db.execute('INSERT INTO canvas_pools VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET '
                       'revision=excluded.revision,config=excluded.config',
                       (identifier, uuid.uuid4().hex, json.dumps(config)))
        return self.listing()

    def delete(self, identifier):
        with self.repository.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            for row in db.execute('SELECT r.config FROM backends b JOIN backend_revisions r ON r.id=b.revision_id'):
                if json.loads(row['config']).get('canvas_pool_id') == identifier:
                    raise ValidationError('This canvas pool is used by an image API. Change its selection first.')
            db.execute('DELETE FROM canvas_pools WHERE id=?', (identifier,))
        return self.listing()
