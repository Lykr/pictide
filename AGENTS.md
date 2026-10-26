# Pictide collaboration guide

[简体中文](docs/zh-CN/AGENTS.md)

Applies throughout the repository. English is the authoritative source.

## Core principles

- Unless instructed otherwise, use the system's current language.
- Lead with results and judgments. Keep only information useful for understanding, decisions, or action; avoid defensive assumptions, self-justification, boilerplate disclaimers, and repetitive updates.
- Prioritize the image exploration experience. This is a proof of concept: choose the smallest complete solution and reuse existing mechanisms; avoid speculative complexity.
- Protect user data, unrelated work, and existing history. Keep development and verification isolated from the user's running application.
- Respect established ownership and module boundaries. Carry out approved work autonomously; seek confirmation for boundary changes under the development workflow.
- Verify changes in proportion to their impact. Report evidence and limitations accurately, distinguishing implemented, deployed, released, and unverified behavior.
- Maintain each rule in its owning document. Update that document when behavior changes; keep this file limited to principles and routing.

## Task routing

Start at [README](README.md), then read and follow the documents relevant to the task:

| Task | Owning documents |
| --- | --- |
| Product decisions | [Product scope and experience goals](docs/guides/about.md) |
| Implementation and delivery | [Development workflow](docs/dev/development.md): design confirmation, task isolation, data protection, commits, push, deployment, and cleanup; [focused checks](docs/dev/testing.md) |
| Architecture and interfaces | [Architecture](docs/dev/architecture.md), [HTTP API](docs/dev/api.md), [frontend ownership](docs/dev/web.md) |
| Interface and interaction | [UI design system](docs/dev/design-system.md), including shared components, notifications, and layout validation |
| Data and offline processing | [Data layout](docs/dev/data-layout.md), [corpus tools](docs/dev/corpus.md) |
| Documentation | [Maintenance and translation policy](docs/dev/README.md#documentation-maintenance) |
