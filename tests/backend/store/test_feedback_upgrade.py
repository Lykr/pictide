"""One-time deployed-layout conversion keeps history, matrix and reset boundaries."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from backend.store.feedback_upgrade import upgrade

class FeedbackUpgradeSmoke(unittest.TestCase):
    def test_preserves_likes_withdrawals_and_event_sequence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'pictide.sqlite3'
            with closing(sqlite3.connect(path)) as db, db:
                db.executescript('''
                    CREATE TABLE artifacts(id TEXT PRIMARY KEY);
                    INSERT INTO artifacts VALUES ('one');
                    CREATE TABLE feedback(artifact_id TEXT REFERENCES artifacts(id),actor_id TEXT,value INTEGER CHECK(value=1),updated_at TEXT,PRIMARY KEY(artifact_id,actor_id));
                    INSERT INTO feedback VALUES ('one','local',1,'today');
                    CREATE TABLE recommendation_events(revision INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT,artifact_id TEXT,liked INTEGER CHECK(liked IN(0,1)),candidate TEXT);
                    INSERT INTO recommendation_events VALUES (3,'local','one',1,'snapshot');
                    INSERT INTO recommendation_events VALUES (4,'local','two',0,'snapshot');
                    UPDATE sqlite_sequence SET seq=12 WHERE name='recommendation_events';
                    CREATE TABLE recommendation_evidence(user_id TEXT,feature_version TEXT,artifact_id TEXT,revision INTEGER,liked INTEGER,candidate TEXT,PRIMARY KEY(user_id,feature_version,artifact_id));
                    INSERT INTO recommendation_evidence VALUES('local','v1','one',3,1,'snapshot');
                    INSERT INTO recommendation_evidence VALUES('local','v1','two',4,0,'snapshot');
                    CREATE TABLE recommendation_policy(precision BLOB,reward BLOB);
                    INSERT INTO recommendation_policy VALUES (x'010203',x'0405');
                    CREATE TABLE recommendation_resets(user_id TEXT,event_floor INTEGER);
                    INSERT INTO recommendation_resets VALUES('local',10);
                ''')
            self.assertTrue(upgrade(path))
            self.assertFalse(upgrade(path))
            with closing(sqlite3.connect(path)) as db, db:
                self.assertEqual(db.execute('SELECT value FROM feedback').fetchall(), [(1,)])
                self.assertEqual(db.execute('SELECT revision,value FROM recommendation_events ORDER BY revision').fetchall(), [(3,1),(4,None)])
                self.assertEqual(db.execute('SELECT value FROM recommendation_evidence ORDER BY revision').fetchall(), [(1,),(None,)])
                self.assertEqual(db.execute('SELECT * FROM recommendation_policy').fetchone(), (b'\x01\x02\x03',b'\x04\x05'))
                self.assertEqual(db.execute('SELECT event_floor FROM recommendation_resets').fetchone()[0],10)
                db.execute("INSERT INTO recommendation_events(user_id,artifact_id,value,candidate) VALUES('local','one',-1,'snapshot')")
                self.assertGreater(db.execute('SELECT MAX(revision) FROM recommendation_events').fetchone()[0],12)
                db.execute("UPDATE feedback SET value=-1 WHERE artifact_id='one'")
                self.assertEqual(db.execute('SELECT value FROM feedback').fetchone()[0],-1)
