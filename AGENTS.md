# Pictide collaboration guide

[简体中文](docs/zh-CN/AGENTS.md)

Applies throughout this repository. Paths are relative to its root; `main` holds integrated work.

## Working agreements

- Communicate concisely in Chinese by default. Prefer direct, positive descriptions of facts, goals, and actions.
- Start at [README](README.md). Consult [product scope](docs/guides/about.md), [architecture](docs/dev/architecture.md), [UI guidelines](docs/dev/design-system.md), [data layout](docs/dev/data-layout.md), and [development workflow](docs/dev/development.md) as needed. Evaluate features against the image exploration experience.
- This is a proof of concept: favor the smallest complete solution and existing mechanisms. Use a few meaningful smoke checks rather than the full suite; avoid speculative abstractions, defensive layers, and migration compatibility.
- Inspect Git status first. Implement on a separate branch; use separate worktrees, data directories, and ports for parallel work or running instances. Preserve unrelated changes and existing history; do not reset or stash without authorization. Delegate only worthwhile independent tasks, with explicit file ownership and coordinated interfaces.
- Follow the English [commit conventions](docs/dev/development.md#commit-conventions). Stage only task files and push new commits to `origin` before delivery; push integrated results to `origin/main`. After integration and a successful push, delete completed task branches locally and on `origin`; retain branches still needed for ongoing work.
- Back up original data before changing it. Present historical data deletion as a reviewable inventory for user confirmation. Preserve images, tasks, likes, and preference records.

## Documentation

- Use English for user guides and current developer documentation. Update English during normal work; refresh Chinese translations on request or before release. Keep Chinese documents under `docs/zh-CN/`, with reciprocal language links where an English source exists. Issue records, change proposals, and the design template remain Chinese.
- Follow entry → overview → details. README puts quick start and user navigation first, developer links last. Keep guides concise and focused on user needs; maintain each rule in one place. See [documentation maintenance](docs/dev/README.md#documentation-maintenance) for directories and translation policy.
- Update the owning document when behavior changes. Check actual call paths and distinguish implemented, released, and unverified behavior. Keep Windows, Linux, and macOS instructions on separate reading paths.

## Module and data boundaries

- `web/` is the sole frontend (`pictide-web`). Roam, Prompts, Generate, tasks, and Settings share one entry and navigation; keep application features within it.
- `backend/host.py` owns HTTP, SSE, and lifecycle; `backend/application.py` orchestrates Candidate, Recommendation, Task, Generation, and Store. Candidate, Recommendation, and Task do not call one another directly.
- Candidate reads the PMI vocabulary, validates/saves presets, and builds complete combinations with continuous-change budgets. The browser owns interaction and drafts. Recommendation scores complete combinations; ComfyUI executes generation API requests.
- Before changing architecture, cross-module calls/data flow, or public module interfaces, present those three design aspects and obtain user confirmation. Reuse approved boundaries without asking again; UI details and internal implementation are autonomous. Use the Chinese template at `docs/zh-CN/dev/design-template.md`, focusing on changes with a short overview.
- Offline processing source/dependencies live in `corpus/`, with instructions in [Corpus tools](docs/dev/corpus.md). Development materials, raw datasets, environments, and verification outputs belong in `dev/`; final archives belong in `releases/`.
- Keep runtime databases, images and prompt JSON, models, logs, caches, temporary files, and environments under the selected data directory. Source and portable deployments share these responsibilities. Do not commit databases or raw materials; image sidecars contain only actual positive/negative prompt JSON.
- Roam prefetch runs on operations/events; do not add timed feeding loops. Feedback supports like, dislike, and withdrawal; unrated remains unknown. Interpret history from generation-time snapshots.

## Verification and deployment

- Reuse shared shadcn components and theme. Frontend changes need type checking, a build, and a few real UI smokes. Deploy matching assets: back up old `web/dist/`, copy new chunks before the entry, and retain old chunks for open tabs. Build separately while serving an instance.
- Precheck image services with read-only requests. Prefer temporary data and simulated backends; report simulation separately from real GPU generation. Scope real GPU tasks explicitly.
- Before restarting, inspect processes and tasks, announce the restart, and preserve drafts and executing work. Close your verification instances and tabs afterward; remove integrated worktrees only after preserving needed data.
