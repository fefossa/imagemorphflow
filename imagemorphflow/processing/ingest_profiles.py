from imagemorphflow.config import load_config, load_mappings as load_symlink_mappings
# Written by Fernanda Garcia Fossa
# Inspired by cytominer_database.ingest, now deprecated
import os
from pathlib import Path
from imagemorphflow.utils import ingest_profiles_utils, file_utils

def process_all_plates(config_path):
    config = load_config(config_path)
    username = os.environ.get("USER") or os.environ.get("USERNAME") or "default_user"

    # Resolve output base path for backend
    base_path = config["base_path"].format(
        username=username, project_name=config["project_name"]
    )
    backend_path = os.path.join(base_path, "backend")
    # Path to symlinks json
    output_dir = Path(base_path)
    json_file = output_dir / "symlinks" / config["symlinks_file"]
    symlink_mappings = load_symlink_mappings(json_file)

    logger = file_utils.setup_logging(config, base_path, pipeline="ingest_profiles")
    logger.info("🚀 Starting ingest profiles")

    # The config for ingest_to_db
    ingest_config = {
        "project_name": config["project_name"],
        "filenames": {
            "image": "Image.txt",
            "cells": "Cells.txt",
            "cytoplasm": "Cytoplasm.txt",
            "nuclei": "Nuclei.txt",
            # "innercells": "InnerCells.txt", # was used for the hek293 project for singlecell information retrieval
        },
        "ingest": config.get("ingest", {}),
        "image_columns": config.get("ingest_image_columns", []),
    }

    if config.get("ingest_filenames"):
        ingest_config["filenames"] = config["ingest_filenames"]

    for plate_old, plate_new in symlink_mappings.items():
        logger.info(f"🧪 Processing plate {plate_new}")
        plate_dir = os.path.join(backend_path, plate_new)
        if not os.path.isdir(plate_dir):
            raise FileNotFoundError(f"Plate directory not found: {plate_dir}")
        db_path = os.path.join(plate_dir, f"{plate_new}.db")
        print(f"\nProcessing plate {plate_new} → {db_path}")
        ingest_profiles_utils.ingest_to_db(
            source=plate_dir,
            config=ingest_config,
            output_db_path=db_path,
            skip_image_prefix=True,  # or False, your choice
        )

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Process all plates and ingest to .db using project config."
    )
    parser.add_argument(
        "--config", required=True, help="Path to main project YAML config."
    )
    args = parser.parse_args()
    process_all_plates(args.config)
