"""Liked ranking smoke: global ordering, combination dedup, filters and fallback."""
from unittest.mock import patch
from backend.recommendation.contracts import FeedbackUpdate, ScoreCandidate, ScoreTerm
from backend.domain import generation_fields
from tests.backend.recommendation.test_recommendation_application import RecommendationApplicationTests


class LikedRankingSmoke(RecommendationApplicationTests):
    def seed(self, name, positive, count=1, snapshot=True):
        fields=generation_fields(dict(backend_id='local',request_id="ranking-"+name,positive=positive,negative='',seed=42))
        if snapshot:
            candidate=dict(candidate_id=name,positive=positive,negative='',terms=[dict(text=t,channel='positive') for t in positive.split(', ')])
            job=self.app.storage.ensure_roam('ranking-test',None,1000,fields,candidate)['job']
        else:
            job=self.app.storage.create_job(fields)
        self.app.storage.complete(job['id'],[dict(node_id='9',index=i,filename=f'{name}-{i}.png') for i in range(count)])
        with self.app.storage.connection() as db:
            identifiers=[r[0] for r in db.execute('SELECT id FROM artifacts WHERE job_id=?',(job['id'],))]
        images=[self.app.storage.artifact(identifier) for identifier in identifiers]
        for image in images:
            self.app.storage.rate(image['id'],1)
        return images

    async def test_rank_all_likes_deduplicate_filter_and_unavailable(self):
        for number,(text,value) in enumerate([('forest',1),('city',-1)]):
            candidate=ScoreCandidate('train-'+text,text,'',(ScoreTerm(text),))
            self.app.recommendation.apply_feedback(FeedbackUpdate('local','training-'+text,number+1,value,candidate,self.version))
        high=self.seed('high','forest')[0]
        low=self.seed('low','city',205)
        missing=self.seed('manual','sketch',snapshot=False)[0]
        with patch.object(self.app.recommendation,'score',wraps=self.app.recommendation.score) as score:
            response=await self.client.get('/api/liked/ranked')
            self.assertEqual(response.status,200)
            payload=await response.json()
            self.assertEqual(score.call_count,1)
            self.assertEqual(len(score.call_args.args[0].candidates),2,'Duplicate prompt groups must share one score')
        self.assertTrue(payload['scoring_available'])
        items=payload['artifacts']
        self.assertEqual(len(items),207,'Ranking must cover likes beyond the first 200')
        self.assertEqual(items[0]['id'],high['id'],'Older preferred picture must rank above newer low-score pictures')
        self.assertEqual(items[-1]['id'],missing['id'],'Unscorable picture must remain last')
        expected=sorted(low,key=lambda a:(a['created_at'],a['id']),reverse=True)
        self.assertEqual([a['id'] for a in items[1:-1]],[a['id'] for a in expected])
        filtered=await (await self.client.get('/api/liked/ranked?tag=forest')).json()
        self.assertEqual([a['id'] for a in filtered['artifacts']],[high['id']])
        empty=await (await self.client.get('/api/liked/ranked?tag=nonexistent')).json()
        self.assertEqual(empty['artifacts'],[])
        with patch.object(self.app.recommendation.encoder,'available',return_value=False):
            cached=await (await self.client.get('/api/liked/ranked')).json()
            self.assertTrue(cached['scoring_available'])
            fallback=await (await self.client.post('/api/liked/ranked/refresh',json={'tags':[]})).json()
        self.assertFalse(fallback['scoring_available'])
        self.assertTrue(fallback['error'])
        self.assertEqual(len(fallback['artifacts']),207)
        self.assertEqual([a['id'] for a in fallback['artifacts']],[a['id'] for a in items], 'Failed refresh preserves cached ranking')