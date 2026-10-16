"""Bounded, request-triggered history cleanup. No polling or scheduled tasks."""
import asyncio
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path, PureWindowsPath
import stat
import time

from .sqlite import now
from .contracts import Storage


LOGGER = logging.getLogger(__name__)
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"})


def is_reparse_point(path):
    try:
        attributes = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(attributes.st_mode) or bool(
        getattr(attributes,"st_file_attributes",0) & getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0x400))


def image_paths(paths, relative):
    """Reject traversal, absolute paths and symlinks before touching files."""
    base = Path(paths.images)
    value = Path(relative)
    windows = PureWindowsPath(relative)
    if is_reparse_point(base) or value.is_absolute() or windows.drive or windows.root or ".." in value.parts or ".." in windows.parts:
        raise ValueError("unsafe image path")
    if value.suffix.lower() not in IMAGE_SUFFIXES:
        raise ValueError("unexpected image extension")
    root = base.resolve()
    image = paths.root / value
    # The stored protocol is relative to data/, e.g. images/<hash>.png.
    # Require lexical containment too, so ancestor walking cannot escape its base.
    if not image.is_relative_to(base):
        raise ValueError("image path leaves data/images")
    sidecar = image.with_suffix(".json")
    for target in (image, sidecar):
        if not target.resolve().is_relative_to(root) or target.resolve() == root:
            raise ValueError("image path leaves data/images")
        current = target
        while True:
            if is_reparse_point(current):
                raise ValueError("reparse point image path")
            if current == base:
                break
            current = current.parent
        if target.exists() and not target.is_file():
            raise ValueError("image path is not a regular file")
    return image, sidecar


def delete_pending(repo: Storage, paths, limit):
    """Serialize active-reference checks and local unlink with cache/like writes."""
    removed = 0
    with repo.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        pending = db.execute("""SELECT artifact_id,local_path FROM pending_image_deletions
            ORDER BY COALESCE(last_attempt,''),created_at,artifact_id LIMIT ?""", (limit,)).fetchall()
        if not pending:
            return 0
        # Keep all active references safe, including differently spelled aliases and
        # differing image suffixes that share the same prompt JSON.
        protected = set()
        for row in db.execute("SELECT local_path FROM artifacts WHERE deleted_at IS NULL AND local_path IS NOT NULL"):
            try:
                # Reference recognition is deliberately more permissive than the
                # deletion boundary: legacy aliases must protect their real file.
                image = (paths.root / row["local_path"]).resolve()
                protected.update((image,image.with_suffix(".json")))
            except (ValueError,OSError,RuntimeError):
                # An invalid active descriptor is never an excuse to delete it.
                LOGGER.warning("Skipped invalid active image reference during cleanup")
        for row in pending:
            db.execute("UPDATE pending_image_deletions SET last_attempt=? WHERE artifact_id=? AND local_path=?",
                       (now(),row["artifact_id"],row["local_path"]))
            try:
                targets = image_paths(paths,row["local_path"])
                if any(target.resolve() in protected for target in targets):
                    continue
                for target in targets:
                    target.unlink(missing_ok=True)
            except (ValueError,OSError,RuntimeError):
                LOGGER.warning("History image removal deferred",exc_info=False)
                continue
            db.execute("DELETE FROM pending_image_deletions WHERE artifact_id=? AND local_path=?",
                       (row["artifact_id"],row["local_path"]))
            removed += 1
    return removed


class LazyCleanup:
    def __init__(self, repo: Storage, paths, retention_days, interval_seconds=60, batch_size=100, *, max_roam_history=None):
        if type(batch_size) is not int or batch_size < 1:
            raise ValueError("batch_size must be positive")
        self.repo = repo
        self.paths = paths
        self.retention_days = retention_days
        self.max_roam_history = max_roam_history or (lambda: 0)
        self.interval_seconds = interval_seconds
        self.batch_size = batch_size
        self.lock = asyncio.Lock()
        self.last_attempt = None
        self.stats = {**repo.cleanup_counts(),"revision":repo.artifact_revision(),"last_run":None,"expired":0,"roam_trimmed":0,"removed_files":0}

    def _run(self, days, max_history):
        expired = 0
        if days > 0:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            expired = self.repo.expire_artifacts(cutoff,self.batch_size)
        trimmed = (self.repo.trim_roam_artifacts(max_history, self.batch_size - expired)
                   if max_history and expired < self.batch_size else 0)
        removed = delete_pending(self.repo,self.paths,self.batch_size)
        return {**self.repo.cleanup_counts(),"revision":self.repo.artifact_revision(),"last_run":now(),"expired":expired,"roam_trimmed":trimmed,"removed_files":removed}

    async def maybe_cleanup(self, force=False, *, roam_only=False):
        async with self.lock:
            clock = time.monotonic()
            due = force or self.last_attempt is None or clock-self.last_attempt >= self.interval_seconds
            max_history = self.max_roam_history()
            if type(max_history) is not int or max_history < 0:
                raise ValueError("max_roam_history must be a nonnegative integer")
            if not max_history and (not due or roam_only):
                return dict(self.stats)
            if due and not roam_only:
                self.last_attempt = clock
            days = self.retention_days() if due and not roam_only else 0
            # Settings validation belongs to the HTTP boundary; fail closed here too.
            if type(days) is not int or days < 0:
                raise ValueError("retention_days must be a nonnegative integer")
            work = asyncio.create_task(asyncio.to_thread(self._run,days,max_history))
            try:
                self.stats = await asyncio.shield(work)
            except asyncio.CancelledError:
                # Finish this bounded local transaction before application shutdown.
                self.stats = await work
                raise
            return dict(self.stats)

    async def remove_pending(self):
        """Drain one existing bounded batch after an explicit gallery removal."""
        async with self.lock:
            work = asyncio.create_task(asyncio.to_thread(delete_pending, self.repo, self.paths, self.batch_size))
            try:
                removed = await asyncio.shield(work)
            except asyncio.CancelledError:
                await work
                raise
            self.stats.update(await asyncio.to_thread(self.repo.cleanup_counts), removed_files=removed)
            self.stats["revision"] = await asyncio.to_thread(self.repo.artifact_revision)
            return dict(self.stats)
