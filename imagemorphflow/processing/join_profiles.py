"""Aggregate plate profiles with explicit, validated analysis options."""

import argparse
from pathlib import Path

import pandas as pd

from imagemorphflow.config import load_config, load_mappings
from imagemorphflow.utils import file_utils, join_profiles_utils


def process_all_plates(config_path):
    config = load_config(config_path)
    base_path = Path(config["base_path"])
    mappings = load_mappings(base_path / "symlinks" / config["symlinks_file"])
    logger = file_utils.setup_logging(config, base_path, pipeline="join_profiles")
    # Fail before writing results if annotation input is unavailable.
    if config.get("annotate", {}).get("perform"):
        platemap = Path(config["annotate"]["platemap"])
        if not platemap.is_file():
            raise FileNotFoundError(f"Platemap missing: {platemap}")
    aggregated, annotated, selection_input = [], [], []
    extra = config.get("ingest", {}).get("split_extra_channels", [])
    if isinstance(extra, dict):
        extra = extra.get("channels", []) if extra.get("enabled", True) else []
    for plate in mappings.values():
        directory, df = join_profiles_utils.join_and_aggregate(
            str(base_path), plate, config["project_name"], extra_channels=extra,
            options=config.get("join", {}),
        )
        aggregated.append(df)
        current = df
        if config.get("annotate", {}).get("perform"):
            current = join_profiles_utils.annotate(current, config["annotate"]["platemap"], directory)
            annotated.append(current)
        if config.get("normalize", {}).get("perform"):
            features, metadata = join_profiles_utils.get_features_and_metadata(current)
            current, _ = join_profiles_utils.normalize(
                current, features, metadata, directory,
                normalize_to_negcon=config["normalize"].get("to_negcons", False),
            )
        selection_input.append(current)
    if not aggregated:
        raise ValueError("No plate profiles to combine")
    combined = base_path / "profiles" / "all"
    combined.mkdir(parents=True, exist_ok=True)
    filename = Path(config["symlinks_file"]).stem
    pd.concat(aggregated, ignore_index=True).to_csv(combined / f"{filename}_allplates_agg.tsv", sep="\t", index=False)
    if annotated:
        pd.concat(annotated, ignore_index=True).to_csv(combined / f"{filename}_allplates_agg_annot.tsv", sep="\t", index=False)
    if config.get("feature_selection", {}).get("perform"):
        df_all = pd.concat(selection_input, ignore_index=True)
        features, _ = join_profiles_utils.get_features_and_metadata(df_all)
        join_profiles_utils.feature_selection(df_all, features, str(combined), filename=filename, logger=logger)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    process_all_plates(parser.parse_args().config)
