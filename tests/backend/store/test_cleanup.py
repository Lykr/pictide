import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import stat
import subprocess
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend.store.cleanup import LazyCleanup, delete_pending, image_paths
from backend.task.assets import cache_output
from backend.domain import ValidationError
from backend.paths import DataPaths
from backend.store.sqlite import Repository


class CleanupFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.paths = DataPaths(self.temp.name).ensure()
        self.repo = Repository(self.paths.database)
        self.repo.save_backend({"id":"test","name":"test","kind":"comfyui","workflow":{}})
        self.number = 0

    def tearDown(self):
        self.temp.cleanup()

    def artifact(self, timestamp=None, path=None):
        self.number += 1
        job = self.repo.create_job({"request_id":f"request-{self.number}","backend_id":"test","positive":"exact +","negative":"exact -","seed":1})
        path = path or f"image-{self.number}.png"
        image = self.paths.images/path
        image.parent.mkdir(parents=True,exist_ok=True)
        image.write_bytes(b"image")
        image.with_suffix(".json").write_text('{"positive":"exact +","negative":"exact -"}',encoding="utf-8")
        self.repo.complete(job["id"],[{"node_id":"7","index":0,"local_path":image.relative_to(self.paths.root).as_posix(),"content_type":"image/png"}])
        with self.repo.connection() as db:
            row = db.execute("SELECT id FROM artifacts WHERE job_id=?",(job["id"],)).fetchone()
            if timestamp:
                db.execute("UPDATE artifacts SET created_at=? WHERE id=?",(timestamp,row["id"]))
        return row["id"],image,job

    def old(self):
        return (datetime.now(timezone.utc)-timedelta(days=8)).isoformat()


