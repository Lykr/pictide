import unittest

from backend.generation.workflows import default_txt2img, uses_default, resolve_backend
from backend.generation import validate_backend
from backend.generation.base import BackendError


class WorkflowTests(unittest.TestCase):
    def test_default_graph_is_independent_and_has_exact_text_bindings(self):
        a = default_txt2img("model.safetensors")
        b = default_txt2img("model.safetensors")
        a["workflow"]["2"]["inputs"]["text"]="edited"
        self.assertEqual(b["workflow"]["2"]["inputs"]["text"],"")
        cleaned = validate_backend({"id":"test","name":"test","base_url":"http://localhost:8188",**b})
        self.assertEqual(cleaned["bindings"]["seed"],{"node_id":"5","input":"seed"})
        self.assertEqual(cleaned["workflow"]["5"]["inputs"]["denoise"],1.0)
        self.assertEqual(cleaned["workflow"]["7"]["class_type"],"PreviewImage")

    def test_mode_inference_preserves_existing_custom_graph(self):
        self.assertTrue(uses_default({}))
        self.assertTrue(uses_default({"workflow":None}))
        self.assertTrue(uses_default({"workflow":{},"workflow_mode":"custom"}))
        self.assertFalse(uses_default({"workflow":default_txt2img("m")["workflow"]}))
        self.assertTrue(uses_default({"workflow":default_txt2img("m")["workflow"],"workflow_mode":"default"}))


class ResolveTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_checkpoint_catalog_does_not_save_broken_template(self):
        class EmptyBackend:
            async def checkpoints(self):
                return []
        with self.assertRaisesRegex(BackendError,"没有可用"):
            await resolve_backend({"id":"empty","name":"empty","base_url":"http://localhost:8188"},None,lambda c,s:EmptyBackend())
