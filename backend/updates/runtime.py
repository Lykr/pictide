"""Local lifecycle records; these never trigger a version check or installation."""
import json
import os
from pathlib import Path


def save_instance(paths, url, arguments, installation):
    record = dict(pid=os.getpid(), url=url, arguments=arguments, data_directory=str(paths.root),
                  installation=installation.root if installation else None, ready=False)
    path = paths.tmp / 'service-instance.json'
    temporary = path.with_suffix('.json.part')
    temporary.write_text(json.dumps(record), encoding='utf8')
    temporary.replace(path)
    return record


def ready_instance(paths, record):
    path = paths.tmp / 'service-instance.json'
    record['ready'] = True
    temporary = path.with_suffix('.json.part')
    temporary.write_text(json.dumps(record), encoding='utf8')
    temporary.replace(path)


def remove_instance(paths, record):
    path = paths.tmp / 'service-instance.json'
    try:
        if json.loads(path.read_text(encoding='utf8')).get('pid') == record['pid']:
            path.unlink()
    except FileNotFoundError:
        pass
