"""SQLite repository; no HTTP or generation-backend dependency."""
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import uuid

from .recommendation import initialize_recommendation, record_feedback

from ..domain import ConflictError, NotFoundError, ValidationError, actual_seed, feedback_value, generation_count, roam_can_enqueue


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


def prompt_tags(positive):
    """Historical comma-separated terms; preserve text and direction semantics."""
    return {term.strip() for term in positive.split(",") if term.strip()}


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
                backend_pending INTEGER NOT NULL DEFAULT 0,
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
                actor_id TEXT NOT NULL, value INTEGER NOT NULL CHECK(value IN (-1,1)),
                updated_at TEXT NOT NULL, PRIMARY KEY(artifact_id, actor_id));
            """)
            if "backend_pending" not in {row["name"] for row in db.execute("PRAGMA table_info(jobs)")}:
                db.execute("ALTER TABLE jobs ADD COLUMN backend_pending INTEGER NOT NULL DEFAULT 0")
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
                epoch TEXT NOT NULL, candidate TEXT NOT NULL, created_at TEXT NOT NULL, discarded_at TEXT);
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
        result.pop("backend_pending", None)
        return result

    def jobs(self, limit=100):
        with self.connection() as db:
            return self._job_rows(db, limit)

    @classmethod
    def _job_rows(cls, db, limit, offset=0):
        rows = db.execute("SELECT j.*,CASE WHEN EXISTS (SELECT 1 FROM roam_jobs s WHERE s.job_id=j.id) THEN 'roam' ELSE 'generate' END AS source,json_extract(r.config,'$.name') AS backend_name,COALESCE(json_extract(r.config,'$.kind'),'comfyui') AS backend_kind,json_type(r.config,'$.bindings.seed')='object' AS seed_applied FROM jobs j JOIN backend_revisions r ON r.id=j.revision_id ORDER BY j.created_at DESC,j.id DESC LIMIT ? OFFSET ?", (limit, offset))
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
            row = db.execute("SELECT j.*,CASE WHEN EXISTS (SELECT 1 FROM roam_jobs s WHERE s.job_id=j.id) THEN 'roam' ELSE 'generate' END AS source,json_extract(r.config,'$.name') AS backend_name,COALESCE(json_extract(r.config,'$.kind'),'comfyui') AS backend_kind,json_type(r.config,'$.bindings.seed')='object' AS seed_applied FROM jobs j JOIN backend_revisions r ON r.id=j.revision_id WHERE j.id=?", (iid,)).fetchone()
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
                             "WHERE r.epoch=? AND r.discarded_at IS NULL AND j.status IN ('failed','unknown','cancelled') "
                             "ORDER BY j.created_at DESC,j.id DESC LIMIT 1", (epoch,)).fetchone()
        if failure:
            message = failure["error"] or "漫游生成失败或已取消，请在漫游设置中保存后重试。"
            db.execute("INSERT OR IGNORE INTO roam_runs(epoch,error) VALUES (?,?)", (epoch, message[:1000]))
        pause = db.execute("SELECT error FROM roam_runs WHERE epoch=?", (epoch,)).fetchone()
        pending = db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','submitting','running')").fetchone()[0]
        roam_pending = db.execute("SELECT count(*) FROM jobs j JOIN roam_jobs r ON r.job_id=j.id "
                                  "WHERE r.discarded_at IS NULL AND j.status IN ('queued','submitting','running')").fetchone()[0]
        return {"ready": ready, "pending": pending, "roam_pending": roam_pending, "paused": pause is not None,
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
            if payload is not None and roam_can_enqueue(result, target):
                identifier = self._create_job(db, payload)
                db.execute("INSERT INTO roam_jobs(job_id,epoch,candidate,created_at) VALUES (?,?,?,?)",
                           (identifier, epoch, snapshot, now()))
                result["pending"] += 1
                result["roam_pending"] += 1
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

    @staticmethod
    def discard_roam_prefetch(db):
        """Called inside the settings transaction; keep the saved cursor and older images."""
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='roam_jobs'").fetchone() is None:
            return
        timestamp = now()
        anchor = db.execute("SELECT a.created_at,a.id FROM roam_view v JOIN artifacts a ON a.id=v.artifact_id "
                            "WHERE v.actor_id='local' AND a.deleted_at IS NULL AND a.roam_hidden_at IS NULL").fetchone()
        newer = " AND (created_at>? OR (created_at=? AND id>?))" if anchor else ""
        parameters = (anchor["created_at"], anchor["created_at"], anchor["id"]) if anchor else ()
        db.execute("UPDATE artifacts SET roam_hidden_at=? WHERE deleted_at IS NULL AND roam_hidden_at IS NULL "
                   "AND EXISTS (SELECT 1 FROM roam_jobs r WHERE r.job_id=artifacts.job_id)" + newer,
                   (timestamp, *parameters))
        db.execute("UPDATE roam_jobs SET discarded_at=? WHERE discarded_at IS NULL "
                   "AND job_id IN (SELECT id FROM jobs WHERE status IN ('queued','submitting','running','unknown'))", (timestamp,))
        db.execute("UPDATE jobs SET status='cancelled',error=?,updated_at=? "
                   "WHERE status='queued' AND backend_prompt_id IS NULL "
                   "AND EXISTS (SELECT 1 FROM roam_jobs r WHERE r.job_id=jobs.id AND r.discarded_at IS NOT NULL)",
                   ("漫游设置已切换，取消旧预取任务。", timestamp))

    def roam_prompt_reference(self, epoch, anchor_id):
        with self.connection() as db:
            db.execute("BEGIN")
            row = db.execute("SELECT r.candidate,j.positive,j.negative FROM roam_jobs r JOIN jobs j ON j.id=r.job_id "
                             "WHERE r.epoch=? AND r.discarded_at IS NULL AND j.status IN ('queued','submitting','running','completed') "
                             "ORDER BY j.created_at DESC,j.id DESC LIMIT 1", (epoch,)).fetchone()
            if row is None:
                if anchor_id is None:
                    saved = db.execute("SELECT artifact_id FROM roam_view WHERE actor_id='local'").fetchone()
                    anchor_id = saved["artifact_id"] if saved else None
                row = db.execute("SELECT r.candidate,j.positive,j.negative FROM artifacts a JOIN jobs j ON j.id=a.job_id "
                                 "JOIN roam_jobs r ON r.job_id=j.id WHERE a.id=? AND a.deleted_at IS NULL "
                                 "AND a.roam_hidden_at IS NULL AND r.discarded_at IS NULL", (anchor_id,)).fetchone()
            if row is None:
                return None
            snapshot = json.loads(row["candidate"])
            return {"candidate_id": snapshot.get("candidate_id", ""), "positive": row["positive"],
                    "negative": row["negative"], "terms": snapshot.get("terms", [])}

    def dispatch_jobs(self, limit=2):
        with self.connection() as db:
            # Count and select from one snapshot. Pending work always returns,
            # including cancelled or uncertain jobs still occupying the backend.
            db.execute("BEGIN")
            query = ("SELECT j.*,CASE WHEN r.job_id IS NULL THEN 'generate' ELSE 'roam' END AS source,"
                     "json_extract(b.config,'$.name') AS backend_name,"
                     "COALESCE(json_extract(b.config,'$.kind'),'comfyui') AS backend_kind,json_type(b.config,'$.bindings.seed')='object' AS seed_applied "
                     "FROM jobs j LEFT JOIN roam_jobs r ON r.job_id=j.id "
                     "JOIN backend_revisions b ON b.id=j.revision_id ")
            pending = db.execute(query + "WHERE j.backend_pending=1 ORDER BY j.created_at,j.id").fetchall()
            slots = max(0, limit - len(pending))
            queued = db.execute(query + "WHERE j.backend_pending=0 AND j.status='queued' AND j.backend_prompt_id IS NULL "
                                "ORDER BY CASE WHEN r.job_id IS NULL THEN 0 ELSE 1 END,j.created_at,j.id LIMIT ?",
                                (slots,)).fetchall()
            return [{**self._job(row), "backend_pending": bool(row["backend_pending"])} for row in [*pending, *queued]]

    def finish_dispatch(self, iid):
        with self.connection() as db:
            db.execute("UPDATE jobs SET backend_pending=0 WHERE id=?", (iid,))

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
            cursor = db.execute("UPDATE jobs SET status='submitting',backend_pending=1,error=NULL,updated_at=? WHERE id=? AND status='queued' AND backend_pending=0 AND backend_prompt_id IS NULL",(now(),iid))
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
            db.execute("UPDATE jobs SET backend_prompt_id=?,backend_pending=1,updated_at=? WHERE id=?", (prompt_id, now(), iid))
        return self.job(iid)

    def complete(self, iid, outputs):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            job = db.execute("SELECT j.status,r.discarded_at,r.candidate FROM jobs j LEFT JOIN roam_jobs r ON r.job_id=j.id WHERE j.id=?", (iid,)).fetchone()
            # A late retry may have copied an expired output again. Never revive it.
            for item in outputs:
                old = db.execute("SELECT id FROM artifacts WHERE job_id=? AND node_id=? AND output_index=? AND deleted_at IS NOT NULL",
                                 (iid,str(item["node_id"]),item["index"])).fetchone()
                if old:
                    self._queue_deletion(db,old["id"],item.get("local_path"))
            if not job or job["status"] in ("cancelled", "failed", "completed"):
                return
            for item in outputs:
                db.execute("INSERT OR IGNORE INTO artifacts (id,job_id,node_id,output_index,descriptor,created_at,local_path,content_type,roam_hidden_at) VALUES (?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()),iid,str(item["node_id"]),item["index"],encode(item),now(),item.get("local_path"),item.get("content_type"),job["discarded_at"]))
            if job["candidate"]:
                snapshot = json.loads(job["candidate"])
                score = snapshot.get("mean_score")
                if (isinstance(score, (int, float)) and math.isfinite(score)
                        and all(snapshot.get(key) is not None for key in (
                            "feature_version", "policy_version", "state_revision", "score_reset_revision"))):
                    images = db.execute("SELECT id FROM artifacts WHERE job_id=? AND deleted_at IS NULL", (iid,))
                    self._save_image_scores(db, [dict(artifact_id=image["id"], score=score,
                        feature_version=snapshot["feature_version"], policy_version=snapshot["policy_version"],
                        state_revision=snapshot["state_revision"]) for image in images],
                        snapshot["score_reset_revision"])
            db.execute("UPDATE jobs SET status='completed',error=NULL,updated_at=? WHERE id=?", (now(),iid))

    def recover_submissions(self):
        with self.connection() as db:
            # A running row may have released its window before an interrupted
            # image save. Inspect its accepted prompt again; never resubmit it.
            db.execute("UPDATE jobs SET backend_pending=1 WHERE status IN ('submitting','running') "
                       "AND backend_prompt_id IS NOT NULL")
            db.execute("UPDATE jobs SET status='unknown',backend_pending=1,"
                       "error='应用在提交期间退出，需要与后端核对。',updated_at=? "
                       "WHERE status='submitting' AND backend_prompt_id IS NULL", (now(),))

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

    def image_score_cache(self, identifiers, feature_version, policy_version):
        identifiers = tuple(dict.fromkeys(identifiers))
        scores = {}
        with self.connection() as db:
            for start in range(0, len(identifiers), 500):
                batch = identifiers[start:start + 500]
                placeholders = ",".join("?" for _ in batch)
                rows = db.execute(f"SELECT * FROM artifact_preference_scores WHERE artifact_id IN ({placeholders}) "
                                  "AND feature_version=? AND policy_version=?",
                                  (*batch, feature_version, policy_version))
                for row in rows:
                    item = dict(row)
                    scores[item.pop("artifact_id")] = item
            score_range = db.execute("SELECT score_min,score_max FROM recommendation_score_range "
                                    "WHERE user_id='local' AND feature_version=? AND policy_version=?",
                                    (feature_version, policy_version)).fetchone()
            refreshed_at = db.execute("SELECT MAX(refreshed_at) FROM artifact_preference_scores "
                                      "WHERE feature_version=? AND policy_version=?",
                                      (feature_version, policy_version)).fetchone()[0]
        return dict(scores=scores, score_min=score_range["score_min"] if score_range else None,
                    score_max=score_range["score_max"] if score_range else None, refreshed_at=refreshed_at)

    @staticmethod
    def _save_image_scores(db, records, reset_revision, refreshed_at=None):
        reset = db.execute("SELECT revision FROM recommendation_resets WHERE user_id='local'").fetchone()
        if (reset["revision"] if reset else 0) != reset_revision:
            return
        scored_at = now()
        # A score computed before image deletion must not recreate its cache later.
        db.executemany("INSERT INTO artifact_preference_scores SELECT ?,?,?,?,?,?,? "
                       "WHERE EXISTS (SELECT 1 FROM artifacts WHERE id=? AND deleted_at IS NULL) "
                       "ON CONFLICT(artifact_id) DO UPDATE SET score=excluded.score, "
                       "feature_version=excluded.feature_version,policy_version=excluded.policy_version, "
                       "state_revision=excluded.state_revision,scored_at=excluded.scored_at, "
                       "refreshed_at=COALESCE(excluded.refreshed_at,artifact_preference_scores.refreshed_at)",
                       [(record["artifact_id"], record["score"], record["feature_version"], record["policy_version"],
                         record["state_revision"], scored_at, refreshed_at, record["artifact_id"]) for record in records])

    def save_image_scores(self, records, reset_revision, refreshed_at=None):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._save_image_scores(db, records, reset_revision, refreshed_at)

    def clear_deleted_image_scores(self):
        with self.connection() as db:
            return db.execute("DELETE FROM artifact_preference_scores WHERE artifact_id IN "
                              "(SELECT id FROM artifacts WHERE deleted_at IS NOT NULL)").rowcount

    def liked_positive_prompts(self, actor_id="local"):
        with self.connection() as db:
            rows = db.execute("SELECT DISTINCT j.positive FROM feedback f "
                              "JOIN artifacts a ON a.id=f.artifact_id JOIN jobs j ON j.id=a.job_id "
                              "WHERE f.actor_id=? AND f.value=1 AND a.deleted_at IS NULL "
                              "ORDER BY j.positive", (actor_id,)).fetchall()
        return [row["positive"] for row in rows]

    def liked_tags(self):
        with self.connection() as db:
            counts = Counter()
            rows = db.execute("SELECT j.positive FROM feedback f "
                              "JOIN artifacts a ON a.id=f.artifact_id JOIN jobs j ON j.id=a.job_id "
                              "WHERE f.actor_id='local' AND f.value=1 AND a.deleted_at IS NULL")
            for row in rows:
                counts.update(prompt_tags(row["positive"]))
        return [{"text": text, "count": counts[text]} for text in sorted(counts)]

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

    def artifact_page(self, liked=False, limit=200, before=None, source="all", around=None, tags=()):
        if tags and not liked:
            raise ValidationError("标签筛选仅用于喜欢图片。")
        selected_tags = set(tags)
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValidationError("图片分页数量必须为 1 到 200。")
        if source not in ("all", "roam", "generate"):
            raise ValidationError("图片来源必须为 all、roam 或 generate。")
        if around is not None and (source != "roam" or liked or before is not None or not isinstance(around, str) or not around or len(around) > 100):
            raise ValidationError("around 仅用于漫游图片，不能与 before 或喜欢筛选同时使用。")
        with self.connection() as db:
            db.execute("BEGIN")
            where_tags = "1"
            if selected_tags:
                db.create_function("has_prompt_tags", 1, lambda positive: selected_tags <= prompt_tags(positive), deterministic=True)
                where_tags = "has_prompt_tags(j.positive)"
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
                COALESCE(json_extract(r.config,'$.kind'),'comfyui') AS backend_kind,json_type(r.config,'$.bindings.seed')='object' AS seed_applied
                FROM artifacts a JOIN jobs j ON j.id=a.job_id
                JOIN backend_revisions r ON r.id=j.revision_id
                LEFT JOIN feedback f ON f.artifact_id=a.id AND f.actor_id='local'
                WHERE a.deleted_at IS NULL AND {where_source} AND {where_visible} AND {where_tags} AND (?=0 OR f.value=1)
                AND (?=0 OR a.created_at<? OR (a.created_at=? AND a.id<?))
                ORDER BY a.created_at DESC,a.id DESC LIMIT ? OFFSET ?""",
                (int(liked),int(marker is not None),marker["created_at"] if marker else "",marker["created_at"] if marker else "",marker["id"] if marker else "",limit+1,offset))
            items = [self._artifact(r) for r in rows]
            has_more = len(items) > limit
            items = items[:limit]
            counts = self._counts(db)
            total = db.execute(f"SELECT count(*) FROM artifacts a JOIN jobs j ON j.id=a.job_id LEFT JOIN feedback f ON f.artifact_id=a.id AND f.actor_id='local' "
                               f"WHERE a.deleted_at IS NULL AND {where_source} AND {where_visible} AND {where_tags} AND (?=0 OR f.value=1)", (int(liked),)).fetchone()[0]
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

    def liked_scoring_inputs(self, tags=()):
        selected = set(tags)
        with self.connection() as db:
            db.execute("BEGIN")
            db.create_function("has_prompt_tags", 1, lambda positive: selected <= prompt_tags(positive), deterministic=True)
            rows = db.execute("""SELECT a.*,j.positive,j.negative,j.seed,f.value AS feedback,
                CASE WHEN rj.job_id IS NULL THEN 'generate' ELSE 'roam' END AS source,
                COALESCE(json_extract(r.config,'$.kind'),'comfyui') AS backend_kind,json_type(r.config,'$.bindings.seed')='object' AS seed_applied,rj.candidate AS scoring_snapshot
                FROM artifacts a JOIN jobs j ON j.id=a.job_id
                JOIN backend_revisions r ON r.id=j.revision_id
                JOIN feedback f ON f.artifact_id=a.id AND f.actor_id='local' AND f.value=1
                LEFT JOIN roam_jobs rj ON rj.job_id=a.job_id
                WHERE a.deleted_at IS NULL AND has_prompt_tags(j.positive)
                ORDER BY a.created_at DESC,a.id DESC""").fetchall()
            items = []
            for row in rows:
                data = dict(row)
                raw = data.pop("scoring_snapshot")
                try:
                    snapshot = json.loads(raw) if raw else None
                except ValueError:
                    snapshot = None
                items.append({"artifact": self._artifact(data), "snapshot": snapshot})
            return {"items": items, "revision": self._artifact_revision(db)}

    def artifact(self, iid):
        with self.connection() as db:
            return self._read_artifact(db, iid)

    def _read_artifact(self, db, iid):
        row = db.execute("""SELECT a.*,j.positive,j.negative,j.seed,f.value AS feedback,
            CASE WHEN EXISTS (SELECT 1 FROM roam_jobs s WHERE s.job_id=a.job_id) THEN 'roam' ELSE 'generate' END AS source,
            COALESCE(json_extract(r.config,'$.kind'),'comfyui') AS backend_kind,json_type(r.config,'$.bindings.seed')='object' AS seed_applied
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
            previous = db.execute("SELECT value FROM feedback WHERE artifact_id=? AND actor_id='local'", (iid,)).fetchone()
            previous_value = previous["value"] if previous else None
            if value is None:
                db.execute("DELETE FROM feedback WHERE artifact_id=? AND actor_id='local'", (iid,))
            else:
                db.execute("INSERT INTO feedback VALUES (?,'local',?,?) ON CONFLICT(artifact_id,actor_id) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (iid,value,now()))
            if previous_value != value:
                record_feedback(db, iid, "local", value)
            # Capture the saved state before releasing the write transaction;
            # concurrent cleanup after commit must not turn success into a 404.
            return self._read_artifact(db, iid)
