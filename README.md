# imagemorphflow

[![CI](https://github.com/cmpela/imagemorphflow/actions/workflows/ci.yml/badge.svg)](https://github.com/cmpela/imagemorphflow/actions/workflows/ci.yml)

Python workflows for high-content microscopy and Cell Painting, from image organization to morphological profiles. **CellProfiler 4.2.8** performs image analysis; **micro-sam** optionally generates segmentation masks; **pycytominer** supports aggregation, annotation, normalization and feature selection. Cellpose integration runs through CellProfiler plugins.

This fork adds installation checks, explicit configuration, failure propagation, execution records, tests and CI to [Fernanda Garcia Fossa's original project](https://github.com/fefossa/imagemorphflow). Original release DOI: [10.5281/zenodo.23361703](https://doi.org/10.5281/zenodo.23361703). The original BSD 3-Clause license and authorship are preserved.

## Installation

Python **3.9+**. The core package supports **macOS, Windows and Linux**, with native CI jobs on all three systems (including Apple Silicon and Intel macOS). CellProfiler, plugins and GPU models are separate scientific dependencies; see the [platform guide](docs/platforms.md) for installation instructions and validation limits.

```bash
git clone https://github.com/cmpela/imagemorphflow.git
cd imagemorphflow
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
imf --help
imf --version
```

Alternatively, from the repository directory:

```bash
conda env create -f environment.yml
conda activate imagemorphflow
```

Dependencies for the CLI, YAML/JSON validation, image organization and SQLite ingestion are installed by default. Extras:

```bash
python -m pip install -e '.[profiles]'  # pycytominer and Parquet support
python -m pip install -e '.[reports]'   # commonly used report dependencies
```

The report and legacy utility scripts are not all covered by the stable pipeline API. See [migration notes](docs/migration.md).

### External scientific tools

Install **CellProfiler 4.2.8** separately in a Conda environment called `cellprofiler4`, following the [official installation instructions](https://github.com/CellProfiler/CellProfiler/wiki). Install [CellProfiler-plugins](https://github.com/CellProfiler/CellProfiler-plugins) for Cellpose and set `plugins_dir` in your manifest.

For the modified micro-sam / pycytominer integrations used by the original project, immutable revisions are recorded in [requirements](requirements/README.md). micro-sam normally uses a separate `sam` environment. Set `cellprofiler_env` and `sam_env` to change environment names. These tools and models are not silently downloaded by this package.

The human-maintained `environment.yml` describes direct requirements, rather than exporting platform-specific Conda builds. To archive a particular experiment, export a platform-specific lock from its verified environment and retain it with the results. The pinned fork requirements are not a lock of every transitive dependency.

## Reproducible CPU example

After installing the package:

```bash
python examples/synthetic/run_demo.py --output demo-output
```

The example generates tiny TIFF images and synthetic CellProfiler-style output, builds load-data CSVs, ingests SQLite tables and verifies that extra-channel joins preserve cell identity. Expected `demo-output/summary.json`:

```json
{"image_rows": 2, "cell_rows": 4, "area_sum": 100, "dna_sum": 1.0}
```

This validates data handling, not segmentation accuracy or biological validity. The example does not execute CellProfiler, pycytominer aggregation or GPU models. It refuses to overwrite an existing output directory; choose a new path to repeat it.

## Configuration

Presets support Cell Painting on **ImageXpress** and **Endeavor**, and brightfield on **Endeavor**. Channel mappings can be overridden. Start with `example_manifest.json`:

```json
{
  "microscope": "imagexpress",
  "modality": "cellpainting",
  "mask_predict": false,
  "steps": ["analysis", "ingest", "join"],
  "join_profile": "basic",
  "overrides": {
    "project_name": "my_project",
    "project_root": "~/projects/my_project",
    "image_path": "/path/to/image/folder",
    "symlinks_file": "my_project.json",
    "max_workers": 4
  }
}
```

The bundled [JSON Schema](imagemorphflow/schemas/manifest.json) validates manifests. Unknown top-level fields, unsupported steps, invalid resource limits and incompatible switches produce errors. `overrides` remains extensible for specialized scripts; review its keys against the presets.

Use `imf doctor` (or `imf doctor --json`) to inspect your OS, Python, Conda and resolved project settings.

Paths share a single resolver. `project_root` defaults to `~/projects/{project_name}`, `base_path` to `{project_root}/workspace`, and image/mask paths derive from that root. `~`, environment variables and `{username}` / `{project_name}` are expanded; `{plate_new}` is retained until each plate is processed. Relative paths are resolved from the working directory, so use absolute paths for repeatable runs.

```bash
imf build --manifest example_manifest.json
imf build --manifest example_manifest.json --step analysis \
  -O max_workers=2 -O feature_selection.perform=false
```

Use top-level `step_overrides` for stage-specific settings, for example `"step_overrides": {"illum": {"pipeline_file": "illum.cppipe"}, "analysis": {"pipeline_file": "analysis.cppipe"}}`. Stage overrides take precedence over shared overrides; CLI `-O` settings take precedence over both.

Effective configs and manifest snapshots are saved under `workspace/configs/effective/`, using unique UTC timestamps. Relative `latest_<step>.yaml` symlinks point to the newest configs. Where symlinks are unavailable, these small YAML files are copied atomically instead.

## Run your own analysis

First inspect the plan without creating files or running commands:

```bash
imf run --manifest example_manifest.json --dry-run
```

Initialize the project explicitly:

```bash
imf build --manifest example_manifest.json --step init
imf run --script initialize_project_structure \
  --config ~/projects/my_project/workspace/configs/effective/latest_init.yaml
```

**Before continuing:**

1. Edit `workspace/symlinks/my_project.json`, assigning a non-empty, unique output name to each acquired plate. Initialization preserves existing assignments.
2. Supply your assay's validated `.cppipe` files in `workspace/pipelines/`, matching `pipeline_file` in each effective config (for example, `analysis_imagexpress.cppipe`). The repository does not include a scientifically validated universal CellProfiler pipeline.
3. Check microscope naming conventions, channels, plugins, model environments and annotation inputs for your experiment.

Then run the selected stages:

```bash
imf run --manifest example_manifest.json
```

`image_link_mode: "auto"` uses directory symlinks when permitted and otherwise reads the original image directory directly. Use `"reference"` to avoid links on every platform or `"symlink"` to require them. Microscopy datasets are never automatically copied by this fallback.

The runner orders initialization, optional scratch copy, load-data creation, optional micro-sam prediction, illumination, analysis, ingestion and joining. Image stages add setup prerequisites; requesting both analysis and join also adds ingestion. `mask_predict=false` skips prediction. Joining existing results can use `steps: ["join"]` without reprocessing images.

For a single stage, the original explicit command remains available:

```bash
imf run --script ingest_profiles --config /absolute/path/latest_ingest.yaml
imf run --script join_profiles --config /absolute/path/latest_join.yaml
```

Running `imf run --config ...` without an explicit script is now rejected: use a manifest to select the full workflow. Commands stream their output. CellProfiler additionally writes its own run log. A failed stage stops subsequent stages and returns a nonzero exit status; persistent batch/segmentation failures are errors even after retrying.

## Analysis options

- `join_profile: "full"` requires your own `overrides.annotate.platemap`; no personal path is bundled.
- Normalization requires annotation. Feature selection can use raw, annotated or normalized profiles, according to the enabled stages.
- `join.count_object_column`, `join.image_feature_categories`, `join.strata`, `join.rename_metadata` and `join.clean_metadata` replace implicit rules based on project names.
- `ingest_image_columns` explicitly selects image-table columns; an empty list preserves them. `ingest_filenames` can replace the default Image/Cells/Cytoplasm/Nuclei file mapping, for example for a nuclei-only assay.
- Missing required batch files fail ingestion. A complete replacement database is built before replacing a previous result.
- `max_workers` controls CellProfiler batches, `max_parallel_plates` controls illumination across plates, and `mask_workers` defaults to **1** for GPU memory safety.
- For external masks, set `masks.include_masks`, `mask_channels`, `mask_output_dir` and `segmentation_method`. For standalone micro-sam prediction also set `mask_predict=true`, `model` and `pattern_images` to match your channel. The brightfield mask defaults are not suitable for every Cell Painting assay. `example_manifest_full.json` demonstrates a nuclear channel override.

## Outputs and provenance

```text
project_root/
├── images/{images,illum,masks}/
└── workspace/
    ├── configs/effective/
    ├── symlinks/               # acquisition → plate-name mappings
    ├── loaddata/               # image metadata CSVs
    ├── pipelines/              # supplied CellProfiler .cppipe files
    ├── backend/               # per-plate batches and SQLite databases
    ├── profiles/              # plate and combined profiles
    └── logs/runs/             # machine-readable execution records
```

Every CLI processing stage records timestamps, success/failure, command, config SHA-256, effective settings, package versions and available source commit. Pipeline and explicit model checkpoint files are hashed when configured. CellProfiler / micro-sam environment versions are probed through Conda when possible; unavailable observations are marked as unavailable. Built-in model names do not identify immutable checkpoint contents: archive and configure a model file when exact weights matter.

Environment variables and credential files are not dumped into records. Configurations themselves are retained: do not place secrets in manifests. Keep raw inputs, plate mappings, pipelines, model weights and verified environment locks with the experiment.

## Development and citation

```bash
python -m unittest discover -s tests -v
ruff check .
python -m build
python tests/smoke_wheel.py dist/*.whl
```

CI executes these checks and the synthetic example. On Windows, run the PowerShell installation commands in the [platform guide](docs/platforms.md); Unix activation commands above apply to macOS/Linux.

The wheel smoke test installs the built artifact in a temporary environment outside the source tree, checking CLI entry points, subpackages, schemas and YAML presets.

See [CONTRIBUTING.md](CONTRIBUTING.md), [CHANGELOG.md](CHANGELOG.md), [migration notes](docs/migration.md), and [CITATION.cff](CITATION.cff).
