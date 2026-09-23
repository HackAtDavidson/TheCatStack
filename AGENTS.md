## Agent skills

### Issue tracker

Issues and specs live in GitHub Issues. Before tracker operations, read `docs/agents/issue-tracker.md`.

### Triage labels

Use the five default triage labels. Before triaging, read `docs/agents/triage-labels.md`.

### Domain docs

Use a single-context layout. Before exploring the codebase, read `docs/agents/domain.md`.

## Atomic feature branches and pull requests

Every change must have one feature outcome. Create a dedicated branch from the intended base using `feat/<short-feature-name>` or `fix/<short-bug-name>`. Keep collection, review/export, screening, email generation, automation, and documentation as separate concerns unless one cannot work without the other.

Before editing, state the feature boundary and the files it should touch. Do not combine unrelated fixes, refactors, dependency upgrades, or documentation rewrites in the same branch. If a feature depends on another unmerged feature, use a stacked branch and name the dependency in the pull request.

Each pull request must be independently reviewable at its branch point: include focused tests for the feature, run the relevant test suite, and keep the diff small enough that a reviewer can explain every changed file. Use one commit per feature when practical. If existing work contains several features, preserve it first, then split it into ordered branches and pull requests before adding more behavior.

Pull request bodies must describe the concrete behavior, the feature boundary, validation evidence, dependencies, and merge risk. A pull request is ready only when its title names one feature, its base is intentional, its tests pass, and no unrelated files remain in the diff.
