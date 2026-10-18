"""SQLite persistence for recommendation contracts, independent of business modules."""
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
import struct

from ..contracts.recommendation import (FeedbackUpdate, PolicyRecord, ResetResult, ResetState,
                                        ScoreCandidate, ScoreTerm)
from ..domain import ConflictError


def initialize_recommendation(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS recommendation_score_range (
        user_id TEXT NOT NULL, feature_version TEXT NOT NULL, policy_version TEXT NOT NULL,
        score_min REAL NOT NULL, score_max REAL NOT NULL,
        PRIMARY KEY(user_id,feature_version,policy_version));
    CREATE TABLE IF NOT EXISTS artifact_preference_scores (
        artifact_id TEXT PRIMARY KEY REFERENCES artifacts(id), score REAL NOT NULL,
        feature_version TEXT NOT NULL, policy_version TEXT NOT NULL,
        state_revision INTEGER NOT NULL, scored_at TEXT NOT NULL, refreshed_at TEXT);
    CREATE TABLE IF NOT EXISTS recommendation_vectors (
        encoder_version TEXT NOT NULL, text TEXT NOT NULL, vector BLOB NOT NULL,
        PRIMARY KEY(encoder_version,text));
    CREATE TABLE IF NOT EXISTS recommendation_policy (
        user_id TEXT NOT NULL, feature_version TEXT NOT NULL, revision INTEGER NOT NULL,
        term_keys TEXT NOT NULL, precision BLOB NOT NULL, reward BLOB NOT NULL,
        evidence_count INTEGER NOT NULL,
        PRIMARY KEY(user_id,feature_version));
    CREATE TABLE IF NOT EXISTS recommendation_events (
        revision INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL, artifact_id TEXT NOT NULL, value INTEGER CHECK(value IN (-1,1)),
        candidate TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS recommendation_events_image
        ON recommendation_events(user_id,artifact_id,revision DESC);
    CREATE TABLE IF NOT EXISTS recommendation_resets (
        user_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
        event_floor INTEGER NOT NULL, reset_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS recommendation_reset_requests (
        user_id TEXT NOT NULL, request_id TEXT NOT NULL, expected_revision INTEGER NOT NULL,
        reset_revision INTEGER NOT NULL, reset_at TEXT NOT NULL,
        PRIMARY KEY(user_id,request_id));
    CREATE TABLE IF NOT EXISTS recommendation_evidence (
        user_id TEXT NOT NULL, feature_version TEXT NOT NULL, artifact_id TEXT NOT NULL,
        revision INTEGER NOT NULL, value INTEGER CHECK(value IN (-1,1)), candidate TEXT NOT NULL,
        PRIMARY KEY(user_id,feature_version,artifact_id));
    """)


def _encode(candidate):
    return json.dumps(asdict(candidate), ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _decode(value):
    value = json.loads(value)
    terms = value.get("terms")
    if not isinstance(terms, list) or not terms:
        raise ValueError("Missing historical prompt terms")
    parsed = []
    for term in terms:
        if not isinstance(term, dict) or not isinstance(term.get("text"), str) or not term["text"].strip():
            raise ValueError("Invalid historical prompt term")
        channel = term.get("channel", "positive")
        if channel not in ("positive", "negative"):
            raise ValueError("Invalid historical prompt channel")
        parsed.append(ScoreTerm(term["text"], channel))
    for channel in ("positive", "negative"):
        # Match the existing prompt join convention without importing candidate code.
        joined = ", ".join(t.text.strip().strip(",").strip() for t in parsed
                           if t.channel == channel and t.text.strip().strip(",").strip())
        if value.get(channel) != joined:
            raise ValueError("Historical prompt terms do not match generated text")
    identifier = value.get("candidate_id")
    if not isinstance(identifier, str) or not identifier:
        raise ValueError("Missing historical candidate identifier")
    return ScoreCandidate(identifier, value["positive"], value["negative"], tuple(parsed))


def record_feedback(db, artifact_id, user_id, value):
    """Called inside the transaction that saves a real feedback state transition."""
    previous = db.execute("SELECT candidate FROM recommendation_events WHERE user_id=? AND artifact_id=? "
                          "ORDER BY revision DESC LIMIT 1", (user_id, artifact_id)).fetchone()
    row = db.execute("SELECT r.candidate,j.positive,j.negative FROM artifacts a "
                     "JOIN jobs j ON j.id=a.job_id JOIN roam_jobs r ON r.job_id=a.job_id "
                     "WHERE a.id=?", (artifact_id,)).fetchone()
    candidate = None
    if row:
        try:
            candidate = _decode(row["candidate"])
            if candidate.positive != row["positive"] or candidate.negative != row["negative"]:
                candidate = None
        except (ValueError, TypeError, KeyError, AttributeError):
            pass
    if candidate is None and previous:
        candidate = _decode(previous["candidate"])
    if candidate is not None:
        db.execute("INSERT INTO recommendation_events(user_id,artifact_id,value,candidate) VALUES (?,?,?,?)",
                   (user_id, artifact_id, value, _encode(candidate)))


class SQLiteRecommendationStore:
    def __init__(self, repository):
        self.repository = repository
        with repository.connection() as db:
            initialize_recommendation(db)

    def observe_score_range(self, user_id, feature_version, policy_version, minimum, maximum):
        with self.repository.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO recommendation_score_range VALUES (?,?,?,?,?) "
                       "ON CONFLICT(user_id,feature_version,policy_version) DO UPDATE SET "
                       "score_min=MIN(score_min,excluded.score_min),score_max=MAX(score_max,excluded.score_max)",
                       (user_id, feature_version, policy_version, minimum, maximum))
            row = db.execute("SELECT score_min,score_max FROM recommendation_score_range "
                             "WHERE user_id=? AND feature_version=? AND policy_version=?",
                             (user_id, feature_version, policy_version)).fetchone()
            return row["score_min"], row["score_max"]

    def get_reset_state(self, user_id):
        with self.repository.connection() as db:
            row = db.execute("SELECT * FROM recommendation_resets WHERE user_id=?", (user_id,)).fetchone()
        return ResetState(row["revision"], row["event_floor"], row["reset_at"]) if row else ResetState()

    def reset_user(self, user_id, request_id, expected_reset_revision):
        with self.repository.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            # Replay before checking the current revision: a retry must not erase
            # feedback learned after the original request completed.
            previous = db.execute("SELECT * FROM recommendation_reset_requests WHERE user_id=? AND request_id=?",
                                  (user_id, request_id)).fetchone()
            if previous:
                if previous["expected_revision"] != expected_reset_revision:
                    raise ConflictError("重置请求标识已用于不同的修订。")
                return ResetResult(request_id, previous["reset_revision"], previous["reset_at"])
            current = db.execute("SELECT revision FROM recommendation_resets WHERE user_id=?", (user_id,)).fetchone()
            revision = current["revision"] if current else 0
            if revision != expected_reset_revision:
                raise ConflictError("偏好已被重置，请刷新后重试。")
            floor = db.execute("SELECT coalesce(MAX(revision),0) FROM recommendation_events WHERE user_id=?",
                               (user_id,)).fetchone()[0]
            reset_at = datetime.now(timezone.utc).isoformat()
            revision += 1
            if user_id == "local":
                db.execute("DELETE FROM artifact_preference_scores")
            db.execute("DELETE FROM recommendation_score_range WHERE user_id=?", (user_id,))
            db.execute("DELETE FROM recommendation_policy WHERE user_id=?", (user_id,))
            db.execute("DELETE FROM recommendation_evidence WHERE user_id=?", (user_id,))
            db.execute("INSERT INTO recommendation_resets VALUES (?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
                       "revision=excluded.revision,event_floor=excluded.event_floor,reset_at=excluded.reset_at",
                       (user_id, revision, floor, reset_at))
            db.execute("INSERT INTO recommendation_reset_requests VALUES (?,?,?,?,?)",
                       (user_id, request_id, expected_reset_revision, revision, reset_at))
            return ResetResult(request_id, revision, reset_at)

    def load_vectors(self, encoder_version, texts):
        result = {}
        with self.repository.connection() as db:
            for text in dict.fromkeys(texts):
                row = db.execute("SELECT vector FROM recommendation_vectors WHERE encoder_version=? AND text=?",
                                 (encoder_version, text)).fetchone()
                if row:
                    data = row["vector"]
                    if len(data) % 4:
                        raise ValueError("Corrupt cached embedding")
                    vector = struct.unpack("<" + "f" * (len(data) // 4), data)
                    if not vector or not all(math.isfinite(n) for n in vector):
                        raise ValueError("Non-finite cached embedding")
                    result[text] = vector
        return result

    def save_vectors(self, encoder_version, vectors):
        rows = []
        for text, vector in vectors.items():
            if not vector or not all(math.isfinite(n) for n in vector):
                raise ValueError("Embedding must contain finite numbers")
            try:
                data = struct.pack("<" + "f" * len(vector), *vector)
            except (OverflowError, struct.error) as exc:
                raise ValueError("Embedding exceeds float32 range") from exc
            if not all(math.isfinite(n) for n in struct.unpack("<" + "f" * len(vector), data)):
                raise ValueError("Embedding exceeds float32 range")
            rows.append((encoder_version, text, data))
        with self.repository.connection() as db:
            db.executemany("INSERT INTO recommendation_vectors VALUES (?,?,?) ON CONFLICT(encoder_version,text) "
                           "DO UPDATE SET vector=excluded.vector", rows)

    def load_policy(self, user_id, feature_version):
        with self.repository.connection() as db:
            row = db.execute("SELECT * FROM recommendation_policy WHERE user_id=? AND feature_version=?",
                             (user_id, feature_version)).fetchone()
        if row is None:
            return None
        return PolicyRecord(row["revision"], tuple(json.loads(row["term_keys"])), bytes(row["precision"]),
                            bytes(row["reward"]), row["evidence_count"])

    def evidence_revision(self, user_id, artifact_id, feature_version):
        with self.repository.connection() as db:
            row = db.execute("SELECT revision FROM recommendation_evidence WHERE user_id=? AND artifact_id=? "
                             "AND feature_version=?", (user_id, artifact_id, feature_version)).fetchone()
            return row["revision"] if row else 0

    @staticmethod
    def _update(row, feature_version):
        return FeedbackUpdate(row["user_id"], row["artifact_id"], row["revision"], row["value"],
                              _decode(row["candidate"]), feature_version)

    def load_evidence(self, user_id, feature_version):
        with self.repository.connection() as db:
            rows = db.execute("SELECT * FROM recommendation_evidence WHERE user_id=? AND feature_version=? "
                              "ORDER BY revision", (user_id, feature_version)).fetchall()
        return tuple(self._update(row, feature_version) for row in rows)

    def pending_feedback(self, user_id, feature_version):
        with self.repository.connection() as db:
            rows = db.execute("SELECT e.* FROM recommendation_events e LEFT JOIN recommendation_evidence a "
                              "ON a.user_id=e.user_id AND a.artifact_id=e.artifact_id AND a.feature_version=? "
                              "WHERE e.user_id=? AND e.revision>coalesce(a.revision,0) "
                              "AND e.revision>coalesce((SELECT event_floor FROM recommendation_resets "
                              "WHERE user_id=e.user_id),0) AND NOT EXISTS "
                              "(SELECT 1 FROM recommendation_events newer WHERE newer.user_id=e.user_id "
                              "AND newer.artifact_id=e.artifact_id AND newer.revision>e.revision) ORDER BY e.revision",
                              (feature_version, user_id)).fetchall()
        return tuple(self._update(row, feature_version) for row in rows)

    def seed_feedback(self, user_id, feature_version):
        # Events are feature-independent immutable historical text. New versions replay
        # the same latest feedback, while old/inactive evidence is never resurrected.
        with self.repository.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM recommendation_resets WHERE user_id=?", (user_id,)).fetchone():
                return
            rows = db.execute("SELECT f.artifact_id,f.value FROM feedback f JOIN artifacts a ON a.id=f.artifact_id "
                              "WHERE f.actor_id=? AND f.value IN (-1,1) AND NOT EXISTS "
                              "(SELECT 1 FROM recommendation_events e WHERE e.user_id=f.actor_id AND e.artifact_id=f.artifact_id) "
                              "AND NOT EXISTS (SELECT 1 FROM recommendation_evidence e WHERE e.user_id=f.actor_id "
                              "AND e.artifact_id=f.artifact_id)", (user_id,)).fetchall()
            for row in rows:
                record_feedback(db, row["artifact_id"], user_id, row["value"])

    def commit_feedback(self, update, state, expected_revision):
        if state.revision != expected_revision + 1:
            raise ValueError("Policy revision must increment exactly once")
        snapshot = _encode(update.candidate)
        _decode(snapshot)
        with self.repository.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            reset = db.execute("SELECT event_floor FROM recommendation_resets WHERE user_id=?",
                               (update.user_id,)).fetchone()
            if reset and update.revision <= reset["event_floor"]:
                return False
            current = db.execute("SELECT revision FROM recommendation_policy WHERE user_id=? AND feature_version=?",
                                 (update.user_id, update.feature_version)).fetchone()
            if (current["revision"] if current else 0) != expected_revision:
                return False
            applied = db.execute("SELECT revision FROM recommendation_evidence WHERE user_id=? AND feature_version=? "
                                 "AND artifact_id=?", (update.user_id, update.feature_version, update.artifact_id)).fetchone()
            if applied and applied["revision"] >= update.revision:
                return False
            latest = db.execute("SELECT * FROM recommendation_events WHERE user_id=? AND artifact_id=? "
                                "ORDER BY revision DESC LIMIT 1", (update.user_id, update.artifact_id)).fetchone()
            if reset and latest is None:
                return False
            if latest and (latest["revision"] != update.revision or
                           latest["value"] != update.value or latest["candidate"] != snapshot):
                return False
            db.execute("INSERT INTO recommendation_policy VALUES (?,?,?,?,?,?,?) "
                       "ON CONFLICT(user_id,feature_version) DO UPDATE SET revision=excluded.revision, "
                       "term_keys=excluded.term_keys,precision=excluded.precision,reward=excluded.reward,evidence_count=excluded.evidence_count",
                       (update.user_id, update.feature_version, state.revision, json.dumps(state.term_keys),
                        state.precision, state.reward, state.evidence_count))
            db.execute("INSERT INTO recommendation_evidence VALUES (?,?,?,?,?,?) "
                       "ON CONFLICT(user_id,feature_version,artifact_id) DO UPDATE SET revision=excluded.revision, "
                       "value=excluded.value,candidate=excluded.candidate",
                       (update.user_id, update.feature_version, update.artifact_id, update.revision, update.value, snapshot))
            return True
