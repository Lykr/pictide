"""Durable recommendation feedback, version isolation and atomic CAS."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from backend.contracts.recommendation import FeedbackUpdate, PolicyRecord, ScoreCandidate, ScoreTerm
from backend.store.recommendation import SQLiteRecommendationStore
from backend.store.sqlite import Repository

class RecommendationStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo=Repository(Path(self.temp.name)/'pictide.sqlite3')
        self.store=SQLiteRecommendationStore(self.repo)
        self.repo.save_backend({'id':'local','kind':'comfyui','bindings':{},'workflow':{}})
        self.candidate=ScoreCandidate('combo','forest, standing','blurry',
            (ScoreTerm('forest'),ScoreTerm('standing'),ScoreTerm('blurry','negative')))
    def image(self,roam=True,snapshot=None):
        import uuid
        job=self.repo.create_job({'request_id':str(uuid.uuid4()),'backend_id':'local',
            'positive':self.candidate.positive,'negative':self.candidate.negative,'seed':1})
        self.repo.complete(job['id'],[{'node_id':'9','index':0,'filename':'image.png'}])
        if roam:
            candidate=snapshot if snapshot is not None else {
                'candidate_id':self.candidate.candidate_id,'positive':self.candidate.positive,
                'negative':self.candidate.negative,'config':'old.json','terms':[
                    {'id':str(n),'source_id':'old','text':t.text,'channel':t.channel,'tags':['private']}
                    for n,t in enumerate(self.candidate.terms)]}
            with self.repo.connection() as db:
                db.execute('INSERT INTO roam_jobs(job_id,epoch,candidate,created_at) VALUES (?,?,?,?)',(job['id'],'epoch',json.dumps(candidate),'2026-01-01'))
        return next(a['id'] for a in self.repo.artifacts() if a['job_id']==job['id'])
    def state(self,revision,count=1):
        return PolicyRecord(revision,('positive:forest',),struct.pack('<4d',1,0,0,1),struct.pack('<2d',1,2),count)
    def pending(self,version='v1'):
        return self.store.pending_feedback('local',version)
    def test_feedback_success_returns_snapshot_before_post_commit_cleanup(self):
        iid = self.image()
        self.repo.rate(iid, 1)
        connection = self.repo.connection
        cleaned = False

        @contextmanager
        def cleanup_after_commit():
            nonlocal cleaned
            with connection() as db:
                yield db
            if not cleaned:
                cleaned = True
                with connection() as db:
                    db.execute("UPDATE artifacts SET deleted_at='2026-10-01' WHERE id=?", (iid,))

        with patch.object(self.repo, 'connection', side_effect=cleanup_after_commit):
            result = self.repo.rate(iid, None)
        self.assertTrue(cleaned)
        self.assertEqual(result['id'], iid)
        self.assertIsNone(result['feedback'])
        self.assertIsNone(self.repo.artifact(iid))
        self.assertIsNone(self.pending()[-1].value)

    def test_vectors_float32_and_version_validation(self):
        self.store.save_vectors('enc1',{'forest':(0.1,0.5,-2.0)})
        result=self.store.load_vectors('enc1',['forest','absent'])
        self.assertAlmostEqual(result['forest'][0],0.1,places=7)
        self.assertEqual(result['forest'][1:],(0.5,-2))
        self.assertEqual(self.store.load_vectors('enc2',['forest']),{})
        for bad in ((float('nan'),),(float('inf'),),(1e100,),()):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                self.store.save_vectors('enc1',{'broken':bad})
        self.assertEqual(self.store.load_vectors('enc1',['broken']),{})
    def test_rate_idempotent_retract_restart(self):
        iid=self.image();self.repo.rate(iid,1)
        first=self.pending()[0]
        self.assertEqual(first.candidate,self.candidate)
        self.repo.rate(iid,1)
        self.assertEqual(self.pending(),(first,))
        self.assertTrue(self.store.commit_feedback(first,self.state(1),0))
        self.assertEqual(self.pending(),())
        self.assertEqual(self.store.load_policy('local','v1'),self.state(1))
        self.repo.rate(iid,None)
        latest=self.pending()[0]
        self.assertIsNone(latest.value)
        self.assertGreater(latest.revision,first.revision)
        self.assertTrue(self.store.commit_feedback(latest,self.state(2,0),1))
        self.repo.rate(iid,None)
        self.assertEqual(self.pending(),())
        restart=SQLiteRecommendationStore(Repository(self.repo.path))
        self.assertEqual(restart.load_evidence('local','v1'),(latest,))
        self.assertEqual(restart.load_policy('local','v1'),self.state(2,0))
        restart.seed_feedback('local','v1')
        self.assertEqual(restart.pending_feedback('local','v1'),())
    def test_pending_latest_wins(self):
        iid=self.image();self.repo.rate(iid,1)
        stale=self.pending()[0]
        self.repo.rate(iid,None)
        newest=self.pending()[0]
        self.assertEqual(len(self.pending()),1)
        self.assertFalse(self.store.commit_feedback(stale,self.state(1),0))
        self.assertIsNone(self.store.load_policy('local','v1'))
        self.assertTrue(self.store.commit_feedback(newest,self.state(1,0),0))
        self.assertFalse(self.store.commit_feedback(stale,self.state(2),1))
        self.assertEqual(self.store.evidence_revision('local',iid,'v1'),newest.revision)
    def test_concurrent_cas_retry(self):
        ids=[self.image(),self.image()]
        for iid in ids:self.repo.rate(iid,1)
        first,second=self.pending()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(lambda u:self.store.commit_feedback(u,self.state(1),0),[first,second]))
        self.assertEqual(sorted(results),[False,True])
        remaining=self.pending()
        self.assertEqual(len(remaining),1)
        self.assertTrue(self.store.commit_feedback(remaining[0],self.state(2,2),1))
        self.assertEqual(len(self.store.load_evidence('local','v1')),2)
    def test_new_version_replays_text_and_retract(self):
        iid=self.image();self.repo.rate(iid,1)
        update=self.pending()[0]
        self.assertTrue(self.store.commit_feedback(update,self.state(1),0))
        self.store.seed_feedback('local','v2')
        second=self.pending('v2')[0]
        self.assertEqual(second,replace(update,feature_version='v2'))
        self.assertTrue(self.store.commit_feedback(second,self.state(1),0))
        self.repo.rate(iid,None)
        self.assertIsNone(self.pending('v2')[0].value)
        self.assertIsNone(self.pending('v1')[0].value)
        self.assertIsNone(self.store.load_policy('other','v1'))
    def test_legacy_seed_idempotent_unverifiable_ignored(self):
        good=self.image();manual=self.image(roam=False)
        broken=self.image(snapshot={'candidate_id':'bad','positive':'forest','negative':'','terms':[]})
        mismatch=self.image(snapshot={'candidate_id':'bad','positive':'forest','negative':'','terms':[{'text':'forest'}]})
        with self.repo.connection() as db:
            for iid in (good,manual,broken,mismatch):
                db.execute("INSERT INTO feedback VALUES (?,'local',1,'2026-01-01')",(iid,))
        self.store.seed_feedback('local','v1')
        update=self.pending()[0]
        self.assertEqual(update.artifact_id,good)
        self.store.seed_feedback('local','v1')
        self.assertEqual(self.pending(),(update,))
        self.repo.rate(good,None);self.store.seed_feedback('local','v1')
        self.assertEqual(len(self.pending()),1)
        self.assertIsNone(self.pending()[0].value)
        for iid in (manual,broken,mismatch):self.assertEqual(self.repo.artifact(iid)['feedback'],1)
    def test_category_rename_preserves_old_snapshots_and_same_feedback_features(self):
        legacy = self.image()  # Historical metadata deliberately keeps its v2 tags field.
        current_snapshot = {
            "candidate_id": self.candidate.candidate_id, "positive": self.candidate.positive,
            "negative": self.candidate.negative, "terms": [
                {"id": str(n), "source_id": "old", "text": term.text,
                 "channel": term.channel, "categories": ["renamed-category"]}
                for n, term in enumerate(self.candidate.terms)]}
        current = self.image(snapshot=current_snapshot)
        with self.repo.connection() as db:
            original = [tuple(row) for row in db.execute("SELECT job_id,candidate FROM roam_jobs ORDER BY job_id")]
        self.repo.rate(legacy, 1)
        update = self.pending()[0]
        self.assertTrue(self.store.commit_feedback(update, self.state(1), 0))
        state = self.store.load_policy("local", "v1")
        self.repo.rate(current, 1)
        pending = self.pending()[0]
        self.assertEqual(update.candidate, pending.candidate)
        self.assertEqual(update.candidate, self.candidate)
        restored = SQLiteRecommendationStore(Repository(self.repo.path))
        restored.seed_feedback("local", "v1")
        self.assertEqual(restored.load_policy("local", "v1"), state)
        self.assertEqual(restored.load_evidence("local", "v1"), (update,))
        self.assertEqual(restored.pending_feedback("local", "v1"), (pending,))
        with self.repo.connection() as db:
            saved = [tuple(row) for row in db.execute("SELECT job_id,candidate FROM roam_jobs ORDER BY job_id")]
        self.assertEqual(saved, original)

    def test_notification_atomic_and_failed_learning_replay(self):
        iid=self.image()
        with patch('backend.store.sqlite.record_feedback',side_effect=RuntimeError('crash')):
            with self.assertRaises(RuntimeError):self.repo.rate(iid,1)
        self.assertIsNone(self.repo.artifact(iid)['feedback'])
        self.assertEqual(self.pending(),())
        self.repo.rate(iid,1)
        restart=SQLiteRecommendationStore(Repository(self.repo.path))
        self.assertEqual(restart.pending_feedback('local','v1'),self.pending())
    def test_retract_uses_retained_snapshot(self):
        iid=self.image();self.repo.rate(iid,1)
        with self.repo.connection() as db:db.execute('DELETE FROM roam_jobs')
        self.repo.rate(iid,None)
        update=self.pending()[0]
        self.assertIsNone(update.value)
        self.assertEqual(update.candidate,self.candidate)
    def test_learning_commit_is_atomic_if_evidence_write_fails(self):
        iid=self.image();self.repo.rate(iid,1)
        update=self.pending()[0]
        with self.repo.connection() as db:
            db.execute("CREATE TRIGGER fail_evidence BEFORE INSERT ON recommendation_evidence "
                       "BEGIN SELECT RAISE(ABORT, 'simulated interruption'); END")
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.commit_feedback(update,self.state(1),0)
        self.assertIsNone(self.store.load_policy('local','v1'))
        self.assertEqual(self.pending(),(update,))
        with self.repo.connection() as db:db.execute('DROP TRIGGER fail_evidence')
        self.assertTrue(self.store.commit_feedback(update,self.state(1),0))
    def test_fabricated_new_revision_cannot_consume_real_notification(self):
        iid=self.image();self.repo.rate(iid,1)
        update=self.pending()[0]
        self.assertFalse(self.store.commit_feedback(replace(update,revision=update.revision+1),self.state(1),0))
        self.assertEqual(self.pending(),(update,))
    def test_rate_without_adapter(self):
        iid=self.image();Repository(self.repo.path).rate(iid,1)
        self.assertEqual(len(self.pending()),1)
    def test_invalid_revision_duplicate_and_opaque_buffers(self):
        update=FeedbackUpdate('local','direct',1,1,self.candidate,'v1')
        with self.assertRaises(ValueError):self.store.commit_feedback(update,self.state(3),0)
        self.assertTrue(self.store.commit_feedback(update,self.state(1),0))
        self.assertFalse(self.store.commit_feedback(update,self.state(2),1))
        self.assertEqual(self.store.load_policy('local','v1'),self.state(1))

if __name__=='__main__':unittest.main()
