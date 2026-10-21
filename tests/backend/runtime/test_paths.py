from tests import ROOT
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from backend.paths import DataPaths, ROOT, configure_runtime, remember_data_directory, saved_data_directory


class DataPathsTests(unittest.TestCase):
    def test_remembered_location_is_portable_and_explicit_overrides_win(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
            program = Path(directory) / 'program'
            program.mkdir()
            settings = program / 'pictide.local.json'
            os.environ.pop('PICTIDE_DATA_DIR', None)
            os.environ.pop('PICTIDE_WEB_DATA_DIR', None)
            with patch('backend.paths.launcher_settings_path', return_value=settings):
                remember_data_directory(program / 'data')
                self.assertEqual(json.loads(settings.read_text())['data_directory'], 'data')
                self.assertEqual(DataPaths().root, program / 'data')
                external = Path(directory) / 'external'
                remember_data_directory(external)
                self.assertEqual(saved_data_directory(), external)
                os.environ['PICTIDE_WEB_DATA_DIR'] = str(program / 'legacy')
                self.assertEqual(DataPaths().root, program / 'legacy')
                os.environ['PICTIDE_DATA_DIR'] = str(program / 'environment')
                self.assertEqual(DataPaths().root, program / 'environment')
                self.assertEqual(DataPaths(program / 'explicit').root, program / 'explicit')
                self.assertFalse(external.exists())
                self.assertFalse((program / 'data').exists())

    def test_default_and_override_precedence(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PICTIDE_DATA_DIR", None)
            os.environ.pop("PICTIDE_WEB_DATA_DIR", None)
            self.assertEqual(DataPaths().root, (ROOT / "data").resolve())
            os.environ["PICTIDE_WEB_DATA_DIR"] = str(ROOT / "environment-data")
            self.assertEqual(DataPaths().root, (ROOT / "environment-data").resolve())
            self.assertEqual(DataPaths(ROOT / "explicit-data").root, (ROOT / "explicit-data").resolve())

    def test_all_paths_and_creation_stay_below_chosen_root(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = DataPaths(Path(directory) / "nested" / "data")
            self.assertIs(paths.ensure(), paths)
            self.assertEqual(paths.database, paths.root / "db" / "pictide.sqlite3")
            for child in (paths.database, paths.images, paths.models, paths.workflows, paths.cache, paths.logs,
                          paths.tmp, paths.runtime):
                self.assertTrue(child.is_relative_to(paths.root))
            for child in (paths.images, paths.models, paths.workflows, paths.cache, paths.logs, paths.database.parent,
                          paths.tmp, paths.runtime, paths.cache / "python", paths.cache / "pip"):
                self.assertTrue(child.is_dir())
            self.assertFalse(paths.database.exists())
            self.assertFalse((paths.root / "dev").exists())
            self.assertFalse((paths.root / "prompts").exists())
            self.assertFalse((paths.root / "previews").exists())
            paths.ensure()

    def test_runtime_redirects_real_temporary_files_and_rotates_only_app_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = logging.Logger("backend")
            foreign = logging.NullHandler()
            logger.addHandler(foreign)
            root_handlers = list(logging.getLogger().handlers)
            try:
                with patch.dict(os.environ, {"HTTPS_PROXY": "http://example.invalid:1234"}), \
                     patch.object(tempfile, "tempdir", tempfile.tempdir), \
                     patch.object(sys, "pycache_prefix", sys.pycache_prefix), \
                     patch("backend.paths.logging.getLogger", return_value=logger):
                    paths = configure_runtime(Path(directory) / "data")
                    self.assertEqual(os.environ["TMP"], str(paths.tmp))
                    self.assertEqual(os.environ["TEMP"], str(paths.tmp))
                    self.assertEqual(os.environ["PYTHONPYCACHEPREFIX"], str(paths.cache / "python"))
                    self.assertEqual(sys.pycache_prefix, str(paths.cache / "python"))
                    self.assertEqual(os.environ["PIP_CACHE_DIR"], str(paths.cache / "pip"))
                    self.assertEqual(os.environ["HTTPS_PROXY"], "http://example.invalid:1234")
                    with tempfile.NamedTemporaryFile() as temporary:
                        self.assertEqual(Path(temporary.name).parent, paths.tmp)
                    self.assertIs(paths.configure_runtime(), paths)
                    handlers = [h for h in logger.handlers if isinstance(h, RotatingFileHandler)]
                    self.assertEqual(len(handlers), 1)
                    self.assertEqual(Path(handlers[0].baseFilename), paths.logs / "pictide.log")
                    self.assertEqual(handlers[0].backupCount, 3)
                    logger.info("runtime path check")
                    self.assertIn("runtime path check", (paths.logs / "pictide.log").read_text(encoding="utf-8"))
                    self.assertIn(foreign, logger.handlers)
            finally:
                for handler in list(logger.handlers):
                    logger.removeHandler(handler)
                    handler.close()
            self.assertEqual(logging.getLogger().handlers, root_handlers)

    def test_reconfiguration_replaces_owned_log_handler_and_releases_old_file(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = logging.Logger("backend")
            try:
                with patch.dict(os.environ), patch.object(tempfile, "tempdir", tempfile.tempdir), \
                     patch.object(sys, "pycache_prefix", sys.pycache_prefix), \
                     patch("backend.paths.logging.getLogger", return_value=logger):
                    first = DataPaths(Path(directory) / "one").configure_runtime()
                    logger.info("old destination")
                    previous = logger.handlers[0]
                    second = DataPaths(Path(directory) / "two").configure_runtime()
                    self.assertEqual(len(logger.handlers), 1)
                    self.assertIsNone(previous.stream)
                    (first.logs / "pictide.log").unlink()
                    logger.warning("new destination")
                    self.assertIn("new destination", (second.logs / "pictide.log").read_text(encoding="utf-8"))
            finally:
                for handler in list(logger.handlers):
                    logger.removeHandler(handler)
                    handler.close()


if __name__ == "__main__":
    unittest.main()
