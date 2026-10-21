"""Liked historical-tag counts and exact AND pagination smoke tests."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer

from backend.domain import ValidationError
from backend.host import APPLICATION, create_app
from backend.store.sqlite import Repository


def seed(repo):
    repo.save_backend({"id": "local", "name": "Test", "kind": "comfyui", "base_url": "http://localhost:8188", "workflow": {}})
    pictures = []
    for index, (positive, outputs, rating) in enumerate([
        (" black hair, glasses, black hair, ,", 2, 1),
        ("black hair, laboratory", 1, 1),
        ("Black hair, glasses", 1, 1),
        ("a woman sitting beside a window", 1, 1),
        ("ignored, glasses", 1, None),
        ("disliked, glasses", 1, -1),
        ("deleted tag", 1, 1),
    ]):
        job = repo.create_job({"request_id": f"liked-tags-{index}", "backend_id": "local", "positive": positive, "negative": "negative only", "seed": 1})
        repo.complete(job["id"], [{"node_id": "9", "index": n} for n in range(outputs)])
        with repo.connection() as db:
            rows = db.execute("SELECT id FROM artifacts WHERE job_id=?", (job["id"],)).fetchall()
            db.execute("UPDATE artifacts SET created_at=? WHERE job_id=?", (f"2026-10-17T00:00:0{index}+00:00", job["id"]))
        ids = [row["id"] for row in rows]
        for identifier in ids:
            if rating is not None:
                repo.rate(identifier, rating)
        pictures.append(ids)
    with repo.connection() as db:
        db.execute("UPDATE artifacts SET deleted_at='deleted' WHERE id=?", (pictures[-1][0],))
        db.execute("UPDATE artifacts SET generated_hidden_at='hidden' WHERE id=?", (pictures[0][0],))
    return pictures


class LikedTagStorageTests(unittest.TestCase):
    def test_counts_and_filtered_pagination(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Repository(Path(directory) / "pictide.sqlite3")
            pictures = seed(repo)
            self.assertEqual(repo.liked_tags(), [
                {"text": "Black hair", "count": 1},
                {"text": "a woman sitting beside a window", "count": 1},
                {"text": "black hair", "count": 3},
                {"text": "glasses", "count": 3},
                {"text": "laboratory", "count": 1},
            ])
            first = repo.artifact_page(liked=True, limit=1, tags=("black hair", "glasses", "glasses"))
            self.assertEqual(first["total"], 2)
            self.assertEqual(first["counts"]["liked"], 5)
            self.assertTrue(first["has_more"])
            second = repo.artifact_page(liked=True, limit=1, before=first["next_cursor"], tags=("black hair", "glasses"))
            self.assertEqual(second["total"], 2)
            self.assertFalse(second["has_more"])
            self.assertEqual({first["artifacts"][0]["id"], second["artifacts"][0]["id"]}, set(pictures[0]))
            self.assertEqual(repo.artifact_page(liked=True, tags=("hair",))["total"], 0)
            self.assertEqual(repo.artifact_page(liked=True, tags=("a woman sitting beside a window",))["total"], 1)
            self.assertEqual(repo.artifact_page(liked=True, source="generate", tags=("black hair", "glasses"))["total"], 1)
            with self.assertRaises(ValidationError):
                repo.artifact_page(tags=("black hair",))
            repo.rate(pictures[0][0], None)
            self.assertEqual(next(t["count"] for t in repo.liked_tags() if t["text"] == "black hair"), 2)


class LikedTagHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_tag_endpoint_and_repeated_query(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            static = root / "static"
            static.mkdir()
            with patch("backend.host.STATIC", static):
                app = create_app(root)
            repo = app[APPLICATION].storage
            seed(repo)
            async with TestClient(TestServer(app)) as client:
                response = await client.get("/api/liked/tags")
                self.assertEqual(response.status, 200)
                data = await response.json()
                self.assertEqual(data["tags"], repo.liked_tags())
                self.assertEqual(data["revision"], repo.artifact_revision())
                response = await client.get("/api/artifacts", params=[("liked", "1"), ("limit", "1"), ("tag", "black hair"), ("tag", "glasses"), ("tag", "glasses")])
                self.assertEqual(response.status, 200)
                first = await response.json()
                self.assertEqual(first["total"], 2)
                self.assertTrue(first["has_more"])
                response = await client.get("/api/artifacts", params=[("liked", "1"), ("limit", "1"), ("tag", "black hair"), ("tag", "glasses"), ("before", first["next_cursor"])])
                self.assertFalse((await response.json())["has_more"])
                for query in ("?tag=glasses", "?liked=0&tag=glasses", "?source=roam&tag=glasses"):
                    response = await client.get("/api/artifacts" + query)
                    self.assertEqual(response.status, 400)
                response = await client.get("/api/artifacts?liked=1&around=example&tag=glasses")
                self.assertEqual(response.status, 400)
