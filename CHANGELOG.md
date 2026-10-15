# Changelog

## 1.2.0 — macOS, Windows and Linux

- Add direct-reference image access when symlinks are unavailable, without copying datasets or requiring administrator privileges.
- Use atomic YAML copies for latest-config aliases when file symlinks are unavailable.
- Resolve Conda using an explicit executable or CONDA_EXE, stream external output, and expose segmentation device selection.
- Add `imf doctor`, platform installation instructions and OS-specific example manifests.
- Close SQLite connections before replacing database files, and clean up logging handles in test fixtures for Windows file-lock semantics.
- Run native CI on Linux, Windows, Apple Silicon macOS and Intel macOS; expand wildcard wheel arguments portably.
- Reject case-colliding/reserved plate names; allow channel overrides to replace presets completely.
- Preserve scientific-validation limits for external pipelines, plugins and GPU backends.

## 1.1.0 — fork improvements

- Package CLI, processing modules, utilities, JSON Schema and YAML presets in wheels; declare core and optional dependencies and use one version source.
- Validate manifests and effective settings; resolve project paths consistently; reject incomplete/duplicate plate mappings.
- Add manifest-driven planning, optional dry-run, explicit stage selection, streaming output and execution records.
- Propagate CellProfiler wrapper/batch and segmentation retry failures; constrain GPU concurrency and expose worker limits.
- Join image channels by well/site keys; reject missing and duplicated channels instead of aligning by row position.
- Make ingestion strict and replace SQLite results atomically; validate extra-channel join cardinality.
- Allow feature selection without normalization; move project-name-specific scientific rules into explicit configuration.
- Remove personal annotation paths, pin documented external fork revisions, and add migration guidance.
- Add regression tests, isolated wheel smoke checks, a CPU synthetic demo, GitHub Actions CI, contributor guidance, citation and issue/PR templates.

## 1.0.0 — 2026-10-14

Original public release by Fernanda Garcia Fossa: CellProfiler workflows, micro-sam prediction, ingestion and pycytominer profile processing.
