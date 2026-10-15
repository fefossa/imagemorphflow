# Migration from the original 1.0.0 release

## Installation and CLI

Reinstall the package to refresh its entry point. Python metadata and documentation now both require Python 3.9+. All subpackages and configuration resources are included in distribution artifacts.

Use `imf run --script NAME --config FILE` for a single stage, or `imf run --manifest FILE` for a planned workflow. The previous implicit list behind `imf run --config FILE` is rejected because it omitted ingestion and ran optional prediction unconditionally.

Manifests are validated before work starts. Top-level typos and invalid enums are rejected. Override keys remain extensible. Normalization requires annotation and annotation requires a platemap. Feature selection can run on the latest available raw/annotated/normalized profile.

Initialization creates a mapping with empty destinations. Fill every destination before continuing. Unknown, empty or duplicate destinations now fail instead of silently skipping plates.

## Paths

Set `project_root` once. Workspace, image, illumination and mask paths derive from it. An existing manifest that overrides only `base_path` infers `project_root` from that workspace's parent. Existing effective configurations with fully specified paths continue to work.

The old `join.full.yaml` contained an author's absolute platemap path. Supply `overrides.annotate.platemap` explicitly.

## Explicit scientific settings

Project names no longer choose analysis algorithms. To reproduce an old experiment, copy its former behavior into configuration and validate output equivalence on representative data:

| Old project-name rule | Explicit replacement |
| --- | --- |
| `cl2025` / `a459` metadata repair | `join.rename_metadata: true`, `join.clean_metadata: true` |
| `cl2025` / `a459` image categories | `join.image_feature_categories: [ImageQuality, Count, TableNumber, ImageNumber]` |
| names containing `glioblastoma` | `join.image_feature_categories: [Skeleton, Median, ImageQuality, Count, TableNumber, ImageNumber]`; `join.strata: [Metadata_Plate, Metadata_Well]` |
| names containing `g35` | same image categories; `join.strata: [Metadata_Plate, Metadata_Well, Metadata_Site]` |
| `20260429_CL2025` / `rpe1` ingestion column filter | set `ingest_image_columns` explicitly, including the image quality/count measurements needed |
| manual edits of `COUNT_OBJECT_COL` | `join.count_object_column: Count_Nuclei` or `Count_Cells` |

The default image categories are `[ImageQuality, Count, TableNumber, ImageNumber, Math]`; default aggregation strata are plate, well and site. Ingestion preserves all image-table columns unless an explicit selection is supplied.

An exact legacy ingestion filter used all columns starting with `ImageQuality_` plus existing columns among `ImageNumber`, `ObjectNumber`, `Metadata_Plate`, `Metadata_Well`, `Metadata_Site`, `Count_Cells`, `Count_Nuclei`, `Count_Cytoplasm`, `Count_Binuclei`, `Math_Measurement`. Enumerate the existing columns needed by your experiment in `ingest_image_columns`.

Missing configured Image/Cells/Cytoplasm/Nuclei batch files now fail ingestion. For assays measuring fewer compartments, provide the complete `ingest_filenames` mapping, for example `{image: Image.txt, nuclei: Nuclei.txt}`.

## Failure semantics and joins

Persistent batch and prediction failures now produce nonzero exit status. Scratch-copy and invalid mapping errors also stop execution. Ingestion creates a temporary complete database before replacing a previous successful result.

Image channels are aligned by well/site identity rather than row order. Missing or duplicated channels are errors. Extra-channel table joins enforce many-to-one cardinality to prevent accidental multiplication of cell rows.

These changes intentionally expose incomplete inputs that older scripts skipped. Re-run affected experiments only after inspecting the error and input integrity.

## Legacy utilities and validation limits

The historical `join_profiles_cp3.py` contains an XML inspection CLI and unfinished integration helpers. Unimplemented helpers now raise a clear error instead of using undefined variables or silently returning. Its feature-list helper requires an explicit profile path.

The CPU example and unit tests verify software behavior. They do not validate segmentation quality, biological interpretation, every report utility, CellProfiler plugin compatibility or GPU execution. Retain your original reference outputs for scientific regression comparisons.
