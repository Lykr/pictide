"""Explicit command-line update orchestration; never part of ordinary startup."""
import asyncio
import json
import os
import sys
import time
from urllib.parse import urlsplit

from .paths import DataPaths
from .store.update_state import unfinished_jobs
from .updates.apply import alive, create_plan, launch_helper, local_json
from .updates.service import UpdateService
from .desktop.terminal import status as terminal_status
from .desktop.text import translate


def status(message, *, stream=None):
    terminal_status(message, heading=translate('updating'), stream=stream)


def running_instance(paths, installation):
    path = paths.tmp / 'service-instance.json'
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding='utf8'))
    if not alive(record.get('pid')):
        return None
    url = urlsplit(record.get('url', ''))
    if (url.scheme != 'http' or url.hostname not in {'127.0.0.1', 'localhost', '::1'}
            or record.get('data_directory') != str(paths.root) or not record.get('ready')
            or record.get('installation') != installation.root):
        raise ValueError('The running instance is not ready or does not match this installation')
    status = local_json(record['url'] + '/api/updates')
    if status.get('installation') != installation.root or status.get('data_directory') != str(paths.root):
        raise ValueError('A different installation owns the running instance')
    return record


async def run(args):
    service = None
    try:
        paths = DataPaths(args.data_dir)
        service = UpdateService(paths)
        if args.update:
            last = [None, 0.0]
            def progress():
                phase = service.state['phase']
                now = time.monotonic()
                if phase != last[0] or now - last[1] >= .5:
                    status(f"Update {phase}: {service.state['downloaded_bytes']}/{service.state['total_bytes']} bytes")
                    last[:] = [phase, now]
            service.on_change = progress
        if args.check_updates:
            result = await service.check()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1 if result['error'] else 0
        if service.installation is None:
            raise ValueError('Direct updates require a portable package. Use --check-updates to find the latest release.')
        record = await asyncio.to_thread(running_instance, paths, service.installation)
        if record:
            base = record['url'] + '/api/updates'
            result = await asyncio.to_thread(local_json, base + '/check', method='POST')
            if result.get('error'):
                raise ValueError(result['error'])
            if result['phase'] == 'current':
                status('Pictide is up to date.')
                return 0
            if not result['can_download']:
                raise ValueError('This version requires a manual update: ' + result['release_url'])
            result = await asyncio.to_thread(local_json, base + '/download', method='POST')
            while result['phase'] in ('downloading', 'verifying'):
                status(f"Preparing update: {result['downloaded_bytes']}/{result['total_bytes']} bytes")
                await asyncio.sleep(.5)
                result = await asyncio.to_thread(local_json, base)
            if result['phase'] != 'ready':
                raise ValueError(result.get('error') or 'Update is not ready')
            await asyncio.to_thread(local_json, base + '/install', method='POST', payload={'initiator_pid': os.getpid()})
        else:
            paths.ensure()
            if await asyncio.to_thread(unfinished_jobs, paths.database):
                raise ValueError('Finish running or queued generation tasks before updating.')
            result = await service.check()
            if result['error']:
                raise ValueError(result['error'])
            if result['phase'] == 'current':
                status('Pictide is up to date.')
                return 0
            service.start_download()
            await service.task
            if service.state['phase'] != 'ready':
                raise ValueError(service.state.get('error') or 'Update is not ready')
            arguments = ['--data-dir', str(paths.root), '--host', args.host, '--port', str(args.port)]
            arguments += ['--lan'] if args.lan else []
            if args.cli:
                arguments.append('--cli')
            if args.no_browser:
                arguments.append('--no-browser')
            if args.desktop or sys.platform == 'win32' and not (args.cli or args.no_browser):
                arguments.append('--desktop')
            path, program = await asyncio.to_thread(create_plan, service, arguments, [os.getpid()])
            launch_helper(path, program)
        status('Update installation has been requested. Pictide will restart after this command exits.\n'
               'Result: ' + str(paths.tmp / 'updates/result.json'))
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        status('Update failed: ' + str(error), stream=sys.stderr)
        return 1
    finally:
        if service is not None:
            await service.close()
