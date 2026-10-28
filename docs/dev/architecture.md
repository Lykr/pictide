# Architecture and Module Boundaries

[简体中文](../zh-CN/dev/architecture.md)

[Documentation navigation](README.md). This page describes modules, responsibilities, and dependencies. See [Calls and Data Flow](architecture/flows.md) for call sequences, [Recommendation Module](architecture/recommendation.md) for recommendation internals, and [Manual Application Updates](architecture/updates.md) for compatible portable upgrades.

Pictide is a local web application with a separate frontend and backend. `web/` is the only browser entry point, and `backend/` provides the business API. In deployment, one Python process serves both the compiled frontend and the API; normal operation requires no Node server.

## Architecture Diagram

The diagram shows the current module responsibilities. The application orchestration layer in the web backend is the interaction hub, passing candidate combinations, scores, generation requests, and feedback between modules. Candidate, Recommendation, and Task do not call or depend on one another directly. The HTTP host is a standalone web service; ComfyUI, OpenAI Images, and Gemini provide only image generation; cloud prompts leave the local application.

```mermaid
flowchart TD
    UI["Browser: image feed / preferences / generation settings"]
    Host["Web backend entry: HTTP API / live events / lifecycle"]
    App["Application orchestration: generation / feedback / prefetch / coordination"]
    Rules["Candidate module: co-occurrence expansion / complete prompts / continuous-change budget"]
    Rec["Recommendation module: combination scoring / MiniLM features / positive and negative preference learning"]
    Jobs["Task module: scheduling / recovery / result association"]
    Backend["Generation backend interface"]
    Comfy["ComfyUI API"]
    Cloud["OpenAI Images / Gemini Interactions"]
    Store["Storage interface"]
    DB[("SQLite + image files")]

    UI <--> Host
    Host <--> App
    App <--> Rules
    App <--> Rec
    App --> Prompt["Prompt conversion: selected tags to natural-language text"]
    Prompt --> LLM["OpenAI-compatible text API"]
    App <--> Jobs
    Jobs --> Backend
    Backend --> Comfy
    Backend --> Cloud
    App --> Store
    Rules --> Store
    Rec --> Store
    Jobs --> Store
    Store --> DB
```

## Directory Mapping

```text
pictide/
  web/                         Only frontend; npm package pictide-web
    index.html                 Single HTML entry point
    src/main.tsx               React application entry and view navigation
    src/                       Pages, interaction controllers, shared components, and theme
    dist/                      Vite distribution assets
  backend/
    host.py                    HTTP API, SSE, static assets, startup, and shutdown
    desktop/                   Desktop session, launcher, localized messages, and Windows tray
    setup/                     Local generation resources/session, Windows preparation UI and hardware detection
    application.py             Application orchestration: generation, candidates, feedback, cleanup
    domain.py                  Shared input validation and errors
    paths.py                   Data paths and this process's runtime environment
    runtime_logging.py         Bounded logs, exception capture, and startup output cleanup
    network.py                 Shared system proxy selection and synchronous resource transport
    candidate/                 Read-only co-occurrence libraries, presets, continuous-change budget, offline import
    recommendation/            Combination features, MiniLM, Bayesian scoring and learning
    prompting/                 Natural-language conversion, text API protocols and ChatGPT sessions
    prompt_preparation.py      App-owned conversion reuse, serialization, and freshness checks
    task/                      Scheduling, recovery, cancellation, and result association
    generation/                Generation interface, ComfyUI workflows, OpenAI Images, and Gemini
    store/                     SQLite, image/JSON storage, cleanup policies, and reclamation
    updates/                   Explicit release checks, downloads, validation, replacement and recovery
    update_cli.py              Command-line update orchestration before ordinary startup
  corpus/                      Offline metadata processing and release vocabulary profiles
  data/                        Configurable runtime data root
  dev/                         Local development environments, datasets, caches, and verification
  releases/                    Final distribution archives
  docs/                        Documentation entry points
    guides/                    User guides
    dev/                       Developer documentation and topic overviews
      architecture/            Architecture and flow details
      reference/               API, data, and design references
    zh-CN/                     Chinese translations and development history
      dev/issues/              Chinese requirement designs, changes, and delivery records
  scripts/
    macos_launcher.swift       System AppKit launcher: preparation, menu bar, and service lifecycle
  tests/
    backend/                   Python checks grouped by application module
    corpus/                    Offline processing checks
    scripts/                   Packaging, cleanup, and launch-script checks
    browser_server.py          Disposable Python service for web/tests/browser/
  start.cmd
  start.ps1
  start.sh
  start.command
```

