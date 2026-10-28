# Developer documentation

[简体中文](../zh-CN/dev/README.md)

[Project home](../../README.md) · [User documentation](../README.md#user-documentation)

Start with the [product goals](../guides/about.md), then read the technical details relevant to your task. For a fresh checkout, [prepare the development environment](development.md#prepare-a-checkout) before consulting architecture, API, or UI documentation.

Prioritize changes that help people discover images they enjoy or guide exploration more naturally. The [product scope and experience goals](../guides/about.md#product-scope) explain how roaming guides feature decisions.

## Architecture and reference

| Topic | Overview | Further reading |
| --- | --- | --- |
| Modules and calls | [Architecture and boundaries](architecture.md) | [Calls and data flow](architecture/flows.md), [Recommendation module](architecture/recommendation.md) |
| HTTP API | [API index and conventions](api.md) | Follow the endpoint references by operation |
| Data | [Layout and responsibilities](data-layout.md) | [SQLite storage reference](reference/storage.md), [Project cleanup](cleanup.md) |

## Development and maintenance

- [Corpus tools](corpus.md): configurable processing, input/output structures, and [prebuilt release vocabularies](corpus.md#prebuilt-vocabulary).
- [Development workflow](development.md): start a task → prepare the environment → verify → integrate and deploy.
- [Focused smoke checks](testing.md): core, UI, corpus and browser groups, plus release gates.
- [GitHub Actions releases](development.md#github-actions-releases): one version tag builds native portable packages and Docker images from the same commit.
- [UI design system](design-system.md): terminology, visuals, components, layout, and interactions.
- [Web code entry points](web.md): pages, controllers, and shared components.

## Documentation maintenance

Developer navigation lists only core documentation for understanding, developing, and maintaining the current application. Keep issue records, change proposals, and historical verification reports out of these navigation lists; current instructions belong in the relevant topic documentation.

User guides start with the need they serve and the shortest path to trying it. Explain only the core workflow and consequences users need to understand; let the interface support exploration of secondary controls. Keep algorithms, exhaustive option lists, edge cases, and implementation history in developer documentation rather than repeating a feature specification in the guides.

The project README puts user guidance first and developer entry points last. Entry pages contain a summary and next steps. English user procedures belong in `docs/guides/`; English developer documentation belongs in `docs/dev/`, with API and data details in `reference/` and architecture details in `architecture/`. Maintain each current rule in one place and link to it elsewhere. Update the relevant documentation when behavior changes, and preserve historical context in issue records.

English is the authoritative source for user guides and core developer documentation, including setup, workflow, architecture, UI guidelines, data, and APIs. During normal development, update only the English source. Refresh Chinese translations on request or in a focused pass before a release; translating every change is not a delivery requirement. Where translations differ, the English source takes precedence.

All Chinese documentation lives under `docs/zh-CN/`, using ordinary `.md` filenames:

| English source | Chinese translation |
| --- | --- |
| `README.md` | `docs/zh-CN/README.md` |
| `AGENTS.md` | `docs/zh-CN/AGENTS.md` |
| `docs/README.md` | `docs/zh-CN/index.md` |
| `docs/guides/<topic>.md` | `docs/zh-CN/guides/<topic>.md` |
| `docs/dev/<topic>.md` | `docs/zh-CN/dev/<topic>.md` |
| `corpus/README.md`, `web/README.md` | `docs/zh-CN/corpus/README.md`, `docs/zh-CN/web/README.md` |

Keep reciprocal language links immediately below each translated page's title. Chinese navigation prefers a Chinese page where one exists; images and other shared assets stay at their existing paths.

Issue records, change proposals, and the design template remain in Chinese under `docs/zh-CN/dev/`. English core navigation links to current English instructions rather than historical records. `AGENTS.md` remains at the repository root as the English collaboration entry point. The distributed frontend notice stays at `web/src/THIRD_PARTY_NOTICES.md` in English, with its Chinese translation in `docs/zh-CN/web/src/`.
