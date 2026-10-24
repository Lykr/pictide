"""Run a small, explicit smoke group without discovering the full test suite."""
import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
GROUPS = {
    'core': (
        'tests.backend.desktop.test_desktop_launcher.DesktopSocketSmoke.test_macos_update_preserves_launcher_mode_including_empty_arguments',
        'tests.backend.candidate.test_cooccurrence_integration.CooccurrenceIntegrationSmoke.test_preset_preview_rounds_and_sqlite_roam',
        'tests.backend.task.test_task_window.TaskWindowSmoke.test_restart_releases_two_missing_unknown_jobs_without_resubmitting',
        'tests.backend.store.test_storage.RepositoryTests.test_existing_database_is_migrated_without_losing_images_or_feedback',
        'tests.backend.recommendation.test_recommendation_application.RecommendationApplicationTests.test_signed_http_feedback_is_exclusive_reversible_and_idempotent',
        'tests.backend.generation.test_cloud_backends.CloudProtocolTests.test_openai_base64_and_actual_request_fields',
        'tests.backend.generation.test_cloud_backends.CloudProtocolTests.test_gemini_interactions_only_final_images_and_stateless',
        'tests.backend.application.test_natural_prompts.NaturalPromptTests.test_stay_skips_llm_and_feedback_uses_semantic_snapshot',
        'tests.backend.application.test_llm_connections.LLMConnectionTests.test_named_connections_select_independently_and_protect_references',
        'tests.backend.application.test_chatgpt.ChatGPTTests.test_registration_pkce_state_signature_and_replay',
    ),
    'corpus': (
        'tests.corpus.test_importer.ImportSmoke.test_post_filter_matches_any_tag_and_keeps_only_surviving_population',
        'tests.corpus.test_portable.PortableCacheSmoke.test_prebuilt_rejects_stale_profile_and_corrupt_files_without_fallback',
        'tests.corpus.test_editions.VocabularyEditionsSmoke.test_two_editions_checksums_reuse_and_default_lock_preserved',
    ),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('group', choices=(*GROUPS, 'ui', 'browser'), nargs='?', default='core')
    parser.add_argument('--list', action='store_true', help='List the selected checks without running them')
    parser.add_argument('--channel', help='Use an installed browser channel, e.g. msedge (browser group only)')
    args = parser.parse_args()
    if args.channel and args.group != 'browser':
        parser.error('--channel applies to the browser group')
    os.chdir(ROOT)
    if args.group in ('ui', 'browser'):
        node = shutil.which('node')
        if not node:
            parser.error('Node.js is required for UI/browser checks')
        command = [node, str(ROOT / 'web/scripts/test.mjs'), args.group]
        if args.list:
            command.append('--list')
        environment = dict(os.environ, PICTIDE_TEST_PYTHON=sys.executable)
        if args.channel:
            environment['PICTIDE_TEST_BROWSER_CHANNEL'] = args.channel
        return subprocess.run(command, env=environment).returncode
    if args.list:
        print('\n'.join(GROUPS[args.group]))
        return 0
    if args.group == 'corpus' and any(importlib.util.find_spec(name) is None for name in ('pyarrow', 'scipy', 'numpy')):
        parser.error('Corpus checks need the offline environment: python -m pip install -r corpus/requirements.txt')
    # Explicit package names keep each smoke group small and deterministic.
    sys.path.insert(0, str(ROOT))
    temporary = ROOT / 'dev/tmp'
    temporary.mkdir(parents=True, exist_ok=True)
    os.environ['TMPDIR'] = os.environ['TEMP'] = os.environ['TMP'] = str(temporary)
    import tempfile
    tempfile.tempdir = str(temporary)
    suite = unittest.defaultTestLoader.loadTestsFromNames(GROUPS[args.group])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
