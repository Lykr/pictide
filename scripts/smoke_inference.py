"""Shared native CPU inference check for portable and container smokes."""
from contextlib import closing
import math
from pathlib import Path
import sqlite3
import struct


def smoke_inference(data, get):
    """Exercise native CPU inference using an inert, completed history fixture."""
    from backend.paths import DataPaths
    from backend.store.sqlite import Repository
    data = Path(data)
    fixture = DataPaths(data).tmp / 'inference-fixture.sqlite3'
    fixture.parent.mkdir(parents=True, exist_ok=True)
    storage = Repository(fixture)
    storage.save_backend({'id': 'cpu-smoke', 'name': 'CPU smoke fixture', 'kind': 'comfyui',
                          'base_url': 'http://127.0.0.1:1', 'api_key': ''})
    texts = ('garden', 'blue sky')
    positive = ', '.join(texts)
    state = storage.ensure_roam('cpu-smoke', None, 1,
        {'backend_id': 'cpu-smoke', 'request_id': 'cpu-smoke', 'positive': positive, 'negative': '', 'seed': 42},
        {'candidate_id': 'cpu-smoke', 'positive': positive, 'negative': '',
         'terms': [{'text': text, 'channel': 'positive'} for text in texts]})
    storage.complete(state['job']['id'], [{'node_id': '9', 'index': 0, 'filename': 'cpu-smoke.png'}])
    artifact = storage.artifacts(source='roam')[0]['id']
    database = DataPaths(data).database
    # Publish completed history atomically: the running worker never sees queued
    # work, and no active backend or image/LLM request is created.
    with closing(sqlite3.connect(database)) as db:
        db.execute('ATTACH DATABASE ? AS fixture', (str(fixture),))
        with db:
            db.execute('BEGIN IMMEDIATE')
            for table in ('backend_revisions', 'jobs', 'artifacts', 'roam_jobs'):
                db.execute(f'INSERT INTO main.{table} SELECT * FROM fixture.{table}')
        if db.execute('SELECT count(*) FROM recommendation_vectors').fetchone()[0]:
            raise RuntimeError('CPU inference smoke requires an empty embedding cache')
    score = get(f'/api/artifacts/{artifact}/preference-score', timeout=60)
    if score.get('status') != 'scored' or not isinstance(score.get('score'), (int, float)) or not math.isfinite(score['score']):
        raise RuntimeError('Native CPU MiniLM scoring failed: ' + str(score))
    with closing(sqlite3.connect(database)) as db:
        vectors = dict(db.execute('SELECT text,vector FROM recommendation_vectors'))
    if set(vectors) != set(texts):
        raise RuntimeError('Native CPU MiniLM did not persist the expected embeddings')
    for vector_data in vectors.values():
        if len(vector_data) != 384 * 4:
            raise RuntimeError('Native MiniLM embedding has the wrong dimension')
        vector = struct.unpack('<384f', vector_data)
        if not all(math.isfinite(value) for value in vector) or not 0.99 < sum(value * value for value in vector) < 1.01:
            raise RuntimeError('Native MiniLM embedding is not finite and normalized')
    return {'texts': list(texts), 'dimension': 384, 'status': score['status']}