class CleanupTests(CleanupFixture,unittest.TestCase):
    def test_boundary_and_any_actor_like_protection(self):
        cutoff = "2026-10-01T00:00:00+00:00"
        ids = [self.artifact(time)[0] for time in (cutoff,"2026-10-01T00:00:00.000001+00:00","2026-09-30T23:59:59+00:00",cutoff)]
        self.repo.rate(ids[2],1)
        with self.repo.connection() as db:
            db.execute("INSERT INTO feedback VALUES (?,'other',1,?)",(ids[3],cutoff))
        self.assertEqual(self.repo.expire_artifacts(cutoff),1)
        self.assertIsNone(self.repo.artifact(ids[0]))
        for iid in ids[1:]:
            self.assertIsNotNone(self.repo.artifact(iid))

    def test_batch_independent_feedback_job_and_idempotency_preserved(self):
        job = self.repo.create_job({"request_id":"batch","backend_id":"test","positive":"p","negative":"n","seed":2})
        self.repo.complete(job["id"],[{"node_id":"7","index":n} for n in range(3)])
        rows = self.repo.artifacts()
        self.repo.rate(rows[0]["id"],1)
        self.repo.rate(rows[1]["id"],1)
        self.repo.rate(rows[1]["id"],None)
        self.assertEqual(self.repo.expire_artifacts("2999-01-01T00:00:00Z"),2)
        self.assertEqual(self.repo.counts(),{"artifacts":1,"liked":1,"roam":0,"generate":1})
        self.assertEqual(self.repo.job(job["id"])["status"],"completed")
        again = self.repo.create_job({"request_id":"batch","backend_id":"test","positive":"p","negative":"n","seed":2})
        self.assertEqual(again["id"],job["id"])
        self.repo.complete(job["id"],[{"node_id":"7","index":n} for n in range(3)])
        self.assertEqual(len(self.repo.artifacts()),1)
        with self.repo.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM feedback").fetchone()[0],1)

    def test_snapshot_and_deleted_cursor_still_pages(self):
        a = self.artifact("2026-01-01T00:00:00Z")[0]
        b = self.artifact("2026-01-02T00:00:00Z")[0]
        c = self.artifact("2026-01-03T00:00:00Z")[0]
        first = self.repo.artifact_page(limit=1)
        self.assertEqual(first["next_cursor"],c)
        self.repo.rate(a,1)
        self.repo.expire_artifacts("2026-01-03T00:00:00Z",1)
        self.assertIsNone(self.repo.artifact(b))
        next_page = self.repo.artifact_page(before=b,limit=1)
        self.assertEqual(next_page["artifacts"][0]["id"],a)
        self.assertEqual(next_page["revision"],1)
        self.assertEqual(next_page["counts"],{"artifacts":2,"liked":1,"roam":0,"generate":2})
        self.assertEqual(next_page["total"],2)
        self.assertIsNone(self.repo.artifact_source(b))
        with self.assertRaises(ValidationError):
            self.repo.rate(b,1)

    def test_files_and_sidecars_missing_is_success(self):
        iid,image,_ = self.artifact(self.old())
        image.unlink()
        self.repo.expire_artifacts(self.old())
        self.assertEqual(delete_pending(self.repo,self.paths,100),1)
        self.assertFalse(image.with_suffix(".json").exists())
        self.assertEqual(self.repo.cleanup_counts(),{"deleted":1,"pending":0})
        self.assertIsNone(self.repo.artifact(iid))

    def test_locked_file_retry_survives_restart(self):
        _,image,_ = self.artifact(self.old())
        self.repo.expire_artifacts(self.old())
        unlink = Path.unlink
        def fail(target,*args,**kwargs):
            if target == image:
                raise PermissionError("locked")
            return unlink(target,*args,**kwargs)
        with patch.object(Path,"unlink",fail):
            self.assertEqual(delete_pending(self.repo,self.paths,100),0)
        self.assertEqual(Repository(self.paths.database).cleanup_counts()["pending"],1)
        self.assertEqual(delete_pending(self.repo,self.paths,100),1)
        self.assertFalse(image.exists())

    def test_escape_and_unexpected_extensions_are_never_deleted(self):
        outside = self.paths.root/"outside.png"
        outside.write_bytes(b"preserve")
        iid,_,_ = self.artifact(self.old())
        with self.repo.connection() as db:
            db.execute("UPDATE artifacts SET local_path='../outside.png' WHERE id=?",(iid,))
        self.repo.expire_artifacts(self.old())
        self.assertEqual(delete_pending(self.repo,self.paths,100),0)
        self.assertTrue(outside.exists())
        for value in ("../outside.png",str(outside),"C:\\outside.png","wrong.json","sub/../../bad.png"):
            with self.assertRaises(ValueError):
                image_paths(self.paths,value)

    def test_shared_image_and_sidecar_protected_until_all_deleted(self):
        first,image,_ = self.artifact(self.old(),"shared.png")
        second,_,_ = self.artifact(path="shared.jpg")
        self.repo.rate(second,1)
        self.repo.expire_artifacts(self.old())
        self.assertEqual(delete_pending(self.repo,self.paths,100),0)
        self.assertTrue(image.exists())
        self.assertTrue(image.with_suffix(".json").exists())
        self.repo.rate(second,None)
        self.repo.expire_artifacts("2999-01-01T00:00:00Z")
        self.assertEqual(delete_pending(self.repo,self.paths,100),2)
        self.assertFalse(image.exists())

    def test_shared_legacy_alias_protects_file(self):
        _,image,_ = self.artifact(self.old(),"alias.png")
        second,_,_ = self.artifact(path="active.png")
        with self.repo.connection() as db:
            db.execute("UPDATE artifacts SET local_path='images/folder/../alias.png' WHERE id=?",(second,))
        self.repo.expire_artifacts(self.old())
        self.assertEqual(delete_pending(self.repo,self.paths,100),0)
        self.assertTrue(image.exists())

    def test_symlink_target_outside_images_is_preserved(self):
        outside = self.paths.root/"outside.png"
        outside.write_bytes(b"keep")
        iid,image,_ = self.artifact(self.old())
        image.unlink()
        try:
            image.symlink_to(outside)
        except OSError:
            self.skipTest("Windows account cannot create symlinks")
        self.repo.expire_artifacts(self.old())
        self.assertEqual(delete_pending(self.repo,self.paths,100),0)
        self.assertEqual(outside.read_bytes(),b"keep")
        self.assertTrue(image.is_symlink())

    @unittest.skipUnless(os.name == "nt","Windows junction test")
    def test_images_root_junction_cannot_delete_external_files(self):
        _,image,_ = self.artifact(self.old())
        outside = self.paths.root/"outside-images"
        outside.mkdir()
        external_image = outside/image.name
        image.rename(external_image)
        image.with_suffix(".json").rename(external_image.with_suffix(".json"))
        self.paths.images.rmdir()
        result = subprocess.run(["cmd","/c","mklink","/J",str(self.paths.images),str(outside)],
                                capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors="replace"))
        try:
            self.assertFalse(self.paths.images.is_symlink())
            self.repo.expire_artifacts(self.old())
            self.assertEqual(delete_pending(self.repo,self.paths,100),0)
            self.assertTrue(external_image.exists())
            self.assertTrue(external_image.with_suffix(".json").exists())
            self.assertEqual(self.repo.cleanup_counts()["pending"],1)
        finally:
            self.paths.images.rmdir()  # Remove the junction itself, never its target.

    def test_all_reparse_points_rejected_even_when_resolving_inside_images(self):
        _,image,_ = self.artifact(self.old(),"nested/regular.png")
        original = Path.lstat
        for target in (self.paths.images,image.parent,image,image.with_suffix(".json")):
            def metadata(path,*args,**kwargs):
                if path == target:
                    return SimpleNamespace(st_mode=stat.S_IFDIR,st_file_attributes=0x400)
                return original(path,*args,**kwargs)
            with patch.object(Path,"lstat",metadata):
                with self.assertRaises(ValueError):
                    image_paths(self.paths,image.relative_to(self.paths.root).as_posix())

    def test_late_cache_and_complete_do_not_revive(self):
        iid,image,job = self.artifact(self.old())
        self.repo.expire_artifacts(self.old())
        delete_pending(self.repo,self.paths,100)
        image.write_bytes(b"late")
        output = {"node_id":"7","index":0,"local_path":image.relative_to(self.paths.root).as_posix(),"content_type":"image/png"}
        self.assertFalse(self.repo.cache_artifact(iid,output))
        self.assertEqual(self.repo.cleanup_counts()["pending"],1)
        self.repo.complete(job["id"],[output])
        self.assertIsNone(self.repo.artifact(iid))
        delete_pending(self.repo,self.paths,100)
        self.assertFalse(image.exists())

    def test_like_and_expiry_race_has_consistent_winner(self):
        for _ in range(12):
            iid,image,_ = self.artifact(self.old())
            barrier = threading.Barrier(2)
            def like():
                barrier.wait()
                try:
                    self.repo.rate(iid,1)
                    return True
                except ValidationError:
                    return False
            def expire():
                barrier.wait()
                self.repo.expire_artifacts(self.old())
            with ThreadPoolExecutor(max_workers=2) as pool:
                liked = pool.submit(like)
                expired = pool.submit(expire)
                winner = liked.result()
                expired.result()
            delete_pending(self.repo,self.paths,100)
            self.assertEqual(self.repo.artifact(iid) is not None,winner)
            self.assertEqual(image.exists(),winner)


