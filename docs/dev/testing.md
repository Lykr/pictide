# Focused smoke checks

[简体中文](../zh-CN/dev/testing.md)

Use a small group for the behavior you changed. The shared entry point works from any directory and does not discover or run the full suite:

```shell
python scripts/check.py core
python scripts/check.py ui
python scripts/check.py corpus
python scripts/check.py browser
```

Run commands from the repository root, or pass an absolute path to `scripts/check.py`. Add `--list` to inspect a group without running it. A failed check returns a nonzero exit code.

Use Python 3.12 to match release CI.

| Group | Checks | Requirements |
| --- | --- | --- |
| `core` (default) | Six HTTP/storage smokes: preset-to-roam flow, blocked queue recovery, database migration, reversible feedback, OpenAI and Gemini protocol requests | Application Python dependencies |
| `ui` | Seven Node test files: tour state and placement, generation drafts, notifications, theme/language races, API key editing, HTTP-compatible request IDs | Node.js |
| `corpus` | Three offline smokes: post filtering, stale/corrupt prebuilt rejection, vocabulary editions | Python environment with `corpus/requirements.txt` |
| `browser` | Fifteen real-page flows: notifications and explicit update-check results without layout shifts, modal retry, mobile tour, Roam keyboard/swipe feedback, API-save-to-Generate, manual update actions with draft protection, mobile update/error presentation, bounded restart waiting, three shared-layout scenarios across image viewers and settings, nonzero safe areas through image-viewer rotation, and standalone actions without `crypto.randomUUID` | Application Python dependencies, frontend dependencies, compiled test frontend and a browser |

`ui` and `browser` also have frontend shortcuts: `pnpm --dir web test` and `pnpm --dir web run test:browser`. The shared Python entry point passes its own interpreter to the browser fixture; the frontend shortcut uses `python` on `PATH`.

Python checks mirror backend responsibilities under `tests/backend/`, with offline checks in `tests/corpus/` and tooling checks in `tests/scripts/`. Packages use explicit imports and share `tests.ROOT` for repository resources. Frontend units live in `web/tests/unit/` and browser flows in `web/tests/browser/`. To run one Python module, use its package name, for example `python -m unittest tests.backend.desktop.test_desktop_launcher -v`.

## Browser preparation

After preparing the [development environment](development.md#prepare-a-checkout), build an isolated frontend and install Chromium:

```shell
pnpm --dir web run typecheck
pnpm --dir web run build --out-dir ../dev/verification/browser/dist
pnpm --dir web exec playwright install chromium
python scripts/check.py browser
```

Alternatively, use an already installed Edge with `python scripts/check.py browser --channel msedge`. On Linux CI, Playwright installs browser system dependencies on the runner with `playwright install --with-deps chromium`.

Each browser test starts its own local HTTP service on an available port, uses temporary data under `dev/verification/browser/`, and closes the service and removes that data afterward. Settings, likes, and generated images do not leak between tests. Generation uses a fake backend, a tiny neutral vocabulary and a deterministic test encoder; it downloads no models and submits no GPU or paid API requests. These checks verify application behavior, not real model compatibility or image quality.

Failures retain screenshots, traces and a JSON report in `dev/verification/browser/`. Inspect a trace with `pnpm --dir web exec playwright show-trace TRACE_PATH`. The browser runner has no automatic retries.

Application-update changes additionally use `python -m unittest tests.backend.updates.test_updates -v` and `web/tests/browser/updates.spec.mjs`. They cover explicit actions, equal/older published versions, unsaved drafts, version reload, bounded restart waiting, and mobile manual-update/error presentation. Release CI adds `--previous-release` to the portable smoke: the actual previous stable package prepares settings and data, a replacement failure restores the old program, and a successful upgrade must serve the target version while preserving data and models. Use `--previous-archive PATH` for an already downloaded older ZIP. Only a successful cross-version native smoke enables direct installation; same-version self-replacement is reported separately.

Controlled-form coverage lives in `web/tests/unit/generation-draft.test.mjs` and `web/tests/browser/react-forms.spec.mjs`. It checks uncertain-submit request IDs, duplicate submission, draft retention, workflow node/JSON editing, validation, and stale workflow responses. Browser task-history checks retain metadata and disclosure state across navigation.

## Release checks

The tag-triggered release workflow runs `core`, `ui` and `browser` once before the four native builds. The offline `corpus` group remains available separately when data processing changes. Each native build retains its own extracted-package startup smoke.

Ordinary branch pushes do not trigger Actions. This update applies to subsequent version tags; it does not rebuild v0.5.0.

The group lists live in `scripts/check.py` and `web/scripts/test.mjs`. Keep them focused on user-visible outcomes and durable data behavior. Run individual existing tests when a change needs more specific coverage. Playwright setup and browser options follow the [official documentation](https://playwright.dev/docs/browsers).