| Diagram module | Location | Responsibilities and boundaries |
| --- | --- | --- |
| UI | `web/` | Presentation, drafts, keyboard controls, and interactions; communicates with the host through HTTP/SSE |
| Host | `backend/host.py` | Requests and responses, origin checks, error mapping, static assets, events, and lifecycle; calls application orchestration |
| App | `backend/application.py` | Connects Candidate, Recommendation, Task, and Store; orchestrates the roam buffer, settings versions, and pause conditions |
| Rules | `backend/candidate/` | Read-only libraries, co-occurrence presets and candidate generation, sequence budgets; does not call generation services |
| Rec | `backend/recommendation/` | Complete-combination scoring, tag feature encoding, and positive/negative preference learning; does not generate candidates or call generation services |
| Jobs | `backend/task/` | Task state, idempotency, recovery, cancellation, and artifact association; depends on generation and storage interfaces |
| Backend / Comfy / Cloud | `backend/generation/` | Registers adapters and capabilities; prepares requests, submits, queries when supported, and reads image outputs |
| Store / DB | `backend/store/` | SQLite and file storage, atomic feedback, image–prompt associations, and lazy cleanup |

## Dependency Rules

- Host handles transport, origin checks, and lifecycle, executing use cases through App. Candidate solving, recommendation algorithms, and SQL belong elsewhere.
- App is the only interaction hub between Candidate, Recommendation, and Task. It obtains the complete candidate pool, requests combination scores, selects a combination, and submits tasks. Scores are not sent back to Candidate for resampling.
- Candidate, Recommendation, and Task do not call or import one another directly. Contracts live with their owning modules: recommendation requests/results in `backend/recommendation/contracts.py`, candidate snapshots in `backend/candidate/contracts.py`, and persistence interfaces in `backend/store/contracts.py`. Importing recommendation contracts loads no service, encoder, or storage implementation; composition imports services and encoders explicitly.
- Candidate reads online libraries and presets through storage interfaces injected by Host, without importing SQLite adapters. Offline download/import tools use SQLite independently and stay outside online startup and request paths.
- Task depends on Generation and Store, handling submission of determined tasks, event verification, recovery, cancellation, and result association. Generation isolates protocol differences. ComfyUI returns a remote task reference; OpenAI Images and Gemini return completed outputs from one HTTP request. Unknown cloud submissions are not automatically retried.
- For `natural_language` backends, App calls Prompting after selecting tags and before creating image tasks. Prompting neither chooses candidates nor calls image APIs; its ChatGPT adapter uses an injected protected credential store for OAuth sessions. `PromptPreparation` coordinates its saved results through `PromptStore`; Candidate and Recommendation continue to receive tag snapshots. See [conversion flow](architecture/flows.md#natural-language-preparation).
- The browser manages presentation, input, and drafts through HTTP/SSE, without reading or writing configuration or databases directly. The prompt page is a view in the same frontend, with no additional site or iframe.
- Store persists tasks, images, feedback, snapshots, and learning state. Feedback learning uses the actual generation snapshot; the current library does not overwrite historical meaning.

## Frontend guide

The first-run guide lives in `web/src/onboarding/`: a generic observable state machine, pure Pictide flow rules, and a state adapter. Business controllers and components publish confirmed facts through `shared/ui-state.mjs` and register semantic element refs through `shared/ui-targets.ts`; they do not import guide steps. The React presentation in `components/onboarding/` measures these elements as layout changes and places hints beside their targets, with arrows and a spotlight. Its geometry helper keeps the hints clear of controls.

The guide observes successful tests, saves, feedback, anchor changes, and actual image loading. A new tour starts at `roam-start` when bootstrap contains an image API; otherwise it starts with API configuration. Windows local preparation uses this existing rule by saving and selecting its complete model workflow before HTTP/bootstrap, without an installation-specific onboarding API or marker. Navigation uses the existing UI intent path; generation and mutations remain user actions on normal controls. Only guide progress and necessary image IDs are stored in browser local storage.

## Startup Preparation

Every default local model declares required dedicated VRAM, physical RAM and supported environments. The Windows TUI blocks model selection when requirements are unmet or unknown; the installer rechecks before downloading any resources for that model. DXGI supplies per-adapter dedicated VRAM; shared memory and capacities from different cards are not combined. Without an execution-card binding, matching cards are checked conservatively using the smallest capacity.

Source and portable startup share `PictideApplication.prepare_startup()` in `backend/application.py`. It asks `backend/setup/vocabulary.py` to reuse any valid local vocabulary, or download an edition pinned by `backend/setup/vocabularies.json`. Interactive terminals choose an edition; unattended startup defaults to `filtered`, and `--vocabulary` supplies an explicit choice when no valid library exists. The Windows desktop parent passes a terminal choice to its hidden worker. All-ratings choices and downloads display an explicit-content warning. Downloads resume in `cache/downloads/vocabularies/`, verify size and SHA-256, and reuse Store's integrity-checked library import and selection; invalid existing files and personal presets/history are preserved. It then asks `backend/recommendation/resources.py` to verify or download the fixed MiniLM files into the selected runtime data directory. Host starts HTTP/SSE and opens the browser only after preparation succeeds. Failure terminates startup, preserving partial downloads for the next attempt. The encoder reads the prepared local files; offline corpus tools remain outside the startup path. See [Recommendation Dependency Preparation](architecture/recommendation.md#recommendation-dependency-preparation).

Windows first-run local generation preparation is implemented and verified with the current NVIDIA portable package; AMD, Intel, and CPU paths have configuration/simulated coverage without hardware verification. Before runtime initialization, the interactive desktop entry confirms the resolved data location and remembers it beside the Windows executable; the hidden worker receives the final root explicitly. It then offers an existing API, local ComfyUI preparation, or later configuration. `--setup` reopens it explicitly; CLI and no-browser startup stay noninteractive by default. The standard-library TUI selects a pinned official Windows portable environment and optional model recipe, confirms downloads, then reports download, verification, extraction, and startup progress. Each recommended recipe includes all model files, a complete default API workflow, and prompt/seed/output bindings. With a model prepared, Host starts the owned ComfyUI process, saves and selects its connection through existing application methods, then exposes HTTP/bootstrap: Roam and Generate can use it immediately. Existing configurations remain intact. ComfyUI-only preparation keeps the manual connection path. Host owns process shutdown; the installer does not write business databases or change Candidate, Recommendation, Task, or the generation protocol.

Optional local ComfyUI lifecycle management lives in `backend/setup/comfy_lifecycle.py`. Host composes it with read-only backend lookup and owns startup/shutdown; its localhost-only settings and discovery routes do not pass process-management responsibilities to generation protocols or Task. Explicit configuration in `runtime/comfyui-lifecycle.json` links one saved direct loopback HTTP ComfyUI API to a Python executable, `main.py`, working directory, and argument list. Settings take effect on the next startup. Without explicit configuration, existing Windows managed-install records retain their prior automatic model/workflow handoff; other installations default off.

`comfy_discovery.py` reads verified portable/virtual-environment layouts, Comfy Desktop installation records, and `/system_stats` launch information without changing those environments. It preserves model and input/output options; the linked API determines the listening endpoint. Before starting, the lifecycle service probes the address and reuses recognizable existing ComfyUI without claiming process ownership. Occupied ports, invalid paths, and bounded startup failures are reported while the Pictide UI remains reachable. `comfy_process.py` shares clean child environments, bounded logs, Windows Job Object ownership, and POSIX process-group cleanup with the original installer-managed service. Only children created by this session are stopped after application shutdown; discovery, settings saves, and status reads do not launch a process or submit generation.

ComfyUI startup uses the existing stdout handoff to display an indeterminate terminal bar, elapsed time, and the most recent bounded, redacted log line. `backend/desktop/startup_progress.py` owns rendering only; it does not infer a completion percentage from elapsed time or logs. `/system_stats` readiness still gates successful completion. The Windows launcher passes its actual terminal capability and width to the hidden worker so redirected output stays plain and throttled; direct CLI terminals animate in place. Ready, failed, and cancelled states end the waiting line cleanly. The underlying process ownership, startup order, HTTP contracts, and log retention remain in their existing owners.

Windows launchers select `--desktop`: a temporary progress process starts the service with `CREATE_NO_WINDOW`, relays startup output and exits after tray registration. This also closes startup terminals hosted by Windows Terminal. `backend/desktop/session.py` owns a data-directory lock and reserves the HTTP port before resource preparation. Once HTTP is ready, it registers the native tray and opens the browser. A failed startup stays visible; unavailable tray support falls back to the original terminal. The tray thread uses Per-Monitor V2 DPI awareness and loads the icon at the taskbar's DPI, without changing system settings. The tray requests normal Host shutdown or opens the browser/application log; it owns no business state. Startup progress and tray messages follow the system display language, using Simplified Chinese or English. `--cli` and `--no-browser` keep terminal operation; Linux retains its terminal launcher.

The macOS `.app` uses a small native launcher compiled from `scripts/macos_launcher.swift` with system AppKit. `Contents/MacOS/Pictide` owns the preparation window, menu bar, data-directory session lock, and child process; `PictideService` runs the existing Host with `--cli --no-browser`. Preparation output updates the window, and HTTP readiness gates opening the browser. Quitting sends a normal stop signal to the owned service and waits for it to exit. CLI arguments delegate to the engine. No additional business API or GUI runtime is introduced. `backend/paths.py` resolves the bundled macOS default to the user’s Application Support directory; explicit paths and environment variables retain precedence. Windows packages expose the existing desktop lifecycle directly through their top-level `Pictide.exe`.

## Outbound Network Requests

Resource downloads and generation adapters share `backend/network.py`: `proxy_for_url()` selects the HTTP(S) proxy for aiohttp requests and ComfyUI WebSocket connections; `open_url()` applies the same rule to synchronous downloads and each redirect target. Proxy discovery and exceptions use Python's standard library (environment variables first, then supported platform settings). Loopback, non-global IP addresses, single-label hosts, and `.localhost`, `.local`, or `.lan` names stay direct. Other internal domains use the system bypass list or `NO_PROXY`; classification adds no DNS lookups. PAC scripts and SOCKS proxies are not evaluated. The shared `tls_context()` uses macOS system certificate trust through `truststore` for resource downloads and generation sessions; Windows and Linux retain Python's default trust configuration. It does not inject global SSL changes or modify system certificates. Local startup probes remain direct, TLS verification stays enabled, and the separate cloud image download session keeps API credentials isolated. User-facing behavior is described under [Network proxy](../guides/getting-started.md#network-proxy).

## Further Reading

| Topic | Documentation |
| --- | --- |
| Module calls for generation, prefetch, and feedback | [Calls and Data Flow](architecture/flows.md) |
| Recommendation responsibilities, features, and current capabilities | [Recommendation Module](architecture/recommendation.md) |
| All HTTP fields and status codes | [API Reference](api.md) |
| Data files, backups, and table ownership | [Data Layout](data-layout.md), [Storage Reference](reference/storage.md) |
| Adding frontend features or generation adapters | [Development Workflow](development.md), [Page Design Guidelines](design-system.md) |
