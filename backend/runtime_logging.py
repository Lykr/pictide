"""Bounded application logs, safe formatting and process-local exception capture."""
from contextlib import contextmanager
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import sys
import threading
from urllib.parse import urlsplit, urlunsplit

LOG_MAX_BYTES = 1024 * 1024
LOG_BACKUP_COUNT = 3
_CREDENTIAL = re.compile(r'''(?i)(["']?(?:api[_-]?key|authorization|access[_-]?token|token|secret)["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;]+)''')
_AUTH_SCHEME = re.compile(r'(?i)\b(Bearer|Basic)\s+[^\s,;"\']+')
_URL = re.compile(r'''https?://[^\s<>"']+''')


def _safe_url(match):
    try:
        value = urlsplit(match.group())
    except ValueError:
        return '[invalid URL]'
    return urlunsplit((value.scheme, value.netloc.rsplit('@', 1)[-1], value.path,
                       '[redacted]' if value.query else '', ''))


class RuntimeFormatter(logging.Formatter):
    def format(self, record):
        text = super().format(record)
        for value in getattr(record, 'sensitive_values', ()):
            if isinstance(value, str) and value:
                text = text.replace(value, '[redacted]') if len(value) >= 4 else re.sub(
                    r'(?<!\w)' + re.escape(value) + r'(?!\w)', '[redacted]', text)
        text = _AUTH_SCHEME.sub(r'\1 [redacted]', text)
        text = _CREDENTIAL.sub(r'\1[redacted]', text)
        text = _URL.sub(_safe_url, text)
        # Keep the context and the exception tail without allowing one server
        # response or a malformed output line to consume an entire log file.
        if len(text) > 16000:
            text = text[:1000] + '\n[log entry truncated]\n' + text[-14000:]
        return text


def make_log_handler(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT,
                                  encoding='utf-8', delay=True)
    handler._pictide_runtime_handler = True
    handler.setFormatter(RuntimeFormatter('%(asctime)s %(levelname)s pid=%(process)d %(name)s: %(message)s'))
    return handler


def close_application_log():
    """Release a progress launcher's file before its worker takes ownership."""
    logger = logging.getLogger('backend')
    for handler in list(logger.handlers):
        if getattr(handler, '_pictide_runtime_handler', False):
            logger.removeHandler(handler)
            handler.close()


class _RuntimeErrors(logging.Handler):
    def emit(self, record):
        logging.getLogger('backend').handle(record)


@contextmanager
def capture_exceptions():
    """Keep unhandled thread/async/server errors in the application's file."""
    previous = threading.excepthook
    def thread_failed(args):
        if args.exc_type is not SystemExit:
            logging.getLogger('backend').error('Unhandled thread exception thread=%s', args.thread.name,
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        previous(args)
    handler = _RuntimeErrors(logging.WARNING)
    sources = [logging.getLogger('asyncio'), logging.getLogger('aiohttp.server')]
    for logger in sources:
        logger.addHandler(handler)
    threading.excepthook = thread_failed
    try:
        yield
    except Exception:
        logging.getLogger('backend').exception('Unhandled application exception')
        raise
    finally:
        if threading.excepthook is thread_failed:
            threading.excepthook = previous
        for logger in sources:
            logger.removeHandler(handler)
        handler.close()


def finish_desktop_output():
    """Release inherited startup capture files before notifying the launcher."""
    descriptors = []
    for index, stream in enumerate((sys.stdout, sys.stderr)):
        if stream is None:
            continue
        try:
            descriptor = stream.fileno()
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(descriptor, int):
            stream.flush()
            descriptors.append((index, descriptor))
    if not descriptors:
        return
    with open(os.devnull, 'w') as destination:
        for _, descriptor in descriptors:
            os.dup2(destination.fileno(), descriptor)


def trim_startup_logs(directory, *, keep=3):
    """Only the new raw startup captures belong to this retention policy."""
    files = sorted(Path(directory).glob('desktop-output-*.log'), key=lambda path: path.stat().st_mtime_ns,
                   reverse=True)
    for path in files[keep:]:
        try:
            path.unlink()
        except OSError:
            # A concurrent launcher may still own its capture on Windows.
            pass