class LazyCleanupTests(CleanupFixture,unittest.IsolatedAsyncioTestCase):
    async def test_real_cache_output_paths_are_deleted_with_sidecars(self):
        class Backend:
            async def image(self,descriptor):
                return b"real pipeline image", "image/png"
        job = self.repo.create_job({"request_id":"real-cache-path","backend_id":"test","positive":"exact +","negative":"exact -","seed":1})
        output = await cache_output(self.paths,Backend(),{"node_id":"7","index":0},job)
        self.assertTrue(output["local_path"].startswith("images/"))
        image = self.paths.root/output["local_path"]
        self.assertTrue(image.is_file())
        self.assertTrue(image.with_suffix(".json").is_file())
        self.repo.complete(job["id"],[output])
        with self.repo.connection() as db:
            db.execute("UPDATE artifacts SET created_at=? WHERE job_id=?",(self.old(),job["id"]))
        stats = await LazyCleanup(self.repo,self.paths,lambda:7).maybe_cleanup()
        self.assertEqual(stats["deleted"],1)
        self.assertEqual(stats["pending"],0)
        self.assertEqual(stats["removed_files"],1)
        self.assertFalse(image.exists())
        self.assertFalse(image.with_suffix(".json").exists())

    async def test_throttle_bounded_batches_and_disabled_pending_recovery(self):
        for _ in range(3):
            self.artifact(self.old())
        days = [7]
        cleanup = LazyCleanup(self.repo,self.paths,lambda:days[0],batch_size=1)
        first = await cleanup.maybe_cleanup()
        self.assertEqual(first["deleted"],1)
        self.assertEqual(first["removed_files"],1)
        self.assertEqual(await cleanup.maybe_cleanup(),first)
        self.assertEqual((await cleanup.maybe_cleanup(force=True))["deleted"],2)
        days[0] = 0
        self.assertEqual((await cleanup.maybe_cleanup(force=True))["deleted"],2)
        self.repo.expire_artifacts(self.old())
        final = await cleanup.maybe_cleanup(force=True)
        self.assertEqual(final["pending"],0)
        self.assertEqual(final["expired"],0)
