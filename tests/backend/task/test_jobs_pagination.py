"""Task history pagination uses isolated SQLite data and no generation calls."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer

from backend.domain import ValidationError
from backend.host import APPLICATION, create_app
from backend.store.sqlite import Repository
from tests.backend.application.test_app import FakeBackend, configuration


def add_jobs(repo, count, start=0):
    """All timestamps deliberately tie, exposing unstable page boundaries."""
    with repo.connection() as db:
        revision = db.execute("SELECT revision_id FROM backends WHERE id='local'").fetchone()[0]
        db.executemany("INSERT INTO jobs (id,request_id,payload_hash,backend_id,revision_id,status,positive,negative,seed,backend_prompt_id,error,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", [
            (f"job-{index:04}", f"request-{index:04}", "fixture", "local", revision,
             "completed", f"prompt {index}", "blurry", index, None, None,
             "2026-10-15T00:00:00+00:00", "2026-10-15T00:00:00+00:00")
            for index in range(start, start + count)])


class JobPageStorageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.repo = Repository(Path(self.directory.name) / "pictide.sqlite3")
        self.repo.save_backend({**configuration(), "id": "local"})

    def tearDown(self):
        self.directory.cleanup()

    def test_empty_and_exact_page_boundaries(self):
        self.assertEqual(self.repo.job_page(3), {
            "jobs": [], "page": 1, "page_size": 15, "total": 0, "total_pages": 1})
        previous = 0
        for count, total_pages, last_count in [(15, 1, 15), (16, 2, 1), (31, 3, 1), (121, 9, 1)]:
            with self.subTest(total=count):
                add_jobs(self.repo, count - previous, previous)
                previous = count
                page = self.repo.job_page(2**53 - 1)
                self.assertEqual((page["total"], page["total_pages"], page["page"]),
                                 (count, total_pages, total_pages))
                self.assertEqual(len(page["jobs"]), last_count)
                self.assertEqual(page["jobs"][-1]["id"], "job-0000")

    def test_tied_timestamps_order_and_old_task_updates(self):
        add_jobs(self.repo, 121)
        with self.repo.connection() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id='job-0000'")
        rows = []
        for number in range(1, 10):
            rows.extend(self.repo.job_page(number)["jobs"])
        self.assertEqual([row["id"] for row in rows],
                         [f"job-{index:04}" for index in reversed(range(121))])
        self.assertEqual(len(self.repo.jobs()), 100)
        self.assertNotIn("job-0000", [row["id"] for row in self.repo.jobs()])
        self.repo.update_job("job-0000", "failed", error="historical failure")
        old = self.repo.job_page(9)["jobs"][0]
        self.assertEqual((old["status"], old["error"]), ("failed", "historical failure"))
        self.assertEqual(old["backend_name"], "Test backend")
        self.assertTrue(old["seed_applied"])
        self.assertEqual(old["source"], "generate")
        self.assertNotIn("config", old)
        self.assertNotIn("payload_hash", old)
        self.assertNotIn("never-return-this-secret", str(old))

    def test_count_and_rows_share_snapshot_during_insert(self):
        add_jobs(self.repo, 30)
        original = self.repo._job_rows

        def rows_after_write(db, limit, offset):
            # A different WAL connection commits after COUNT, before SELECT.
            add_jobs(self.repo, 1, 30)
            return original(db, limit, offset)

        with patch.object(self.repo, "_job_rows", side_effect=rows_after_write):
            page = self.repo.job_page(1)
        self.assertEqual(page["total"], 30)
        self.assertEqual(page["jobs"][0]["id"], "job-0029")
        self.assertEqual(self.repo.job_page(1)["total"], 31)

    def test_created_time_takes_priority_over_id(self):
        add_jobs(self.repo, 3)
        with self.repo.connection() as db:
            db.execute("UPDATE jobs SET created_at='2026-10-16T00:00:00+00:00' WHERE id='job-0000'")
            db.execute("UPDATE jobs SET created_at='2026-10-14T00:00:00+00:00' WHERE id='job-0002'")
        self.assertEqual([row["id"] for row in self.repo.job_page(1)["jobs"]],
                         ["job-0000", "job-0001", "job-0002"])

    def test_storage_rejects_invalid_pages(self):
        for page in (0, -1, True, 1.0, "1", None, 2**53):
            with self.subTest(page=page), self.assertRaises(ValidationError):
                self.repo.job_page(page)


class JobPageHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        static = patch("backend.host.STATIC", Path(self.directory.name))
        static.start()
        self.addCleanup(static.stop)
        self.backend = FakeBackend()
        self.client = TestClient(TestServer(create_app(
            Path(self.directory.name) / "data", lambda config, session: self.backend)))
        await self.client.start_server()
        self.repo = self.client.server.app[APPLICATION].storage
        self.repo.save_backend({**configuration(), "id": "local"})

    async def asyncTearDown(self):
        await self.client.close()
        self.directory.cleanup()

    async def test_empty_then_paginate_more_than_100_and_keep_legacy_list(self):
        response = await self.client.get("/api/jobs?page=1")
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {
            "jobs": [], "page": 1, "page_size": 15, "total": 0, "total_pages": 1})
        add_jobs(self.repo, 121)
        response = await self.client.get("/api/jobs?page=4")
        page = await response.json()
        self.assertEqual(response.status, 200)
        self.assertEqual((page["page"], page["page_size"], page["total"], page["total_pages"]),
                         (4, 15, 121, 9))
        self.assertEqual([row["id"] for row in page["jobs"]],
                         [f"job-{index:04}" for index in reversed(range(61, 76))])
        with self.repo.connection() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id='job-0000'")
        self.repo.update_job("job-0000", "cancelled")
        response = await self.client.get("/api/jobs?page=9007199254740991")
        page = await response.json()
        self.assertEqual((page["page"], page["jobs"][0]["status"]), (9, "cancelled"))
        legacy = await (await self.client.get("/api/jobs")).json()
        self.assertEqual(set(legacy), {"jobs"})
        self.assertEqual(len(legacy["jobs"]), 100)
        self.assertEqual(legacy["jobs"][0]["id"], "job-0120")
        self.assertEqual(self.backend.submissions, [])

    async def test_invalid_query_values_are_400(self):
        for page in ("", "0", "-1", "1.5", "1e2", "+1", " 1", "1 ", "abc",
                     "true", "NaN", "١", "9007199254740992", "9" * 5000):
            with self.subTest(page=page):
                response = await self.client.get("/api/jobs", params={"page": page})
                self.assertEqual(response.status, 400)
                self.assertIn("error", await response.json())
        response = await self.client.get("/api/jobs?page=0001")
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["page"], 1)


if __name__ == "__main__":
    unittest.main()
