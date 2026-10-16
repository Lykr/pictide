"""SQLite repository; no HTTP or generation-backend dependency."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

from .recommendation import initialize_recommendation, record_feedback

from ..domain import ConflictError, NotFoundError, ValidationError, actual_seed, feedback_value, generation_count


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def utc_timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z","+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")
    except (TypeError,ValueError,AttributeError):
        return None


class Repository:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
            CREATE TABLE IF NOT EXISTS backend_revisions (
                id TEXT PRIMARY KEY, backend_id TEXT NOT NULL,
                config TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS backends (
                id TEXT PRIMARY KEY,
                revision_id TEXT NOT NULL REFERENCES backend_revisions(id));
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE,
                payload_hash TEXT NOT NULL,
                backend_id TEXT NOT NULL,
                revision_id TEXT NOT NULL REFERENCES backend_revisions(id),
                status TEXT NOT NULL, positive TEXT NOT NULL, negative TEXT NOT NULL,
                seed INTEGER NOT NULL, backend_prompt_id TEXT, error TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status, created_at);
            CREATE INDEX IF NOT EXISTS jobs_created ON jobs(created_at DESC, id DESC);
            CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
                node_id TEXT NOT NULL, output_index INTEGER NOT NULL,
                descriptor TEXT NOT NULL, created_at TEXT NOT NULL,
                UNIQUE(job_id, node_id, output_index));
            CREATE TABLE IF NOT EXISTS feedback (
                artifact_id TEXT NOT NULL REFERENCES artifacts(id),
                actor_id TEXT NOT NULL, value INTEGER NOT NULL CHECK(value=1),
                updated_at TEXT NOT NULL, PRIMARY KEY(artifact_id, actor_id));
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(artifacts)")}
            for column in ("local_path","content_type","deleted_at","generated_hidden_at","roam_hidden_at"):
                if column not in columns:
                    db.execute(f"ALTER TABLE artifacts ADD COLUMN {column} TEXT")
            db.executescript("""
            CREATE INDEX IF NOT EXISTS artifacts_cleanup ON artifacts(deleted_at,created_at);
            CREATE TABLE IF NOT EXISTS pending_image_deletions (
                artifact_id TEXT NOT NULL REFERENCES artifacts(id),
                local_path TEXT NOT NULL, created_at TEXT NOT NULL,
                last_attempt TEXT,
                PRIMARY KEY(artifact_id,local_path));
            CREATE TABLE IF NOT EXISTS roam_jobs (
                job_id TEXT PRIMARY KEY REFERENCES jobs(id),
                epoch TEXT NOT NULL, candidate TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS roam_jobs_epoch ON roam_jobs(epoch);
            CREATE TABLE IF NOT EXISTS roam_runs (
                epoch TEXT PRIMARY KEY, error TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS roam_view (
                actor_id TEXT PRIMARY KEY CHECK(actor_id='local'),
                artifact_id TEXT REFERENCES artifacts(id), viewed_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS generation_batches (
                request_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL,
                count INTEGER NOT NULL, job_ids TEXT NOT NULL, created_at TEXT NOT NULL);
            """)
            if "context" not in {row["name"] for row in db.execute("PRAGMA table_info(generation_batches)")}:
                db.execute("ALTER TABLE generation_batches ADD COLUMN context TEXT")
            initialize_recommendation(db)
            self._migrate_feedback(db)

    @staticmethod
    def _migrate_feedback(db):
        # Rebuild legacy feedback atomically; only likes remain, across all actors.
        # Inspect the actual constraint so an already migrated database stays read-only.
        def likes_only():
            sql = db.execute("SELECT sql FROM sqlite_schema WHERE type='table' AND name='feedback'").fetchone()[0]
            return "check(value=1)" in "".join(sql.lower().split())

        if likes_only():
            return
        db.execute("BEGIN IMMEDIATE")
        # Another application may have completed the migration while this one waited.
        if likes_only():
            return
        db.execute("""CREATE TABLE feedback_likes (
            artifact_id TEXT NOT NULL REFERENCES artifacts(id),
            actor_id TEXT NOT NULL, value INTEGER NOT NULL CHECK(value=1),
            updated_at TEXT NOT NULL, PRIMARY KEY(artifact_id, actor_id))""")
        db.execute("INSERT INTO feedback_likes SELECT artifact_id,actor_id,value,updated_at FROM feedback WHERE value=1")
        db.execute("DROP TABLE feedback")
        db.execute("ALTER TABLE feedback_likes RENAME TO feedback")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.create_function("utc_timestamp",1,utc_timestamp,deterministic=True)
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def backends(self):
        with self.connection() as db:
            return [json.loads(row["config"]) for row in db.execute(
                "SELECT r.config FROM backends b JOIN backend_revisions r ON r.id=b.revision_id ORDER BY r.created_at")]

    def backend(self, iid):
        with self.connection() as db:
            row = db.execute("SELECT r.config FROM backends b JOIN backend_revisions r ON r.id=b.revision_id WHERE b.id=?", (iid,)).fetchone()
            return json.loads(row["config"]) if row else None

    def save_backend(self, config):
        # Old jobs keep the endpoint, authentication and workflow they were submitted with.
        with self.connection() as db:
            self._save_backend(db, config)
        return config

    @staticmethod
    def _save_backend(db, config):
        revision = str(uuid.uuid4())
        db.execute("INSERT INTO backend_revisions VALUES (?,?,?,?)", (revision, config["id"], encode(config), now()))
        db.execute("INSERT INTO backends VALUES (?,?) ON CONFLICT(id) DO UPDATE SET revision_id=excluded.revision_id", (config["id"], revision))

    def delete_backend(self, iid):
        # Revisions keep the complete configuration, including authentication,
        # for old jobs and manual recovery; no tasks or artifacts are deleted.
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            return bool(db.execute("DELETE FROM backends WHERE id=?", (iid,)).rowcount)

    def detach_workflow(self, identifier):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT r.config FROM backends b JOIN backend_revisions r ON r.id=b.revision_id "
                              "WHERE json_extract(r.config,'$.workflow_id')=?", (identifier,)).fetchall()
            for row in rows:
                config = json.loads(row["config"])
                for key in ("workflow_id", "workflow_name", "workflow_revision"):
                    config.pop(key, None)
                self._save_backend(db, config)
            return len(rows)

    @staticmethod
    def _job(row):
        result = dict(row)
        if "seed_applied" in result:
            result["seed_applied"] = bool(result["seed_applied"])
        result.pop("config", None)
        result.pop("payload_hash", None)
        return result

    def jobs(self, limit=100):
        with self.connection() as db:
            return self._job_rows(db, limit)

    @classmethod
    def _job_rows(cls, db, limit, offset=0):
        rows = db.execute("SELECT j.*,CASE WHEN EXISTS (SELECT 1 FROM roam_jobs s WHERE s.job_id=j.id) THEN 'roam' ELSE 'generate' END AS source,json_extract(r.config,'$.name') AS backend_name,json_type(r.config,'$.bindings.seed')='object' AS seed_applied FROM jobs j JOIN backend_revisions r ON r.id=j.revision_id ORDER BY j.created_at DESC,j.id DESC LIMIT ? OFFSET ?", (limit, offset))
        return [cls._job(row) for row in rows]

    def job_page(self, page):
        if type(page) is not int or not 1 <= page <= 2**53 - 1:
            raise ValidationError("页码必须是 1 至 9007199254740991 的整数。")
        page_size = 15
        with self.connection() as db:
            # Pin COUNT and rows to the same read snapshot while tasks change.
            db.execute("BEGIN")
            total = db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            total_pages = max(1, (total + page_size - 1) // page_size)
            page = min(page, total_pages)
            return {"jobs": self._job_rows(db, page_size, (page - 1) * page_size),
                    "page": page, "page_size": page_size,
                    "total": total, "total_pages": total_pages}

    def job(self, iid):
        with self.connection() as db:
            row = db.execute("SELECT j.*,CASE WHEN EXISTS (SELECT 1 FROM roam_jobs s WHERE s.job_id=j.id) THEN 'roam' ELSE 'generate' END AS source,json_extract(r.config,'$.name') AS backend_name,json_type(r.config,'$.bindings.seed')='object' AS seed_applied FROM jobs j JOIN backend_revisions r ON r.id=j.revision_id WHERE j.id=?", (iid,)).fetchone()
            return self._job(row) if row else None

    def job_backend(self, iid):
        with self.connection() as db:
            row = db.execute("SELECT r.config FROM jobs j JOIN backend_revisions r ON r.id=j.revision_id WHERE j.id=?", (iid,)).fetchone()
            return json.loads(row["config"]) if row else None

    def create_job(self, payload):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            iid = self._create_job(db, payload)
        return self.job(iid)

    def create_jobs(self, payload, count=1):
        """Reserve an entire idempotent batch, never a partial queue submission."""
        count = generation_count(count)
        digest = hashlib.sha256(encode({**payload, "count": count}).encode()).hexdigest()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            batch = db.execute("SELECT * FROM generation_batches WHERE request_id=?", (payload["request_id"],)).fetchone()
            if batch:
                if batch["payload_hash"] != digest:
                    raise ConflictError("相同请求 ID 已用于其他生成内容或数量，请新建请求。")
                identifiers = json.loads(batch["job_ids"])
            else:
                old = db.execute("SELECT id,payload_hash FROM jobs WHERE request_id=?", (payload["request_id"],)).fetchone()
                if old:
                    # Upgrade pre-batch, single-job idempotency without creating more work.
                    if count != 1 or old["payload_hash"] != hashlib.sha256(encode(payload).encode()).hexdigest():
                        raise ConflictError("相同请求 ID 已用于其他生成内容或数量，请新建请求。")
                    identifiers = [old["id"]]
                else:
                    pending = db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','submitting','running')").fetchone()[0]
                    if pending + count > 10:
                        raise ValidationError(f"队列最多容纳 10 个待处理任务，当前仅剩 {10-pending} 个名额。")
                    identifiers = []
                    for index in range(count):
                        fields = dict(payload)
                        if index:
                            fields["request_id"] = "batch-" + uuid.uuid4().hex
                            if payload["seed"] != -1:
                                fields["seed"] = (payload["seed"] + index) % (2**53)
                        identifiers.append(self._create_job(db, fields))
                db.execute("INSERT INTO generation_batches(request_id,payload_hash,count,job_ids,created_at) VALUES (?,?,?,?,?)",
                           (payload["request_id"], digest, count, encode(identifiers), now()))
        return [self.job(identifier) for identifier in identifiers]

    @staticmethod
    def _create_job(db, payload, capacity=10):
        digest = hashlib.sha256(encode(payload).encode()).hexdigest()
        iid = str(uuid.uuid4())
        old = db.execute("SELECT * FROM jobs WHERE request_id=?", (payload["request_id"],)).fetchone()
        if old:
            if old["payload_hash"] != digest:
                raise ConflictError("相同请求 ID 已用于其他生成内容，请新建请求。")
            return old["id"]
        backend = db.execute("SELECT revision_id FROM backends WHERE id=?", (payload["backend_id"],)).fetchone()
        if not backend:
            raise ValidationError("生图后端不存在，请先保存后端配置。")
        pending = db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','submitting','running')").fetchone()[0]
        if pending >= capacity:
            raise ValidationError(f"待处理任务已达 {capacity} 个，请等待完成后再生成。")
        timestamp = now()
        db.execute("""INSERT INTO jobs
            (id,request_id,payload_hash,backend_id,revision_id,status,positive,negative,seed,created_at,updated_at)
            VALUES (?,?,?,?,?,'queued',?,?,?,?,?)""",
            (iid,payload["request_id"],digest,payload["backend_id"],backend["revision_id"],payload["positive"],payload["negative"],actual_seed(payload["seed"]),timestamp,timestamp))
        return iid

    @staticmethod
    def _generation_plan(db, request_id, digest):
        row = db.execute("SELECT * FROM generation_batches WHERE request_id=?", (request_id,)).fetchone()
        if row is None:
            if db.execute("SELECT 1 FROM jobs WHERE request_id=?", (request_id,)).fetchone():
                raise ConflictError("相同请求 ID 已用于其他生成内容，请新建请求。")
            return None
        if row["payload_hash"] != digest or row["context"] is None:
            raise ConflictError("相同请求 ID 已用于其他生成内容或数量，请新建请求。")
        return {"identifiers": json.loads(row["job_ids"]), "context": json.loads(row["context"])}

    def generation_plan(self, request_id, digest):
        with self.connection() as db:
            plan = self._generation_plan(db, request_id, digest)
        if plan is None:
            return None
        jobs = [self.job(identifier) for identifier in plan["identifiers"]]
        return {"job": jobs[0], "jobs": jobs, **plan["context"]}

    def commit_generation_plan(self, request_id, digest, plans, context, backend):
        if not 1 <= len(plans) <= 100:
            raise ValidationError("一次生成最多提交 100 个任务。")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = self._generation_plan(db, request_id, digest)
            if previous is None:
                current = db.execute("SELECT r.config FROM backends b JOIN backend_revisions r ON r.id=b.revision_id WHERE b.id=?",
                                     (backend["id"],)).fetchone()
                if current is None or encode(json.loads(current["config"])) != encode(backend):
                    raise ConflictError("生图后端已变更，请重新提交生成。")
                pending = db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','submitting','running')").fetchone()[0]
                if pending + len(plans) > 100:
                    raise ValidationError(f"队列最多容纳 100 个待处理任务，当前仅剩 {max(0,100-pending)} 个名额。")
                identifiers = [self._create_job(db, fields, capacity=100) for fields in plans]
                db.execute("INSERT INTO generation_batches(request_id,payload_hash,count,job_ids,created_at,context) VALUES (?,?,?,?,?,?)",
                           (request_id, digest, len(plans), encode(identifiers), now(), encode(context)))
        return self.generation_plan(request_id, digest)

    @staticmethod
    def _roam_state(db, epoch, anchor_id):
        if anchor_id is None:
            ready = db.execute("SELECT count(*) FROM artifacts a JOIN roam_jobs r ON r.job_id=a.job_id WHERE a.deleted_at IS NULL AND a.roam_hidden_at IS NULL").fetchone()[0]
        else:
            anchor = db.execute("SELECT a.created_at,a.id FROM artifacts a JOIN roam_jobs r ON r.job_id=a.job_id WHERE a.id=? AND a.deleted_at IS NULL AND a.roam_hidden_at IS NULL", (anchor_id,)).fetchone()
            if anchor is None:
                raise NotFoundError("当前漫游图片已清理或不存在，请刷新后重试。")
            ready = db.execute("SELECT count(*) FROM artifacts a JOIN roam_jobs r ON r.job_id=a.job_id WHERE a.deleted_at IS NULL AND a.roam_hidden_at IS NULL "
                               "AND (a.created_at>? OR (a.created_at=? AND a.id>?))",
                               (anchor["created_at"], anchor["created_at"], anchor["id"])).fetchone()[0]
        failure = db.execute("SELECT j.status,j.error FROM roam_jobs r JOIN jobs j ON j.id=r.job_id "
                             "WHERE r.epoch=? AND j.status IN ('failed','unknown','cancelled') "
                             "ORDER BY j.created_at DESC,j.id DESC LIMIT 1", (epoch,)).fetchone()
        if failure:
            message = failure["error"] or "漫游生成失败或已取消，请在漫游设置中保存后重试。"
            db.execute("INSERT OR IGNORE INTO roam_runs(epoch,error) VALUES (?,?)", (epoch, message[:1000]))
        pause = db.execute("SELECT error FROM roam_runs WHERE epoch=?", (epoch,)).fetchone()
        pending = db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','submitting','running')").fetchone()[0]
        return {"ready": ready, "pending": pending, "paused": pause is not None,
                **({"error": pause["error"]} if pause else {})}

    def ensure_roam(self, epoch, anchor_id, target, payload=None, candidate=None):
        """Count authoritative images and atomically enqueue one associated job."""
        snapshot = json.dumps(candidate, ensure_ascii=False, allow_nan=False) if candidate is not None else None
        if payload is not None and snapshot is None:
            raise ValidationError("漫游任务必须关联推荐候选快照。")
        identifier = None
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            result = self._roam_state(db, epoch, anchor_id)
            if payload is not None and target > result["ready"] and not result["pending"] and not result["paused"]:
                identifier = self._create_job(db, payload)
                db.execute("INSERT INTO roam_jobs(job_id,epoch,candidate,created_at) VALUES (?,?,?,?)",
                           (identifier, epoch, snapshot, now()))
                result["pending"] += 1
        if identifier is not None:
            result["job"] = self.job(identifier)
        return result

    def pause_roam(self, epoch, message):
        with self.connection() as db:
            db.execute("INSERT OR IGNORE INTO roam_runs(epoch,error) VALUES (?,?)", (epoch, message[:1000]))

    def roam_snapshot(self, job_id):
        with self.connection() as db:
            row = db.execute("SELECT candidate FROM roam_jobs WHERE job_id=?", (job_id,)).fetchone()
            return json.loads(row["candidate"]) if row else None

    def next_job(self):
        with self.connection() as db:
            # Resume accepted work first; manual queued work precedes prefetch.
            row = db.execute("SELECT j.id FROM jobs j LEFT JOIN roam_jobs r ON r.job_id=j.id "
                             "WHERE j.status IN ('queued','submitting','running') "
                             "ORDER BY CASE WHEN j.backend_prompt_id IS NOT NULL THEN 0 ELSE 1 END,"
                             "CASE WHEN r.job_id IS NULL THEN 0 ELSE 1 END,j.created_at LIMIT 1").fetchone()
            return self.job(row["id"]) if row else None

    def cancel_pending_jobs(self):
        # One conditional write races safely with claim_job: only one can win.
        # A roam job is identified by its persisted source, never a browser list.
        with self.connection() as db:
            cursor = db.execute("UPDATE jobs SET status='cancelled',error=?,updated_at=? "
                "WHERE status='queued' AND backend_prompt_id IS NULL "
                "AND NOT EXISTS (SELECT 1 FROM roam_jobs WHERE roam_jobs.job_id=jobs.id)",
                ("已取消待执行的生成任务。", now()))
            return cursor.rowcount

    def claim_job(self, iid):
        with self.connection() as db:
            cursor = db.execute("UPDATE jobs SET status='submitting',error=NULL,updated_at=? WHERE id=? AND status='queued' AND backend_prompt_id IS NULL",(now(),iid))
            return cursor.rowcount == 1

    def update_job(self, iid, status=None, **fields):
        if set(fields) - {"backend_prompt_id", "error"}:
            raise ValueError("Unknown job update field")
        if status:
            fields["status"] = status
        fields["updated_at"] = now()
        assignments = ",".join(f"{key}=?" for key in fields)
        with self.connection() as db:
            # Cancellation wins races with late backend responses.
            db.execute(f"UPDATE jobs SET {assignments} WHERE id=? AND status NOT IN ('cancelled','completed','failed')", (*fields.values(), iid))
        return self.job(iid)

    def attach_prompt(self, iid, prompt_id):
        with self.connection() as db:
            # Retain the external id even if cancellation raced with POST /prompt.
            db.execute("UPDATE jobs SET backend_prompt_id=?,updated_at=? WHERE id=?", (prompt_id, now(), iid))
        return self.job(iid)

    def complete(self, iid, outputs):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            job = db.execute("SELECT status FROM jobs WHERE id=?", (iid,)).fetchone()
            # A late retry may have copied an expired output again. Never revive it.
            for item in outputs:
                old = db.execute("SELECT id FROM artifacts WHERE job_id=? AND node_id=? AND output_index=? AND deleted_at IS NOT NULL",
                                 (iid,str(item["node_id"]),item["index"])).fetchone()
                if old:
                    self._queue_deletion(db,old["id"],item.get("local_path"))
            if not job or job["status"] in ("cancelled", "failed", "completed"):
                return
            for item in outputs:
                db.execute("INSERT OR IGNORE INTO artifacts (id,job_id,node_id,output_index,descriptor,created_at,local_path,content_type) VALUES (?,?,?,?,?,?,?,?)", (str(uuid.uuid4()),iid,str(item["node_id"]),item["index"],encode(item),now(),item.get("local_path"),item.get("content_type")))
            db.execute("UPDATE jobs SET status='completed',error=NULL,updated_at=? WHERE id=?", (now(),iid))

    def recover_submissions(self):
        with self.connection() as db:
            db.execute("UPDATE jobs SET status='unknown',error='应用在提交期间退出，需要与后端核对。',updated_at=? WHERE status='submitting' AND backend_prompt_id IS NULL", (now(),))

    def unknown_jobs(self):
        with self.connection() as db:
            return [self._job(r) for r in db.execute("SELECT j.*,CASE WHEN EXISTS (SELECT 1 FROM roam_jobs s WHERE s.job_id=j.id) THEN 'roam' ELSE 'generate' END AS source FROM jobs j WHERE status='unknown'")]

    @staticmethod
    def _artifact(row):
        result = dict(row)
        result["seed_applied"] = bool(result.get("seed_applied"))
        result["image_url"] = f"/api/artifacts/{result['id']}/image"
        result.pop("descriptor", None)
        return result

    def counts(self):
        with self.connection() as db:
            return self._counts(db)

    @staticmethod
    def _counts(db):
        total = db.execute("SELECT count(*) FROM artifacts WHERE deleted_at IS NULL").fetchone()[0]
        roam = db.execute("SELECT count(*) FROM artifacts a JOIN roam_jobs r ON r.job_id=a.job_id WHERE a.deleted_at IS NULL AND a.roam_hidden_at IS NULL").fetchone()[0]
        generated = db.execute("SELECT count(*) FROM artifacts a WHERE a.deleted_at IS NULL AND a.generated_hidden_at IS NULL AND NOT EXISTS (SELECT 1 FROM roam_jobs r WHERE r.job_id=a.job_id)").fetchone()[0]
        return {"artifacts": total, "roam": roam, "generate": generated,
                "liked":db.execute("SELECT count(*) FROM feedback f JOIN artifacts a ON a.id=f.artifact_id WHERE a.deleted_at IS NULL AND f.actor_id='local' AND f.value=1").fetchone()[0]}

    def artifacts(self, liked=False, limit=200, before=None, source="all"):
        return self.artifact_page(liked=liked,limit=limit,before=before,source=source)["artifacts"]

    @staticmethod
    def _roam_anchor(db, identifier):
        """Keep a removed cursor near its original position, preferring older."""
        row = db.execute("SELECT a.id,a.created_at,a.deleted_at,a.roam_hidden_at FROM artifacts a JOIN roam_jobs r ON r.job_id=a.job_id WHERE a.id=?", (identifier,)).fetchone()
        if row and row["deleted_at"] is None and row["roam_hidden_at"] is None:
            return row
        if row:
            older = db.execute("SELECT a.id,a.created_at FROM artifacts a JOIN roam_jobs r ON r.job_id=a.job_id "
                               "WHERE a.deleted_at IS NULL AND a.roam_hidden_at IS NULL AND (a.created_at<? OR (a.created_at=? AND a.id<?)) "
                               "ORDER BY a.created_at DESC,a.id DESC LIMIT 1", (row["created_at"], row["created_at"], row["id"])).fetchone()
            if older:
                return older
            return db.execute("SELECT a.id,a.created_at FROM artifacts a JOIN roam_jobs r ON r.job_id=a.job_id "
                              "WHERE a.deleted_at IS NULL AND a.roam_hidden_at IS NULL AND (a.created_at>? OR (a.created_at=? AND a.id>?)) "
                              "ORDER BY a.created_at,a.id LIMIT 1", (row["created_at"], row["created_at"], row["id"])).fetchone()
        return db.execute("SELECT a.id,a.created_at FROM artifacts a JOIN roam_jobs r ON r.job_id=a.job_id "
                          "WHERE a.deleted_at IS NULL AND a.roam_hidden_at IS NULL ORDER BY a.created_at DESC,a.id DESC LIMIT 1").fetchone()

    def roam_view(self, payload=None):
        if payload is not None:
            identifier, timestamp = payload.get("artifact_id"), payload.get("viewed_at")
            if "artifact_id" not in payload or (identifier is not None and (not isinstance(identifier, str) or not identifier or len(identifier) > 100)):
                raise ValidationError("漫游 artifact_id 须为图片 ID 或 null。")
            if type(timestamp) is not int or not 0 <= timestamp <= 2**53-1:
                raise ValidationError("漫游 viewed_at 须为非负安全整数毫秒时间戳。")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE" if payload is not None else "BEGIN")
            saved = db.execute("SELECT artifact_id,viewed_at FROM roam_view WHERE actor_id='local'").fetchone()
            if payload is not None and (saved is None or timestamp > saved["viewed_at"]):
                if identifier is not None and not db.execute("SELECT a.id FROM artifacts a JOIN roam_jobs r ON r.job_id=a.job_id WHERE a.id=? AND a.deleted_at IS NULL AND a.roam_hidden_at IS NULL", (identifier,)).fetchone():
                    raise NotFoundError("当前漫游图片已清理或不存在。")
                db.execute("INSERT INTO roam_view VALUES ('local',?,?) ON CONFLICT(actor_id) DO UPDATE SET artifact_id=excluded.artifact_id,viewed_at=excluded.viewed_at", (identifier, timestamp))
                saved = {"artifact_id": identifier, "viewed_at": timestamp}
            if saved is None:
                return {"artifact_id": None, "viewed_at": 0}
            anchor = self._roam_anchor(db, saved["artifact_id"]) if saved["artifact_id"] else None
            return {"artifact_id": anchor["id"] if anchor else None, "viewed_at": saved["viewed_at"]}

    def artifact_page(self, liked=False, limit=200, before=None, source="all", around=None):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValidationError("图片分页数量必须为 1 到 200。")
        if source not in ("all", "roam", "generate"):
            raise ValidationError("图片来源必须为 all、roam 或 generate。")
        if around is not None and (source != "roam" or liked or before is not None or not isinstance(around, str) or not around or len(around) > 100):
            raise ValidationError("around 仅用于漫游图片，不能与 before 或喜欢筛选同时使用。")
        with self.connection() as db:
            db.execute("BEGIN")
            where_source = "1" if source == "all" else ("EXISTS" if source == "roam" else "NOT EXISTS") + " (SELECT 1 FROM roam_jobs s WHERE s.job_id=a.job_id)"
            # Keep hidden/deleted markers usable for stable pagination, but never
            # return them as generated results (all/liked still retain hidden likes).
            where_visible = "a.generated_hidden_at IS NULL" if source == "generate" else "a.roam_hidden_at IS NULL" if source == "roam" else "1"
            marker = None
            if before:
                marker = db.execute(f"SELECT a.created_at,a.id FROM artifacts a WHERE a.id=? AND {where_source}",(before,)).fetchone()
                if not marker:
                    raise ValidationError("图片分页位置无效，请刷新列表。")
            offset, anchor = 0, None
            if around is not None:
                anchor = self._roam_anchor(db, around)
                if anchor:
                    rank = db.execute("SELECT count(*) FROM artifacts a JOIN roam_jobs r ON r.job_id=a.job_id "
                                      "WHERE a.deleted_at IS NULL AND a.roam_hidden_at IS NULL AND (a.created_at>? OR (a.created_at=? AND a.id>?))",
                                      (anchor["created_at"], anchor["created_at"], anchor["id"])).fetchone()[0]
                    available = db.execute("SELECT count(*) FROM artifacts a JOIN roam_jobs r ON r.job_id=a.job_id WHERE a.deleted_at IS NULL AND a.roam_hidden_at IS NULL").fetchone()[0]
                    offset = max(0, min(rank - limit // 2, available - limit))
            rows = db.execute(f"""SELECT a.*,j.positive,j.negative,j.seed,f.value AS feedback,
                CASE WHEN EXISTS (SELECT 1 FROM roam_jobs s WHERE s.job_id=a.job_id) THEN 'roam' ELSE 'generate' END AS source,
                json_type(r.config,'$.bindings.seed')='object' AS seed_applied
                FROM artifacts a JOIN jobs j ON j.id=a.job_id
                JOIN backend_revisions r ON r.id=j.revision_id
                LEFT JOIN feedback f ON f.artifact_id=a.id AND f.actor_id='local'
                WHERE a.deleted_at IS NULL AND {where_source} AND {where_visible} AND (?=0 OR f.value=1)
                AND (?=0 OR a.created_at<? OR (a.created_at=? AND a.id<?))
                ORDER BY a.created_at DESC,a.id DESC LIMIT ? OFFSET ?""",
                (int(liked),int(marker is not None),marker["created_at"] if marker else "",marker["created_at"] if marker else "",marker["id"] if marker else "",limit+1,offset))
            items = [self._artifact(r) for r in rows]
            has_more = len(items) > limit
            items = items[:limit]
            counts = self._counts(db)
            total = db.execute(f"SELECT count(*) FROM artifacts a LEFT JOIN feedback f ON f.artifact_id=a.id AND f.actor_id='local' "
                               f"WHERE a.deleted_at IS NULL AND {where_source} AND {where_visible} AND (?=0 OR f.value=1)", (int(liked),)).fetchone()[0]
            return {"artifacts":items,"has_more":has_more,"has_newer":offset > 0 if around is not None else marker is not None,
                    "anchor_id":anchor["id"] if anchor else None,
                    "next_cursor":items[-1]["id"] if has_more else None,
                    "total":total,"counts":counts,"source":source,
                    "revision":self._artifact_revision(db)}

    @staticmethod
    def _artifact_revision(db):
        # Both irreversible visibility transitions invalidate in-flight pages.
        return db.execute("SELECT count(deleted_at)+count(generated_hidden_at)+count(roam_hidden_at) FROM artifacts").fetchone()[0]

    def artifact_revision(self):
        with self.connection() as db:
            return self._artifact_revision(db)

    def clear_generated(self, iid=None):
        """Atomically remove a generated snapshot, preserving any actor's likes."""
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if iid is not None:
                row = db.execute("SELECT EXISTS (SELECT 1 FROM roam_jobs r WHERE r.job_id=a.job_id) AS roam FROM artifacts a WHERE a.id=?", (iid,)).fetchone()
                if row and row["roam"]:
                    raise ValidationError("只能清理生成页面的图片。")
            rows = db.execute("""SELECT a.id,a.local_path,
                EXISTS (SELECT 1 FROM feedback f WHERE f.artifact_id=a.id AND f.value=1) AS liked
                FROM artifacts a WHERE a.deleted_at IS NULL AND a.generated_hidden_at IS NULL
                AND NOT EXISTS (SELECT 1 FROM roam_jobs r WHERE r.job_id=a.job_id)
                AND (? IS NULL OR a.id=?)""", (iid, iid)).fetchall()
            removed = hidden = 0
            timestamp = now()
            for row in rows:
                if row["liked"]:
                    db.execute("UPDATE artifacts SET generated_hidden_at=? WHERE id=?", (timestamp, row["id"]))
                    hidden += 1
                else:
                    db.execute("UPDATE artifacts SET deleted_at=? WHERE id=?", (timestamp, row["id"]))
                    self._queue_deletion(db, row["id"], row["local_path"])
                    removed += 1
            return {"removed": removed, "hidden": hidden, "revision": self._artifact_revision(db)}

    def artifact(self, iid):
        with self.connection() as db:
            row = db.execute("""SELECT a.*,j.positive,j.negative,j.seed,f.value AS feedback,
                CASE WHEN EXISTS (SELECT 1 FROM roam_jobs s WHERE s.job_id=a.job_id) THEN 'roam' ELSE 'generate' END AS source,
                json_type(r.config,'$.bindings.seed')='object' AS seed_applied
                FROM artifacts a JOIN jobs j ON j.id=a.job_id
                JOIN backend_revisions r ON r.id=j.revision_id
                LEFT JOIN feedback f ON f.artifact_id=a.id AND f.actor_id='local' WHERE a.id=? AND a.deleted_at IS NULL""", (iid,)).fetchone()
            return self._artifact(row) if row else None

    def artifact_source(self, iid):
        with self.connection() as db:
            row = db.execute("SELECT a.descriptor,r.config FROM artifacts a JOIN jobs j ON j.id=a.job_id JOIN backend_revisions r ON r.id=j.revision_id WHERE a.id=? AND a.deleted_at IS NULL", (iid,)).fetchone()
            return (json.loads(row["config"]),json.loads(row["descriptor"])) if row else None

    def cache_artifact(self,iid,output):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute("UPDATE artifacts SET local_path=?,content_type=? WHERE id=? AND deleted_at IS NULL",(output["local_path"],output["content_type"],iid))
            if cursor.rowcount:
                return True
            if db.execute("SELECT 1 FROM artifacts WHERE id=?",(iid,)).fetchone():
                self._queue_deletion(db,iid,output["local_path"])
            return False

    @staticmethod
    def _queue_deletion(db,iid,path):
        if path:
            db.execute("INSERT OR IGNORE INTO pending_image_deletions (artifact_id,local_path,created_at) VALUES (?,?,?)",(iid,path,now()))

    def expire_artifacts(self, cutoff, limit=100):
        """Commit tombstones before any file operation; feedback wins by write order."""
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("""SELECT a.id,a.local_path FROM artifacts a
                WHERE a.deleted_at IS NULL AND utc_timestamp(a.created_at)<=utc_timestamp(?)
                AND NOT EXISTS (SELECT 1 FROM feedback f WHERE f.artifact_id=a.id AND f.value=1)
                ORDER BY a.created_at,a.id LIMIT ?""",(cutoff,limit)).fetchall()
            timestamp = now()
            for row in rows:
                db.execute("UPDATE artifacts SET deleted_at=? WHERE id=?",(timestamp,row["id"]))
                self._queue_deletion(db,row["id"],row["local_path"])
            return len(rows)

    def trim_roam_artifacts(self, max_history, limit=100):
        """Trim visible roam history; preserve liked files outside the roam view."""
        if type(max_history) is not int or max_history < 0 or type(limit) is not int or limit < 1:
            raise ValidationError("漫游清理数量必须是非负整数，批量大小必须是正整数。")
        if max_history == 0:
            return 0
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            saved = db.execute("SELECT artifact_id FROM roam_view WHERE actor_id='local'").fetchone()
            anchor = self._roam_anchor(db, saved["artifact_id"]) if saved and saved["artifact_id"] else None
            if anchor is None:
                return 0
            scope = """FROM artifacts a JOIN roam_jobs r ON r.job_id=a.job_id
                WHERE a.deleted_at IS NULL AND a.roam_hidden_at IS NULL
                AND (utc_timestamp(a.created_at)<utc_timestamp(?)
                     OR (utc_timestamp(a.created_at)=utc_timestamp(?) AND a.id<?))"""
            parameters = (anchor["created_at"], anchor["created_at"], anchor["id"])
            excess = db.execute("SELECT count(*) " + scope, parameters).fetchone()[0] - max_history
            if excess <= 0:
                return 0
            rows = db.execute("SELECT a.id,a.local_path,EXISTS (SELECT 1 FROM feedback f WHERE f.artifact_id=a.id AND f.value=1) AS liked " + scope +
                              " ORDER BY utc_timestamp(a.created_at),a.id LIMIT ?", (*parameters, min(excess, limit))).fetchall()
            timestamp = now()
            for row in rows:
                if row["liked"]:
                    db.execute("UPDATE artifacts SET roam_hidden_at=? WHERE id=?", (timestamp, row["id"]))
                else:
                    db.execute("UPDATE artifacts SET deleted_at=? WHERE id=?", (timestamp, row["id"]))
                    self._queue_deletion(db, row["id"], row["local_path"])
            return len(rows)

    def cleanup_counts(self):
        with self.connection() as db:
            return {"deleted":db.execute("SELECT count(*) FROM artifacts WHERE deleted_at IS NOT NULL").fetchone()[0],
                    "pending":db.execute("SELECT count(*) FROM pending_image_deletions").fetchone()[0]}

    def rate(self, iid, value):
        value = feedback_value(value)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM artifacts WHERE id=? AND deleted_at IS NULL", (iid,)).fetchone():
                raise ValidationError("图片不存在。")
            was_liked = bool(db.execute("SELECT 1 FROM feedback WHERE artifact_id=? AND actor_id='local' AND value=1", (iid,)).fetchone())
            if value is None:
                db.execute("DELETE FROM feedback WHERE artifact_id=? AND actor_id='local'", (iid,))
            else:
                db.execute("INSERT INTO feedback VALUES (?,'local',?,?) ON CONFLICT(artifact_id,actor_id) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (iid,value,now()))
            if was_liked != (value == 1):
                record_feedback(db, iid, "local", value == 1)
        return self.artifact(iid)
