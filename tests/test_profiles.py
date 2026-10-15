from support import temporary_directory
from contextlib import closing
import json
import logging
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import yaml

from imagemorphflow.processing.join_profiles import process_all_plates
from imagemorphflow.utils.ingest_profiles_utils import ingest_to_db
from imagemorphflow.utils.join_profiles_utils import merge_extra_channel_tables


def write_outputs(root, missing=False):
    folder = Path(root) / "batch1"
    folder.mkdir(parents=True)
    pd.DataFrame({"ImageNumber": [1], "Metadata_Plate": ["p01"], "Metadata_Well": ["A01"],
                  "Metadata_Site": [1], "Count_Cells": [2]}).to_csv(folder / "Image.txt", index=False)
    for compartment in ("Cells", "Nuclei", "Cytoplasm"):
        if missing and compartment == "Nuclei":
            continue
        pd.DataFrame({"ImageNumber": [1, 1], "ObjectNumber": [1, 2], "AreaShape_Area": [10, 20],
                      "Intensity_MeanIntensity_DNA": [0.2, 0.4]}).to_csv(folder / f"{compartment}.txt", index=False)


def ingest_config():
    return {"filenames": {name.lower(): f"{name}.txt" for name in ("Image", "Cells", "Nuclei", "Cytoplasm")},
            "ingest": {"split_extra_channels": ["DNA"]}}


class ProfileTests(unittest.TestCase):
    def test_sqlite_ingest_and_channel_split(self):
        with temporary_directory() as directory:
            root = Path(directory)
            write_outputs(root / "source")
            db = root / "plate.db"
            ingest_to_db(root / "source", ingest_config(), db)
            with closing(sqlite3.connect(db)) as conn:
                cells = pd.read_sql("SELECT * FROM Cells", conn)
                extra = pd.read_sql("SELECT * FROM Cells_DNA_extra", conn)
                self.assertEqual(len(cells), 2)
                self.assertNotIn("Cells_Intensity_MeanIntensity_DNA", cells.columns)
                self.assertEqual(list(extra["Cells_Intensity_MeanIntensity_DNA"]), [0.2, 0.4])
                cells = cells.rename(columns={"TableNumber": "Image_TableNumber", "ImageNumber": "Metadata_ImageNumber", "ObjectNumber": "Cells_Number_Object_Number"})
            joined = merge_extra_channel_tables(cells, db, ["DNA"], ["cells"])
            self.assertEqual(len(joined), 2)
            self.assertEqual(list(joined["Cells_Intensity_MeanIntensity_DNA"]), [0.2, 0.4])
            # Duplicate right-side object keys must not silently multiply cell rows.
            with closing(sqlite3.connect(db)) as conn:
                pd.concat([extra, extra.iloc[:1]]).to_sql("Cells_DNA_extra", conn, if_exists="replace", index=False)
            with self.assertRaises(pd.errors.MergeError):
                merge_extra_channel_tables(cells, db, ["DNA"], ["cells"])

    def test_invalid_input_preserves_existing_database(self):
        with temporary_directory() as directory:
            root = Path(directory)
            write_outputs(root / "source", missing=True)
            db = root / "plate.db"
            db.write_bytes(b"previous result")
            with self.assertRaisesRegex(ValueError, "Nuclei"):
                ingest_to_db(root / "source", ingest_config(), db)
            self.assertEqual(db.read_bytes(), b"previous result")

    def test_transaction_failure_preserves_database(self):
        with temporary_directory() as directory:
            root = Path(directory)
            write_outputs(root / "source")
            db = root / "plate.db"
            db.write_bytes(b"previous result")
            with patch.object(pd.DataFrame, "to_sql", side_effect=RuntimeError("disk failure")):
                with self.assertRaisesRegex(RuntimeError, "disk failure"):
                    ingest_to_db(root / "source", ingest_config(), db)
            self.assertEqual(db.read_bytes(), b"previous result")
            self.assertEqual(list(root.glob("plate_*.db")), [])

    def test_empty_source_is_error(self):
        with temporary_directory() as directory:
            with self.assertRaisesRegex(ValueError, "No data"):
                ingest_to_db(directory, ingest_config(), Path(directory) / "out.db")

    def test_feature_selection_without_normalization_uses_raw_profiles(self):
        with temporary_directory() as directory:
            root = Path(directory)
            (root / "symlinks").mkdir()
            (root / "symlinks" / "plates.json").write_text(json.dumps({"raw": "p01"}))
            config = root / "join.yaml"
            config.write_text(yaml.safe_dump({"base_path": str(root), "project_name": "demo", "symlinks_file": "plates.json",
                                             "annotate": {"perform": False}, "normalize": {"perform": False},
                                             "feature_selection": {"perform": True}}))
            raw = pd.DataFrame({"Metadata_Well": ["A01"], "Cells_AreaShape_Area": [15.0]})
            with patch("imagemorphflow.processing.join_profiles.join_profiles_utils.join_and_aggregate", return_value=(str(root), raw)), \
                 patch("imagemorphflow.processing.join_profiles.join_profiles_utils.get_features_and_metadata", return_value=(["Cells_AreaShape_Area"], ["Metadata_Well"])), \
                 patch("imagemorphflow.processing.join_profiles.join_profiles_utils.feature_selection") as select:
                process_all_plates(config)
            pd.testing.assert_frame_equal(select.call_args.args[0], raw)
            self.assertTrue((root / "profiles" / "all" / "plates_allplates_agg.tsv").exists())
