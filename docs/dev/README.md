# Developer documentation

[简体中文](README.zh-CN.md)

[Project home](../../README.md) · [User documentation](../README.md#user-documentation)

Start with the [product goals](../guides/about.md), then read the technical details relevant to your task. For a fresh checkout, [prepare the development environment (Chinese)](development.md#首次准备检出目录) before consulting architecture, API, or UI documentation.

Prioritize changes that help people discover images they enjoy or guide exploration more naturally. The [product scope and experience goals](../guides/about.md#product-scope) explain how roaming guides feature decisions.

## Architecture and reference

| Topic | Overview | Further reading |
| --- | --- | --- |
| Modules and calls | [Architecture and boundaries](architecture.md) | [Calls and data flow](architecture/flows.md), [Recommendation module](architecture/recommendation.md) |
| HTTP API | [API index and conventions](api.md) | Follow the endpoint references by operation |
| Data | [Layout and responsibilities](data-layout.md) | [SQLite storage reference](reference/storage.md), [Project cleanup](cleanup.md) |

## Development and maintenance

- [Corpus tools](corpus.md): configurable processing, input/output structures, and [prebuilt release vocabularies](corpus.md#prebuilt-vocabulary).
- [Development workflow (Chinese)](development.md): start a task → prepare the environment → verify → integrate and deploy.
- [Focused smoke checks](testing.md): core, UI, corpus and browser groups, plus release gates.
- [GitHub Actions releases (Chinese)](development.md#github-actions-发版): prepare locked resources, then push a version tag to build native portable packages.
- [UI design system (Chinese)](design-system.md): terminology, visuals, components, layout, and interactions.
- [Web code entry points](web.md): pages, controllers, and shared components.

## Documentation maintenance

Developer navigation lists only core documentation for understanding, developing, and maintaining the current application. Keep issue records, change proposals, and historical verification reports out of these navigation lists; current instructions belong in the relevant topic documentation.

User guides start with the need they serve and the shortest path to trying it. Explain only the core workflow and consequences users need to understand; let the interface support exploration of secondary controls. Keep algorithms, exhaustive option lists, edge cases, and implementation history in developer documentation rather than repeating a feature specification in the guides.

The project README puts user guidance first and developer entry points last, with links to technical details. Entry pages contain a summary and next steps. User procedures belong in `docs/guides/`; developer documentation belongs in `docs/dev/`, with API and data details in `reference/`, architecture details in `architecture/`, and requirements and delivery records in `issues/`. Maintain each current rule in one place and link to it elsewhere. Topic pages explain their purpose before details. Update the relevant documentation when behavior changes, and keep past decisions in issue records with their historical context.

User-facing documentation and descriptions of the current architecture, data layout, and HTTP API use English at the original path. Keep a Simplified Chinese counterpart beside each translated page as `name.zh-CN.md`, with reciprocal language links immediately below the title. Keep Chinese navigation within the translated Chinese pages where a counterpart exists. Update both language versions when the documented behavior changes.

Issue records and design-change proposals, including the design template, continue to use Chinese. Internal development procedures and UI specifications remain Chinese in this translation pass; links from English pages identify Chinese-only material.
