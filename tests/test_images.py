from support import temporary_directory
import logging
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from PIL import Image

from imagemorphflow.utils.load_data_utils import generate_load_data


class ImageTests(unittest.TestCase):
    def run_load(self, directory):
        return generate_load_data(logging.getLogger("test"), str(directory), {"w1": "DNA", "w2": "ER"},
                                  output_dir_bool=True, output_dir=str(directory / "out"), cluster=True,
                                  cluster_img_folder=str(directory), cluster_illum_folder=str(directory / "illum"))

    def test_channels_match_well_and_site(self):
        with temporary_directory() as temp:
            path = Path(temp)
            for well in ("A01", "B01"):
                for channel in ("w1", "w2"):
                    Image.new("I;16", (4, 4)).save(path / f"{well}_s12_{channel}.tif")
            self.run_load(path)
            df = pd.read_csv(path / "out" / "load_data.csv")
            self.assertEqual(len(df), 2)
            self.assertTrue((df["Metadata_Site"] == 12).all())
            for _, row in df.iterrows():
                self.assertTrue(row["FileName_ER"].startswith(row["Metadata_Well"]))
                self.assertTrue(row["FileName_DNA"].startswith(row["Metadata_Well"]))

    def test_missing_channel_fails_instead_of_misalignment(self):
        with temporary_directory() as temp:
            path = Path(temp)
            Image.new("L", (4, 4)).save(path / "A01_s1_w1.tif")
            with self.assertRaisesRegex(ValueError, "Missing channels"):
                self.run_load(path)

    def test_mask_prediction_uses_nested_load_data_paths(self):
        import csv
        from imagemorphflow.utils.predict_masks_utils import generate_segmentation_command
        with temporary_directory() as directory:
            root = Path(directory)
            data = root / 'loaddata' / 'p01'
            data.mkdir(parents=True)
            nested = root / 'images' / 'p01' / 'acquisition' / 'latest'
            nested.mkdir(parents=True)
            with (data / 'load_data.csv').open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=['FileName_DNA', 'PathName_DNA'])
                writer.writeheader()
                writer.writerow({'FileName_DNA':'A01_s1_w1.tif', 'PathName_DNA':str(nested)})
            config = {'base_path':str(root), 'model':'vit_l_lm', 'pattern_images':'*_w1.tif', 'sam_env':'custom-sam', 'tile_shape':[128,256]}
            commands = generate_segmentation_command(str(root / 'images' / 'p01'), str(root / 'masks'), 'p01', config)
            self.assertEqual(len(commands), 1)
            self.assertEqual(commands[0][1:5], ['run','--no-capture-output','-n','custom-sam'])
            self.assertIn(str(nested / 'A01_s1_w1.tif'), commands[0])
            index = commands[0].index('--tile_shape')
            self.assertEqual(commands[0][index+1:index+3], ['128','256'])
