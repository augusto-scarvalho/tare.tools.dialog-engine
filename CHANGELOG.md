# Changelog

Notable changes to `tare.tools.dialog-engine` are recorded here, newest first. This file starts with a concise retrospective of the current public baseline; Git history remains authoritative for commit-level detail.

## Unreleased

- Exclude local credential files, private work folders, agent-local settings and SQLite sidecars from future Git additions.

- Stop tracking 12 generated dialog gap reports; preserve regeneration through the existing tooling.

- Publish the repository-owned domain ontology for pinned federated discovery.
  Its concepts describe architectural requirements, not implementation or
  execution attestations; the owner ADRs retain their implementation roadmap.

### Added

- Moved `SPEC-DIALOG-001` from the central Library copy into this owning
  repository and linked it from the documentation index.
- Added a shared, tested changelog guard for local pre-push and GitHub CI. It
  requires meaningful `Unreleased` entries for material changes, validates
  committed content, and prevents silent deletion or rewriting of history.

## 2026-08-21

### Changed

- Converted diagrams in both READMEs to Mermaid ([4274294](https://github.com/augusto-scarvalho/tare.tools.dialog-engine/commit/4274294)).

## 2026-08-19

### Added

- Added the dynamic-workflows architecture record and documentation index ([a90e05d](https://github.com/augusto-scarvalho/tare.tools.dialog-engine/commit/a90e05d)).

### Changed

- Generalized enterprise schema examples and modernized Portuguese diagrams ([36a6b97](https://github.com/augusto-scarvalho/tare.tools.dialog-engine/commit/36a6b97)).

## 2026-08-18

### Added

- Introduced decoupled schema binding and the universal state-machine adapter ([8676142](https://github.com/augusto-scarvalho/tare.tools.dialog-engine/commit/8676142)).
- Localized the codebase, documentation, fixtures, and CLI to English with Portuguese alternatives ([6b890cd](https://github.com/augusto-scarvalho/tare.tools.dialog-engine/commit/6b890cd)).

### Changed

- Made mutation generation lazy to avoid unnecessary document materialization ([eb37d5f](https://github.com/augusto-scarvalho/tare.tools.dialog-engine/commit/eb37d5f)).
