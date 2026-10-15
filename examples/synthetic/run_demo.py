from contextlib import closing
"""CPU-only example: synthetic images -> load-data CSV -> SQLite -> checked joins."""

import argparse
import json
import logging
import sqlite3
from pathlib import Path

import pandas as pd
from PIL import Image

from imagemorphflow.processing.ingest_profiles import process_all_plates
from imagemorphflow.utils.join_profiles_utils import merge_extra_channel_tables
from imagemorphflow.utils.load_data_utils import generate_load_data


def run_demo(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    images = output / "images" / "p01"
    images.mkdir(parents=True)
    for well in ("A01", "B01"):
        for channel in ("w1", "w2"):
            Image.new("I;16", (8, 8), color=512).save(images / f"{well}_s1_{channel}.tif")
    workspace = output / "workspace"
    (workspace / "symlinks").mkdir(parents=True)
    (workspace / "symlinks" / "demo.json").write_text('{"raw":"p01"}\n')
    generate_load_data(logging.getLogger("demo"), str(images), {"w1": "DNA", "w2": "ER"},
                       output_dir_bool=True, output_dir=str(workspace / "loaddata" / "p01"),
                       cluster=True, cluster_img_folder=str(images), cluster_illum_folder=str(output / "illum"))
    batch = workspace / "backend" / "p01" / "batch1"
    batch.mkdir(parents=True)
    pd.DataFrame({"ImageNumber": [1, 2], "Metadata_Plate": ["p01", "p01"], "Metadata_Well": ["A01", "B01"],
                  "Metadata_Site": [1, 1], "Count_Cells": [2, 2]}).to_csv(batch / "Image.txt", index=False)
    for compartment in ("Cells", "Cytoplasm", "Nuclei"):
        pd.DataFrame({"ImageNumber": [1, 1, 2, 2], "ObjectNumber": [1, 2, 1, 2],
                      "AreaShape_Area": [10, 20, 30, 40],
                      "Intensity_MeanIntensity_DNA": [0.1, 0.2, 0.3, 0.4]}).to_csv(batch / f"{compartment}.txt", index=False)
    config = {"project_name": "demo", "project_root": str(output), "base_path": str(workspace),
              "symlinks_file": "demo.json", "ingest": {"split_extra_channels": ["DNA"]}}
    config_path = output / "config.json"
    config_path.write_text(json.dumps(config, indent=2))
    process_all_plates(str(config_path))
    db = workspace / "backend" / "p01" / "p01.db"
    with closing(sqlite3.connect(db)) as connection:
        cells = pd.read_sql("SELECT * FROM Cells", connection).rename(columns={
            "TableNumber": "Image_TableNumber", "ImageNumber": "Metadata_ImageNumber", "ObjectNumber": "Cells_Number_Object_Number"})
    merged = merge_extra_channel_tables(cells, db, ["DNA"], ["cells"])
    actual = {"image_rows": len(pd.read_csv(workspace / "loaddata" / "p01" / "load_data.csv")),
              "cell_rows": len(merged), "area_sum": int(merged["Cells_AreaShape_Area"].sum()),
              "dna_sum": round(float(merged["Cells_Intensity_MeanIntensity_DNA"].sum()), 6)}
    expected = {"image_rows": 2, "cell_rows": 4, "area_sum": 100, "dna_sum": 1.0}
    if actual != expected:
        raise RuntimeError(f"Unexpected demo output: {actual}; expected {expected}")
    (output / "summary.json").write_text(json.dumps(actual, indent=2) + "\n")
    print(f"Demo verified: {actual}")
    return actual


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("demo-output"))
    run_demo(parser.parse_args().output)
