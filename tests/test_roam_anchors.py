"""Focused picture-anchor smokes with neutral synthetic tags and no GPU."""
from backend.store.roam_settings import RoamSettings
import test_roam_modes as fixtures


class RoamAnchorsSmoke(fixtures.RoamModesSmoke):
    async def test_anchor_sources_persistence_and_prefetch_invalidation(self):
        await self.put(dict(prefetch_count=5, backend_id="local", preset_id="neutral"))
        current = self.finish((await self.ensure())["job"])
        self.app.storage.roam_view(dict(artifact_id=current["id"], viewed_at=1))
        self.finish((await self.ensure())["job"])
        queued = (await self.ensure())["job"]
        running = (await self.ensure())["job"]
        self.app.storage.claim_job(running["id"])
        self.app.storage.attach_prompt(running["id"], "old")
        self.app.storage.update_job(running["id"], "running")
        saved = await self.put(dict(pinned_positive=["blue_sky", "blue sky", "illustration", "custom look"]))
        self.assertEqual(saved["pinned_positive"], ["blue sky", "custom look"])
        self.assertEqual(saved["preset_base_positive"], ["illustration"])
        self.assertEqual([a["id"] for a in self.app.storage.artifacts(source="roam")], [current["id"]])
        self.assertEqual(self.app.storage.job(queued["id"])["status"], "cancelled")
        self.app.storage.complete(running["id"], [{"node_id":"9","index":0,"filename":"late.png"}])
        self.assertEqual([a["id"] for a in self.app.storage.artifacts(source="roam")], [current["id"]])
        document = self.app.roam.get()
        await self.put(dict(pinned_positive=["blue sky", "custom look"]))
        self.assertEqual(self.app.roam.get()["epoch"], document["epoch"])
        reloaded = RoamSettings(self.app.paths).get()
        self.assertEqual(reloaded["pinned_positive"], saved["pinned_positive"])
        preset = self.app.candidates.load_preset("neutral")
        preset["document"]["base_positive"].append("blue sky")
        await self.app.candidate("save_preset", preset)
        updated = await self.app.roam_settings()
        self.assertEqual(updated["pinned_positive"], ["custom look"])
        self.assertEqual(updated["preset_base_positive"], ["illustration", "blue sky"])
        preset["document"]["base_positive"].remove("blue sky")
        await self.app.candidate("save_preset", preset)
        self.assertEqual((await self.app.roam_settings())["pinned_positive"], ["custom look"])
        await self.put(dict(pinned_positive=[]))
        new = self.finish((await self.ensure())["job"])
        self.app.storage.roam_view(dict(artifact_id=new["id"], viewed_at=2))
        future = self.finish((await self.ensure())["job"])
        preset["document"]["base_positive"].append("sunlight")
        await self.app.candidate("save_preset", preset)
        self.assertNotIn(future["id"], [a["id"] for a in self.app.storage.artifacts(source="roam")])
        # Offline preset editing is normalized again on application startup.
        await self.put(dict(pinned_positive=["blue sky"]))
        await self.client.close()
        preset["document"]["base_positive"].append("blue sky")
        self.app.candidates.save_preset(preset)
        await self.open_app()
        self.assertEqual((await self.app.roam_settings())["pinned_positive"], [])
        await self.app.candidate("delete_preset", identifier="neutral")
        self.assertEqual((await self.app.roam_settings())["preset_base_positive"], [])

    async def test_candidates_preserve_anchors_limits_along_and_stay(self):
        preset = self.app.candidates.load_preset("neutral")
        original = dict(preset["document"])
        context = dict(preset_id="neutral", mode="fixed_seed", seed=12)
        pins = ["blue sky", "garden", "custom look", "another look"]
        pool = self.app.candidates.provider.generate(context, dict(count=2, pinned_positive=pins,
            allowed_positive_tags=["night"]))
        for item in pool:
            self.assertEqual(item.positive, "illustration, blue sky, garden, custom look, another look")
        self.assertEqual(self.app.candidates.load_preset("neutral")["document"], original)
        reference = dict(candidate_id=pool[0].id, positive=pool[0].positive, negative=pool[0].negative,
            terms=[dict(source_id=t.source_id, id=t.id, text=t.text, categories=list(t.categories), channel=t.channel)
                   for t in pool[0].terms])
        along = self.app.candidates.provider.generate(context, dict(prompt_mode="along", pinned_positive=pins,
            previous_candidate=reference))[0]
        self.assertEqual(along.positive, pool[0].positive)
        stay = self.app.candidates.provider.generate(context, dict(prompt_mode="stay", pinned_positive=["night"],
            previous_candidate=reference))[0]
        self.assertEqual(stay.positive, reference["positive"])
        await self.put(dict(prefetch_count=0, preset_id="neutral", pinned_positive=["blue sky"]))
        await self.put(dict(prompt_mode="stay"))
        response = await self.client.put("/api/settings/roam", json=dict(pinned_positive=[]))
        self.assertEqual(response.status, 400)
        await self.put(dict(pinned_positive=["blue sky"]))
        response = await self.client.put("/api/settings/roam", json=dict(pinned_positive=None))
        self.assertEqual(response.status, 400)
